"""Current known-preference diagnostics; never changes the v1.2 market selector."""
from pathlib import Path
import json
import yaml
import duckdb
import pandas as pd

from radar.research.high_beta.channel import settings,channel_analysis,daily_state
from radar.research.high_beta.daily import listing_context,source_hash
from radar.research.candidates import fingerprint
from radar.research.daily import current_inputs


def main():
    root=Path(__file__).resolve().parents[1];out=root/'data/research/high-beta-channel-v1.2'
    definitions=yaml.safe_load((root/'config/q2_v1_2_diagnostic_set.yaml').read_text())
    r=json.loads((out/'daily/latest.json').read_text())
    if r['as_of']!=definitions['as_of']:raise ValueError('Diagnostic date differs from the registered snapshot')
    by={x['symbol']:x for x in r['diagnostics']}
    day,_,names,f=current_inputs(root/'data/market.duckdb',r['as_of']);cfg=settings(root);rows=[]
    _,classification=listing_context(root,names,day)
    with duckdb.connect(str(root/'data/market.duckdb'),read_only=True) as c:
        refs=c.execute("select symbol,date,close,provider,feed,adjustment from daily_bars where symbol in ('SPY','QQQ') and date<=? order by symbol,date",[day]).df()
    data_hash=fingerprint({'names':names,'bars':pd.util.hash_pandas_object(f,index=False).astype(str).tolist(),
        'benchmark':pd.util.hash_pandas_object(refs,index=False).astype(str).tolist(),'classification':classification})
    if data_hash!=r['data_hash'] or source_hash()!=r['code_hash']:
        raise ValueError('Diagnostic inputs changed; cannot mix new fits with saved market features')
    for s in definitions['positive_preferences']+definitions['negative_preferences']:
        original=by[s];a=original['window_metadata']['analysis'];bars=f.loc[f.symbol.eq(s)]
        ch=channel_analysis(bars,cfg);fits=[c for c in ch['windows'] if 'lower' in c]
        best=max(fits,key=lambda c:c['channel_clarity_score']) if fits else None
        rows.append({'symbol':s,'market':a['market'],'reasons':a['reason_codes'],'status':original['status'],
            'channel_qualified':ch['qualified'],'diagnostic_only_best_rejected_fit':best,
            'diagnostic_daily':daily_state(bars,best['lower'],best['upper'],cfg) if best else None,
            'best_per_timeframe':{tf:max([c for c in fits if c['timeframe']==tf],key=lambda c:c['channel_clarity_score'],default=None) for tf in ['weekly','monthly']}})
    payload={'version':definitions['version'],'as_of':r['as_of'],'snapshot_code_hash':r['code_hash'],
        'config_hash':r['config_hash'],'diagnostic_only':True,'rows':rows}
    encoded=json.dumps(payload,sort_keys=True,indent=2,allow_nan=False)
    path=out/('known-diagnostics-'+fingerprint(payload)+'.json')
    if path.exists() and path.read_text()!=encoded:raise ValueError('immutable diagnostics changed')
    if not path.exists():path.write_text(encoded)
    print(json.dumps({'path':str(path),'count':len(rows),'no_ticker_selection_rule':True}))


if __name__=='__main__':main()
