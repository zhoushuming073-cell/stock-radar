"""Reuse immutable feature bytes only after proving identical causal inputs."""
import argparse
import json
from pathlib import Path
from radar.lab.universe import LocalSecurityMaster
from radar.pit.features import rebind_identical_features

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--previous',type=Path,required=True)
    p.add_argument('--build',type=Path,required=True)
    p.add_argument('--config',type=Path,default=Path('config/research.yaml'))
    p.add_argument('--external-prices',type=Path)
    a=p.parse_args()
    sidecar=a.build/'security-master-feature-store.json'
    if sidecar.exists():
        p.error('feature sidecar already exists; immutable binding retained')
    old=LocalSecurityMaster(a.previous/'security-master.csv',a.previous/'security-master-manifest.json')
    new=LocalSecurityMaster(a.build/'security-master.csv',a.build/'security-master-manifest.json')
    r=rebind_identical_features(old,new,a.config,a.external_prices)
    sidecar.write_text(json.dumps(r,indent=2),encoding='utf-8')
    print(json.dumps(r['reviewed_reuse'],indent=2))
