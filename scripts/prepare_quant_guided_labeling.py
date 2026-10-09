from pathlib import Path
import argparse
import json
from radar.vision.quant_guided import build, verify_quant
from radar.vision.quant_contracts import verify_quant_dataset

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--root',type=Path,default=Path.cwd())
    p.add_argument('--config',type=Path,default=Path('config/quant_vision_labeling_v1.yaml'))
    p.add_argument('--reuse-verified-scan',type=Path)
    p.add_argument('--verify-only',action='store_true'); a=p.parse_args()
    if not a.verify_only: build(a.root,a.root/a.config,scan_cache=a.reuse_verified_scan.resolve() if a.reuse_verified_scan else None)
    import yaml
    cfg=yaml.safe_load((a.root/a.config).read_text(encoding='utf-8'))
    result=verify_quant_dataset(a.root/cfg['output_dir'])
    print(json.dumps(result,ensure_ascii=False,indent=2))
