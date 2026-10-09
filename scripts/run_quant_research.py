"""Pre-register -> causal historical signals -> native LEAN. No Cloud or return optimization."""
import argparse
import json
from pathlib import Path
from radar.research.quant_lean import freeze,verify_freeze,run_method
from radar.research.historical_quant import scan_historical

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--freeze-only',action='store_true');p.add_argument('--signals-only',action='store_true')
    p.add_argument('--execute-only',action='store_true');p.add_argument('--split',choices=['train','validation','all'],default='all')
    p.add_argument('--method',choices=['q1','q2','all'],default='all')
    args=p.parse_args();root=Path(__file__).resolve().parents[1];directory=root/'data/research/quant-research-v1'
    receipt=freeze(root,directory)
    print('Frozen before portfolio results: '+str(directory/'freeze.json'),flush=True)
    if args.freeze_only:return
    results=[]
    for split,window in receipt['research_config']['intervals'].items():
        if args.split not in {'all',split}:continue
        verify_freeze(root,receipt)
        if not args.execute_only:
            scan_historical(root,split,window[0],window[1],directory/split,progress=lambda x:print(x,flush=True))
        if not args.signals_only:
            for method in ['q1','q2']:
                if args.method not in {'all',method}:continue
                try:r=run_method(root,receipt,directory,split,method)
                except Exception as e:
                    r={'status':'FAILED','split':split,'method':method,'error':str(e)}
                    (directory/split/(method+'-failure.json')).write_text(json.dumps(r,indent=2),encoding='utf-8')
                results.append(r);print(json.dumps({k:r.get(k) for k in ['status','split','method','run_id','selected_signals','error']},indent=2),flush=True)
    if results:(directory/'execution-summary.json').write_text(json.dumps(results,indent=2,allow_nan=False),encoding='utf-8')

if __name__=='__main__':main()

