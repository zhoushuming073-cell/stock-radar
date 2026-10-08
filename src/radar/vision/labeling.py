"""Blind P0/P1 dataset preparation and Label Studio round-trip."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math
import shutil
from itertools import zip_longest
from importlib.metadata import version as dependency_version
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from radar.research.infrastructure import shape_research_universe_v1
from .contracts import validate_pair_manifest, validate_sample_manifest
from .render import RENDERER_VERSION, render_blind_png

SINGLE_CHOICES = {"很喜欢", "一般", "不喜欢", "看不懂"}
REASON_CHOICES = {"下跌未停", "承接明显", "拉升已过", "疑似形态异常"}
PAIR_CHOICES = {"A更值得继续观察", "B更值得继续观察", "都不好", "难判断"}
CONFIDENCE_CHOICES = {"高", "中", "低"}


@dataclass(frozen=True)
class VisionPilotConfig:
    version: str
    seed: int
    single_count: int
    pair_count: int
    repeat_fraction: float
    window_lengths: tuple[int, ...]
    allowed_splits: tuple[str, ...]
    output_dir: str
    label_studio_document_root: str
    local_files_prefix: str
    anchors: tuple[dict[str, str], ...]


def load_config(path: str | Path) -> VisionPilotConfig:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    pilot = raw["pilot"]
    cfg = VisionPilotConfig(
        version=str(raw["version"]),
        seed=int(pilot["seed"]),
        single_count=int(pilot["single_count"]),
        pair_count=int(pilot["pair_count"]),
        repeat_fraction=float(pilot["repeat_fraction"]),
        window_lengths=tuple(int(x) for x in pilot["window_lengths"]),
        allowed_splits=tuple(str(x) for x in pilot["allowed_splits"]),
        output_dir=str(raw["output_dir"]),
        label_studio_document_root=str(raw["label_studio"]["document_root"]),
        local_files_prefix=str(raw["label_studio"]["local_files_prefix"]).rstrip("/"),
        anchors=tuple(dict(x) for x in raw.get("anchors", [])),
    )
    if cfg.single_count < 1 or cfg.pair_count < 0:
        raise ValueError("pilot counts must be non-negative")
    if not 0 <= cfg.repeat_fraction <= 0.5:
        raise ValueError("repeat_fraction must be between 0 and 0.5")
    if not set(cfg.window_lengths) <= {20, 40, 60, 126}:
        raise ValueError("unsupported window length")
    if not set(cfg.allowed_splits) <= {"train", "validation"}:
        raise ValueError("P0/P1 labeling must stay in Train/Validation")
    if not cfg.window_lengths or not cfg.allowed_splits:
        raise ValueError('nonempty windows and splits required')
    if cfg.label_studio_document_root != 'data':
        raise ValueError('Label Studio document root must be project data/')
    output = Path(cfg.output_dir)
    if output.is_absolute() or '..' in output.parts or output.parts[:1] != ('data',):
        raise ValueError('pilot output must stay inside project data/')
    expected = '/data/local-files/?d=' + output.relative_to('data').as_posix()
    if cfg.local_files_prefix != expected:
        raise ValueError('local image URL must match the pilot data directory')
    return cfg


def _opaque_id(*parts: object, size: int = 24) -> str:
    body = "|".join(str(x) for x in parts)
    return sha256(body.encode("utf-8")).hexdigest()[:size]


def _calendar_guard(dates: pd.Series) -> None:
    try:
        import exchange_calendars as xcals
    except ImportError as exc:
        raise RuntimeError('Install vision dependencies with: pip install -e ".[vision]"') from exc
    calendar = xcals.get_calendar("XNYS")
    unique = pd.DatetimeIndex(pd.to_datetime(dates).dt.normalize().unique()).sort_values()
    if len(unique) == 0:
        raise ValueError("empty decision dates")
    sessions = pd.DatetimeIndex(calendar.sessions_in_range(unique.min(), unique.max()))
    if sessions.tz is not None:
        sessions = sessions.tz_localize(None)
    sessions = sessions.normalize()
    invalid = unique.difference(sessions)
    if len(invalid):
        raise ValueError("non-session decision dates: " + ",".join(str(x.date()) for x in invalid[:10]))


def _query_anchor(api, security_id: str, cfg: VisionPilotConfig) -> dict[str, Any] | None:
    split_sql = ",".join("?" for _ in cfg.allowed_splits)
    length_sql = ",".join("?" for _ in cfg.window_lengths)
    params: list[Any] = [security_id, *cfg.allowed_splits, *cfg.window_lengths]
    sql = f"""SELECT security_id,decision_date,length,split_assignment,membership_status,shape_research_status
              FROM visual_window_index
              WHERE security_id=? AND supported_membership
                AND split_assignment IN ({split_sql}) AND length IN ({length_sql})
              ORDER BY decision_date DESC,length DESC LIMIT 1"""
    row = api.core.connection.execute(sql, params).df()
    return None if row.empty else row.iloc[0].to_dict()


def _deterministic_pool(api, cfg: VisionPilotConfig, target: int) -> pd.DataFrame:
    """Small deterministic stratified pool without loading millions of rows."""
    strata = api.core.connection.execute(
        """SELECT split_assignment,length,year(decision_date) AS y,count(*) AS n
           FROM visual_window_index
           WHERE supported_membership AND split_assignment IN (SELECT unnest(?))
             AND length IN (SELECT unnest(?))
           GROUP BY ALL ORDER BY split_assignment,length,y""",
        [list(cfg.allowed_splits),list(cfg.window_lengths)]
    ).df()
    strata = strata[
        strata["split_assignment"].isin(cfg.allowed_splits)
        & strata["length"].isin(cfg.window_lengths)
    ]
    if strata.empty:
        raise ValueError("no eligible visual windows")
    per = max(2, math.ceil((target * 6) / len(strata)))
    frames: list[pd.DataFrame] = []
    for r in strata.itertuples():
        query = """SELECT security_id,decision_date,length,split_assignment,membership_status,shape_research_status
                   FROM visual_window_index
                   WHERE supported_membership AND split_assignment=? AND length=? AND year(decision_date)=?
                   ORDER BY md5(security_id || '|' || cast(decision_date AS VARCHAR) || '|' ||
                                cast(length AS VARCHAR) || '|""" + str(cfg.seed) + """')
                   LIMIT ?"""
        frames.append(api.core.connection.execute(query, [r.split_assignment, int(r.length), int(r.y), per]).df())
    # Explicit v2 policy: rotate split/year/window strata, skip used securities.
    # This balances coverage rather than sorting a pooled sample back into one year.
    seen=set(); ordered=[]
    for batch in zip_longest(*(f.to_dict('records') for f in frames)):
        for row in batch:
            if row is not None and row['security_id'] not in seen:
                seen.add(row['security_id']);ordered.append(row)
    return pd.DataFrame.from_records(ordered)


def _render_rows(root: Path, api, rows: pd.DataFrame, cfg: VisionPilotConfig, anchor_map: dict[tuple, str]) -> pd.DataFrame:
    output = root / cfg.output_dir
    images = output / "images"
    images.mkdir(parents=True, exist_ok=True)
    windows = output / 'windows'
    windows.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    for r in rows.itertuples(index=False):
        decision = pd.Timestamp(r.decision_date).normalize()
        window = api.window(str(r.security_id), decision, int(r.length))
        if window.metadata["split_assignment"] not in cfg.allowed_splits:
            raise ValueError("sample escaped allowed splits")
        blind = _opaque_id(api.fingerprint, cfg.version, cfg.seed, RENDERER_VERSION,
                           r.security_id, decision.date(), int(r.length))
        path = images / f"{blind}.png"
        _, image_hash = render_blind_png(window.normalized, path)
        window.ohlcv.to_parquet(windows / f'{blind}-ohlcv.parquet',index=False)
        window.normalized.to_parquet(windows / f'{blind}-normalized.parquet',index=False)
        key = (str(r.security_id), str(decision.date()), int(r.length))
        records.append(
            {
                "task_id": "single-" + blind,
                "blind_id": blind,
                "task_kind": "single",
                "security_id": str(r.security_id),
                "decision_date": decision,
                "window_length": int(r.length),
                "split_assignment": str(window.metadata["split_assignment"]),
                "membership_status": str(window.metadata["membership_status"]),
                "shape_readiness_status": str(window.metadata["shape_readiness_status"]),
                "ohlcv_hash": str(window.metadata["ohlcv_hash"]),
                "normalized_hash": str(window.metadata["normalized_hash"]),
                "dataset_version": str(window.metadata["dataset_version"]),
                "infrastructure_hash": str(api.fingerprint),
                "renderer_version": RENDERER_VERSION,
                "image_sha256": image_hash,
                "image_path": path.relative_to(output).as_posix(),
                "repeat_group": None,
                "anchor_kind": anchor_map.get(key),
            }
        )
    return pd.DataFrame.from_records(records)


def _add_repeats(manifest: pd.DataFrame, cfg: VisionPilotConfig) -> pd.DataFrame:
    n = int(round(len(manifest) * cfg.repeat_fraction))
    if n <= 0:
        return manifest
    ordered = manifest.assign(
        _repeat_order=manifest["blind_id"].map(lambda x: _opaque_id(cfg.seed, "repeat", x, size=64))
    ).sort_values("_repeat_order")
    repeats = ordered.head(n).drop(columns="_repeat_order").copy()
    repeats["task_kind"] = "single_repeat"
    repeats["repeat_group"] = repeats["blind_id"]
    repeats["task_id"] = ['single-' + _opaque_id(cfg.seed, 'repeat-task', blind)
                          for blind in repeats['blind_id']]
    return pd.concat([manifest, repeats], ignore_index=True)


def _build_pairs(manifest: pd.DataFrame, cfg: VisionPilotConfig) -> pd.DataFrame:
    base = manifest[manifest["task_kind"] == "single"].copy()
    base["_order"] = base["blind_id"].map(lambda x: _opaque_id(cfg.seed, "pair", x, size=64))
    base = base.sort_values(["split_assignment", "window_length", "_order"])
    columns=['pair_id','left_task_id','right_task_id','left_blind_id','right_blind_id','window_length','split_assignment']
    if cfg.pair_count == 0:
        return pd.DataFrame(columns=columns)
    def group_pairs(split,length,group):
        seen: set[tuple[str,str]] = set()
        rows = list(group.itertuples(index=False))
        if len(rows) < 2:
            return
        for shift in range(1, len(rows)):
            for i, left in enumerate(rows):
                right = rows[(i + shift) % len(rows)]
                if left.security_id == right.security_id:
                    continue
                identity = tuple(sorted((str(left.blind_id), str(right.blind_id))))
                if identity in seen:
                    continue
                seen.add(identity)
                pair_id = "pair-" + _opaque_id(cfg.seed, *identity)
                yield (
                    {
                        "pair_id": pair_id,
                        "left_task_id": left.task_id,
                        "right_task_id": right.task_id,
                        "left_blind_id": left.blind_id,
                        "right_blind_id": right.blind_id,
                        "window_length": int(length),
                        "split_assignment": str(split),
                    }
                )
    generators=[group_pairs(split,length,group) for (split,length),group in
                base.groupby(['split_assignment','window_length'],sort=True)]
    pairs=[]
    for batch in zip_longest(*generators):
        pairs.extend(row for row in batch if row is not None)
        if len(pairs)>=cfg.pair_count:break
    if len(pairs) < cfg.pair_count:
        raise ValueError(f"only {len(pairs)} safe pairs available; requested {cfg.pair_count}")
    return pd.DataFrame.from_records(pairs[: cfg.pair_count])


def _local_url(cfg: VisionPilotConfig, image_path: str) -> str:
    return f"{cfg.local_files_prefix}/{image_path}"


def build_label_studio_bundle(root: str | Path, config_path: str | Path) -> dict[str, Any]:
    """Build the blinded pilot bundle. No future outcome table is read."""
    root = Path(root).resolve()
    cfg = load_config(config_path)
    output = root / cfg.output_dir
    output.mkdir(parents=True, exist_ok=True)
    if any(output.glob('human*labels*.parquet')):
        raise ValueError('refusing to rebuild a pilot that contains human labels')
    with shape_research_universe_v1(root) as api:
        anchors: list[dict[str, Any]] = []
        anchor_map: dict[tuple, str] = {}
        anchor_coverage=[]
        for anchor in cfg.anchors:
            row = _query_anchor(api, anchor["security_id"], cfg)
            if row is None:
                anchor_coverage.append({'kind':anchor['kind'],'eligible':False,
                                       'reason':'no supported Train/Validation window at configured lengths'})
                continue
            anchor_coverage.append({'kind':anchor['kind'],'eligible':True})
            key = (str(row["security_id"]), str(pd.Timestamp(row["decision_date"]).date()), int(row["length"]))
            anchor_map[key] = anchor["kind"]
            anchors.append(row)
        anchor_frame = pd.DataFrame.from_records(anchors)
        wanted = max(cfg.single_count - len(anchor_frame), 0)
        pool = _deterministic_pool(api, cfg, max(wanted, cfg.single_count))
        if not anchor_frame.empty:
            pool = pool[~pool["security_id"].isin(set(anchor_frame["security_id"].astype(str)))]
        selected = pd.concat([anchor_frame, pool.head(wanted)], ignore_index=True).head(cfg.single_count)
        if len(selected) != cfg.single_count:
            raise ValueError("could not construct requested pilot")
        if selected["security_id"].duplicated().any():
            raise ValueError("P0/P1 pilot must use unique securities before deliberate repeats")
        _calendar_guard(selected["decision_date"])
        manifest = _render_rows(root, api, selected, cfg, anchor_map)
        manifest = _add_repeats(manifest, cfg)
        manifest = validate_sample_manifest(manifest)
        pairs = validate_pair_manifest(_build_pairs(manifest, cfg))
        fingerprint = api.fingerprint
        from radar.pit.features import file_hash
        source_unchanged = file_hash(api.core.directory/'shape.duckdb') == api.core.manifest['database_sha256']
        if not source_unchanged:raise ValueError('frozen source changed during pilot preparation')

    manifest.to_parquet(output / "sample-manifest.parquet", index=False)
    manifest.to_json(output / "sample-manifest.jsonl", orient="records", lines=True, date_format="iso")
    pairs.to_parquet(output / "pair-manifest.parquet", index=False)
    # Retire only generated, unreferenced assets; preserve them locally for audit.
    active=set(manifest.blind_id)
    retired=output.parent/'retired-assets'
    for folder, pattern in [('images','*.png'),('windows','*.parquet')]:
        for p in (output/folder).glob(pattern):
            if p.name.split('-')[0].split('.')[0] not in active:
                retired.mkdir(exist_ok=True)
                digest=sha256(p.read_bytes()).hexdigest()
                target=retired/(digest+'-'+p.name)
                if target.exists():target=retired/(digest+'-'+_opaque_id(str(p.stat().st_mtime_ns))+'-'+p.name)
                shutil.move(str(p),str(target))
    singles = [
        {"data": {"image": _local_url(cfg, str(r.image_path)), "task_id": str(r.task_id)}}
        for r in manifest.assign(_task_order=manifest.task_id.map(
            lambda x:_opaque_id(cfg.seed,'display',x))).sort_values('_task_order').itertuples(index=False)
    ]
    by_task = manifest.set_index("task_id")
    pair_tasks = []
    for r in pairs.itertuples(index=False):
        left = by_task.loc[r.left_task_id]
        right = by_task.loc[r.right_task_id]
        pair_tasks.append(
            {
                "data": {
                    "image_a": _local_url(cfg, str(left.image_path)),
                    "image_b": _local_url(cfg, str(right.image_path)),
                    "pair_id": str(r.pair_id),
                }
            }
        )
    (output / "label-studio-single-tasks.json").write_text(
        json.dumps(singles, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output / "label-studio-pair-tasks.json").write_text(
        json.dumps(pair_tasks, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    receipt = {
        "version": cfg.version,
        "infrastructure_hash": fingerprint,
        "renderer_version": RENDERER_VERSION,
        "single_unique": int((manifest["task_kind"] == "single").sum()),
        "single_repeats": int((manifest["task_kind"] == "single_repeat").sum()),
        "unique_securities": int(manifest.loc[manifest["task_kind"] == "single", "security_id"].nunique()),
        "pairs": len(pairs),
        "allowed_splits": list(cfg.allowed_splits),
        "window_lengths": list(cfg.window_lengths),
        "future_outcomes_read": False,
        "strategy2_scores_read": False,
        "unknown_membership_included": False,
        'source_read_only_and_unchanged':source_unchanged,
        'sampling_policy':'round-robin-split-year-window-v2; one unique security',
        'sampling_seed':cfg.seed,
        'config_sha256':file_hash(Path(config_path)),
        'label_schema_version':'human-vision-v1',
        'local_files_prefix':cfg.local_files_prefix,
        'anchor_coverage':anchor_coverage,
        'renderer_dependencies':{name:dependency_version(name) for name in
            ['mplfinance','matplotlib','numpy','pandas','Pillow']},
        'artifact_hashes':{name:file_hash(output/name) for name in
            ['sample-manifest.parquet','pair-manifest.parquet','label-studio-single-tasks.json','label-studio-pair-tasks.json']},
    }
    (output / "bundle-receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return receipt


def _latest_annotation(task: dict[str, Any]) -> dict[str, Any] | None:
    annotations = [a for a in task.get("annotations", []) if not a.get("was_cancelled")]
    if not annotations:
        return None
    return sorted(annotations, key=lambda a: str(a.get("updated_at") or a.get("created_at") or ""))[-1]


def _choice_map(annotation: dict[str, Any]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for result in annotation.get("result", []):
        value = result.get("value", {})
        key=str(result.get('from_name'))
        if 'choices' not in value or key in out or not isinstance(value['choices'],list):
            raise ValueError('unknown or duplicated annotation result')
        out[key]=[str(x) for x in value['choices']]
    return out


def _one(values: dict[str, list[str]], key: str) -> str | None:
    picked = values.get(key) or []
    if len(picked)>1:raise ValueError('multiple values for a single choice')
    return picked[0] if picked else None


def import_label_studio_export(
    export_path: str | Path,
    manifest_path: str | Path,
    pair_manifest_path: str | Path | None = None,
    *,
    label_version: str = "human-vision-v1",
    output_path: str | Path | None = None,
) -> pd.DataFrame:
    """Normalize Label Studio export without joining future outcome labels."""
    tasks = json.loads(Path(export_path).read_text(encoding="utf-8"))
    if not isinstance(tasks, list):
        raise ValueError("Label Studio export must be a JSON task list")
    manifest = validate_sample_manifest(pd.read_parquet(manifest_path))
    known_single = set(manifest["task_id"].astype(str))
    known_pairs: set[str] = set()
    pair_rows=None
    if pair_manifest_path is not None and Path(pair_manifest_path).exists():
        pair_rows=validate_pair_manifest(pd.read_parquet(pair_manifest_path)).set_index('pair_id')
        known_pairs = set(pair_rows.index.astype(str))
    samples=manifest.set_index('task_id')
    receipt_path=Path(manifest_path).parent/'bundle-receipt.json'
    prefix=json.loads(receipt_path.read_text(encoding='utf-8'))['local_files_prefix'] if receipt_path.exists() else None
    rows: list[dict[str, Any]] = []
    for task in tasks:
        if task.get('meta',{}).get('label_origin')=='smoke' and not label_version.startswith('smoke-'):
            raise ValueError('SMOKE labels cannot enter human Ground Truth')
        data = task.get("data", {})
        key = str(data.get("task_id") or data.get("pair_id") or "")
        if key not in known_single and key not in known_pairs:
            raise ValueError("foreign or unblinded Label Studio task")
        required={'pair_id','image_a','image_b'} if key in known_pairs else {'task_id','image'}
        if set(data)!=required:raise ValueError('unknown identity/outcome fields in exported task')
        if key in known_pairs:
            pair=pair_rows.loc[key]
            paths={'image_a':samples.loc[pair.left_task_id].image_path,
                   'image_b':samples.loc[pair.right_task_id].image_path}
        else:paths={'image':samples.loc[key].image_path}
        for field,path in paths.items():
            if (prefix is not None and data[field]!=prefix+'/'+path) or (prefix is None and not data[field].endswith('/'+path)):
                raise ValueError('exported image differs from task manifest')
        annotation = _latest_annotation(task)
        if annotation is None:
            continue
        choices = _choice_map(annotation)
        allowed={'preference','pair_confidence'} if key in known_pairs else {'overall_setup','confidence','reasons'}
        if set(choices)-allowed:raise ValueError('unknown annotation fields')
        record = {
            "task_id": key,
            "task_kind": "pair" if key in known_pairs else "single",
            "label_version": label_version,
            "completed_by": str(annotation.get("completed_by", "")),
            "created_at": str(annotation.get("created_at", "")),
            "updated_at": str(annotation.get("updated_at", "")),
        }
        if key in known_pairs:
            preference = _one(choices, "preference")
            confidence = _one(choices, "pair_confidence")
            if preference not in PAIR_CHOICES or confidence not in CONFIDENCE_CHOICES:
                raise ValueError("invalid or incomplete pair annotation")
            record.update({"preference": preference, "confidence": confidence})
        else:
            overall = _one(choices, "overall_setup")
            confidence = _one(choices, "confidence")
            reasons = choices.get("reasons", [])
            if overall not in SINGLE_CHOICES or confidence not in CONFIDENCE_CHOICES:
                raise ValueError("invalid or incomplete single annotation")
            if not set(reasons) <= REASON_CHOICES:
                raise ValueError("unknown subjective reason")
            record.update(
                {"overall_setup": overall, "reasons": "|".join(sorted(reasons)), "confidence": confidence}
            )
        rows.append(record)
    if len({row['task_id'] for row in rows})!=len(rows):
        raise ValueError('duplicated exported task')
    result = pd.DataFrame.from_records(rows)
    if output_path is not None:
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.suffix.lower() == ".parquet":
            result.to_parquet(target, index=False)
        else:
            result.to_csv(target, index=False)
    return result


def repeat_consistency(labels: pd.DataFrame, manifest: pd.DataFrame) -> dict[str, Any]:
    """Simple human self-consistency diagnostic for deliberately repeated images."""
    repeats = manifest[manifest["repeat_group"].notna()][["task_id", "repeat_group"]].copy()
    if repeats.empty:
        return {"repeat_groups": 0, "comparable": 0, "agreement": None}
    original = manifest[manifest["task_kind"] == "single"][["task_id", "blind_id"]].rename(
        columns={"task_id": "original_task_id", "blind_id": "repeat_group"}
    )
    mapping = repeats.merge(original, on="repeat_group", how="inner")
    if labels.empty or not (labels["task_kind"] == "single").any():
        return {"repeat_groups": len(mapping), "comparable": 0, "agreement": None}
    values = labels[labels["task_kind"] == "single"].set_index("task_id")["overall_setup"].to_dict()
    pairs = [(values.get(r.original_task_id), values.get(r.task_id)) for r in mapping.itertuples(index=False)]
    comparable = [(a, b) for a, b in pairs if a is not None and b is not None]
    agreement = None if not comparable else sum(a == b for a, b in comparable) / len(comparable)
    distribution={}
    for a,b in comparable:
        key=a+' -> '+b;distribution[key]=distribution.get(key,0)+1
    return {"repeat_groups": len(mapping), "comparable": len(comparable), "agreement": agreement,
            'confusion_distribution':distribution}
