"""Strict Q/X population and sampling checks, independent of future Y."""
from hashlib import sha256
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .quant_features import array_features
from .quant_guided import load_quant_config, select, verify_quant
from .verification import file_hash

META={'security_id','decision_date','length','split_assignment','membership_status','shape_research_status',
      'issuer_key','issuer_known','candidate_stratum','year','feature_version'}
SELECTED_EXTRA={'draw','selection_draw','issuer_window_count','stage1_probability','sampling_layer','stage2_probability','sampling_cell',
                'anchor_kind','conditional_path_probability','task_id','window_length','normalized_hash','ohlcv_hash','image_sha256'}


def validate_quant_frame(frame,cfg,selected=False):
    factors=set(array_features(np.ones((60,5)),cfg))
    expected=META|factors|(SELECTED_EXTRA if selected else set())
    if set(frame)!=expected: raise ValueError('Q schema fields differ (identity/outcomes must stay outside X/H): '+str(set(frame)^expected))
    if not set(frame.split_assignment)<= {'train','validation'}: raise ValueError('Test/Fresh in Quant pool')
    if not set(frame.membership_status)<= {'confirmed_member','probable_member'}: raise ValueError('unknown membership in Quant pool')
    if not set(frame.shape_research_status)<= {'READY','READY_WITH_MINOR_UNCERTAINTY'}: raise ValueError('unsafe Quant identity/window')
    if set(frame.feature_version)!={cfg['feature_version']}: raise ValueError('wrong factor version')
    if not set(frame.length)<= {60,126} or not np.isfinite(frame[list(factors)].to_numpy()).all(): raise ValueError('invalid factors')
    if frame[['security_id','decision_date','length']].duplicated().any(): raise ValueError('duplicate Quant window')
    for k in [x for x in factors if x.startswith('score_') or x.endswith('_score')]:
        if not frame[k].between(0,100).all(): raise ValueError('invalid score range')
    if selected and frame.issuer_key.duplicated().any(): raise ValueError('issuer overlap')
    return frame


def verify_quant_dataset(bundle):
    bundle=Path(bundle); result=verify_quant(bundle)
    cfg=load_quant_config(bundle/'config.yaml'); receipt=json.loads((bundle/'bundle-receipt.json').read_text(encoding='utf-8'))
    if file_hash(bundle/'config.yaml')!=receipt['config_sha256']: raise ValueError('configuration binding mismatch')
    paths=[Path(__file__).with_name('quant_guided.py'),Path(__file__).with_name('quant_features.py')]
    actual=sha256(b''.join(p.read_bytes() for p in paths)).hexdigest()
    if actual!=receipt['implementation_sha256']: raise ValueError('generator implementation changed; explicit new version required')
    q=validate_quant_frame(pd.read_parquet(bundle/'quant-features.parquet'),cfg,True)
    pool=validate_quant_frame(pd.read_parquet(bundle/'scanned-features.parquet'),cfg)
    chosen,reps=select(pool,cfg)
    keys=['security_id','decision_date','length','sampling_layer','stage1_probability','stage2_probability','conditional_path_probability']
    pd.testing.assert_frame_equal(chosen[keys].reset_index(drop=True),q[keys].reset_index(drop=True),check_dtype=False)
    frame=pd.read_parquet(bundle/'sampling-frame.parquet')
    pd.testing.assert_frame_equal(reps.reset_index(drop=True),frame.reset_index(drop=True),check_dtype=False)
    result.update(scanned_features_validated=len(pool),sampling_replay='PASS',generator_hash_verified=actual)
    return result
