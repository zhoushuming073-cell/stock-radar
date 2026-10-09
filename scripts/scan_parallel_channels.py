"""Research-only read-only DuckDB scanner. Does NOT place broker orders."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
import yaml

from radar.research.parallel_channel import ChannelSettings, analyze


def main() -> None:
    ap = argparse.ArgumentParser(description="Month/week parallel channel + daily pullback research")
    ap.add_argument("--db", type=Path, default=Path("data/market.duckdb"))
    ap.add_argument("--csv", type=Path, help="Optional offline daily-bar CSV with symbol/date/OHLCV columns")
    ap.add_argument("--asof", required=True, help="A fully completed US market session, YYYY-MM-DD")
    ap.add_argument("--config", type=Path, default=Path("config/parallel_channel_v1.yaml"))
    ap.add_argument("--symbols", nargs="*", help="Optional restriction, not a predefined watchlist")
    ap.add_argument("--top", type=int, default=50)
    ap.add_argument("--out", type=Path, help="Optional local JSON report; never committed")
    args = ap.parse_args()
    if args.top < 1:
        ap.error("--top must be positive")
    asof = pd.Timestamp(args.asof)
    if asof.tzinfo is not None:
        ap.error("--asof must not contain timezone")
    raw = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    cfg = ChannelSettings(**(raw.get("settings") or {}))
    results = []
    skips = {}
    if args.csv:
        frame = pd.read_csv(args.csv)
        if "symbol" not in frame.columns:
            ap.error("CSV needs a symbol column")
        symbols = sorted(set(args.symbols) if args.symbols else set(frame.symbol))
        def read_rows(symbol):
            return frame.loc[frame.symbol == symbol].sort_values("date").tail(430).copy()
        source = "csv/daily-bars"
    else:
        if not args.db.is_file():
            ap.error(f"database not found: {args.db}")
        import duckdb  # installed by the Stock Radar project
        cn = duckdb.connect(str(args.db), read_only=True)
        try:
            # A CURRENT assets list is not historical PIT membership.
            symbols = sorted(set(args.symbols)) if args.symbols else [
                r[0] for r in cn.execute("""SELECT DISTINCT symbol FROM assets
                    WHERE upper(trim(status))='ACTIVE'
                    AND upper(trim(asset_class))='US_EQUITY'
                    AND symbol NOT IN ('SPY','QQQ') ORDER BY symbol""").fetchall()]
        except Exception:
            cn.close()
            raise
        def read_rows(symbol):
            return cn.execute("""SELECT date,open,high,low,close,volume FROM daily_bars
                    WHERE symbol=? AND date<=? ORDER BY date DESC LIMIT 430""",
                    [symbol, asof.date()]).df().iloc[::-1].reset_index(drop=True)
        source = "current-assets/read-only-daily-bars"
    try:
        for s in symbols:
            bars = read_rows(s)
            try:
                result = analyze(bars, asof, cfg)
            except (ValueError, TypeError, IndexError, OverflowError) as exc:
                skips[s] = str(exc)
                continue
            if result["qualified"]:
                results.append({"symbol": s, **result})
    finally:
        if not args.csv:
            cn.close()
    results.sort(key=lambda x: (x["watch"], x["rank_score"]), reverse=True)
    payload = {"version": "parallel-channel-v1", "asof": args.asof,
               "source": source, "total_scanned": len(symbols),
               "channels_found": len(results), "watch_count": sum(r["watch"] for r in results),
               "skipped": skips, "candidates": results[:args.top],
               "important": "Research-only. Not PIT-certified; no news/fundamental risk filter, no fills or alpha claim."}
    txt = json.dumps(payload, indent=2, ensure_ascii=False, default=str)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(txt, encoding="utf-8")
    print(txt)


if __name__ == "__main__":
    main()
