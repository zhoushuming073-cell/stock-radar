"""Print a compact summary of the full-strategy2 scenario grid.

Usage:
    python scripts/print_full_strategy2_summary.py
    python scripts/print_full_strategy2_summary.py --input path/to/scenario_summary.csv
"""

import argparse
import csv
from pathlib import Path

DEFAULT_INPUT = (
    Path(__file__).resolve().parent.parent
    / "data"
    / "research"
    / "full-strategy2-v1"
    / "scenario_summary.csv"
)

COLUMNS = [
    "split",
    "slippage_bps_per_side",
    "total_return",
    "max_drawdown",
    "trade_count",
]

PERCENT_COLUMNS = {"total_return", "max_drawdown"}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Print split / slippage / return / drawdown / trade_count "
        "from a scenario_summary.csv file."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help=f"Path to scenario_summary.csv (default: {DEFAULT_INPUT})",
    )
    args = parser.parse_args()

    if not args.input.exists():
        raise SystemExit(f"input file not found: {args.input}")

    with args.input.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        missing = [c for c in COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise SystemExit(f"missing columns in {args.input}: {', '.join(missing)}")
        rows = [
            {c: (row.get(c) or "").strip() for c in COLUMNS}
            for row in reader
        ]

    widths = {c: len(c) for c in COLUMNS}
    for row in rows:
        for column in COLUMNS:
            widths[column] = max(widths[column], len(format_cell(column, row[column])))

    header = "  ".join(column.ljust(widths[column]) for column in COLUMNS)
    print(header)
    print("  ".join("-" * widths[column] for column in COLUMNS))
    for row in rows:
        print(
            "  ".join(
                format_cell(column, row[column]).ljust(widths[column])
                for column in COLUMNS
            )
        )


def format_cell(column: str, raw: str) -> str:
    if column in PERCENT_COLUMNS:
        try:
            return f"{float(raw) * 100:.2f}%"
        except ValueError:
            return raw
    if column == "slippage_bps_per_side":
        try:
            return f"{float(raw):g}"
        except ValueError:
            return raw
    return raw


if __name__ == "__main__":
    main()
