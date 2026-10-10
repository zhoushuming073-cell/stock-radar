"""Q2 v1.3 candidate-only audit. It never reads future labels or portfolio results."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path

import pandas as pd

from radar.lab.data import available_features
from radar.lab.research_backend import FEATURES, ResearchHistory, load_signal_frame
from radar.lab.research_adapter import ResearchStrategyContext
from radar.strategy.loader import load_strategy_directory


def audit(root: Path, start: str, end: str) -> dict:
    if not "2021-09-01" <= start <= end <= "2025-09-08":
        raise ValueError("candidate audit is limited to Train/Validation")
    registration = load_strategy_directory(
        root / "templates/q2_relaxed_channel_v1_3",
        available_features(root / "data/phase2-research.duckdb") | FEATURES)
    frame = load_signal_frame(root, pd.Timestamp(start), pd.Timestamp(end))
    counts: Counter = Counter()
    reasons: Counter = Counter()
    selected_by_date = {}
    source_counts: Counter = Counter()
    with ResearchHistory(root) as host:
        for day, daily in frame.groupby(frame["date"], sort=True):
            counts["sessions"] += 1
            counts["eligible_member_days"] += len(daily)
            counts["market_input_safe"] += int(daily.market_input_safe.sum())
            source_counts.update(daily.source.value_counts().to_dict())
            columns = ["symbol", "security_name", "close", "security_id",
                       "beta_spy_126", "avg_dollar_volume_20", "market_input_safe"]
            context = ResearchStrategyContext(day, daily[columns].reset_index(drop=True), host.history)
            diagnostics = registration.plugin.candidate_diagnostics(context, registration.config)
            for key in ("market", "structure", "low_region", "readiness", "selected"):
                counts[key] += int(diagnostics[key].sum())
            reasons.update(diagnostics.reason.value_counts().to_dict())
            selected_by_date[str(pd.Timestamp(day).date())] = int(diagnostics.selected.sum())
        report = {
            "method": registration.config["method"], "plugin_version": registration.manifest.version,
            "backend": "research_infrastructure_v1", "semantic_hash": host.fingerprint,
            "core_database_sha256": host.database_sha256, "start": start, "end": end,
            "counts": dict(counts), "exclusion_reasons": dict(reasons),
            "source_member_days": dict(source_counts), "selected_by_date": selected_by_date,
            "outcomes_or_portfolio_returns_read": False,
        }
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--start", default="2024-09-30")
    parser.add_argument("--end", default="2024-10-11")
    parser.add_argument("--output", type=Path)
    options = parser.parse_args()
    result = audit(options.root.resolve(), options.start, options.end)
    encoded = json.dumps(result, indent=2, sort_keys=True)
    if options.output:
        options.output.parent.mkdir(parents=True, exist_ok=True)
        options.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)


if __name__ == "__main__":
    main()
