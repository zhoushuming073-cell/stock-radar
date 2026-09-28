from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from radar.lab.parameters import (execution_defaults_from_legacy, research_hash,
                                  resolve_config, validate_execution)
from radar.lab.scanner import (before_adverse_name, candidate_metrics, evaluation_settings,
                               label_candidate, signal_event_flags)
from radar.lab.schema import parameter_schema
from radar.lab.universe import LocalSecurityMaster


def _resolved():
    execution = execution_defaults_from_legacy({}, slippage_bps=10,
                                               execution_timing="next_open")
    return resolve_config(
        strategy_defaults={"min_pullback": .08, "max_new": 3,
                           "exit": {"stop_loss": -.10}},
        strategy_draft={"min_pullback": .12, "max_new": 3,
                        "exit": {"stop_loss": None}},
        evaluation_defaults=evaluation_settings(None),
        execution_defaults=execution,
        dataset={"split": "train", "universe_mode": "current_snapshot",
                 "universe_fingerprint": None},
        execution_overrides={"max_new_positions_per_day": 5},
    )


def test_resolved_sources_hash_and_nullable_exit():
    run = _resolved()
    assert run.values["strategy"]["min_pullback"] == .12
    assert run.sources["strategy.min_pullback"] == "run_override"
    assert run.values["execution"]["exit"]["stop_loss"] is None
    assert run.sources["execution.exit.stop_loss"] == "run_override"
    assert run.values["execution"]["max_new_positions_per_day"] == 5
    assert run.sources["execution.max_new_positions_per_day"] == "run_override"
    assert run.sources["execution.sizing.method"] == "host_default"
    assert research_hash({**run.values, "view": {"display_top_k": 5}}) == research_hash(
        {**run.values, "view": {"display_top_k": 20}})
    with pytest.raises(ValueError, match="namespace"):
        research_hash({**run.values, "misc": {}})


def test_invalid_execution_override_caught_before_queue():
    policy = execution_defaults_from_legacy({}, slippage_bps=10,
                                            execution_timing="next_open")
    policy["sizing"]["method"] = "unknown"
    with pytest.raises(ValueError, match="sizing.method"):
        validate_execution(policy)


def test_semantic_schema_has_core_advanced_and_explicit_paths():
    schema = parameter_schema("full_strategy2_v1", {"min_pullback": .08},
                              evaluation_settings(None),
                              execution_defaults_from_legacy({}, slippage_bps=10,
                                                             execution_timing="next_open"))
    by_path = {item["path"]: item for item in schema}
    assert len(by_path) == len(schema)
    assert by_path["strategy.min_pullback"]["default"] == .08
    assert by_path["strategy.min_pullback"]["level"] == "core"
    assert by_path["strategy.selection.max_candidates"]["nullable"] is True
    assert by_path["evaluation.top_k_values"]["modes"] == ["scanner"]
    assert by_path["evaluation.primary_adverse_target"]["modes"] == ["scanner"]
    assert by_path["execution.liquidity.max_adv_participation"]["min"] > 0
    assert by_path["execution.exit.stop_loss"]["modes"] == ["backtest"]
    assert all({"path", "label", "description", "namespace", "type", "unit", "default",
                "min", "max", "step", "nullable", "level", "modes", "searchable"} <= set(item)
               for item in schema)
    assert parameter_schema("unregistered_plugin", {"random_value": 5}, {}, {}) == []


def test_target_before_adverse_and_same_session_ambiguity():
    settings = evaluation_settings({"horizon_sessions": 2, "upside_targets": [.05],
                                    "downside_targets": [-.05], "primary_target": .05,
                                    "top_k_values": [5]})
    future = pd.DataFrame({"open": [10, 10], "high": [10.1, 10.6],
                           "low": [9.4, 9.8]})
    label = label_candidate(pd.Timestamp("2025-01-01"), 9.5, future, settings)
    name = before_adverse_name(.05, -.05, 2)
    assert label["hit_5pct_2d"] is True
    assert label["hit_minus_5pct_2d"] is True
    assert label[name] is False
    assert label["time_to_5pct"] == 2
    future.loc[0, "high"] = 10.6
    label = label_candidate(pd.Timestamp("2025-01-01"), 9.5, future, settings)
    assert label[name] is None
    assert label["ambiguous_same_session"] is True


def test_primary_adverse_pair_is_explicit_and_hashed():
    settings = evaluation_settings({"primary_target": .07,
                                    "upside_targets": [.05, .07],
                                    "primary_adverse_target": -.05,
                                    "success_rule": "target_before_adverse"})
    metrics = candidate_metrics(pd.DataFrame({"label": [], "rank": []}),
                                pd.DataFrame({"label": []}), settings)
    assert metrics["primary_outcome"] == before_adverse_name(.07, -.05, 10)
    assert metrics["primary_outcome"] != before_adverse_name(.07, -.08, 10)
    other = evaluation_settings({**settings, "primary_adverse_target": -.08})
    original = _resolved().values
    assert research_hash({**original, "evaluation": settings}) != research_hash(
        {**original, "evaluation": other})
    for override in ({"primary_adverse_target": -.07},
                     {"primary_adverse_target": .05},
                     {"downside_targets": [-.03], "primary_adverse_target": -.05}):
        with pytest.raises(ValueError, match="primary_adverse_target"):
            evaluation_settings(override)
    with pytest.raises(ValueError, match="primary_target"):
        evaluation_settings({"primary_target": .07})


def test_current_plugin_spec_uses_scanner_v2():
    spec = (Path(__file__).parents[1] / "docs" / "STRATEGY_PLUGIN_SPEC.md").read_text(
        encoding="utf-8")
    assert "scanner-forward-v2" in spec
    assert "scanner-forward-v1" not in spec


def test_event_cooldown_preserves_observations():
    dates = pd.bdate_range("2025-01-02", periods=8)
    candidates = pd.DataFrame({"signal_date": [dates[i] for i in (0, 1, 4, 5)],
                               "symbol": ["AAA"] * 4})
    assert signal_event_flags(candidates, 5, dates) == [True, False, False, True]
    settings = evaluation_settings(None)
    label = {"hit_5pct_10d": True, "mfe_10": .1, "mae_10": -.01,
             "false_falling_knife": False,
             **{f"hit_{n}pct_10d": True for n in (3, 8, 10)}}
    candidates["rank"] = 1
    candidates["label"] = [label] * 4
    metrics = candidate_metrics(candidates, candidates, settings, dates)
    assert metrics["candidate_observation_count"] == 4
    assert metrics["unique_signal_event_count"] == 2
    assert metrics["event_top_5_count"] == 2
    assert metrics["event_precision_at_5"] == 1.0


def test_event_precision_and_lift_exclude_cooldown_repeats():
    dates = pd.bdate_range("2025-01-02", periods=6)
    hit = {"hit_5pct_10d": True, "mfe_10": .1, "mae_10": -.01,
           "false_falling_knife": False,
           **{f"hit_{n}pct_10d": True for n in (3, 8, 10)}}
    miss = {**hit, "hit_5pct_10d": False}
    candidates = pd.DataFrame({
        "signal_date": [dates[0], dates[1], dates[1]],
        "symbol": ["AAA", "AAA", "BBB"], "rank": [1, 1, 2],
        "label": [miss, hit, hit],
    })
    settings = evaluation_settings({"event_cooldown_sessions": 5})
    metrics = candidate_metrics(candidates, candidates, settings, dates)
    assert metrics["precision_at_5"] == pytest.approx(2 / 3)
    assert metrics["event_top_5_count"] == 2
    assert metrics["event_precision_at_5"] == pytest.approx(.5)
    assert metrics["event_lift_at_5"] == pytest.approx(.75)
    renamed = candidates.iloc[:2].copy()
    renamed["symbol"] = ["OLD", "NEW"]
    renamed["security_id"] = ["ID-1", "ID-1"]
    assert signal_event_flags(renamed, 5, dates) == [True, False]


def test_pit_listing_delisting_ticker_change_reuse_and_gap(tmp_path):
    frame = pd.DataFrame([
        ["1", "AAA", "2025-01-02", "2025-01-06", "2025-01-02", "2025-01-08", "NYSE", "common", True],
        ["1", "BBB", "2025-01-07", "2025-01-08", "2025-01-02", "2025-01-08", "NYSE", "common", True],
        ["2", "AAA", "2025-01-09", "", "2025-01-09", "", "NYSE", "common", True],
    ], columns=["security_id", "symbol", "valid_from", "valid_to", "listing_date",
                "delisting_date", "exchange", "security_type", "eligible"])
    csv_path = tmp_path / "security-master.csv"
    manifest_path = tmp_path / "security-master-manifest.json"
    frame.to_csv(csv_path, index=False)
    manifest_path.write_text(json.dumps({"provider": "synthetic fixture", "source_version": "1",
                                         "coverage_start": "2025-01-01", "coverage_end": "2025-01-10",
                                         "coverage_complete": True}), encoding="utf-8")
    provider = LocalSecurityMaster(csv_path, manifest_path)
    assert provider.eligible_on(pd.Timestamp("2025-01-03"))["security_id"].tolist() == ["1"]
    assert provider.eligible_on(pd.Timestamp("2025-01-07"))["symbol"].tolist() == ["BBB"]
    assert provider.eligible_on(pd.Timestamp("2025-01-09"))["security_id"].tolist() == ["2"]
    assert provider.eligible_on(pd.Timestamp("2025-01-10"))["security_id"].tolist() == ["2"]
    assert provider.eligible_on(pd.Timestamp("2025-01-01")).empty
    assert "1" not in provider.eligible_on(pd.Timestamp("2025-01-09"))["security_id"].tolist()
    prices = pd.DataFrame({"date": pd.to_datetime(["2025-01-03", "2025-01-07", "2025-01-09"]),
                           "symbol": ["AAA", "BBB", "AAA"], "close": [10, 11, 12],
                           "security_name": ["present-day name"] * 3})
    filtered = provider.filter_frame(prices)
    assert filtered["security_id"].tolist() == ["1", "1", "2"]
    assert filtered["security_name"].tolist() == ["AAA", "BBB", "AAA"]
    with pytest.raises(ValueError, match="gap"):
        provider.validate_coverage([pd.Timestamp("2025-01-01")])
