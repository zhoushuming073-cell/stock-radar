"""Independent Q/X/H contract, immutable human annotation revisions. Y absent."""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
from typing import Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict, field_validator

from .quant_contracts import verify_quant_dataset as verify_quant

REASONS={'前期强势','回撤较充分','下跌尚未结束','出现承接迹象','已经开始转强','尚未真正转强','最近涨得过多',
         '当前价格偏贵','当前价格位置合理','形态凌乱','无法判断'}


class HumanLabel(BaseModel):
    model_config=ConfigDict(extra='forbid')
    task_id: str
    annotation_id: int
    ls_task_id: int
    project_id: int
    label_version: Literal['quant-human-v1']
    label_origin: Literal['human','smoke']
    observe: Literal['观察','不观察','不确定']
    entry: Literal['当前可买','等回落或进一步确认','不买','不确定']
    confidence: Literal['高','中','低']
    reasons: list[str]
    created_at: str
    updated_at: str
    repeat_group: str | None

    @field_validator('reasons')
    @classmethod
    def valid_reasons(cls,v):
        if len(v)!=len(set(v)) or not set(v)<=REASONS: raise ValueError('invalid reasons')
        return sorted(v)

    @field_validator('created_at','updated_at')
    @classmethod
    def time_is_valid(cls,v):
        t=pd.Timestamp(v)
        if t.tzinfo is None: raise ValueError('annotation timestamp must include timezone')
        return v


def parse_export(bundle, tasks, origin):
    bundle=Path(bundle)
    if origin not in ('human','smoke'): raise ValueError('explicit namespace required')
    verify_quant(bundle)
    receipt=json.loads((bundle/'label-studio-projects.json').read_text(encoding='utf-8'))
    expected_project=receipt[origin]['id']
    manifest=pd.read_parquet(bundle/'sample-manifest.parquet').set_index('task_id')
    prefix=json.loads((bundle/'bundle-receipt.json').read_text())['local_files_prefix']
    records=[]; seen=set()
    for t in tasks:
        data=t.get('data',{}); meta=t.get('meta',{})
        if set(data)!={'task_id','image'} or data.get('task_id') not in manifest.index: raise ValueError('foreign or leaking task data')
        tid=data['task_id']; m=manifest.loc[tid]
        if tid in seen: raise ValueError('duplicate task export')
        seen.add(tid)
        if data['image']!=prefix+'/'+m.image_path: raise ValueError('wrong image mapping')
        if meta.get('label_version')!='quant-human-v1' or meta.get('label_origin')!=origin or t.get('project')!=expected_project:
            raise ValueError('wrong project, label version or namespace')
        annotations=[a for a in t.get('annotations',[]) if not a.get('was_cancelled')]
        if len(annotations)>1: raise ValueError('multiple annotators require explicit adjudication')
        for a in annotations:
            values={}
            for result in a.get('result',[]):
                k=result.get('from_name')
                if k not in ('observe','entry','confidence','reasons') or k in values or result.get('to_name')!='chart' or result.get('type')!='choices':
                    raise ValueError('invalid/duplicate labeling control')
                choices=result.get('value',{}).get('choices')
                if not isinstance(choices,list): raise ValueError('invalid choice result')
                if k!='reasons' and len(choices)!=1: raise ValueError('single choice required')
                values[k]=choices if k=='reasons' else choices[0]
            if not {'observe','entry','confidence'}<=set(values): raise ValueError('incomplete saved annotation')
            label=HumanLabel(task_id=tid,annotation_id=a['id'],ls_task_id=t['id'],project_id=expected_project,
               label_version='quant-human-v1',label_origin=origin,created_at=a['created_at'],updated_at=a['updated_at'],
               repeat_group=None if pd.isna(m.repeat_group) else m.repeat_group,**dict(reasons=[],**values) if 'reasons' not in values else values)
            records.append(label.model_dump())
    return records


def _import_labels(bundle, export_path, origin):
    """Atomic append-only revisions; latest Parquet is a rebuildable materialized view."""
    bundle=Path(bundle); tasks=json.loads(Path(export_path).read_text(encoding='utf-8'))
    records=parse_export(bundle,tasks,origin)
    folder=bundle/'labels'/origin; folder.mkdir(parents=True,exist_ok=True)
    revisions=folder/'revisions.json'
    old=json.loads(revisions.read_text(encoding='utf-8')) if revisions.exists() else []
    all_records=list(old); added=0
    by_rev={(r['task_id'],r['annotation_id'],r['updated_at']):r for r in old}
    for r in records:
        key=(r['task_id'],r['annotation_id'],r['updated_at'])
        if key in by_rev:
            if by_rev[key]!=r: raise ValueError('conflicting contents for same annotation revision')
            continue
        history=[o for o in old if o['task_id']==r['task_id']]
        if history and (any(o['annotation_id']!=r['annotation_id'] for o in history)
                        or pd.Timestamp(r['updated_at'])<max(pd.Timestamp(o['updated_at']) for o in history)):
            raise ValueError('foreign annotation ID or stale revision')
        all_records.append(r); added+=1
    # Preserve the original export under its CONTENT hash. Never overwrite raw labels.
    digest=sha256(Path(export_path).read_bytes()).hexdigest()
    source=folder/(digest+'.json')
    if not source.exists(): source.write_bytes(Path(export_path).read_bytes())
    latest={}
    for r in sorted(all_records,key=lambda r:pd.Timestamp(r['updated_at'])): latest[r['task_id']]=r
    temp=folder/'revisions.json.tmp'; temp.write_text(json.dumps(all_records,ensure_ascii=False,indent=2),encoding='utf-8'); temp.replace(revisions)
    if all_records:
        temp=folder/'labels.parquet.tmp'; pd.DataFrame(latest.values()).to_parquet(temp,index=False)
        temp.replace(folder/'labels.parquet')
    return {'origin':origin,'accepted_labels':len(latest),'new_revisions':added,'export_sha256':digest,
            'repeat_statistics':repeat_statistics(bundle,list(latest.values()),origin)}


def import_labels(bundle,export_path,origin):
    """One writer per namespace; stale locks fail explicitly instead of losing labels."""
    if origin not in ('human','smoke'): raise ValueError('explicit namespace required')
    folder=Path(bundle)/'labels'/origin; folder.mkdir(parents=True,exist_ok=True)
    lock=folder/'import.lock'
    try: fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    except FileExistsError as exc: raise ValueError('another import or stale import.lock; no labels overwritten') from exc
    try:
        os.write(fd,str(os.getpid()).encode()); os.close(fd)
        return _import_labels(bundle,export_path,origin)
    finally:
        lock.unlink()


def repeat_statistics(bundle,records,origin):
    manifest=pd.read_parquet(Path(bundle)/'sample-manifest.parquet')
    labels={r['task_id']:r for r in records}; originals=manifest[manifest.task_kind=='single'].set_index('blind_id')
    n=0; agree={'observe':0,'entry':0}; confusion={'observe':{},'entry':{}}
    for r in manifest[manifest.task_kind=='single_repeat'].itertuples():
        a=labels.get(r.task_id); b=labels.get(originals.loc[r.blind_id,'task_id'])
        if a is None or b is None: continue
        n+=1
        for k in agree:
            agree[k]+=int(a[k]==b[k]); pair=b[k]+' → '+a[k]; confusion[k][pair]=confusion[k].get(pair,0)+1
    return {'origin':origin,'matched_repeat_pairs':n,'agree_counts':agree,'confusion':confusion,
            'human_consistency_claim':origin=='human' and n>0,
            'note':'smoke validates plumbing only; no human consistency inference' if origin=='smoke' else 'descriptive count, not a model-quality claim'}
