"""DuckDB schema for the Phase 1 data foundation.

All timestamps are UTC instants stored as TIMESTAMPTZ. Future db.py upserts
should retain an asset's earliest first_seen and latest last_seen, and accept
mutable attributes only from an equal or newer observation. A daily bar may be
replaced only by a newer download with the same provider, feed and adjustment;
a provenance mismatch must raise an error rather than silently mixing series.
"""

from __future__ import annotations

import duckdb

SCHEMA_VERSION = 1
RESEARCH_SCHEMA_VERSION = 3

EXPECTED_COLUMNS = {
    "assets": {
        "symbol": "VARCHAR",
        "name": "VARCHAR",
        "exchange": "VARCHAR",
        "asset_class": "VARCHAR",
        "status": "VARCHAR",
        "tradable": "BOOLEAN",
        "fractionable": "BOOLEAN",
        "shortable": "BOOLEAN",
        "easy_to_borrow": "BOOLEAN",
        "first_seen": "TIMESTAMP WITH TIME ZONE",
        "last_seen": "TIMESTAMP WITH TIME ZONE",
        "updated_at": "TIMESTAMP WITH TIME ZONE",
    },
    "daily_bars": {
        "symbol": "VARCHAR",
        "date": "DATE",
        "open": "DOUBLE",
        "high": "DOUBLE",
        "low": "DOUBLE",
        "close": "DOUBLE",
        "volume": "BIGINT",
        "vwap": "DOUBLE",
        "trade_count": "BIGINT",
        "provider": "VARCHAR",
        "feed": "VARCHAR",
        "adjustment": "VARCHAR",
        "downloaded_at": "TIMESTAMP WITH TIME ZONE",
    },
}


def _check_existing_columns(connection: duckdb.DuckDBPyConnection, table: str) -> None:
    rows = connection.execute(f"PRAGMA table_info('{table}')").fetchall()
    actual = {row[1]: row[2] for row in rows}
    expected = EXPECTED_COLUMNS[table]
    mismatches = {
        name: (kind, actual.get(name))
        for name, kind in expected.items()
        if actual.get(name) != kind
    }
    if mismatches:
        raise ValueError(f"{table} has missing or incompatible columns: {mismatches}")
    primary_key = {row[1] for row in rows if row[5]}
    required_key = {"symbol"} if table == "assets" else {"symbol", "date"}
    if primary_key != required_key:
        raise ValueError(f"{table} has incompatible primary key: {primary_key}")


def ensure_schema(connection: duckdb.DuckDBPyConnection) -> None:
    """Create version 1 atomically; repeated calls preserve existing rows."""
    connection.execute("BEGIN TRANSACTION")
    try:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS assets (
                symbol VARCHAR PRIMARY KEY,
                name VARCHAR, exchange VARCHAR, asset_class VARCHAR,
                status VARCHAR, tradable BOOLEAN, fractionable BOOLEAN,
                shortable BOOLEAN, easy_to_borrow BOOLEAN,
                first_seen TIMESTAMPTZ, last_seen TIMESTAMPTZ,
                updated_at TIMESTAMPTZ
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_bars (
                symbol VARCHAR, date DATE,
                open DOUBLE, high DOUBLE, low DOUBLE, close DOUBLE,
                volume BIGINT, vwap DOUBLE, trade_count BIGINT,
                provider VARCHAR, feed VARCHAR, adjustment VARCHAR,
                downloaded_at TIMESTAMPTZ,
                PRIMARY KEY (symbol, date)
            )
            """
        )
        for table in EXPECTED_COLUMNS:
            _check_existing_columns(connection, table)
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL
            )
            """
        )
        connection.execute(
            "INSERT INTO schema_migrations VALUES (?, current_timestamp) ON CONFLICT DO NOTHING",
            [SCHEMA_VERSION],
        )
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise


# Phase 2 tables live only in a research database until their calculations are
# validated. Raw daily_bars keeps its original meaning and primary key.
STRATEGY2_EXTRA_COLUMNS = {
    name: "DOUBLE" for name in (
        "ma20_slope_5", "ma50_slope_5", "relative_strength_spy_20",
        "relative_strength_qqq_20", "pullback_days_20", "red_day_count_5",
        "red_day_count_10", "max_single_day_loss_10", "atr_normalized_drawdown_20",
        "range_3_over_10", "new_low_frequency_10",
    )
}
STRATEGY2_EXTRA_COLUMNS.update({"reclaim_ma_5": "BOOLEAN", "reclaim_ma_10": "BOOLEAN"})

RESEARCH_COLUMNS = {
    "daily_features": {
        "symbol": "VARCHAR", "date": "DATE", "feature_version": "VARCHAR",
        **{name: "DOUBLE" for name in (
            "ret_1", "ret_3", "ret_5", "ret_20", "ret_40", "ret_60",
            "ma_5", "ma_10", "ma_20", "ma_50",
            "dist_ma_5", "dist_ma_10", "dist_ma_20", "dist_ma_50",
            "atr_14", "atr_20", "atr_pct_14", "atr_pct_20",
            "realized_vol_20", "realized_vol_60",
            "beta_spy_60", "beta_spy_126", "beta_qqq_60", "beta_qqq_126",
            "idio_vol_spy_60", "idio_vol_qqq_60",
            "avg_volume_20", "avg_dollar_volume_20",
            "high_20", "high_60", "low_20", "low_60",
            "drawdown_20", "drawdown_60", "rebound_from_low_5", "rebound_from_low_10",
            "body_pct", "lower_wick_ratio", "upper_wick_ratio", "close_location", "range_pct",
            "red_body_avg_3", "red_body_avg_5", "decline_speed_3",
            "decline_speed_prev_3", "decline_acceleration", "atr_contraction",
            "range_contraction", "volume_contraction", "down_volume_ratio",
            "new_low_frequency_5", "early_reversal_score_raw", "not_extended_score_raw",
            "burst_p75_5d", "hit_5_rate", "hit_10_rate",
            "elasticity_beta_raw", "elasticity_atr_raw", "elasticity_idio_raw",
            "elasticity_burst_raw", "elasticity_hit_raw",
            "elasticity_beta_component", "elasticity_atr_component",
            "elasticity_idio_component", "elasticity_burst_component",
            "elasticity_hit_component", "elasticity_score",
        )},
        "failed_breakdown": "BOOLEAN", "support_reclaim": "BOOLEAN",
        "higher_low_proxy": "BOOLEAN", "tradability_pass": "BOOLEAN",
        **STRATEGY2_EXTRA_COLUMNS,
        "computed_at": "TIMESTAMP WITH TIME ZONE",
    },
    "forward_labels": {
        "symbol": "VARCHAR", "signal_date": "DATE", "label_version": "VARCHAR",
        "entry_date": "DATE", "entry_open": "DOUBLE",
        **{name: "DOUBLE" for name in (
            "return_close_1d", "return_close_3d", "return_close_5d", "return_close_10d",
            "mfe_high_5d", "mfe_high_10d", "mae_low_5d", "mae_low_10d",
            "simulated_exit_price", "simulated_gross_return",
        )},
        **{name: "BOOLEAN" for name in (
            "exec_hit_tp_5d", "exec_hit_tp_10d", "exec_hit_sl_5d", "exec_hit_sl_10d",
        )},
        "simulated_exit_date": "DATE", "simulated_exit_reason": "VARCHAR",
    },
    "research_runs": {
        "run_id": "VARCHAR", "created_at": "TIMESTAMP WITH TIME ZONE",
        "git_commit": "VARCHAR", "data_snapshot": "TIMESTAMP WITH TIME ZONE",
        "provider": "VARCHAR", "feed": "VARCHAR", "adjustment": "VARCHAR",
        "feature_version": "VARCHAR", "label_version": "VARCHAR",
        "config_hash": "VARCHAR", "train_start": "DATE", "train_end": "DATE",
        "validation_start": "DATE", "validation_end": "DATE",
        "test_start": "DATE", "test_end": "DATE", "status": "VARCHAR",
    },
}

RESEARCH_KEYS = {
    "daily_features": ("symbol", "date", "feature_version"),
    "forward_labels": ("symbol", "signal_date", "label_version"),
    "research_runs": ("run_id",),
}


def ensure_research_schema(connection: duckdb.DuckDBPyConnection) -> None:
    """Apply Phase 2 research tables atomically without changing raw-bar semantics."""
    ensure_schema(connection)
    connection.execute("BEGIN TRANSACTION")
    try:
        for table, columns in RESEARCH_COLUMNS.items():
            definitions = ", ".join(f"{name} {kind}" for name, kind in columns.items())
            key = ", ".join(RESEARCH_KEYS[table])
            connection.execute(
                f"CREATE TABLE IF NOT EXISTS {table} ({definitions}, PRIMARY KEY ({key}))"
            )
            rows = connection.execute(f"PRAGMA table_info('{table}')").fetchall()
            actual = {row[1]: row[2] for row in rows}
            if table == "daily_features":
                for name, kind in STRATEGY2_EXTRA_COLUMNS.items():
                    if name not in actual:
                        connection.execute(f"ALTER TABLE daily_features ADD COLUMN {name} {kind}")
                rows = connection.execute(f"PRAGMA table_info('{table}')").fetchall()
                actual = {row[1]: row[2] for row in rows}
            mismatches = {
                name: (kind, actual.get(name))
                for name, kind in columns.items() if actual.get(name) != kind
            }
            if mismatches:
                raise ValueError(f"{table} has missing or incompatible columns: {mismatches}")
            primary_key = {row[1] for row in rows if row[5]}
            if primary_key != set(RESEARCH_KEYS[table]):
                raise ValueError(f"{table} has incompatible primary key: {primary_key}")
        for version in (2, RESEARCH_SCHEMA_VERSION):
            connection.execute(
                "INSERT INTO schema_migrations VALUES (?, current_timestamp) ON CONFLICT DO NOTHING",
                [version],
            )
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise
