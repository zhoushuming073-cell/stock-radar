from __future__ import annotations

import sqlite3
import hashlib
import json
from typing import Any, Mapping

import pandas as pd
import pytest
import duckdb

from radar.lab.data import _market_context, load_strategy_segment, MARKET_FEATURES
from radar.lab.scanner import (LABEL_VERSION, build_labels, candidate_metrics,
                               evaluation_settings, label_candidate, target_name)
from radar.lab.scanner_worker import scan_frames
from radar.lab.store import RunStore, _json
from radar.lab.universe import LocalSecurityMaster
from radar.strategy.base import StrategyPlugin
from radar.strategy.context import StrategyContext
from radar.strategy.validation import is_future_feature
from radar.research.pipeline import FEATURE_VERSION


class ManyCandidates(StrategyPlugin):
    seen_columns: set[str] = set()

    def required_features(self) -> set[str]:
        return {"ret_1"}

    def hard_filter(self, context: StrategyContext, config: Mapping[str, Any]) -> pd.Series:
        self.seen_columns = set(context.frame)
        return pd.Series(True, index=context.frame.index)

    def score(self, context: StrategyContext, config: Mapping[str, Any]) -> pd.Series:
        return context.frame["ret_1"]

    def select(self, candidates: pd.DataFrame, config: Mapping[str, Any]) -> pd.DataFrame:
        ranked = candidates.sort_values(["strategy_score", "symbol"], ascending=[False, True])
        maximum = config["selection"]["max_candidates"]
        return ranked if maximum is None else ranked.head(maximum)

    def diagnostic_scores(self, context: StrategyContext, config: Mapping[str, Any]) -> pd.DataFrame:
        return pd.DataFrame({"support_evidence": context.frame["ret_1"] * 2,
                             "p_hit_5pct_10d": 0.5}, index=context.frame.index)


def test_golden_forward_labels_and_incomplete_horizon():
    settings = evaluation_settings(None)
    sessions = pd.bdate_range("2025-01-02", periods=11)
    bars = pd.DataFrame({"date": sessions, "symbol": "AAA", "open": 10.0,
                         "high": [10.0, 10.1, 10.2, 10.6, 10.1, 10.0, 10.0,
                                  10.0, 10.0, 10.0, 10.0],
                         "low": [9.8, 9.9, 9.6, 9.5, 8.9, 9.0, 9.0, 9.0, 9.0, 9.0, 9.0]})
    label = label_candidate(sessions[0], 9.8, bars.iloc[1:], settings)
    assert label["entry_reference_price"] == 10.0
    assert label["hit_3pct_10d"] is True
    assert label["hit_5pct_10d"] is True
    assert label["hit_8pct_10d"] is False
    assert label["time_to_5pct"] == 3
    assert label["mfe_10"] == pytest.approx(0.06)
    assert label["mae_10"] == pytest.approx(-0.11)
    assert label["new_low_after_signal"] is True
    assert label["false_falling_knife"] is True
    signal = pd.DataFrame({"signal_date": [sessions[0], sessions[1]], "symbol": "AAA"})
    labels = build_labels(signal, bars, sessions, settings)["label"].tolist()
    assert labels[0] == label
    assert labels[1] is None


def test_forward_label_censoring_reasons_and_denominators():
    sessions = pd.bdate_range("2025-01-02", periods=11)
    bars = pd.DataFrame([{"date": day, "symbol": symbol, "open": 10.,
                          "high": 10.6, "low": 9.9}
                         for day in sessions for symbol in ("OK", "GAP", "END")
                         if not (symbol == "GAP" and day == sessions[3])
                         and not (symbol == "END" and day > sessions[2])])
    signals = pd.DataFrame({"signal_date": [sessions[0]] * 4 + [sessions[1]],
                            "symbol": ["OK", "GAP", "END", "ABSENT", "OK"]})
    labels = build_labels(signals, bars, sessions, evaluation_settings(None),
                          {"END": sessions[2]})
    assert labels["label_status"].tolist() == ["labeled", "censored", "censored",
                                                "censored", "censored"]
    assert labels["label_reason"].tolist() == [None, "missing_symbol_bar",
        "security_no_longer_eligible", "missing_symbol_bar", "insufficient_future_sessions"]
    candidate = signals.iloc[:3].copy()
    for field in labels:
        candidate[field] = labels.iloc[:3][field].to_list()
    candidate["rank"] = [1, 2, 3]
    metrics = candidate_metrics(candidate, candidate, evaluation_settings(None), sessions)
    assert (metrics["candidate_observation_count"], metrics["labeled_candidate_count"],
            metrics["censored_candidate_count"]) == (3, 1, 2)
    assert metrics["candidate_censoring_rate"] == pytest.approx(2 / 3)
    assert (metrics["background_count"], metrics["labeled_background_count"],
            metrics["censored_background_count"]) == (3, 1, 2)
    assert metrics["background_censoring_rate"] == pytest.approx(2 / 3)
    assert (metrics["unique_signal_event_count"], metrics["labeled_signal_event_count"],
            metrics["censored_signal_event_count"]) == (3, 1, 2)
    assert metrics["signal_event_censoring_rate"] == pytest.approx(2 / 3)
    bad = bars.copy()
    bad.loc[(bad.symbol == "OK") & (bad.date == sessions[4]), "high"] = None
    assert build_labels(signals.iloc[[0]], bad, sessions, evaluation_settings(None)).iloc[0][
        "label_reason"] == "missing_price_data"


def test_lightweight_background_primary_outcome_matches_full_label():
    sessions = pd.bdate_range("2025-01-02", periods=3)
    bars = pd.DataFrame({"date": sessions, "symbol": "AAA", "open": 10.,
                         "high": [10., 10.6, 10.], "low": [9.9, 9.4, 9.9]})
    signals = pd.DataFrame({"signal_date": [sessions[0]], "symbol": ["AAA"]})
    for rule in ("target_touch", "target_before_adverse"):
        settings = evaluation_settings({"horizon_sessions": 2, "success_rule": rule})
        full = build_labels(signals, bars, sessions, settings).iloc[0]
        light = build_labels(signals, bars, sessions, settings, primary_only=True).iloc[0]
        assert light.label == full.label["hit_5pct_2d" if rule == "target_touch"
                                                else "up_5pct_before_down_5pct_2d"]
        assert light.label_status == full.label_status
        assert light.label_reason == full.label_reason
        candidate = signals.copy()
        candidate["rank"] = 1
        candidate["label"] = [full.label]
        background = signals.copy()
        background["label"] = [light.label]
        background["label_status"] = [light.label_status]
        metrics = candidate_metrics(candidate, background, settings, sessions)
        assert metrics["labeled_background_count"] == (1 if rule == "target_touch" else 0)
        assert metrics["censored_background_count"] == (0 if rule == "target_touch" else 1)


def test_precision_and_lift_use_full_eligible_background():
    settings = evaluation_settings(None)
    date = pd.Timestamp("2025-01-02")
    hit = {"hit_5pct_10d": True, "mfe_10": 0.08, "mae_10": -0.02,
           "false_falling_knife": False, **{f"hit_{n}pct_10d": True for n in (3, 8, 10)}}
    miss = {**hit, "hit_5pct_10d": False, "mfe_10": 0.01}
    candidates = pd.DataFrame({"signal_date": [date] * 5, "rank": [1, 2, 3, 4, 5],
                               "label": [hit, hit, hit, hit, miss]})
    background = pd.DataFrame({"signal_date": [date] * 10,
                               "label": [hit, hit, hit, hit, miss, miss, miss, miss, miss, miss]})
    metrics = candidate_metrics(candidates, background, settings)
    assert metrics["base_rate"] == pytest.approx(0.4)
    assert metrics["precision_at_5"] == pytest.approx(0.8)
    assert metrics["lift_at_5"] == pytest.approx(2.0)
    assert metrics["top_10_count"] == 5


def test_missing_top_rank_label_does_not_promote_rank_six():
    settings = evaluation_settings(None)
    hit = {"hit_5pct_10d": True, "mfe_10": .1, "mae_10": -.01,
           "false_falling_knife": False,
           **{f"hit_{n}pct_10d": True for n in (3, 8, 10)}}
    miss = {**hit, "hit_5pct_10d": False}
    day = pd.Timestamp("2025-01-02")
    candidates = pd.DataFrame({"signal_date": [day] * 6, "rank": range(1, 7),
                               "label": [None, hit, miss, hit, hit, hit]})
    background = pd.DataFrame({"label": [hit, miss]})
    metrics = candidate_metrics(candidates, background, settings)
    assert metrics["top_5_count"] == 4
    assert metrics["precision_at_5"] == pytest.approx(.75)


@pytest.mark.parametrize("maximum", [5, 10, 20, None])
def test_scanner_more_than_three_candidates_without_portfolio(maximum):
    plugin = ManyCandidates()
    sessions = pd.bdate_range("2025-01-02", periods=11)
    symbols = [f"S{i:02d}" for i in range(21)]
    first = pd.DataFrame({"date": sessions[0], "symbol": symbols,
                          "security_name": symbols, "close": 10.0,
                          "ret_1": list(range(21)), "tradability_pass": True})
    frame = first.set_index(["date", "symbol"], drop=False)
    bars = pd.DataFrame([{"date": day, "symbol": symbol, "open": 10.0,
                          "high": 10.6, "low": 9.9, "close": 10.0}
                         for day in sessions for symbol in symbols])
    rows, metrics = scan_frames(plugin, {"selection": {"max_candidates": maximum}}, frame,
                                bars, sessions, sessions[0], sessions[0],
                                evaluation_settings(None))
    assert len(rows) == 21
    assert sum(row["selected"] for row in rows) == (21 if maximum is None else maximum)
    assert rows[0]["symbol"] == "S20"
    assert rows[0]["diagnostics"]["support_evidence"] == 40
    assert rows[0]["features"] == {"close": 10.0, "ret_1": 20}
    assert rows[0]["probabilities"]["p_hit_5pct_10d"] == 0.5
    assert plugin.seen_columns == {"symbol", "security_name", "close", "ret_1"}
    assert metrics["candidate_count"] == 21
    assert metrics["precision_at_20"] == 1.0
    assert metrics["p_hit_5pct_10d_brier"] == pytest.approx(0.25)
    assert metrics["p_hit_5pct_10d_calibration_bins"][0]["count"] == 21


def test_evaluation_top_k_does_not_truncate_persisted_candidates():
    sessions = pd.bdate_range("2025-01-02", periods=11)
    symbols = [f"S{i:02d}" for i in range(12)]
    features = pd.DataFrame({"date": sessions[0], "symbol": symbols,
                             "security_name": symbols, "close": 10.,
                             "ret_1": list(range(12)), "tradability_pass": True})
    bars = pd.DataFrame([{"date": day, "symbol": symbol, "open": 10.,
                          "high": 10.6, "low": 9.9}
                         for day in sessions for symbol in symbols])
    rows_by_k = []
    for top_k in ([5], [10]):
        rows, metrics = scan_frames(
            ManyCandidates(), {"selection": {"max_candidates": None}},
            features.set_index(["date", "symbol"], drop=False), bars, sessions,
            sessions[0], sessions[0], evaluation_settings({"top_k_values": top_k}))
        rows_by_k.append(rows)
        assert metrics["candidate_count"] == 12
    assert [row["symbol"] for row in rows_by_k[0]] == [
        row["symbol"] for row in rows_by_k[1]]


def test_filter_funnel_and_exclusion_reasons_are_causal():
    class FilterCandidates(ManyCandidates):
        def hard_filter(self, context, config):
            return context.frame["ret_1"].ge(15)

        def filter_diagnostics(self, context, config):
            score = context.frame["ret_1"]
            return pd.DataFrame({"filter_pass_prior_strength": score.ge(10),
                                 "filter_pass_pullback": score.ge(15)},
                                index=context.frame.index)

    sessions = pd.bdate_range("2025-01-02", periods=11)
    symbols = [f"S{i:02d}" for i in range(21)]
    first = pd.DataFrame({"date": sessions[0], "symbol": symbols,
                          "security_name": symbols, "close": 10.0,
                          "ret_1": list(range(21)), "tradability_pass": True})
    bars = pd.DataFrame([{"date": day, "symbol": symbol, "open": 10.0,
                          "high": 10.6, "low": 9.9, "close": 10.0}
                         for day in sessions for symbol in symbols])
    rows, metrics = scan_frames(FilterCandidates(), {"selection": {"max_candidates": None}},
                                first.set_index(["date", "symbol"], drop=False),
                                bars, sessions, sessions[0], sessions[0],
                                evaluation_settings(None))
    funnel = metrics["funnel_by_day"][0]
    assert [funnel[key] for key in ("eligible_universe", "tradable", "feature_complete",
                                   "prior_strength", "pullback", "final_ranked_candidate")] == [21, 21, 21, 11, 6, 6]
    assert len(rows) == 6
    reasons = {item["symbol"]: item["stages"] for item in metrics["near_misses"]}
    assert reasons["S09"] == {"prior_strength": False, "pullback": False}
    assert reasons["S14"] == {"prior_strength": True, "pullback": False}


def test_pit_forward_label_follows_security_identity_across_ticker_change(tmp_path):
    csv = tmp_path / "security-master.csv"
    manifest = tmp_path / "security-master-manifest.json"
    pd.DataFrame([
        ["ID-1", "OLD", "2025-01-02", "2025-01-02", "2025-01-02", "", "NYSE", "common", True],
        ["ID-1", "NEW", "2025-01-03", "", "2025-01-02", "", "NYSE", "common", True],
    ], columns=["security_id", "symbol", "valid_from", "valid_to", "listing_date",
                "delisting_date", "exchange", "security_type", "eligible"]).to_csv(csv, index=False)
    manifest.write_text(json.dumps({"provider": "synthetic", "source_version": "1",
                                    "coverage_start": "2025-01-02", "coverage_end": "2025-01-03",
                                    "coverage_complete": True}), encoding="utf-8")
    provider = LocalSecurityMaster(csv, manifest)
    sessions = pd.DatetimeIndex(["2025-01-02", "2025-01-03"])
    features = pd.DataFrame({"date": [sessions[0]], "symbol": ["OLD"],
                             "security_id": ["ID-1"], "security_name": ["Example"],
                             "close": [10.0], "ret_1": [.2], "tradability_pass": [True]})
    bars = pd.DataFrame({"date": sessions, "symbol": ["OLD", "NEW"],
                         "open": [10.0, 10.0], "high": [10.0, 10.6],
                         "low": [9.9, 9.9], "close": [10.0, 10.5]})
    settings = evaluation_settings({"horizon_sessions": 1})
    rows, metrics = scan_frames(ManyCandidates(), {"selection": {"max_candidates": None}},
                                features.set_index(["date", "symbol"], drop=False),
                                bars, sessions, sessions[0], sessions[0], settings,
                                universe_provider=provider)
    assert rows[0]["security_id"] == "ID-1"
    assert rows[0]["label"]["hit_5pct_1d"] is True
    assert rows[0]["label_status"] == "labeled"
    assert metrics["base_rate"] == 1.0


def test_market_context_uses_history_through_signal_date_only():
    days = pd.bdate_range("2025-01-02", periods=80)
    original = pd.DataFrame([{"date": day, "symbol": symbol, "close": float(i + 100)}
                             for i, day in enumerate(days) for symbol in ("SPY", "QQQ")])
    breadth = pd.DataFrame({"date": days, "market_breadth": 0.6})
    first = _market_context(original, breadth)
    changed = original.copy()
    changed.loc[changed["date"] > days[65], "close"] *= 100
    second = _market_context(changed, breadth)
    columns = ["spy_trend", "qqq_trend", "spy_drawdown", "qqq_drawdown",
               "market_realized_volatility", "market_breadth"]
    pd.testing.assert_series_equal(first.loc[65, columns], second.loc[65, columns])


def test_train_market_context_warmup_is_null_not_whole_window_error(tmp_path):
    sessions = pd.bdate_range("2025-01-02", periods=70)
    bars = pd.DataFrame([{"date": day, "symbol": symbol, "open": 100.,
                          "close": 100. + index}
                         for index, day in enumerate(sessions)
                         for symbol in ("AAA", "SPY", "QQQ")])
    features = pd.DataFrame([{"date": day, "symbol": "AAA",
                              "feature_version": FEATURE_VERSION,
                              "avg_dollar_volume_20": 1e9,
                              "elasticity_score": 90., "drawdown_20": -.1,
                              "ret_1": .01, "close_location": .8,
                              "tradability_pass": True, "dist_ma_20": .1}
                             for day in sessions])
    assets = pd.DataFrame({"symbol": ["AAA"], "name": ["AAA Inc"]})
    database = tmp_path / "market.duckdb"
    with duckdb.connect(str(database)) as connection:
        connection.register("bars_input", bars)
        connection.register("features_input", features)
        connection.register("assets_input", assets)
        connection.execute("CREATE TABLE daily_bars AS SELECT * FROM bars_input")
        connection.execute("CREATE TABLE daily_features AS SELECT * FROM features_input")
        connection.execute("CREATE TABLE assets AS SELECT * FROM assets_input")
    frame = load_strategy_segment(database, sessions[0], sessions[-1], set(MARKET_FEATURES))
    assert len(frame) == len(sessions)
    assert pd.isna(frame.iloc[0]["spy_trend"])
    assert pd.notna(frame.iloc[-1]["spy_trend"])


def test_market_regime_uses_primary_outcome_not_target_touch():
    sessions = pd.bdate_range("2025-01-02", periods=11)
    features = pd.DataFrame({"date": [sessions[0]], "symbol": ["AAA"],
                             "security_name": ["Example"], "close": [10.0],
                             "ret_1": [.2], "tradability_pass": [True],
                             "spy_trend": [.1]})
    bars = pd.DataFrame({"date": sessions, "symbol": "AAA", "open": 10.0,
                         "high": [10.0] * 11, "low": [9.9] * 11,
                         "close": [10.0] * 11})
    bars.loc[1, "low"] = 9.4
    bars.loc[2, "high"] = 10.6
    settings = evaluation_settings({"success_rule": "target_before_adverse"})
    rows, metrics = scan_frames(
        ManyCandidates(), {"selection": {"max_candidates": None}},
        features.set_index(["date", "symbol"], drop=False), bars, sessions,
        sessions[0], sessions[0], settings)
    assert rows[0]["label"][metrics["primary_target"]] is True
    assert rows[0]["label"][metrics["primary_outcome"]] is False
    assert metrics["spy_above_ma20_labeled_count"] == 1
    assert metrics["spy_above_ma20_success_rate"] == 0.0


def test_scanner_outcomes_are_prohibited_plugin_inputs():
    for name in ("hit_5pct_10d", "time_to_5pct", "mfe_10", "mae_10",
                 "entry_reference_price", "new_low_after_signal", "false_falling_knife"):
        assert is_future_feature(name)
    assert not is_future_feature("p_hit_5pct_10d")
    assert target_name(.025, 10) == "hit_2p5pct_10d"


def test_completed_scanner_snapshot_is_immutable(tmp_path):
    store = RunStore(tmp_path / "runs.sqlite")
    metadata = {key: "sample" for key in ("strategy_id", "strategy_version",
                "plugin_interface_version", "config", "selection", "evaluation",
                "feature_version", "market_feature_version", "data_snapshot",
                "source_watermark", "git_revision", "signal_start", "signal_end",
                "label_version", "strategy_code_hash", "config_hash")}
    metadata["label_version"] = LABEL_VERSION
    run_id = store.create_scanner_run(metadata)
    store.start_scanner_run(run_id, 123)
    store.finish_scanner_run(run_id, [{"signal_date": "2025-01-02", "symbol": "AAA",
        "security_name": "A", "rank": 1, "strategy_score": 1.0, "selected": True,
        "diagnostics": {"x_score": 2.0}, "probabilities": {}, "label": None,
        "label_status": "censored", "label_reason": "missing_symbol_bar",
        "market_context": {}, "features": {"close": 10.0}}], {"candidate_count": 1})
    assert len(store.get_scanner_candidates(run_id)) == 1
    assert store.get_scanner_candidates(run_id)[0]["features"] == {"close": 10.0}
    assert store.get_scanner_candidates(run_id)[0]["label_reason"] == "missing_symbol_bar"
    assert store.get_scanner_run(run_id)["artifact_hashes"]["format"] == "scanner-candidates-v4"
    assert store.get_scanner_run(run_id)["artifact_hashes"]["candidates_sha256"]
    assert store.get_scanner_run(run_id)["artifact_hashes"]["candidates_sha256"] == hashlib.sha256(
        _json(store.get_scanner_candidates(run_id)).encode("utf-8")).hexdigest()
    assert store.verify_scanner_artifacts(run_id)
    with sqlite3.connect(store.path) as connection:
        with pytest.raises(sqlite3.DatabaseError, match="immutable"):
            connection.execute("UPDATE scanner_candidates SET strategy_score=2 WHERE run_id=?", (run_id,))
        with pytest.raises(sqlite3.DatabaseError, match="immutable"):
            connection.execute("UPDATE scanner_runs SET metadata_json='{}' WHERE run_id=?", (run_id,))
