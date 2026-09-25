"""Read-only Phase 2 data provenance and universe audit."""

import argparse
import json
from pathlib import Path

import duckdb


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, default=ROOT / "data" / "phase2-research.duckdb")
    parser.add_argument("--output", type=Path, default=ROOT / "reports" / "phase2" / "data_audit.json")
    args = parser.parse_args()
    conn = duckdb.connect(str(args.database), read_only=True)
    try:
        bars = conn.execute("""
            SELECT COUNT(*), COUNT(DISTINCT symbol), COUNT(DISTINCT date), MIN(date), MAX(date),
                   COUNT(*) FILTER (WHERE open IS NULL OR high IS NULL OR low IS NULL OR close IS NULL OR volume IS NULL),
                   COUNT(*) FILTER (WHERE open <= 0 OR high < low OR close <= 0 OR volume < 0)
            FROM daily_bars
        """).fetchone()
        provenance = conn.execute("""
            SELECT provider,feed,adjustment,COUNT(*) FROM daily_bars
            GROUP BY 1,2,3 ORDER BY 4 DESC
        """).fetchall()
        benchmark = conn.execute("""
            SELECT symbol, COUNT(*), MIN(date), MAX(date) FROM daily_bars
            WHERE symbol IN ('SPY','QQQ') GROUP BY symbol ORDER BY symbol
        """).fetchall()
        coverage = conn.execute("""
            SELECT COUNT(*) FILTER (WHERE sessions >= 1000),
                   COUNT(*) FILTER (WHERE sessions BETWEEN 250 AND 999),
                   COUNT(*) FILTER (WHERE sessions < 250),
                   MAX(sessions), MEDIAN(sessions)
            FROM (SELECT symbol, COUNT(*) AS sessions FROM daily_bars
                  WHERE symbol NOT IN ('SPY','QQQ') GROUP BY symbol)
        """).fetchone()
        universe = conn.execute("""
            SELECT COUNT(*),
                   COUNT(*) FILTER (WHERE upper(name) LIKE '%ETF%'),
                   COUNT(*) FILTER (WHERE upper(name) LIKE '%ETN%'),
                   COUNT(*) FILTER (WHERE upper(name) LIKE '%TRUST%'),
                   COUNT(*) FILTER (WHERE upper(exchange)='OTC')
            FROM assets WHERE upper(asset_class)='US_EQUITY' AND upper(status)='ACTIVE'
        """).fetchone()
        selected = conn.execute("""
            WITH selected AS (
                SELECT DISTINCT symbol FROM daily_features
                WHERE feature_version='phase2a_f_v2'
            )
            SELECT COUNT(*),
                   COUNT(*) FILTER (WHERE upper(a.name) LIKE '%ETF%'),
                   COUNT(*) FILTER (WHERE upper(a.name) LIKE '%ETN%'),
                   COUNT(*) FILTER (WHERE upper(a.name) LIKE '%TRUST%')
            FROM selected s JOIN assets a ON s.symbol=a.symbol
        """).fetchone()
        tables = {name: conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
                  for name in ("daily_features", "forward_labels", "research_runs")}
        max_label_date = conn.execute("SELECT MAX(signal_date) FROM forward_labels").fetchone()[0]
        scored = conn.execute("""
            SELECT COUNT(*) FILTER (WHERE elasticity_score IS NOT NULL), COUNT(*)
            FROM daily_features WHERE feature_version='phase2a_f_v2'
        """).fetchone()
        current_labels = conn.execute("""
            SELECT COUNT(*) FROM forward_labels l
            JOIN (SELECT DISTINCT symbol FROM daily_features
                  WHERE feature_version='phase2a_f_v2') f USING (symbol)
            WHERE l.label_version='open_close_v1'
        """).fetchone()[0]
    finally:
        conn.close()
    result = {
        "database": str(args.database),
        "daily_bars": {"rows": bars[0], "symbols": bars[1], "sessions": bars[2],
                       "start": str(bars[3]), "end": str(bars[4]),
                       "null_ohlcv_rows": bars[5], "invalid_price_volume_rows": bars[6]},
        "provenance": [{"provider": a, "feed": b, "adjustment": c, "rows": n}
                       for a, b, c, n in provenance],
        "benchmarks": [{"symbol": a, "sessions": n, "start": str(start), "end": str(end)}
                       for a, n, start, end in benchmark],
        "stock_history": {"at_least_1000_sessions": coverage[0],
                          "250_to_999_sessions": coverage[1], "under_250_sessions": coverage[2],
                          "max_sessions": coverage[3], "median_sessions": coverage[4]},
        "current_asset_master": {"active_us_equity": universe[0],
                                 "name_contains_etf": universe[1],
                                 "name_contains_etn": universe[2],
                                 "name_contains_trust": universe[3], "otc": universe[4],
                                 "note": "Name patterns are only audit hints, not reliable security classification."},
        "selected_research_symbols": {"count": selected[0],
                                      "name_contains_etf": selected[1],
                                      "name_contains_etn": selected[2],
                                      "name_contains_trust": selected[3]},
        "research_tables": tables, "scored_feature_rows": scored[0],
        "current_run_feature_rows": scored[1], "current_run_label_rows": current_labels,
        "last_forward_label_signal_date": str(max_label_date),
        "limitations": ["current active asset list has survivorship bias",
                        "Alpaca us_equity includes funds and other equity-like securities"],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
