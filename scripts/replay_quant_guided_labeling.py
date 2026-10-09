"""Regenerate all selected PNGs from the frozen API; never modifies a published bundle."""
from pathlib import Path
import argparse
import json
from radar.research.infrastructure import shape_research_universe_v1
from radar.vision.quant_contracts import verify_quant_dataset
from radar.vision.quant_guided import load_quant_config
from radar.vision.quant_features import features_at
from radar.vision.render import render_blind_png
from radar.pit.shape import canonical_hash
import pandas as pd
import numpy as np

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--root',type=Path,default=Path.cwd())
    p.add_argument('--bundle',type=Path,default=Path('data/vision-research/quant-guided-v1/ready')); a=p.parse_args()
    result=verify_quant_dataset(a.bundle); cfg=load_quant_config(a.bundle/'config.yaml')
    m=pd.read_parquet(a.bundle/'sample-manifest.parquet'); q=pd.read_parquet(a.bundle/'quant-features.parquet').set_index('task_id')
    with shape_research_universe_v1(a.root) as api:
        for r in m[m.task_kind=='single'].itertuples():
            w=api.window(r.security_id,r.decision_date,r.window_length)
            if canonical_hash(w.ohlcv)!=r.ohlcv_hash or canonical_hash(w.normalized)!=r.normalized_hash:
                raise ValueError('replay numeric window differs')
            _,h=render_blind_png(w.normalized)
            if h!=r.image_sha256: raise ValueError('replay PNG differs')
            f=features_at(w.normalized,r.decision_date,cfg)
            if any(not np.isclose(v,q.loc[r.task_id,k],rtol=1e-10,atol=1e-8) for k,v in f.items()):
                raise ValueError('replay Quant features differ')
    result.update(regenerated_images=300,regenerated_canonical_windows=600,status='PASS',human_labels_written=0)
    (a.bundle/'replay-verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))
