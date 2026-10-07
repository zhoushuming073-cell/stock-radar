"""Generate native inputs only from a verified frozen dependency closure."""
from pathlib import Path

import duckdb
import pandas as pd

from radar.pit.actions import factor_lines
from radar.pit.builder import digest
from radar.pit.run import require_ready, iso


def execution_inputs(manifest: dict):
    require_ready(manifest)
    identity = {}
    securities = {}
    selected = {s["security_id"] for s in manifest["signals"]}
    selected |= {p["security_id"] for p in manifest["prior_open_positions"]}
    if manifest["prior_open_positions"]:
        raise ValueError("native execution requires a fresh cash-funded portfolio; prior holdings import is not supported")
    for row in manifest["dependencies"]:
        if row["security_id"] not in selected:
            continue
        mappings = sorted(row["mappings"], key=lambda x: x["valid_from"])
        root = mappings[0]["symbol"]
        if root in securities or root in {"SPY", "QQQ"}:
            raise ValueError("native map root collision; distinct securities may not share a file")
        identity[row["security_id"]] = root
        terminal = next((a for a in row["actions"] if a["handling_mode"] == "native_cash_entitlement"), None)
        # Native map-end removal must follow entitlement recognition, otherwise
        # LEAN liquidates automatically at the last quote. Quote eligibility
        # stops independently at last_tradable_session; no later bars are made.
        final = terminal["review"]["settlement_date"] if terminal else "2050-12-31"
        map_rows = [f"{min(row['required_sessions']).replace('-', '')},{mappings[0]['symbol'].lower()}\n"]
        for mapping in mappings[:-1]:
            map_rows.append(f"{iso(mapping['valid_to']).replace('-', '')},{mapping['symbol'].lower()}\n")
        map_rows.append(f"{final.replace('-', '')},{mappings[-1]['symbol'].lower()}\n")
        securities[root] = {"security_id": row["security_id"], "maps": "".join(map_rows),
                            "actions": row["actions"], "required_sessions": row["required_sessions"],
                            "execution_sessions": row["execution_sessions"], "terminal": terminal,
                            "native_map_end_semantics": "economic lifecycle end, not legal delisting or last tradable session"}
    # Locate the exact frozen feature store. It must contain raw execution prices
    # as certified, not dividend-adjusted or already split-adjusted substitutes.
    candidates = [Path(v["path"]) for v in manifest["files"].values()
                  if Path(v["path"]).name == "security-master-feature-store.json"]
    if len(candidates) != 1:
        raise ValueError("PIT execution needs the frozen feature sidecar")
    import json
    sidecar = json.loads(candidates[0].read_text(encoding="utf-8"))
    with duckdb.connect(sidecar["database"], read_only=True) as c:
        bars = c.execute("""SELECT date,symbol,security_id,open,high,low,close,volume
            FROM daily_bars WHERE date BETWEEN ? AND ? ORDER BY date,symbol""",
            [manifest["calendar"][0], manifest["window"][2]]).df()
    signals = [{**{k: v for k, v in s.items() if k != "security_id"},
                "symbol": identity[s["security_id"]]} for s in manifest["signals"]]
    price_parts = []
    for root, spec in securities.items():
        source = bars.loc[bars.security_id.eq(spec["security_id"])].copy()
        raw_closes = {iso(r.date): float(r.close) for r in source.itertuples(index=False)}
        execution_actions = [a for a in spec["actions"] if manifest["window"][0] <= a["effective_date"] <= manifest["window"][2]]
        spec["factors"] = factor_lines(execution_actions, manifest["calendar"], raw_closes)
        source["mapped_symbol"] = source["symbol"]
        source["symbol"] = root
        price_parts.append(source)
    benchmark = bars.loc[bars.symbol.eq("SPY")].copy()
    benchmark["mapped_symbol"] = "SPY"
    price_parts.append(benchmark)
    prices = pd.concat(price_parts, ignore_index=True)
    dataset = {"origin": manifest["data_origin"], "source_master_version": manifest["universe_version"],
               "dependency_sha256": manifest["dependency_sha256"], "securities": securities,
               "price_basis": "raw", "feature_basis": "causal_split_only",
               "actions_sha256": digest({k: v["actions"] for k, v in securities.items()}),
               "map_sha256": digest({k: v["maps"] for k, v in securities.items()}),
               "factor_sha256": digest({k: v["factors"] for k, v in securities.items()})}
    return signals, prices, dataset
