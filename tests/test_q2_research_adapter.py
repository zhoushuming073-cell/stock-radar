"""Q2 v1.3 causal host capability and import contract, without portfolio outcomes."""
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import zipfile

import pandas as pd
import pytest

from radar.lab.data import available_features
from radar.lab.manager import RunManager
from radar.lab.research_backend import FEATURES, ResearchHistory, load_signal_frame
from radar.lab.research_adapter import ResearchStrategyContext, evaluate_research_selection
from radar.lab.universe import load_universe
from radar.strategy.context import StrategyContext
from radar.strategy.loader import load_strategy_directory


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates/q2_relaxed_channel_v1_3"
FILES = ("manifest.yaml", "strategy.yaml", "strategy.py", "README.md",
         "tests/test_strategy.py")


def _installed_data():
    profile = json.loads((ROOT / "config/research_infrastructure_v1.json").read_text(encoding="utf-8"))
    if not (ROOT / profile["core_directory"] / "shape.duckdb").exists():
        pytest.skip("frozen local Research Infrastructure v1 data unavailable")


def _registration():
    return load_strategy_directory(
        TEMPLATE, available_features(ROOT / "data/phase2-research.duckdb") | FEATURES)


def test_history_is_clipped_defensive_and_missing_is_explicit():
    _installed_data()
    frame = load_signal_frame(ROOT, pd.Timestamp("2024-10-01"), pd.Timestamp("2024-10-01"))
    target = frame.loc[frame.market_input_safe].iloc[0]
    with ResearchHistory(ROOT) as host:
        bars = host.history(target.security_id, pd.Timestamp("2024-10-01"), 430)
        assert bars.attrs["backend"] == "research_infrastructure_v1"
        assert bars.date.max() == pd.Timestamp("2024-10-01")
        assert len(bars) <= 430
        original = host.history(target.security_id, pd.Timestamp("2024-10-01"), 430)
        bars.loc[bars.index[-1], "close"] = 999999
        pd.testing.assert_frame_equal(original, host.history(target.security_id, pd.Timestamp("2024-10-01"), 430))
        assert host.benchmark("SPY", pd.Timestamp("2024-10-01")).date.max() <= pd.Timestamp("2024-10-01")
        assert host.benchmark("QQQ", pd.Timestamp("2024-10-01")).date.max() <= pd.Timestamp("2024-10-01")
        with pytest.raises(ValueError):
            host.history("not-a-security", pd.Timestamp("2024-10-01"))
        with pytest.raises(ValueError):
            host.history(target.security_id, pd.Timestamp("2026-09-29"))


def test_context_rejects_post_t_and_old_plugin_needs_no_history():
    frame = pd.DataFrame({"symbol": ["A"], "security_name": ["A"], "close": [10.],
                          "security_id": ["id"]})
    context = StrategyContext(pd.Timestamp("2024-10-01"), frame)
    with pytest.raises(AttributeError):
        context.history("id")
    future = pd.DataFrame({"date": [pd.Timestamp("2024-10-02")], "close": [11.]})
    with pytest.raises(ValueError, match="post-signal"):
        ResearchStrategyContext(pd.Timestamp("2024-10-01"), frame,
                                lambda *_: future).history("id")


def test_dated_membership_and_historical_disappeared_id():
    _installed_data()
    with ResearchHistory(ROOT) as host:
        row = host.api.core.connection.execute("""SELECT i.security_id,i.decision_date
            FROM universe_window_index i JOIN population p
            ON i.security_id=p.security_id AND i.decision_date=p.date
            WHERE i.length=126 AND i.supported_membership
              AND p.valid_to<DATE '2026-09-29'
            ORDER BY i.decision_date LIMIT 1""").fetchone()
        assert row is not None
        historical = host.api.universe_on(row[1], 126)
        assert row[0] in set(historical.security_id)
        # Neither current listing files nor ticker aliases are consulted.
        assert host.history(row[0], pd.Timestamp(row[1]), 126).date.max() == pd.Timestamp(row[1])


def test_research_universe_does_not_consult_current_snapshot(monkeypatch):
    _installed_data()
    def forbidden():
        raise AssertionError("current survivor universe was consulted")
    monkeypatch.setattr("radar.lab.universe.current_snapshot_provenance", forbidden)
    provider, provenance = load_universe(ROOT, "research_infrastructure_v1",
                                         [pd.Timestamp("2024-10-01")])
    assert provider is None
    assert provenance.provider == "shape_research_universe_v1"


def test_nonempty_and_empty_selection_with_real_history():
    _installed_data()
    registration = _registration()
    frame = load_signal_frame(ROOT, pd.Timestamp("2024-10-01"), pd.Timestamp("2024-10-01"))
    with ResearchHistory(ROOT) as host:
        ranked, selected = evaluate_research_selection(registration.plugin, registration.config,
                                                       frame, host.history)
        assert 0 < len(selected) <= 10
        again, same = evaluate_research_selection(registration.plugin, registration.config,
                                                  frame, host.history)
        pd.testing.assert_frame_equal(ranked, again)
        pd.testing.assert_frame_equal(selected, same)
        empty = frame.loc[frame.beta_spy_126.lt(2) & frame.market_input_safe].head(20)
        _, none = evaluate_research_selection(registration.plugin, registration.config,
                                              empty, host.history)
        assert none.empty


def test_zip_import_through_real_lab_manager(tmp_path):
    zip_path = tmp_path / "q2_v13_relaxed_channel_plugin.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for relative in FILES:
            archive.write(TEMPLATE / relative, f"q2_relaxed_channel_v1_3/{relative}")
    with TemporaryDirectory(prefix="q2-manager-import-") as temporary:
        manager = RunManager(ROOT, store_path=tmp_path / "runs.sqlite3")
        manager.plugin_dir = Path(temporary)
        installed = manager.import_zip(zip_path)
        assert installed.manifest.id == "q2_relaxed_channel_v1_3"
        assert installed.config["data_backend"] == "research_infrastructure_v1"
        assert installed.path.parent == Path(temporary)
        metadata = manager._prepare_runs(
            ["q2_relaxed_channel_v1_3@1.3.0"], split="validation",
            window_override=("2024-10-01", "2024-10-01", "2024-10-15"))[0]
        assert metadata["universe_mode"] == "research_infrastructure_v1"
        assert metadata["research_backend"]["core_database_sha256"] == metadata["data_snapshot"]
        assert metadata["execution_policy"]["max_holding_sessions"] == 10
        assert metadata["engine"] == "lean"
