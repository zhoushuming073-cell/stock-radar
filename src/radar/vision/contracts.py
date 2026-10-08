"""Data contracts for blinded visual-research labeling artifacts."""
from __future__ import annotations

from typing import Literal

import pandas as pd


def _pandera():
    try:
        import pandera.pandas as pa
        from pandera.typing import Series
    except ImportError as exc:
        raise RuntimeError(
            'Vision data contracts require the optional dependencies. '
            'Install with: pip install -e ".[vision]"'
        ) from exc
    return pa, Series


def validate_sample_manifest(frame: pd.DataFrame) -> pd.DataFrame:
    """Validate the private, local-only sample manifest with Pandera.

    The manifest may contain identity/date metadata because it never becomes a
    model input or a Label Studio-visible field.  The public task file contains
    opaque IDs and local image URLs only.
    """
    pa, Series = _pandera()

    class SampleManifest(pa.DataFrameModel):
        task_id: Series[str] = pa.Field(str_length={"min_value": 8})
        blind_id: Series[str] = pa.Field(str_length={"min_value": 12})
        task_kind: Series[str] = pa.Field(isin=["single", "single_repeat"])
        security_id: Series[str] = pa.Field(str_length={"min_value": 1})
        decision_date: Series[pd.Timestamp]
        window_length: Series[int] = pa.Field(isin=[20, 40, 60, 126])
        split_assignment: Series[str] = pa.Field(isin=["train", "validation"])
        membership_status: Series[str] = pa.Field(isin=["confirmed_member", "probable_member"])
        shape_readiness_status: Series[str] = pa.Field(isin=["READY", "READY_WITH_MINOR_UNCERTAINTY"])
        ohlcv_hash: Series[str] = pa.Field(str_length={"min_value": 64, "max_value": 64})
        normalized_hash: Series[str] = pa.Field(str_length={"min_value": 64, "max_value": 64})
        dataset_version: Series[str] = pa.Field(str_length={"min_value": 1})
        infrastructure_hash: Series[str] = pa.Field(str_length={"min_value": 1})
        renderer_version: Series[str] = pa.Field(str_length={"min_value": 1})
        image_sha256: Series[str] = pa.Field(str_length={"min_value": 64, "max_value": 64})
        image_path: Series[str] = pa.Field(str_length={"min_value": 1})
        repeat_group: Series[str] = pa.Field(nullable=True)
        anchor_kind: Series[str] = pa.Field(nullable=True)

        class Config:
            strict = True
            coerce = True

    out = SampleManifest.validate(frame, lazy=True)
    if out["task_id"].duplicated().any():
        raise ValueError("duplicate task_id")
    if out["blind_id"].isna().any():
        raise ValueError("missing blind_id")
    return out


def validate_pair_manifest(frame: pd.DataFrame) -> pd.DataFrame:
    pa, Series = _pandera()

    class PairManifest(pa.DataFrameModel):
        pair_id: Series[str] = pa.Field(str_length={"min_value": 8})
        left_task_id: Series[str] = pa.Field(str_length={"min_value": 8})
        right_task_id: Series[str] = pa.Field(str_length={"min_value": 8})
        left_blind_id: Series[str] = pa.Field(str_length={"min_value": 12})
        right_blind_id: Series[str] = pa.Field(str_length={"min_value": 12})
        window_length: Series[int] = pa.Field(isin=[20, 40, 60, 126])
        split_assignment: Series[str] = pa.Field(isin=["train", "validation"])

        class Config:
            strict = True
            coerce = True

    out = PairManifest.validate(frame, lazy=True)
    if out["pair_id"].duplicated().any():
        raise ValueError("duplicate pair_id")
    if (out["left_blind_id"] == out["right_blind_id"]).any():
        raise ValueError("pair compares an image with itself")
    return out
