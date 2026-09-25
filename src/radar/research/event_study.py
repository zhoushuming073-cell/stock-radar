"""Train/validation factor event study with chronological embargoes."""

from __future__ import annotations

from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import yaml

from radar.research.pipeline import FEATURE_VERSION, LABEL_VERSION
from radar.features.scoring import load_research_config
from radar.research.cost_sensitivity import illustrative_net_returns


FACTORS = (
    "drawdown_20", "drawdown_60", "ret_20", "ret_60", "atr_pct_20",
    "lower_wick_ratio", "close_location", "volume_contraction",
    "decline_acceleration", "rebound_from_low_5", "elasticity_score",
)
OUTCOMES = (
    "return_close_1d", "return_close_3d", "return_close_5d", "return_close_10d",
    "mfe_high_5d", "mfe_high_10d", "mae_low_5d", "mae_low_10d",
)
ELASTICITY_RAW = (
    "elasticity_beta_raw", "elasticity_atr_raw", "elasticity_idio_raw",
    "elasticity_burst_raw", "elasticity_hit_raw", "hit_5_rate", "hit_10_rate",
)


def _boundaries(sessions: list, cfg: dict) -> tuple[int, int, int]:
    n = len(sessions)
    train_end = int(n * cfg["train_fraction"])
    validation_end = int(n * (cfg["train_fraction"] + cfg["validation_fraction"]))
    embargo = int(cfg["embargo_sessions"])
    if embargo < int(cfg["max_forward_sessions"]):
        raise ValueError("embargo must cover the longest forward label")
    if train_end <= embargo or validation_end - train_end <= 2 * embargo:
        raise ValueError("not enough sessions for purged chronological study")
    return train_end, validation_end, embargo


def _summary(group: pd.DataFrame, cost_config: dict) -> dict:
    result = {"sample_count": int(len(group))}
    for name in OUTCOMES:
        series = group[name].dropna()
        result[f"{name}_n"] = int(len(series))
        result[f"{name}_mean"] = series.mean() if len(series) else np.nan
        result[f"{name}_median"] = series.median() if len(series) else np.nan
    for horizon in (5, 10):
        series = group[f"return_close_{horizon}d"].dropna()
        result[f"abs_return_close_{horizon}d_mean"] = series.abs().mean() if len(series) else np.nan
    for threshold in (0.05, 0.10):
        for horizon in (5, 10):
            series = group[f"mfe_high_{horizon}d"].dropna()
            result[f"p_mfe_{horizon}d_ge_{int(threshold*100)}pct"] = (
                series.ge(threshold).mean() if len(series) else np.nan
            )
    for horizon in (5, 10):
        for kind in ("tp", "sl"):
            series = group[f"exec_hit_{kind}_{horizon}d"].dropna()
            result[f"p_exec_{kind}_{horizon}d"] = series.astype(float).mean() if len(series) else np.nan
    result["median_executable_gross_return"] = group["simulated_gross_return"].median()
    gross = group["simulated_gross_return"].dropna()
    for bps in (0, 5, 10, 20):
        slip = bps / 10_000
        net = (1 + gross) * (1 - slip) / (1 + slip) - 1
        result[f"median_return_slippage_{bps}bps_per_side_no_fees"] = net.median() if len(net) else np.nan
        if len(group):
            net_with_fees = illustrative_net_returns(
                group["entry_open"], group["simulated_exit_price"],
                cost_config, slippage_bps=bps)
            result[f"median_net_fees_slippage_{bps}bps_per_side"] = net_with_fees.median()
            result[f"p_net_positive_fees_slippage_{bps}bps_per_side"] = (
                net_with_fees.dropna().gt(0).mean() if net_with_fees.notna().any() else np.nan)
        else:
            result[f"median_net_fees_slippage_{bps}bps_per_side"] = np.nan
            result[f"p_net_positive_fees_slippage_{bps}bps_per_side"] = np.nan
    for name in ELASTICITY_RAW:
        if name in group:
            result[f"{name}_median"] = group[name].median()
    return result


def run_factor_event_study(database: Path, config_path: Path, output_dir: Path) -> dict:
    all_config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config = all_config["research"]
    cost_config = all_config["illustrative_costs"]
    gate = load_research_config(config_path)
    conn = duckdb.connect(str(database), read_only=True)
    try:
        sessions = [r[0] for r in conn.execute(
            "SELECT date FROM daily_bars WHERE symbol='SPY' ORDER BY date"
        ).fetchall()]
        train_end, validation_end, embargo = _boundaries(sessions, config)
        selected = [*FACTORS, *OUTCOMES,
                    "exec_hit_tp_5d", "exec_hit_tp_10d", "exec_hit_sl_5d", "exec_hit_sl_10d",
                    "simulated_gross_return", "entry_open", "simulated_exit_price"]
        feature_cols = ", ".join(f"f.{name}" for name in (*FACTORS, *ELASTICITY_RAW))
        label_cols = ", ".join(f"l.{name}" for name in selected if name not in FACTORS)
        data = conn.execute(f"""
            SELECT f.symbol, f.date, b.close, f.avg_dollar_volume_20,
                   a.tradable, a.exchange, a.name AS security_name, {feature_cols}, {label_cols}
            FROM daily_features f
            JOIN forward_labels l ON f.symbol=l.symbol AND f.date=l.signal_date
            JOIN daily_bars b ON f.symbol=b.symbol AND f.date=b.date
            JOIN assets a ON f.symbol=a.symbol
            WHERE f.feature_version=? AND l.label_version=? AND f.date<=?
              AND f.symbol NOT IN ('SPY','QQQ')
        """, [FEATURE_VERSION, LABEL_VERSION, sessions[validation_end - embargo - 1]]).df()
    finally:
        conn.close()
    dates = pd.to_datetime(data["date"]).dt.date
    train = data.loc[dates <= sessions[train_end - embargo - 1]].copy()
    validation = data.loc[(dates >= sessions[train_end + embargo]) &
                          (dates <= sessions[validation_end - embargo - 1])].copy()
    # Current asset metadata creates survivorship bias, so both sets are
    # described as current-snapshot universe rather than point-in-time.
    def liquid(frame: pd.DataFrame) -> pd.DataFrame:
        return frame.loc[
            frame["close"].ge(gate.min_price)
            & frame["avg_dollar_volume_20"].ge(gate.min_avg_dollar_volume_20)
            & frame["tradable"].eq(True)
            & frame["exchange"].astype("string").str.upper().isin(("NYSE", "NASDAQ", "AMEX", "ARCA", "BATS"))
        ].copy()
    train, validation = liquid(train), liquid(validation)
    rows: list[dict] = []
    for factor in FACTORS:
        train_values = train[factor].dropna()
        if len(train_values) < 100:
            continue
        edges = np.unique(np.quantile(train_values, [0, .2, .4, .6, .8, 1]))
        if len(edges) < 3:
            continue
        edges[0], edges[-1] = -np.inf, np.inf
        for split, frame in (("train", train), ("validation", validation)):
            bucket = pd.cut(frame[factor], bins=edges, labels=False, include_lowest=True)
            for band, group in frame.groupby(bucket, observed=True):
                rows.append({"factor": factor, "split": split, "bucket": int(band) + 1,
                             "bucket_low": edges[int(band)], "bucket_high": edges[int(band) + 1],
                             **_summary(group, cost_config)})
    result = pd.DataFrame(rows)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "strategy2_factor_study.csv"
    result.to_csv(path, index=False)
    # These are exploratory slices, not trading rules. Thresholds are learned
    # from Train alone, then applied unchanged to Validation.
    thresholds = {
        "elastic_top20": train["elasticity_score"].quantile(.8),
        "drawdown_bottom20": train["drawdown_20"].quantile(.2),
        "prior_strength_top40": train["ret_60"].quantile(.6),
        "lower_wick_top40": train["lower_wick_ratio"].quantile(.6),
    }
    interaction_rows: list[dict] = []
    for split, frame in (("train", train), ("validation", validation)):
        elastic = frame["elasticity_score"].ge(thresholds["elastic_top20"])
        drawdown = frame["drawdown_20"].le(thresholds["drawdown_bottom20"])
        prior = frame["ret_60"].ge(thresholds["prior_strength_top40"])
        wick = frame["lower_wick_ratio"].ge(thresholds["lower_wick_top40"])
        slices = {
            "eligible_baseline": pd.Series(True, index=frame.index),
            "elastic_top20": elastic,
            "drawdown_bottom20": drawdown,
            "elastic_and_drawdown": elastic & drawdown,
            "elastic_drawdown_prior": elastic & drawdown & prior,
            "elastic_drawdown_wick": elastic & drawdown & wick,
        }
        for name, mask in slices.items():
            interaction_rows.append({"split": split, "slice": name, **_summary(frame.loc[mask], cost_config)})
    interaction_path = output_dir / "strategy2_interaction_study.csv"
    pd.DataFrame(interaction_rows).to_csv(interaction_path, index=False)
    elasticity_rows = []
    for split, frame in (("train", train), ("validation", validation)):
        score = frame["elasticity_score"]
        bands = {
            "top_5": score.ge(95), "top_10": score.ge(90),
            "top_15": score.ge(85), "top_20": score.ge(80),
            "p60_80": score.ge(60) & score.lt(80),
            "p40_60": score.ge(40) & score.lt(60),
            "p20_40": score.ge(20) & score.lt(40),
            "bottom_20": score.lt(20),
        }
        for name, mask in bands.items():
            elasticity_rows.append({"split": split, "band": name, **_summary(frame.loc[mask], cost_config)})
    elasticity_path = output_dir / "elasticity_distribution.csv"
    pd.DataFrame(elasticity_rows).to_csv(elasticity_path, index=False)
    proxy_rows = []
    proxy_counts = {}
    for split, frame in (("train", train), ("validation", validation)):
        # Name matching only tests sensitivity; it is not a security master.
        explicit_fund_name = frame["security_name"].astype("string").str.contains(
            r"\bETF\b|\bETN\b|exchange.traded", case=False, regex=True, na=False)
        stock_proxy = frame.loc[~explicit_fund_name]
        proxy_counts[split] = len(stock_proxy)
        score = stock_proxy["elasticity_score"]
        bands = {"eligible_proxy_baseline": pd.Series(True, index=stock_proxy.index),
                 "elastic_top20": score.ge(80), "elastic_bottom20": score.lt(20),
                 "elastic_and_drawdown": score.ge(thresholds["elastic_top20"]) &
                 stock_proxy["drawdown_20"].le(thresholds["drawdown_bottom20"])}
        for name, mask in bands.items():
            proxy_rows.append({"split": split, "slice": name,
                               **_summary(stock_proxy.loc[mask], cost_config)})
    proxy_path = output_dir / "security_name_proxy_sensitivity.csv"
    pd.DataFrame(proxy_rows).to_csv(proxy_path, index=False)
    corr_path = output_dir / "factor_spearman_train.csv"
    train[list(FACTORS)].corr(method="spearman").to_csv(corr_path)
    metadata = {
        "sessions": len(sessions), "train_start": str(sessions[0]),
        "train_end_usable": str(sessions[train_end - embargo - 1]),
        "validation_start_usable": str(sessions[train_end + embargo]),
        "validation_end_usable": str(sessions[validation_end - embargo - 1]),
        "test_start": str(sessions[validation_end]), "test_end": str(sessions[-1]),
        "train_rows_after_gate": len(train), "validation_rows_after_gate": len(validation),
        "factors_studied": int(result["factor"].nunique()) if not result.empty else 0,
        "output": str(path), "interaction_output": str(interaction_path),
        "elasticity_output": str(elasticity_path), "correlation_output": str(corr_path),
        "security_name_proxy_output": str(proxy_path),
        "security_name_proxy_rows": proxy_counts,
        "exploratory_train_thresholds": {key: float(value) for key, value in thresholds.items()},
        "illustrative_cost_profile": cost_config["profile"],
        "illustrative_order_notional_usd": cost_config["order_notional_usd"],
        "limitations": [
            "current-snapshot assets introduce survivorship bias",
            "ETF/ETN exclusion by name is an incomplete classification proxy",
            "factor events overlap in time and are descriptive, not independent observations",
            "execution labels are gross; separate cost columns model fees and slippage",
            "fee profile is illustrative and the user's actual plan is unconfirmed",
            "final test period was not read into the event study",
        ],
    }
    (output_dir / "strategy2_factor_study_metadata.yaml").write_text(
        yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    return metadata
