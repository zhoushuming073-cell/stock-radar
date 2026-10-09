"""Port verified Quant candidates without resampling on future availability."""
from pathlib import Path
from hashlib import sha256
from collections import Counter
import json
import numpy as np
import pandas as pd
import yaml
from radar.pit.shape import canonical_hash,tensor
from radar.research.infrastructure import shape_research_universe_v1
from .quant_contracts import verify_quant_dataset
from .dual_contracts import NumericInput,VectorInput,FutureOutcome
from .dual_render import left_svg,right_svg,geometry_hash,digest,VERSION
from .dual_outcomes import read_future,outcome

def load_config(root):
    cfg=yaml.safe_load((Path(root)/'config/quant_vision_dual_stage_v3.yaml').read_text(encoding='utf-8'))
    expected={'version':'dual-stage-v3','allowed_splits':['train','validation'],'horizon':10,'target':.05,'adverse':-.03,'fee_bps':0,'slippage_bps':0}
    if any(cfg.get(k)!=v for k,v in expected.items()):raise ValueError('explicit new version required for changed outcome contract')
    out=Path(cfg['output'])
    if out.is_absolute() or '..' in out.parts or out.parts[0]!='.local':raise ValueError('outside Label Studio local-files root required')
    return cfg

def build(root):
    root=Path(root).resolve();cfg=load_config(root);source=root/cfg['source_bundle'];verify_quant_dataset(source)
    out=root/cfg['output']
    if out.exists():raise ValueError('immutable v3 bundle exists; verify or create explicitly versioned dataset')
    out.mkdir(parents=True);(out/'left').mkdir();(out/'right').mkdir();(out/'numeric').mkdir()
    old=pd.read_parquet(source/'sample-manifest.parquet');q=pd.read_parquet(source/'quant-features.parquet');items={};rows=[]
    with shape_research_universe_v1(root) as db:
        for r in old.itertuples():
            if r.split_assignment not in cfg['allowed_splits']:raise ValueError('protected split')
            group=digest((r.ohlcv_hash+r.normalized_hash).encode())
            if group not in items:
                w=db.window(r.security_id,r.decision_date,int(r.window_length))
                if canonical_hash(w.ohlcv)!=r.ohlcv_hash or canonical_hash(w.normalized)!=r.normalized_hash:raise ValueError('source window drift')
                svg=left_svg(w.normalized);(out/'left'/f'{group}.svg').write_bytes(svg)
                np.save(out/'numeric'/f'{group}.npy',tensor(w.normalized),allow_pickle=False)
                x=NumericInput(version='x-left-num-v3',raw_hash=r.ohlcv_hash,normalized_hash=r.normalized_hash,tensor_sha256=digest((out/'numeric'/f'{group}.npy').read_bytes()),length=int(r.window_length),channels='open,high,low,close,volume',split=r.split_assignment).model_dump()
                v=VectorInput(version='x-left-svg-v3',renderer=VERSION,svg_sha256=digest(svg),geometry_sha256=geometry_hash(svg),numeric_hash=r.normalized_hash).model_dump()
                task_hash=digest(json.dumps({'x':x,'v':v},sort_keys=True,separators=(',',':')).encode())
                # Independent future read starts ONLY after the left artifacts are fixed.
                bars,flags,provenance=read_future(db,w.metadata)
                reference=float(w.ohlcv.close.iloc[-1])
                # Earlier raw splits are already corrected by causal normalization.
                prior_low=float(w.normalized.low.min()/w.normalized.close.iloc[-1]*reference)
                y=outcome(bars,reference,provenance,flags,prior_low=prior_low)
                future_svg=right_svg(bars,reference,y['entry_open'])
                (out/'right'/f'{group}.svg').write_bytes(future_svg)
                future={'bars':bars,'Y_future':y,'svg_hash':digest(future_svg),'reference':reference}
                (out/'right'/f'{group}.json').write_text(json.dumps(future,allow_nan=False),encoding='utf-8')
                items[group]={'X_left_num':x,'X_left_svg':v,'task_hash':task_hash,'right_hash':digest(future_svg),'future_json_hash':digest((out/'right'/f'{group}.json').read_bytes()),'outcome_status':y['status']}
            item=items[group]
            for origin in ('human','smoke'):
                tid=digest(('v3:'+origin+':'+r.task_id).encode())[:24]
                rows.append({'task_id':tid,'origin':origin,'group':group,'source_task':r.task_id,'security_id':r.security_id,'decision_date':str(r.decision_date)[:10],'length':int(r.window_length),'split':r.split_assignment,**item})
    # Keep ten distinct charts plus repeat in smoke; no human labels are created.
    human=[r for r in rows if r['origin']=='human'];smoke=[r for r in rows if r['origin']=='smoke'];bygroup={}
    for r in smoke:bygroup.setdefault(r['group'],[]).append(r)
    repeated=next(v for v in bygroup.values() if len(v)>1);smoke_selected=[repeated[0]]
    for v in bygroup.values():
        if len(smoke_selected)>=10:break
        if v[0]['group']!=repeated[0]['group']:smoke_selected.append(v[0])
    smoke_selected.append(repeated[1]);rows=human+smoke_selected
    (out/'manifest.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    pd.DataFrame(rows).to_parquet(out/'manifest.parquet',index=False);q.to_parquet(out/'Q_private.parquet',index=False)
    config_hash=digest((root/'config/quant_vision_dual_stage_v3.yaml').read_bytes())
    code_hash=digest(b''.join((Path(__file__).parent/p).read_bytes() for p in ('dual_dataset.py','dual_outcomes.py','dual_render.py','dual_contracts.py')))
    receipt={'version':cfg['version'],'unique':len(items),'human_tasks':len(human),'smoke_tasks':len(smoke_selected),'repeats':len(human)-len(items),
        'source_quant_receipt_hash':digest((source/'bundle-receipt.json').read_bytes()),'config_hash':config_hash,'code_hash':code_hash,
        'manifest_hash':digest((out/'manifest.json').read_bytes()),'infrastructure_hash':db.fingerprint,
        'outcome_counts':dict(Counter(v['outcome_status'] for v in items.values())),
        'selection_depends_on_Y':False,'automatic_v1_label_migration':False,'private_storage_outside_ls_document_root':True}
    (out/'receipt.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8');return receipt

def verify(root):
    root=Path(root);out=root/load_config(root)['output'];rows=json.loads((out/'manifest.json').read_text());receipt=json.loads((out/'receipt.json').read_text())
    if digest((out/'manifest.json').read_bytes())!=receipt['manifest_hash']:raise ValueError('manifest changed')
    if digest((root/'config/quant_vision_dual_stage_v3.yaml').read_bytes())!=receipt['config_hash']:raise ValueError('config drift')
    if digest(b''.join((Path(__file__).parent/p).read_bytes() for p in ('dual_dataset.py','dual_outcomes.py','dual_render.py','dual_contracts.py')))!=receipt['code_hash']:raise ValueError('source drift')
    for r in rows:
        x=NumericInput.model_validate(r['X_left_num']);v=VectorInput.model_validate(r['X_left_svg']);g=r['group']
        svg=(out/'left'/f'{g}.svg').read_bytes();n=(out/'numeric'/f'{g}.npy').read_bytes()
        if digest(svg)!=v.svg_sha256 or geometry_hash(svg)!=v.geometry_sha256 or digest(n)!=x.tensor_sha256:raise ValueError('left hash drift')
        raw=(out/'right'/f'{g}.json').read_bytes()
        if digest(raw)!=r['future_json_hash']:raise ValueError('future label drift')
        y=json.loads(raw);FutureOutcome.model_validate(y['Y_future'])
        if digest((out/'right'/f'{g}.svg').read_bytes())!=r['right_hash']:raise ValueError('right drift')
    return receipt
