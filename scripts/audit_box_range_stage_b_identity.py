"""Aggregate issuer-alias check against RI v1's recorded construction input."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from hashlib import sha256
import json
from pathlib import Path

import duckdb
import pandas as pd

from radar.box_labeling.history import BoxHistory
from radar.box_labeling.stage_b import DOMAIN, EXCLUDED_SYMBOLS, digest


def as_of_t_evidence(connection: duckdb.DuckDBPyConnection,
                     selected: list[dict]) -> list[tuple]:
    """Count only issuer evidence available at each frozen decision date."""
    connection.register("selected", pd.DataFrame(selected)[["security_id", "decision_date"]])
    return connection.execute("""SELECT s.security_id,
        count(DISTINCT e.cik) FILTER (WHERE CAST(e.available_on AS DATE)
            <= CAST(s.decision_date AS DATE)),
        count(*) FILTER (WHERE e.name_compatible IS FALSE AND
            CAST(e.available_on AS DATE) <= CAST(s.decision_date AS DATE)),
        count(*) FILTER (WHERE e.name_compatible IS FALSE AND
            CAST(e.available_on AS DATE) > CAST(s.decision_date AS DATE))
        FROM selected s LEFT JOIN issuer_evidence e USING(security_id)
        GROUP BY s.security_id""").fetchall()


def window_episode_evidence(connection: duckdb.DuckDBPyConnection,
                            windows: list[dict]) -> list[tuple]:
    """Check dated ticker episodes covering each causal 126-session window."""
    connection.register("windows", pd.DataFrame(windows))
    return connection.execute("""SELECT w.security_id,
        count(DISTINCT t.interval_id), count(DISTINCT t.symbol),
        count(DISTINCT e.cik)
        FROM windows w LEFT JOIN ticker_episode t
          ON w.security_id=t.security_id
          AND t.valid_from <= CAST(w.decision_date AS DATE)
          AND t.valid_to >= CAST(w.window_start AS DATE)
        LEFT JOIN issuer_evidence e
          ON e.interval_id=t.interval_id
          AND e.security_id=t.security_id
          AND CAST(e.available_on AS DATE) <= CAST(w.decision_date AS DATE)
        GROUP BY w.security_id""").fetchall()


def audit(research_root: Path, selection: Path, prior_manifest: Path) -> dict:
    frozen = json.loads(selection.read_bytes())
    selected = frozen["rows"]
    if len(selected) != 48 or not frozen["selection_precedes_detector"]:
        raise ValueError("expected frozen Stage B blind batch")
    core_manifest = research_root / json.loads(
        (research_root / "config/research_infrastructure_v1.json").read_text(
            encoding="utf-8"))["core_directory"] / "manifest.json"
    source = json.loads(core_manifest.read_text(encoding="utf-8"))["inputs"]["historical_database"]
    construction = Path(source["path"])
    if not construction.is_file():
        raise FileNotFoundError("recorded RI v1 construction database is unavailable")
    hasher = sha256()
    with construction.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            hasher.update(chunk)
    if hasher.hexdigest() != source["sha256"]:
        raise ValueError("RI v1 construction source hash changed")
    prior = json.loads(prior_manifest.read_bytes())
    with BoxHistory(research_root) as provider:
        if frozen["ri_semantic_hash"] != provider.semantic_hash:
            raise ValueError("RI v1 semantics changed")
        c = provider.api.core.connection
        stage_a = {r[0] for r in c.execute(f"""SELECT security_id
            FROM universe_window_index WHERE {DOMAIN}
            QUALIFY row_number() OVER(PARTITION BY year(decision_date)
                ORDER BY hash(security_id || CAST(decision_date AS VARCHAR) || ?)) <= 24""",
            ["box-range-stage-a-20261013"]).fetchall()}
        reference = {r[0] for r in c.execute("""SELECT DISTINCT security_id
            FROM shape_price WHERE symbol IN (SELECT unnest(?))""",
            [sorted(EXCLUDED_SYMBOLS)]).fetchall()}
        windows = []
        for row in selected:
            history = provider.history(row["security_id"], row["decision_date"], 126)
            windows.append({"security_id": row["security_id"],
                            "window_start": str(history.date.iloc[0].date()),
                            "decision_date": row["decision_date"]})
    selected_ids = {r["security_id"] for r in selected}
    previous_ids = {r["security_id"] for r in prior}
    all_ids = list(selected_ids | previous_ids | stage_a | reference)
    with duckdb.connect(str(construction), read_only=True) as c:
        evidence = c.execute("""SELECT DISTINCT security_id,cik
            FROM issuer_evidence WHERE security_id IN (SELECT unnest(?))
            AND cik IS NOT NULL""", [all_ids]).fetchall()
        by_id = defaultdict(set)
        for security_id, cik in evidence:
            by_id[security_id].add(cik)
        asof = as_of_t_evidence(c, selected)
        episodes = window_episode_evidence(c, windows)
        quality = c.execute("""SELECT count(*),
            count(*) FILTER (WHERE official_identity),
            count(*) FILTER (WHERE cik_count=1),
            count(*) FILTER (WHERE names_compatible)
            FROM identity_quality WHERE security_id IN (SELECT unnest(?))""",
            [list(selected_ids)]).fetchone()
        retrospective_levels = c.execute("""SELECT q.level,count(*)
            FROM selected s JOIN identity_quality q USING(security_id)
            GROUP BY q.level ORDER BY q.level""").fetchall()
        reviewed_at_t = c.execute("""SELECT count(DISTINCT s.security_id)
            FROM selected s JOIN review_annotation a USING(security_id)
            WHERE a.known_on <= CAST(s.decision_date AS DATE)
            AND CAST(s.decision_date AS DATE)
                BETWEEN a.disputed_start AND a.disputed_end""").fetchone()[0]
        asof_sources = c.execute("""SELECT e.source,count(DISTINCT s.security_id)
            FROM selected s JOIN issuer_evidence e USING(security_id)
            WHERE e.cik IS NOT NULL
            AND CAST(e.available_on AS DATE) <= CAST(s.decision_date AS DATE)
            GROUP BY e.source ORDER BY e.source""").fetchall()
    ciks = lambda ids: set().union(*(by_id.get(i, set()) for i in ids))
    chosen_ciks = ciks(selected_ids)
    return {
        "selection_sha256": digest(selection.read_bytes()),
        "ri_recorded_construction_version": construction.parent.name,
        "ri_recorded_construction_sha256": source["sha256"],
        "selected": len(selected_ids),
        "all_time_cik_counts": dict(sorted(Counter(len(by_id[i]) for i in selected_ids).items())),
        "as_of_t_cik_counts": dict(sorted(Counter(n for _, n, _, _ in asof).items())),
        "window_126_ticker_episode_counts": dict(sorted(
            Counter(n for _, n, _, _ in episodes).items())),
        "window_126_symbol_counts": dict(sorted(
            Counter(n for _, _, n, _ in episodes).items())),
        "window_126_as_of_t_episode_cik_counts": dict(sorted(
            Counter(n for _, _, _, n in episodes).items())),
        "as_of_t_incompatible_name_ids": sum(before > 0 for _, _, before, _ in asof),
        "post_t_only_incompatible_name_ids": sum(
            before == 0 and after > 0 for _, _, before, after in asof),
        "distinct_selected_ciks": len(chosen_ciks),
        "overlap_ciks_with_prior_pilot": len(chosen_ciks & ciks(previous_ids)),
        "overlap_ciks_with_stage_a": len(chosen_ciks & ciks(stage_a)),
        "overlap_ciks_with_six_references": len(chosen_ciks & ciks(reference)),
        "quality_rows": quality[0], "official_identity_rows": quality[1],
        "single_cik_quality_rows": quality[2], "compatible_names_rows": quality[3],
        "as_of_t_cik_evidence_source_id_counts": dict(asof_sources),
        "as_of_t_reviewed_discontinuity_ids": reviewed_at_t,
        "retrospective_identity_level_counts": dict(retrospective_levels),
        "retrospective_identity_scope": "full-window; not a T-known selection predicate",
        "issuer_alias_gate": "PROVISIONAL; OBS identities are not official, and one as-of-T name conflict requires review",
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--research-root", type=Path, required=True)
    p.add_argument("--selection", type=Path, required=True)
    p.add_argument("--prior-manifest", type=Path, required=True)
    args = p.parse_args()
    print(json.dumps(audit(args.research_root, args.selection, args.prior_manifest),
                     sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
