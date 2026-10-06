"""Identity-bounded causal features in a separate, immutable research store.

Uses the existing feature formulas and configuration unchanged. Missing bars
stay missing. Rolling histories cannot cross unresolved listing episodes.
"""
from __future__ import annotations

from datetime import timezone
import hashlib
import json
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import yaml

from radar.features.base import compute_base_features
from radar.features.elasticity import ElasticityConfig, compute_elasticity_inputs
from radar.features.scoring import COMPONENT_NAMES, load_research_config, score_elasticity, tradability_gate
from radar.features.strategy2 import compute_strategy2_features
from radar.lab.universe import LocalSecurityMaster
from radar.research.pipeline import FEATURE_VERSION
from radar.schema import RESEARCH_COLUMNS, ensure_research_schema

PIT_FEATURE_BASIS = "pit-identity-causal-v1"


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def build_features(source: Path, master: LocalSecurityMaster, config: Path, output: Path,
                   progress=None, *, expected_source_hash: str | None = None) -> dict:
    """Refuse replacement; stage only in a new directory outside existing DBs."""
    source, output = source.resolve(), output.resolve()
    if output == source or output.exists():
        raise ValueError("PIT feature destination must be a new database")
    source_hash = file_hash(source)
    if expected_source_hash is not None and source_hash != expected_source_hash:
        raise ValueError("source research snapshot changed")
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = output.with_suffix(".building.duckdb")
    if staging.exists():
        raise ValueError("prior unfinished PIT feature staging store exists")
    cfg = load_research_config(config)
    raw_cfg = yaml.safe_load(config.read_text(encoding="utf-8"))["elasticity"]
    ecfg = ElasticityConfig(**{key: raw_cfg[key] for key in (
        "history_window", "history_min", "burst_quantile", "hit_5_weight", "hit_10_weight")})
    mappings = master.frame.copy()
    mappings["valid_to"] = mappings.valid_to.fillna(master.coverage_end)
    con = duckdb.connect(str(staging))
    counts = {"securities": 0, "feature_rows": 0}
    try:
        con.execute("SET memory_limit='2GB'")
        con.execute("SET threads=2")
        ensure_research_schema(con)
        con.execute("ALTER TABLE daily_bars ADD COLUMN security_id VARCHAR")
        con.execute("ALTER TABLE daily_features ADD COLUMN security_id VARCHAR")
        escaped = str(source).replace("'", "''")
        con.execute(f"ATTACH '{escaped}' AS source_snapshot (READ_ONLY)")
        con.register("pit_mappings", mappings)
        con.execute("""INSERT INTO daily_bars
            SELECT b.*,m.security_id FROM source_snapshot.daily_bars b JOIN pit_mappings m
            ON b.symbol=m.symbol AND b.date BETWEEN m.valid_from AND m.valid_to
            WHERE m.eligible AND (m.listing_date IS NULL OR b.date>=m.listing_date)
              AND (m.delisting_date IS NULL OR b.date<=m.delisting_date)
            ORDER BY m.security_id,b.date""")
        con.execute("""INSERT INTO daily_bars
            SELECT b.*,NULL FROM source_snapshot.daily_bars b WHERE symbol IN ('SPY','QQQ')
              AND date<=? AND NOT EXISTS (
                SELECT 1 FROM daily_bars p WHERE p.symbol=b.symbol AND p.date=b.date)""", [master.coverage_end.date()])
        con.execute("DETACH source_snapshot")
        con.unregister("pit_mappings")
        con.execute("CREATE INDEX pit_bar_identity ON daily_bars(security_id)")
        benchmark = con.execute("SELECT date,symbol,close FROM daily_bars WHERE symbol IN ('SPY','QQQ') ORDER BY date").df()
        benchmark["date"] = pd.to_datetime(benchmark.date)
        closes = {s: benchmark.loc[benchmark.symbol.eq(s)].set_index("date").close for s in ("SPY", "QQQ")}
        if any(closes[s].empty for s in closes):
            raise ValueError("PIT features require SPY and QQQ price history")
        sessions = closes["SPY"].index
        identities = [r[0] for r in con.execute("SELECT DISTINCT security_id FROM daily_bars WHERE security_id IS NOT NULL ORDER BY security_id").fetchall()]
        fields = [*RESEARCH_COLUMNS["daily_features"], "security_id"]
        watermark = con.execute("SELECT MAX(downloaded_at) FROM daily_bars").fetchone()[0]
        for i, identity in enumerate(identities):
            raw = con.execute("SELECT date,symbol,open,high,low,close,volume FROM daily_bars WHERE security_id=? ORDER BY date", [identity]).df()
            raw["date"] = pd.to_datetime(raw.date)
            if raw.date.duplicated().any():
                raise ValueError("ambiguous security bars within one session")
            indexed = raw.set_index("date")
            bars = indexed[["open", "high", "low", "close", "volume"]].reindex(sessions)
            feature = pd.concat([compute_base_features(bars),
                compute_elasticity_inputs(bars, closes["SPY"], closes["QQQ"], ecfg),
                compute_strategy2_features(bars, closes["SPY"], closes["QQQ"])], axis=1)
            feature["elasticity_atr_raw"] = feature.atr_pct_20
            observed = bars.close.notna()
            feature["tradability_pass"] = tradability_gate(pd.DataFrame({
                "close": bars.close, "avg_dollar_volume_20": feature.avg_dollar_volume_20,
                "history_sessions": observed.cumsum()}, index=sessions), cfg)
            feature["date"] = sessions.date
            feature["symbol"] = indexed.symbol.reindex(sessions)
            feature["security_id"] = identity
            feature["feature_version"] = FEATURE_VERSION
            feature["computed_at"] = watermark
            payload = feature.loc[observed].reindex(columns=fields)
            con.register("pit_feature_payload", payload)
            con.execute(f"INSERT INTO daily_features ({','.join(fields)}) SELECT {','.join(fields)} FROM pit_feature_payload")
            con.unregister("pit_feature_payload")
            counts["feature_rows"] += len(payload)
            counts["securities"] += 1
            if progress and (i % 100 == 0 or i == len(identities) - 1):
                progress({"completed": i + 1, "total": len(identities), **counts})
        columns = [f"elasticity_{COMPONENT_NAMES[key]}_component" for key in cfg.weights] + ["elasticity_score"]
        assignments = ",".join(f"{key}=s.{key}" for key in columns)
        for offset in range(0, len(sessions), 20):
            first, last = sessions[offset].date(), sessions[min(offset + 19, len(sessions) - 1)].date()
            raw = con.execute("""SELECT symbol,date,elasticity_beta_raw,elasticity_atr_raw,
                elasticity_idio_raw,elasticity_burst_raw,elasticity_hit_raw FROM daily_features
                WHERE tradability_pass AND date BETWEEN ? AND ?""", [first, last]).df()
            if raw.empty:
                continue
            scored = score_elasticity(raw, cfg)
            con.register("pit_scores", scored[["symbol", "date", *columns]])
            con.execute(f"""UPDATE daily_features f SET {assignments} FROM pit_scores s
                WHERE f.symbol=s.symbol AND f.date=s.date AND f.date BETWEEN ? AND ?""", [first, last])
            con.unregister("pit_scores")
        con.execute("CREATE TABLE feature_session_coverage AS SELECT feature_version,date,COUNT(*) row_count FROM daily_features GROUP BY 1,2")
        con.execute("CHECKPOINT")
    finally:
        con.close()
    if file_hash(source) != source_hash:
        raise ValueError("source research snapshot changed during PIT feature build")
    staging.rename(output)
    manifest = {"database": str(output), "database_sha256": file_hash(output),
                "source_database": str(source), "source_database_sha256": source_hash,
                "master_output_sha256": hashlib.sha256(master.csv_path.read_bytes()).hexdigest(),
                "research_config_sha256": file_hash(config), "feature_basis": PIT_FEATURE_BASIS,
                "formula_version": FEATURE_VERSION, "counts": counts,
                "limitations": ["no vendor bar identity certification", "missing prices retained in universe audit", "unresolved episodes reset rolling history"],
                "builder_code_sha256": file_hash(Path(__file__))}
    output.with_suffix(".manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest
