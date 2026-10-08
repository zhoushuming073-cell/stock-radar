from __future__ import annotations

import json
from pathlib import Path

from hypothesis import given, strategies as st
import numpy as np
import pandas as pd
from PIL import Image
import pytest
import yaml

from radar.vision.contracts import validate_pair_manifest, validate_sample_manifest
from radar.vision.labeling import (
    VisionPilotConfig,
    _build_pairs,
    _opaque_id,
    import_label_studio_export,
    load_config,
    repeat_consistency,
)
from radar.vision.render import RENDERER_VERSION, render_blind_png


def frame(n=60):
    dates = pd.bdate_range("2024-01-02", periods=n)
    close = np.linspace(1.0, 1.2, n)
    return pd.DataFrame(
        {
            "date": dates,
            "open": close * 0.995,
            "high": close * 1.015,
            "low": close * 0.985,
            "close": close,
            "volume": np.linspace(0.2, 1.0, n),
        }
    )


@given(st.text(min_size=0, max_size=80), st.integers(min_value=8, max_value=64))
def test_opaque_ids_are_deterministic_and_fixed_length(value, size):
    a = _opaque_id(value, "salt", size=size)
    b = _opaque_id(value, "salt", size=size)
    assert a == b
    assert len(a) == size
    assert set(a) <= set("0123456789abcdef")


def test_render_blind_png_is_repeatable_and_has_no_text_metadata(tmp_path):
    first, h1 = render_blind_png(frame(), tmp_path / "a.png")
    second, h2 = render_blind_png(frame(), tmp_path / "b.png")
    assert first == second
    assert h1 == h2
    with Image.open(tmp_path / "a.png") as image:
        assert image.width > 0 and image.height > 0
        assert "ticker" not in json.dumps(image.info).lower()
        assert "symbol" not in json.dumps(image.info).lower()


def sample_manifest():
    digest = "a" * 64
    return pd.DataFrame(
        [
            {
                "task_id": "single-aaaaaaaaaaaa",
                "blind_id": "aaaaaaaaaaaa",
                "task_kind": "single",
                "security_id": "SEC-A",
                "decision_date": pd.Timestamp("2024-01-05"),
                "window_length": 60,
                "split_assignment": "train",
                "membership_status": "confirmed_member",
                "shape_readiness_status": "READY",
                "ohlcv_hash": digest,
                "normalized_hash": digest,
                "dataset_version": "dataset-v1",
                "infrastructure_hash": "infra-v1",
                "renderer_version": RENDERER_VERSION,
                "image_sha256": digest,
                "image_path": "images/aaaaaaaaaaaa.png",
                "repeat_group": None,
                "anchor_kind": None,
            },
            {
                "task_id": "repeat-001-aaaaaaaaaaaa",
                "blind_id": "aaaaaaaaaaaa",
                "task_kind": "single_repeat",
                "security_id": "SEC-A",
                "decision_date": pd.Timestamp("2024-01-05"),
                "window_length": 60,
                "split_assignment": "train",
                "membership_status": "confirmed_member",
                "shape_readiness_status": "READY",
                "ohlcv_hash": digest,
                "normalized_hash": digest,
                "dataset_version": "dataset-v1",
                "infrastructure_hash": "infra-v1",
                "renderer_version": RENDERER_VERSION,
                "image_sha256": digest,
                "image_path": "images/aaaaaaaaaaaa.png",
                "repeat_group": "aaaaaaaaaaaa",
                "anchor_kind": None,
            },
        ]
    )


def test_pandera_manifest_accepts_blind_train_data_and_rejects_test():
    good = validate_sample_manifest(sample_manifest())
    assert len(good) == 2
    bad = sample_manifest()
    bad.loc[0, "split_assignment"] = "test"
    with pytest.raises(Exception):
        validate_sample_manifest(bad)


def test_pair_contract_rejects_self_comparison():
    good = pd.DataFrame(
        [
            {
                "pair_id": "pair-aaaaaaaa",
                "left_task_id": "single-left",
                "right_task_id": "single-right",
                "left_blind_id": "aaaaaaaaaaaa",
                "right_blind_id": "bbbbbbbbbbbb",
                "window_length": 60,
                "split_assignment": "validation",
            }
        ]
    )
    assert len(validate_pair_manifest(good)) == 1
    bad = good.copy()
    bad.loc[0, "right_blind_id"] = bad.loc[0, "left_blind_id"]
    with pytest.raises(ValueError, match="itself"):
        validate_pair_manifest(bad)


def test_pair_builder_hits_requested_count_without_same_security():
    rows = []
    digest = "a" * 64
    for i in range(20):
        rows.append(
            {
                "task_id": f"single-{i:03d}-abcdefgh",
                "blind_id": f"{i:012x}",
                "task_kind": "single",
                "security_id": f"SEC-{i:03d}",
                "decision_date": pd.Timestamp("2024-01-05"),
                "window_length": 60,
                "split_assignment": "train",
                "membership_status": "confirmed_member",
                "shape_readiness_status": "READY",
                "ohlcv_hash": digest,
                "normalized_hash": digest,
                "dataset_version": "v",
                "infrastructure_hash": "i",
                "renderer_version": RENDERER_VERSION,
                "image_sha256": digest,
                "image_path": f"images/{i:012x}.png",
                "repeat_group": None,
                "anchor_kind": None,
            }
        )
    manifest = pd.DataFrame(rows)
    cfg = VisionPilotConfig(
        version="test",
        seed=7,
        single_count=20,
        pair_count=15,
        repeat_fraction=0,
        window_lengths=(60,),
        allowed_splits=("train",),
        output_dir="data/x",
        label_studio_document_root="data",
        local_files_prefix="/data/local-files/?d=x",
        anchors=(),
    )
    pairs = _build_pairs(manifest, cfg)
    assert len(pairs) == 15
    lookup = manifest.set_index("task_id")["security_id"].to_dict()
    assert all(lookup[a] != lookup[b] for a, b in zip(pairs.left_task_id, pairs.right_task_id))


def write_manifest(tmp_path):
    manifest = sample_manifest()
    path = tmp_path / "manifest.parquet"
    manifest.to_parquet(path, index=False)
    return manifest, path


def annotation(task_id, overall):
    return {
        "data": {"task_id": task_id, "image": "/data/local-files/?d=x/images/aaaaaaaaaaaa.png"},
        "annotations": [
            {
                "completed_by": 1,
                "created_at": "2026-10-08T00:00:00Z",
                "updated_at": "2026-10-08T00:00:00Z",
                "result": [
                    {"from_name": "overall_setup", "value": {"choices": [overall]}},
                    {"from_name": "confidence", "value": {"choices": ["高"]}},
                    {"from_name": "reasons", "value": {"choices": []}},
                ],
            }
        ],
    }


def test_label_import_is_manifest_bound_and_repeat_consistency(tmp_path):
    manifest, manifest_path = write_manifest(tmp_path)
    export = tmp_path / "export.json"
    export.write_text(
        json.dumps(
            [
                annotation("single-aaaaaaaaaaaa", "很喜欢"),
                annotation("repeat-001-aaaaaaaaaaaa", "很喜欢"),
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    labels = import_label_studio_export(export, manifest_path)
    assert set(labels["overall_setup"]) == {"很喜欢"}
    summary = repeat_consistency(labels, manifest)
    assert summary["comparable"] == 1
    assert summary["agreement"] == 1.0


def test_label_import_rejects_foreign_task(tmp_path):
    _, manifest_path = write_manifest(tmp_path)
    export = tmp_path / "foreign.json"
    export.write_text(json.dumps([annotation("SEC-A-2024-01-05", "很喜欢")], ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="foreign"):
        import_label_studio_export(export, manifest_path)


def test_config_refuses_test_or_fresh_labeling(tmp_path):
    config = {
        "version": "v",
        "output_dir": "data/vision-research/test",
        "pilot": {
            "seed": 1,
            "single_count": 10,
            "pair_count": 2,
            "repeat_fraction": 0.1,
            "window_lengths": [60],
            "allowed_splits": ["test"],
        },
        "label_studio": {"document_root": "data", "local_files_prefix": "/data/local-files/?d=x"},
        "anchors": [],
    }
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    with pytest.raises(ValueError, match="Train/Validation"):
        load_config(path)


def test_label_studio_templates_do_not_expose_identity_or_outcomes():
    root = Path(__file__).resolve().parents[1]
    for name in ("vision-single.xml", "vision-pair.xml"):
        text = (root / "labeling" / name).read_text(encoding="utf-8").lower()
        for forbidden in ("$ticker", "$symbol", "$date", "$future", "$return", "$profit", "$security_id"):
            assert forbidden not in text
