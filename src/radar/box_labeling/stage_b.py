"""Private, pre-result blind audit selection for range-detector Stage B."""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
import json
from pathlib import Path

from .history import BoxHistory
from .numeric import numeric_bundle, canonical, VERSION as NUMERIC_VERSION
from .render import render_bundle, VERSION as RENDER_VERSION
import numpy as np

VERSION = "box-range-stage-b-blind-v1"
SEED = "box-range-stage-b-20261013-before-detector-output"
YEARS = (2022, 2023, 2024, 2025)
EXCLUDED_SYMBOLS = frozenset({"IREN", "RIOT", "APLD", "SOFI", "IONQ", "POET"})
DOMAIN = """length=126 AND supported_membership AND shape_research_ready AND
 ((decision_date BETWEEN DATE '2022-01-01' AND DATE '2024-08-29') OR
  (decision_date BETWEEN DATE '2024-09-30' AND DATE '2025-09-08'))"""


def packed(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode()


def digest(value: bytes) -> str:
    return sha256(value).hexdigest()


def prior_ids(path: Path) -> set[str]:
    if not path.exists():
        raise FileNotFoundError("prior label manifest required for separation")
    return {row["security_id"] for row in json.loads(path.read_bytes())}


def freeze_blind_pool(research_root: Path, output: Path, prior_manifest: Path,
                      *, per_year: int = 12) -> dict:
    """Select distinct security IDs without looking at detector outputs or labels.

    The private mapping is immutable after creation. This is a hash-priority
    sample, not a known-probability estimate of the US issuer universe.
    """
    if not 1 <= per_year <= 32:
        raise ValueError("per_year outside audited range")
    if output.exists():
        raise FileExistsError("blind selection already frozen")
    excluded = prior_ids(prior_manifest)
    with BoxHistory(research_root) as provider:
        connection = provider.api.core.connection
        old = connection.execute(f"""SELECT security_id, decision_date
          FROM universe_window_index WHERE {DOMAIN}
          QUALIFY row_number() OVER (PARTITION BY year(decision_date)
             ORDER BY hash(security_id || CAST(decision_date AS VARCHAR) || ?)) <= 24""",
            ["box-range-stage-a-20261013"]).fetchall()
        excluded.update(row[0] for row in old)
        denominator_rows = connection.execute(f"""SELECT year(decision_date),
          count(*), count(DISTINCT security_id) FROM universe_window_index
          WHERE {DOMAIN} GROUP BY 1 ORDER BY 1""").fetchall()
        selected = []
        used = set(excluded)
        exclusions = Counter()
        for year in YEARS:
            rows = connection.execute(f"""SELECT security_id, decision_date,
              historical_ticker, membership_status, source, basis
              FROM universe_window_index WHERE {DOMAIN}
              AND year(decision_date)=? ORDER BY
              hash(security_id || CAST(decision_date AS VARCHAR) || ?),
              security_id, decision_date LIMIT 20000""", [year, SEED]).fetchall()
            count = 0
            for security_id, day, symbol, membership, source, basis in rows:
                if symbol in EXCLUDED_SYMBOLS:
                    exclusions["six_reference_symbols"] += 1
                    continue
                if security_id in used:
                    exclusions["prior_or_repeated_security_id"] += 1
                    continue
                # Provider gate before freezing. No detector is called here.
                try:
                    provider.history(security_id, day, max_sessions=126)
                except ValueError:
                    exclusions["provider_rejected"] += 1
                    continue
                selected.append({"task_id": digest(packed([VERSION, SEED, security_id,
                    str(day)]))[:24], "security_id": security_id,
                    "decision_date": str(day), "historical_ticker": symbol,
                    "year": year, "split": "train" if str(day) <= "2024-08-29" else "validation",
                    "membership_status": membership, "source": source, "basis": basis})
                used.add(security_id)
                count += 1
                if count == per_year:
                    break
            if count != per_year:
                raise ValueError(f"insufficient safe, distinct rows in {year}")
        body = {"version": VERSION, "seed": SEED, "selection_precedes_detector": True,
                "reference_symbols_excluded": sorted(EXCLUDED_SYMBOLS),
                "prior_label_manifest_sha256": digest(prior_manifest.read_bytes()),
                "ri_semantic_hash": provider.semantic_hash,
                "denominators": {str(y): {"eligible_security_days": n,
                    "distinct_security_ids": ids} for y, n, ids in denominator_rows},
                "exclusions_during_draw": dict(exclusions), "rows": selected}
    output.parent.mkdir(parents=True, exist_ok=True)
    raw = packed(body)
    output.write_bytes(raw)
    return {"version": VERSION, "selection_sha256": digest(raw),
            "selected": len(selected), "by_year": dict(Counter(str(r["year"]) for r in selected)),
            "membership": dict(Counter(r["membership_status"] for r in selected)),
            "denominators": body["denominators"], "exclusions": dict(exclusions),
            "issuer_alias_separation_verified": False,
            "note": "ID separation only; issuer alias linkage remains an audit gate."}


def materialize_blind_tasks(research_root: Path, selection: Path,
                            output: Path, expected_selection_sha256: str) -> dict:
    """Render immutable blind charts using the existing v1.1 Label Studio UI.

    This deliberately never calls a range detector or reads future outcomes.
    """
    raw_selection = selection.read_bytes()
    if digest(raw_selection) != expected_selection_sha256:
        raise ValueError("selection receipt changed")
    frozen = json.loads(raw_selection)
    if frozen["version"] != VERSION or not frozen["selection_precedes_detector"]:
        raise ValueError("unfrozen selection")
    if output.exists():
        if (output / "manifest.json").exists() or (output / "receipt.json").exists() or list(output.glob("annotations*")):
            raise FileExistsError("blind task or annotation batch already exists")
    else:
        output.mkdir(parents=True)
    for subdir in ("charts", "numeric", "raw"):
        (output / subdir).mkdir(exist_ok=True)
    manifest = []
    with BoxHistory(research_root) as provider:
        if provider.semantic_hash != frozen["ri_semantic_hash"]:
            raise ValueError("research semantics changed")
        for row in frozen["rows"]:
            # The 126-session gate was frozen first. Extend backward only while
            # every added bar remains trusted; never splice over unsafe history.
            low, high = 126, 1100
            history = provider.history(row["security_id"], row["decision_date"], 126)
            while low < high:
                mid = (low + high + 1) // 2
                try:
                    expanded = provider.history(row["security_id"], row["decision_date"], mid)
                except ValueError:
                    high = mid - 1
                else:
                    low = mid
                    history = expanded
            bundle = numeric_bundle(history, row["decision_date"])
            renders = render_bundle(bundle)
            scales = {}
            for name, item in bundle["scales"].items():
                chart = renders[name]["svg"].encode()
                stem = f'{row["task_id"]}-{name}'
                (output / "charts" / f"{stem}.svg").write_bytes(chart)
                np.save(output / "numeric" / f"{stem}.npy",
                        item["tensor"], allow_pickle=False)
                (output / "raw" / f"{stem}.json").write_bytes(canonical(item["raw"]))
                scales[name] = {"raw_hash": item["raw_hash"],
                    "tensor_hash": item["tensor_hash"], "chart_hash": digest(chart),
                    "length": item["length"], "available": item["available"],
                    "chart_file": f"{stem}.svg", "tensor_file": f"{stem}.npy",
                    "raw_file": f"{stem}.json"}
            manifest.append({**row, "scales": scales,
                "stratum": "blind_unconditional",
                "trusted_prefix_sessions": len(history),
                "normalization_version": NUMERIC_VERSION,
                "renderer_version": RENDER_VERSION,
                "candidate_plugin_version": "none; pre-detector blind hash draw",
                "config_hash": expected_selection_sha256})
    manifest_raw = packed(manifest)
    (output / "manifest.json").write_bytes(manifest_raw)
    receipt = {"version": "box-label-tasks-v1", "manifest_hash": digest(manifest_raw),
        "selection_sha256": expected_selection_sha256,
        "ri_semantic_hash": frozen["ri_semantic_hash"],
        "renderer_version": RENDER_VERSION, "task_count": len(manifest),
        "detector_outputs_read": False, "future_outcomes_read": False}
    (output / "receipt.json").write_bytes(packed(receipt))
    return receipt
