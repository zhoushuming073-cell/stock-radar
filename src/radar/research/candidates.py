"""Independent Q1/Q2 candidates. No Human/Vision/outcome or execution imports."""
from datetime import date
from typing import Literal
from pathlib import Path
import hashlib
import json
import pandas as pd
import yaml
from pydantic import BaseModel, ConfigDict, Field
from radar.research.fuzzy_shape import features_at, DIMENSIONS
from radar.research.parallel_channel import ChannelSettings, analyze

SCHEMA_VERSION = 'quant-candidate-v1'

def fingerprint(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()

def code_hash():
    folder=Path(__file__).parent
    return fingerprint({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in
                        [folder/'candidates.py',folder/'fuzzy_shape.py',folder/'parallel_channel.py',folder/'sessions.py']})

class Candidate(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
    schema_version: Literal['quant-candidate-v1']='quant-candidate-v1'
    method: Literal['q1_fuzzy_shape','q2_parallel_channel']
    version: str
    decision_date: date
    security_id: str
    symbol: str
    name: str | None = None
    score: float=Field(ge=0,le=100)
    rank: int | None = Field(default=None,ge=1)
    status: Literal['qualified','watch','wait','rejected']
    subscores: dict[str,float]
    reason_codes: list[str]
    window_metadata: dict
    data_quality_flags: list[str]
    provenance: dict

def configurations(root):
    root=Path(root)
    return (yaml.safe_load((root/'config/quant_vision_labeling_v1.yaml').read_text(encoding='utf-8')),
            ChannelSettings(**yaml.safe_load((root/'config/parallel_channel_v1.yaml').read_text(encoding='utf-8'))['settings']))

def q1(frame,asof,cfg,*,security_id,symbol,name=None,provenance=None,quality_flags=()):
    """Use the accepted 126-day score by default, never choose a lucky window."""
    x=frame.loc[pd.to_datetime(frame.date)<=pd.Timestamp(asof)].tail(126).copy()
    if len(x)!=126:raise ValueError('Q1 requires a complete safe 126-session window')
    f=features_at(x,asof,cfg)
    s=cfg['scores']
    status=('qualified' if f['quant_score']>=s['high_score'] and f['extension_score']<s['conflict_extension_score']
            else 'wait' if f['shape_score']>=s['conflict_shape_score'] and f['extension_score']>=s['conflict_extension_score']
            else 'watch' if f['quant_score']>=s['medium_score'] else 'rejected')
    reasons=['fuzzy_high' if f['quant_score']>=s['high_score'] else 'fuzzy_medium' if f['quant_score']>=s['medium_score'] else 'below_watch_band']
    if f['extension_score']>=s['conflict_extension_score']:reasons.append('extended_wait')
    return Candidate(method='q1_fuzzy_shape',version='fuzzy-shape-v1',decision_date=asof,
        security_id=security_id,symbol=symbol,name=name,score=f['quant_score'],status=status,
        subscores={k:f['score_'+k] for k in DIMENSIONS},reason_codes=reasons,
        window_metadata={'length':126,'observed_through':str(asof),'features':f},
        data_quality_flags=list(quality_flags),provenance=provenance or {})

def q2(frame,asof,cfg,*,security_id,symbol,name=None,provenance=None,quality_flags=(),historical=False):
    r=analyze(frame,asof,cfg,absolute_tradability=not historical)
    status='qualified' if r['qualified'] else 'watch' if r['watch'] else 'rejected'
    if status=='watch' and r.get('daily',{}).get('stage')=='near_lower_wait':status='wait'
    channels=r.get('channels',[])
    failures=sorted({k for c in channels for k,v in c.get('tests',{}).items() if not v})
    return Candidate(method='q2_parallel_channel',version=r['version'],decision_date=asof,
        security_id=security_id,symbol=symbol,name=name,score=r.get('rank_score',0),status=status,
        subscores={'channel_quality':r.get('consensus',{}).get('quality',0),
                   'entry':(r.get('daily') or {}).get('entry_score',0)},
        reason_codes=[r['reason'],*['channel_'+f for f in failures]],
        window_metadata={'length':len(frame.loc[pd.to_datetime(frame.date)<=pd.Timestamp(asof)]),
                         'observed_through':str(asof),'analysis':r},
        data_quality_flags=list(quality_flags),provenance=provenance or {})

def rank_candidates(rows):
    """Method-local qualified-first ordering, score descending then stable identity."""
    rows=sorted(rows,key=lambda r:(r.status!='qualified',-r.score,r.security_id,r.symbol))
    return [r.model_copy(update={'rank':i}) for i,r in enumerate(rows,1)]

