"""Data contracts for blinded visual-research labeling artifacts."""
from __future__ import annotations

import pandas as pd


def _pandera():
    try:
        import pandera.pandas as pa
    except ImportError as exc:
        raise RuntimeError(
            'Vision data contracts require the optional dependencies. '
            'Install with: pip install -e ".[vision]"'
        ) from exc
    return pa


def validate_sample_manifest(frame: pd.DataFrame) -> pd.DataFrame:
    """Validate the private, local-only sample manifest with Pandera."""
    pa = _pandera()
    schema = pa.DataFrameSchema(
        {
            "task_id": pa.Column(str, checks=pa.Check.str_length(min_value=8)),
            "blind_id": pa.Column(str, checks=pa.Check.str_length(min_value=12)),
            "task_kind": pa.Column(str, checks=pa.Check.isin(["single", "single_repeat"])),
            "security_id": pa.Column(str, checks=pa.Check.str_length(min_value=1)),
            "decision_date": pa.Column("datetime64[ns]", coerce=True),
            "window_length": pa.Column(int, checks=pa.Check.isin([20, 40, 60, 126]), coerce=True),
            "split_assignment": pa.Column(str, checks=pa.Check.isin(["train", "validation"])),
            "membership_status": pa.Column(str, checks=pa.Check.isin(["confirmed_member", "probable_member"])),
            "shape_readiness_status": pa.Column(
                str, checks=pa.Check.isin(["READY", "READY_WITH_MINOR_UNCERTAINTY"])
            ),
            "ohlcv_hash": pa.Column(str, checks=pa.Check.str_length(min_value=64, max_value=64)),
            "normalized_hash": pa.Column(str, checks=pa.Check.str_length(min_value=64, max_value=64)),
            "dataset_version": pa.Column(str, checks=pa.Check.str_length(min_value=1)),
            "infrastructure_hash": pa.Column(str, checks=pa.Check.str_length(min_value=1)),
            "renderer_version": pa.Column(str, checks=pa.Check.str_length(min_value=1)),
            "image_sha256": pa.Column(str, checks=pa.Check.str_length(min_value=64, max_value=64)),
            "image_path": pa.Column(str, checks=pa.Check.str_length(min_value=1)),
            "repeat_group": pa.Column(str, nullable=True),
            "anchor_kind": pa.Column(str, nullable=True),
        },
        strict=True,
        coerce=True,
    )
    out = schema.validate(frame, lazy=True)
    if out["task_id"].duplicated().any():
        raise ValueError("duplicate task_id")
    if out["blind_id"].isna().any():
        raise ValueError("missing blind_id")
    return out


def validate_pair_manifest(frame: pd.DataFrame) -> pd.DataFrame:
    pa = _pandera()
    schema = pa.DataFrameSchema(
        {
            "pair_id": pa.Column(str, checks=pa.Check.str_length(min_value=8)),
            "left_task_id": pa.Column(str, checks=pa.Check.str_length(min_value=8)),
            "right_task_id": pa.Column(str, checks=pa.Check.str_length(min_value=8)),
            "left_blind_id": pa.Column(str, checks=pa.Check.str_length(min_value=12)),
            "right_blind_id": pa.Column(str, checks=pa.Check.str_length(min_value=12)),
            "window_length": pa.Column(int, checks=pa.Check.isin([20, 40, 60, 126]), coerce=True),
            "split_assignment": pa.Column(str, checks=pa.Check.isin(["train", "validation"])),
        },
        strict=True,
        coerce=True,
    )
    out = schema.validate(frame, lazy=True)
    if out["pair_id"].duplicated().any():
        raise ValueError("duplicate pair_id")
    if (out["left_blind_id"] == out["right_blind_id"]).any():
        raise ValueError("pair compares an image with itself")
    return out
