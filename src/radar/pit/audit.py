"""Membership and OHLCV audits keep absent prices in the denominator."""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from radar.lab.universe import LocalSecurityMaster


def membership_report(master: LocalSecurityMaster, database: Path, output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(database), read_only=True) as c:
        current = {r[0] for r in c.execute("""SELECT symbol FROM assets
                    WHERE upper(trim(status))='ACTIVE' AND upper(trim(asset_class))='US_EQUITY'""").fetchall()}
        sessions = {str(r[0]) for r in c.execute("SELECT date FROM daily_bars WHERE symbol='SPY'").fetchall()}
    rows, comparisons, previous = [], [], set()
    snapshot_file = master.csv_path.with_name("snapshot-audit.json")
    snapshot_dates = set()
    if snapshot_file.exists():
        snapshot_dates = {r["date"] for r in json.loads(snapshot_file.read_text(encoding="utf-8"))["snapshots"]
                          if r.get("accepted")}
    frame = master.frame
    potential_reuse = frame.groupby("symbol").security_id.nunique()
    same_id_symbols = frame.groupby("security_id").symbol.nunique()
    for day in pd.date_range(master.coverage_start, master.coverage_end):
        record = {"date": str(day.date()), "trading_session_in_local_prices": str(day.date()) in sessions,
                  "snapshot_observed": str(day.date()) in snapshot_dates, "source_gap": False}
        try:
            observed = master.observed_on(day)
        except ValueError:
            record.update({"source_gap": True, "observed_instruments": None, "eligible_common": None})
            rows.append(record)
            previous = set()
            continue
        eligible = observed[observed.eligible]
        symbols = set(observed.symbol)
        counts = Counter(observed.exchange)
        record.update({"observed_instruments": len(observed), "eligible_common": len(eligible),
                       "nasdaq": counts["NASDAQ"], "nyse": counts["NYSE"], "amex": counts["AMEX"],
                       "common": int(observed.security_type.eq("common").sum()),
                       "unknown_security_type": int(observed.security_type.eq("unknown").sum()),
                       "unresolved_identity": int(observed.resolution_status.ne("verified").sum()) if "resolution_status" in observed else None,
                       "added_observations": len(symbols - previous) if previous else None,
                       "removed_observations": len(previous - symbols) if previous else None})
        rows.append(record)
        previous = symbols
    daily = pd.DataFrame(rows)
    daily.to_csv(output / "daily-universe.csv", index=False)
    rng = np.random.default_rng(20261007)
    for year in range(master.coverage_start.year, master.coverage_end.year + 1):
        choices = daily.loc[daily.date.str.startswith(str(year)) & ~daily.source_gap &
                            daily.trading_session_in_local_prices, "date"].tolist()
        if not choices:
            comparisons.append({"year": year, "status": "no covered local trading date"})
            continue
        for day in sorted(rng.choice(choices, size=min(2, len(choices)), replace=False)):
            day = str(day)
            observed = master.observed_on(day)
            pit = set(observed.symbol)
            eligible = set(observed.loc[observed.eligible, "symbol"])
            comparisons.append({"date": day, "pit_observed": len(pit), "pit_eligible_common": len(eligible),
                "current_snapshot": len(current), "intersection": len(pit & current),
                "pit_only": len(pit - current), "current_only": len(current - pit),
                "pit_only_symbols": sorted(pit - current), "current_only_symbols": sorted(current - pit),
                "pit_eligible_symbols": sorted(eligible)})
    (output / "current-vs-pit.json").write_text(json.dumps(comparisons, indent=2), encoding="utf-8")
    summary = {"coverage_start": str(master.coverage_start.date()), "coverage_end": str(master.coverage_end.date()),
               "calendar_days": len(daily), "source_gap_days": int(daily.source_gap.sum()),
               "local_trading_gap_days": int((daily.source_gap & daily.trading_session_in_local_prices).sum()),
               "unique_security_episodes": int(frame.security_id.nunique()), "mapping_intervals": len(frame),
               "potential_ticker_reuse_or_unresolved_episode_splits": int(potential_reuse.gt(1).sum()),
               "verified_multi_symbol_identities": int(same_id_symbols.gt(1).sum()),
               "actual_delisting_dates_known": int(frame.delisting_date.notna().sum()),
               "unresolved_identity_intervals": int(frame.resolution_status.ne("verified").sum()) if "resolution_status" in frame else None,
               "unknown_type_intervals": int(frame.security_type.eq("unknown").sum()),
               "fingerprint": master.fingerprint, "formal_pit_ready": False,
               "limitations": ["observed absence is not certified delisting", "current-only includes source scope/type/gap differences, not only future IPOs",
                               "episode IDs are conservative identities, not verified securities", "no instrument-level identity certification for vendor bars"]}
    (output / "membership-summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def price_coverage_report(master: LocalSecurityMaster, database: Path, output: Path,
                          warmup_sessions: int = 126) -> dict:
    """Audit every mapping, including unknown types and securities without bars."""
    output.mkdir(parents=True, exist_ok=True)
    mappings = master.frame.reset_index(drop=True).copy()
    mappings["interval_id"] = np.arange(len(mappings))
    mappings["valid_to"] = mappings.valid_to.fillna(master.coverage_end)
    with duckdb.connect(str(database), read_only=True) as c:
        c.execute("SET memory_limit='2GB'")
        c.register("pit_mapping_audit", mappings)
        result = c.execute("""
            SELECT m.interval_id,COUNT(b.date) AS bar_rows,
                   COUNT(b.date) FILTER (WHERE b.open>0 AND b.high>=b.low AND b.low>0
                     AND b.close>0 AND b.volume>=0 AND b.open BETWEEN b.low AND b.high
                     AND b.close BETWEEN b.low AND b.high) AS valid_ohlcv_rows,
                   MIN(b.date) AS first_bar,MAX(b.date) AS last_bar
            FROM pit_mapping_audit m LEFT JOIN daily_bars b
            ON m.symbol=b.symbol AND b.date BETWEEN m.valid_from AND m.valid_to
            GROUP BY m.interval_id
        """).df()
        sessions = pd.DatetimeIndex([r[0] for r in c.execute(
            "SELECT date FROM daily_bars WHERE symbol='SPY' ORDER BY date").fetchall()])
    result = mappings.merge(result, on="interval_id", validate="one_to_one")
    first = pd.to_datetime(result.valid_from).to_numpy(dtype="datetime64[ns]")
    last = pd.to_datetime(result.valid_to).to_numpy(dtype="datetime64[ns]")
    calendar = sessions.to_numpy(dtype="datetime64[ns]")
    result["expected_sessions_in_available_calendar"] = np.searchsorted(calendar, last, side="right") - np.searchsorted(calendar, first)
    result["missing_sessions"] = (result.expected_sessions_in_available_calendar - result.valid_ohlcv_rows).clip(lower=0)
    result["no_bars"] = result.bar_rows.eq(0)
    result["complete_available_interval_ohlcv"] = result.expected_sessions_in_available_calendar.gt(0) & result.missing_sessions.eq(0)
    result["starts_after_listing_date"] = result.listing_date.notna() & pd.to_datetime(result.first_bar).gt(result.listing_date)
    result["ends_before_delisting_date"] = result.delisting_date.notna() & pd.to_datetime(result.last_bar).lt(result.delisting_date)
    result["starts_after_first_observation"] = pd.to_datetime(result.first_bar).gt(result.valid_from)
    result["ends_before_last_observation"] = pd.to_datetime(result.last_bar).lt(pd.to_datetime(result.get("last_observed_date", result.valid_to)))
    result["warmup_rows_insufficient"] = result.groupby("security_id").bar_rows.transform("sum").lt(warmup_sessions)
    result.to_csv(output / "price-coverage-intervals.csv", index=False)
    securities = result.groupby("security_id").agg(bar_rows=("bar_rows", "sum"),
        missing_sessions=("missing_sessions", "sum"), expected_sessions=("expected_sessions_in_available_calendar", "sum"))
    common = result.loc[result.eligible].groupby("security_id").agg(
        bar_rows=("bar_rows", "sum"), missing_sessions=("missing_sessions", "sum"),
        expected_sessions=("expected_sessions_in_available_calendar", "sum"))
    summary = {"database": str(database.resolve()), "pit_security_episodes": len(securities),
        "no_any_bars_securities": int(securities.bar_rows.eq(0).sum()),
        "complete_available_interval_ohlcv_securities": int((securities.missing_sessions.eq(0) & securities.expected_sessions.gt(0)).sum()),
        "insufficient_warmup_securities": int(securities.bar_rows.lt(warmup_sessions).sum()),
        "expected_sessions": int(securities.expected_sessions.sum()), "missing_ohlcv_sessions": int(securities.missing_sessions.sum()),
        "intervals_starting_after_listing_date": int(result.starts_after_listing_date.sum()),
        "intervals_ending_before_delisting_date": int(result.ends_before_delisting_date.sum()),
        "actual_listing_date_known_intervals": int(result.listing_date.notna().sum()),
        "actual_delisting_date_known_intervals": int(result.delisting_date.notna().sum()),
        "intervals_ending_before_last_observation": int(result.ends_before_last_observation.sum()),
        "missing_terminal_price_policy": "unresolved delisting execution; no forward fill, zero or invented payout",
        "identity_certified_ohlcv": False,
        "eligible_common_episodes": {"total": len(common),
            "no_any_bars": int(common.bar_rows.eq(0).sum()),
            "complete_available_interval_ohlcv": int((common.missing_sessions.eq(0) & common.expected_sessions.gt(0)).sum()),
            "insufficient_warmup": int(common.bar_rows.lt(warmup_sessions).sum()),
            "expected_sessions": int(common.expected_sessions.sum()),
            "missing_ohlcv_sessions": int(common.missing_sessions.sum())},
        "limitations": ["completeness is only within observed membership and local SPY calendar", "complete interval OHLCV is not proof of historical vendor identity",
                        "listing/delisting dates remain unknown without verified source evidence", "no future adjusted-series or corporate-action certification"]}
    (output / "price-coverage-summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary
