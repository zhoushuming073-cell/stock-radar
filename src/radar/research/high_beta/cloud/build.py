"""Generate a small free-Cloud bundle from frozen Stock Radar source.

No market data access or remote API. The selector/function bodies and native
execution policy are copied from source; only imports and transport differ.
"""
from __future__ import annotations
import ast
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import zipfile

import yaml
from radar.backtest.costs import load_fee_config
from radar.research.quant_lean import execution_config
from radar.research.sessions import calendar
from radar.research.high_beta.channel import VERSION,settings


Q2_NAMES=('Settings','beta','market_features','_channel','channel_analysis','daily_state','analyze','candidate','rank')
CHANNEL_NAMES=('ChannelSettings','_ramp','_validate','_aggregate','_slope_pairs','_slope','_pivots','_distinct','_fit')
SOURCE_PATHS=('src/radar/research/high_beta/channel.py','src/radar/research/parallel_channel.py',
    'src/radar/features/elasticity.py','src/radar/research/candidates.py','src/radar/research/sessions.py',
    'src/radar/lean/algorithm_fixed_horizon.py','config/high_beta_channel_v1_2.yaml',
    'config/quant_research_v1.yaml','config/research.yaml','config/q2_v12_cloud_exploratory.yaml',
    'src/radar/research/high_beta/cloud/data.py','src/radar/research/high_beta/cloud/fill.py',
    'src/radar/research/high_beta/cloud/main.py','src/radar/research/high_beta/cloud/build.py')


def sha(raw):return hashlib.sha256(raw).hexdigest()


class Relocate(ast.NodeTransformer):
    def visit_ImportFrom(self,node):
        if node.module=='radar.research.sessions':node.module='sr_sessions'
        return node


def extracted(path,names):
    tree=ast.parse(path.read_text(encoding='utf-8'))
    found={n.name:n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
    if set(names)-set(found):raise ValueError('Missing source function')
    # AST unparse preserves semantics; no handcrafted selector translation.
    return '\n\n'.join(ast.unparse(Relocate().visit(found[name])) for name in names)+'\n'


SESSION_HOST='''
import pandas as pd

class SessionCalendar:
    def __init__(self):self.sessions=pd.DatetimeIndex(DATES)
    def sessions_in_range(self,first,last):
        a,b=pd.Timestamp(first),pd.Timestamp(last)
        if a.tzinfo is not None or b.tzinfo is not None:raise ValueError('naive sessions required')
        if a< pd.Timestamp('2020-01-01') or b>pd.Timestamp('2026-12-31'):raise ValueError('calendar range exceeded')
        return self.sessions[(self.sessions>=a)&(self.sessions<=b)]
    def date_to_session(self,day,direction='none'):
        d=pd.Timestamp(day)
        if d in self.sessions:return d
        if direction=='previous':
            i=self.sessions.searchsorted(d)-1
            if i>=0 and d<=pd.Timestamp('2026-12-31'):return self.sessions[i]
        raise ValueError('no exchange session in calendar')
    def is_session(self,day):return pd.Timestamp(day) in self.sessions

_CAL=SessionCalendar()
def calendar():return _CAL
def require_session(day,*,now=None):
    d=pd.Timestamp(day)
    if d.tzinfo is not None or d!=d.normalize() or not _CAL.is_session(d):raise ValueError('real exchange session required')
    if now is not None and d.date()>pd.Timestamp(now).date():raise ValueError('future session')
    return str(d.date())
'''


def sources(root):
    root=Path(root);study=yaml.safe_load((root/'config/q2_v12_cloud_exploratory.yaml').read_text(encoding='utf-8'))
    if study['selector_version']!=VERSION or study['parameter_optimization'] or study['top_k']!=10:
        raise ValueError('Wrong/optimized selector contract')
    parent=yaml.safe_load((root/study['execution_config']).read_text(encoding='utf-8'))
    execution=execution_config(parent)
    execution['max_positions']=parent['maximum_positions']
    fees=asdict(load_fee_config(root/parent['fees']))
    hashes={p:sha((root/p).read_bytes()) for p in SOURCE_PATHS}
    receipt={'selector_version':VERSION,'domain':'qc-native-exploratory-r1','sources':hashes,
             'selector_sha256':sha(json.dumps(hashes,sort_keys=True,separators=(',',':')).encode())}
    header='# GENERATED from Stock Radar frozen source; do not edit formulas here.\n'
    files={'sr_q2.py':header+'''from dataclasses import asdict,dataclass
import math
import numpy as np
import pandas as pd
from sr_math import _market_model
from sr_data import Candidate,QcEvidence as MarketEvidence
from sr_contracts import fingerprint
from sr_channel import ChannelSettings,_aggregate,_fit,_validate
from sr_sessions import calendar
VERSION = "high-beta-liquid-channel-v1.2"
'''+extracted(root/SOURCE_PATHS[0],Q2_NAMES),
        'sr_channel.py':header+'''from __future__ import annotations
from dataclasses import asdict,dataclass
from typing import Any
from functools import lru_cache
import math
import numpy as np
import pandas as pd
COLUMNS=('date','open','high','low','close','volume')
'''+extracted(root/SOURCE_PATHS[1],CHANNEL_NAMES),
        'sr_math.py':header+'import numpy as np\nimport pandas as pd\n'+extracted(root/SOURCE_PATHS[2],('_market_model',)),
        'sr_contracts.py':header+'import hashlib\nimport json\n'+extracted(root/SOURCE_PATHS[3],('fingerprint',)),
        'sr_execution.py':header+(root/SOURCE_PATHS[5]).read_text(encoding='utf-8'),
        'sr_config.py':header+'STUDY = '+repr(study)+'\nSETTINGS = '+repr(asdict(settings(root)))+
            '\nEXECUTION = '+repr(execution)+'\nFEES = '+repr(fees)+'\nRECEIPT = '+repr(receipt)+'\n'}
    dates=[str(x.date()) for x in calendar().sessions_in_range('2020-01-02','2026-12-31')]
    # One string rather than a repr list stays below32K free file limit.
    files['sr_sessions.py']=header+'DATES = '+repr(' '.join(dates))+'.split()\n'+SESSION_HOST
    for target,relative in [('main.py','main.py'),('sr_data.py','data.py'),('sr_fill.py','fill.py')]:
        files[target]=(root/'src/radar/research/high_beta/cloud'/relative).read_text(encoding='utf-8')
    for name,source in files.items():
        ast.parse(source,filename=name)
        if len(source.encode('utf-8'))>32000:raise ValueError(f'Free Cloud file limit: {name}')
    if len(files)+1>25:raise ValueError('Free Cloud project file quota')
    return files,receipt


def prepare(root,out):
    files,receipt=sources(root);out=Path(out);upload=out/'upload';upload.mkdir(parents=True,exist_ok=True)
    # Reject an unexpectedly stale export instead of uploading unrelated files.
    stale={p.name for p in upload.iterdir()}-set(files)
    if stale:raise ValueError(f'Unexpected upload artifacts: {sorted(stale)}')
    for name,source in files.items():(upload/name).write_bytes(source.encode('utf-8'))
    manifest={'status':'SOURCE_PACKAGE_READY_CLOUD_NOT_RUN','receipt':receipt,
        'files':{n:{'bytes':len(s.encode()),'sha256':sha(s.encode())} for n,s in files.items()},
        'upload_files':len(files),'cloud_result':None,'market_data_included':False,
        'human_control':'free web IDE upload and Backtest click'}
    (out/'upload-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    with zipfile.ZipFile(out/'q2-v1.2-cloud-source.zip','w',compression=zipfile.ZIP_DEFLATED) as archive:
        for name,source in sorted(files.items()):
            info=zipfile.ZipInfo(name,date_time=(2026,10,9,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
            archive.writestr(info,source.encode())
    return manifest
