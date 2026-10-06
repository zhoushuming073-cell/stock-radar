"""Auxiliary evidence is cross-check material, not automatic identity truth."""
import hashlib
import json
from pathlib import Path
import re

import duckdb
import pandas as pd

from radar.pit.sources import git


def validation_report(master, cache: Path, pins: dict, output: Path, database: Path | None = None) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    frame = master.frame
    rows, auxiliary = [], {}
    aliases = {"delisted": "delisted-equity-data", "reference": "ticker-reference-data"}
    for name, path in (("delisted", "data/delisted_equity_data.json"),
                       ("reference", "data/ticker_changes.json")):
        if name not in pins:
            continue
        repo = cache / (aliases[name] + ".git")
        if not repo.exists():
            repo = cache / (name + ".git")
        raw = git(repo, "show", pins[name]["commit"] + ":" + path)
        auxiliary[name] = {**pins[name], "path": path, "file_sha256": hashlib.sha256(raw).hexdigest()}
        data = json.loads(raw)
        if name == "delisted":
            us = [r for r in data["records"] if r.get("market") == "US"]
            exact = 0
            for r in us:
                raw_date = r.get("delisting_date", "")
                precise = bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw_date))
                try:
                    event_day = pd.Timestamp(raw_date) if precise else None
                except ValueError:
                    precise, event_day = False, None
                exact += precise
                mapping = frame.loc[frame.symbol.eq(r["ticker"])]
                nearest = None
                if event_day is not None and not mapping.empty:
                    ends = pd.to_datetime(mapping.get("last_observed_date", mapping.valid_to))
                    distance = (ends - event_day).dt.days
                    nearest = int(distance.loc[distance.abs().idxmin()])
                rows.append({"source": name, "symbol": r["ticker"], "company_name": r["company_name"],
                    "source_delisting_date": raw_date, "date_is_exact": precise,
                    "source_delisting_type": r["delisting_type"],
                    "source_recycled_claim": r.get("ticker_recycled"),
                    "observed_mapping_intervals": len(mapping),
                    "nearest_observation_end_minus_reported_delisting_days": nearest,
                    "resolution_status": "unresolved", "evidence_url": r.get("source"),
                    "notes": "secondary claim; ticker/name/date require independent SEC/exchange validation"})
            auxiliary[name].update({"us_records": len(us), "exact_date_records": exact,
                                     "complete_us_coverage": False})
            if database is not None:
                claims = pd.DataFrame([{ "record_id": index, "symbol": r["symbol"],
                    "event_date": pd.Timestamp(r["source_delisting_date"])}
                    for index, r in enumerate(rows) if r["source"] == "delisted" and r["date_is_exact"]
                    and master.coverage_start <= pd.Timestamp(r["source_delisting_date"]) <= master.coverage_end])
                if not claims.empty:
                    with duckdb.connect(str(database), read_only=True) as con:
                        con.register("delisted_claims", claims)
                        coverage = con.execute("""SELECT r.record_id,COUNT(b.date) AS bar_rows,
                            MAX(b.date) AS last_bar_before_reported_event
                            FROM delisted_claims r LEFT JOIN daily_bars b
                            ON r.symbol=b.symbol AND b.date BETWEEN ? AND r.event_date
                            GROUP BY r.record_id""", [master.coverage_start.date()]).df()
                    nearby = 0
                    for item in coverage.to_dict("records"):
                        row = rows[item["record_id"]]
                        last = item["last_bar_before_reported_event"]
                        distance = None if pd.isna(last) else int((pd.Timestamp(row["source_delisting_date"]) - pd.Timestamp(last)).days)
                        row.update({"local_raw_symbol_bar_rows_before_reported_event": int(item["bar_rows"]),
                            "last_raw_symbol_bar_before_reported_event": None if pd.isna(last) else str(pd.Timestamp(last).date()),
                            "calendar_days_before_reported_event": distance,
                            "vendor_bar_identity_verified": False})
                        nearby += distance is not None and distance <= 7
                    auxiliary[name]["local_price_cross_check"] = {"claims_in_requested_period": len(claims),
                        "no_any_raw_symbol_bars_before_event": int(coverage.bar_rows.eq(0).sum()),
                        "raw_symbol_last_bar_within_7_calendar_days_before_event": nearby,
                        "limitations": "secondary dates and raw-symbol prices are unverified; proximity is not terminal economics or complete delisted coverage"}
        else:
            renames = {s: r for s, r in data.items() if isinstance(r, dict) and r.get("old_ticker")}
            for symbol, r in renames.items():
                rows.append({"source": name, "symbol": symbol, "old_symbol": r["old_ticker"],
                    "issuer_cik_claim": r.get("cik"), "has_effective_date": False,
                    "old_observed_intervals": int(frame.symbol.eq(r["old_ticker"]).sum()),
                    "new_observed_intervals": int(frame.symbol.eq(symbol).sum()),
                    "resolution_status": "unresolved",
                    "notes": "undated issuer-level cache cannot establish security identity or ticker interval"})
            auxiliary[name].update({"lookup_entries": len(data), "rename_candidates": len(renames),
                                     "effective_dates_available": False})
    pd.DataFrame(rows).to_csv(output / "auxiliary-evidence.csv", index=False)
    sec_errors = {}
    for path in (cache / "sec").glob("*-error.json"):
        sec_errors[path.name] = json.loads(path.read_text(encoding="utf-8"))
    summary = {"primary": pins["symbols"], "validation_sources": auxiliary,
               "sec_bulk_fetch_errors": sec_errors,
               "sec_dated_manual_evidence": master.manifest.get("build_inputs", {}).get("identity_evidence", []),
               "license": "No LICENSE files found in the three pinned source trees; redistribution permission unverified; data remains local.",
               "identity_policy": "No automatic CIK-only or undated rename merge. Reviewed SEC/exchange plus class evidence only.",
               "membership_confidence": "inferred observed screener population; bounded carry between snapshots",
               "source_scope": "NASDAQ Screener exchange-filtered equity-like products, not official exhaustive Symbol Directory",
               "corporate_action_coverage": "not established", "terminal_value_coverage": "not established"}
    (output / "source-validation-summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary
