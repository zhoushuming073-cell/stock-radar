"""Real market/action accounting witnesses; these are NOT formal Scanner portfolios."""
from pathlib import Path
import json
from uuid import uuid4

import duckdb
import pandas as pd

from radar.backtest.costs import load_fee_config
from radar.lab.parameters import execution_defaults_from_legacy
from radar.lean.export import prepare_bundle
from radar.lean.result_adapter import normalize
from radar.lean.runtime import installation, invoke, digest as file_hash, verify_bundle
from radar.pit.actions import factor_lines
from radar.pit.builder import digest
from radar.pit.trust import load_catalog


def public_series(root, symbol, start, end):
    candidates = list((root/'data/pit/raw/final-goldens').glob(symbol+'-*.json'))
    candidates += list((root/'data/pit/raw/public-prices').glob(symbol+'-*.json'))
    for path in candidates:
        data=json.loads(path.read_text(encoding='utf-8'))
        if path.stem.rsplit('-',1)[-1] != digest(data):
            raise ValueError('golden payload content-address mismatch')
        rows=[r for r in data['rows'] if start<=r['date']<=end]
        if rows and data['requested_start']<=start and data['requested_end']>=end:
            if data['source_version']!='vt6qeesk27k07492k5jc5b7p04mf0s6o' or data['license']!='CC-BY-SA-4.0':
                raise ValueError('golden public source pin/license mismatch')
            captured=[]
            for query in data['queries']:
                raw=path.parent/(query['raw_sha256']+'.raw')
                if file_hash(raw)!=query['raw_sha256']:raise ValueError('golden raw source mutation')
                payload=json.loads(raw.read_text(encoding='utf-8'))
                if (payload.get('query_execution_status')!='Success' or payload.get('sql_query')!=query['sql']
                        or "AS OF 'vt6qeesk27k07492k5jc5b7p04mf0s6o'" not in query['sql']):
                    raise ValueError('golden SQL response status/pin mismatch')
                if 'FROM ohlcv ' in query['sql']:captured.extend(payload['rows'])
            if digest(captured)!=digest(data['rows']):raise ValueError('golden aggregated rows mismatch')
            review=json.loads((root/'config/pit_public_price_review.json').read_text(encoding='utf-8'))
            license_raw=root/'data/pit/raw/public-prices'/(review['license_raw_sha256']+'.raw')
            if file_hash(license_raw)!=review['license_raw_sha256']:raise ValueError('golden license mutation')
            frame=pd.DataFrame(rows).rename(columns={'act_symbol':'symbol'})
            for key in ('open','high','low','close','volume'):frame[key]=frame[key].astype(float)
            return frame, {'path':str(path),'physical_sha256':file_hash(path),'payload_sha256':digest(data),
                           'provider':data['provider'],'source_version':data['source_version'],
                           'license':data['license'],'license_raw_sha256':review['license_raw_sha256'],
                           'queries':data['queries']}
    raise ValueError('no captured public series for '+symbol)


def main():
    root=Path.cwd();home,engine=installation(root)
    catalog=load_catalog(root/'config/pit_trust_evidence.json',root/'data/pit/raw/official-evidence')
    reports=[]
    for kind,start,end,ticker,security,source in [
        ('rename','2022-06-06','2022-06-14','FB','SEC-0001326801-CLASS-A','fb'),
        ('split','2024-06-05','2024-06-10','NVDA','SEC-0001045810-COMMON','nvda'),
        ('acquisition','2023-10-09','2023-10-16','ATVI','SEC-0000718877-COMMON','atvi')]:
        spy,benchmark=public_series(root,'SPY',start,end)
        evidence=[benchmark,catalog['sources'][source]]
        sessions=list(pd.to_datetime(spy.date));days=[str(d.date()) for d in sessions]
        event=next(e for e in catalog['events'] if e['security_id']==security and
                   e['event_type']=={'rename':'symbol_change','split':'split','acquisition':'merger'}[kind])
        action={**event,'event_id':f"{security}:{kind}:{event['effective_date']}",
                'source':catalog['sources'][source],'handling_mode':{'rename':'same_identity_map','split':'native_raw_split',
                    'acquisition':'native_cash_entitlement'}[kind]}
        terminal=None
        if kind=='rename':
            # Public Dolt META lacks June 9/10. Do NOT accept that partial series.
            # This bounded accounting witness uses the original licensed local
            # broker snapshot with explicit dated FB/META mapping, no file splice.
            database=root/'data/phase2-research.duckdb'
            with duckdb.connect(str(database),read_only=True) as c:
                prices=c.execute("""SELECT date,symbol,open,high,low,close,volume FROM daily_bars
                    WHERE date BETWEEN ? AND ? AND symbol IN ('FB','META') ORDER BY date""",[start,end]).df()
            prices['date']=pd.to_datetime(prices.date).dt.strftime('%Y-%m-%d')
            prices=prices.loc[((prices.date<'2022-06-09') & prices.symbol.eq('FB')) |
                              ((prices.date>='2022-06-09') & prices.symbol.eq('META'))].copy()
            evidence.append({'database':str(database),'sha256':file_hash(database),
                'provider':'existing local broker research snapshot','basis':'split-only; no META split in bounded case',
                'license':'existing user-authorized local data; no public redistribution claim',
                'residual_risk':'supplier historical identity is not independently vendor-certified'})
            maps='20220606,fb\n20220608,fb\n20501231,meta\n'
            hold=4
        else:
            prices,receipt=public_series(root,ticker,start, '2023-10-12' if kind=='acquisition' else end)
            evidence.append(receipt)
            maps=f"{start.replace('-','')},{ticker.lower()}\n20501231,{ticker.lower()}\n"
            hold=2 if kind=='split' else 10
        if kind=='split':action['ratio']=10
        if kind=='acquisition':
            # Official 8-K automatically converts ordinary common into the $95
            # cash right at effective time. This is a declared recognition
            # convention, NOT a claim about actual bank payment/withholding date.
            action['event_type']='cash_acquisition'
            action['review']={'settlement_verified':True,'currency':'USD','cash_per_share':95.,
                'settlement_policy':'cash_entitlement_at_effective_date','settlement_date':'2023-10-13',
                'last_tradable_session':'2023-10-12','settlement_fee':0,
                'scope':'ordinary listed common; no treasury/parent holdings/appraisal election; gross USD cash right; no withholding simulation'}
            terminal=action
            maps='20231009,atvi\n20231013,atvi\n'
        price_days=set(prices.date.astype(str))
        required={d for d in days if kind!='acquisition' or d<='2023-10-12'}
        if price_days!=required:raise ValueError('real golden missing/extra market session '+kind)
        prices['security_id']=security
        prices['mapped_symbol']=prices['symbol'];prices['symbol']=ticker
        spy['mapped_symbol']='SPY';spy['security_id']=None
        bars=pd.concat([prices,spy],ignore_index=True)
        execution=execution_defaults_from_legacy({'initial_capital':100000.,'max_new_candidates':1,
            'take_profit':None,'stop_loss':None,'max_holding_sessions':hold,'entry_gap_min':-.1,'entry_gap_max':.1,
            'max_position_fraction':.25,'minimum_position_fraction':0.,'max_order_to_avg_dollar_volume':.01},
            slippage_bps=10.,execution_timing='next_open')
        signal={'signal_date':start,'symbol':ticker,'rank':1,'strategy_score':1.,'strategy_id':'pit_real_accounting_golden',
            'strategy_version':'1.0.0','reference_close':float(prices.iloc[0].close),'avg_dollar_volume_20':1e8,'allocation_weight':1.}
        factors=factor_lines([action] if kind=='split' else [],days,{str(r.date):float(r.close) for r in prices.itertuples()})
        spec={'security_id':security,'maps':maps,'factors':factors,'actions':[action],'terminal':terminal}
        identity=digest({'case':kind,'evidence':evidence,'prices':prices.to_json(orient='records'),
                         'spec':spec,'execution':execution,'algorithm':file_hash(root/'src/radar/lean/algorithm.py')})
        dataset={'origin':'Stock Radar generated PIT execution dataset','source_master_version':'real scoped golden evidence',
            'dependency_sha256':identity,'securities':{ticker:spec},'price_basis':'raw',
            'actions_sha256':digest([action]),'map_sha256':digest(maps),'factor_sha256':digest(factors)}
        metadata={'window':[start,start,end],'strategy_id':signal['strategy_id'],'strategy_version':signal['strategy_version'],
            'universe_mode':'point_in_time','golden_case':kind,'formal_pit_portfolio':False,
            'validation_scope':'native corporate-action accounting only; hand-authored test signal, not frozen Strategy 2 Scanner'}
        output=root/'data/pit/native-real-goldens'/identity
        if not output.exists():
            path=prepare_bundle(home,output,metadata,sessions,[signal],bars,execution,
                                load_fee_config(root/'config/research.yaml'),pit_dataset=dataset)
            run_id=str(uuid4());raw=invoke(root,output,path,run_id,lambda _:None,lambda:False,engine)
        else:
            path=output/'manifest.json';verify_bundle(output,file_hash(path))
            raw=next(p for p in output.glob('*.json') if len(p.stem)==36 and p.stem.count('-')==4)
            run_id=raw.stem
        normalized,metrics=normalize(output,raw,engine)
        if metrics['trade_count']!=1:raise ValueError('golden native position was not closed')
        trade=normalized['trades'][0]
        if kind=='split':
            split=next(a for a in normalized['corporate_actions'] if a['event_type']=='split')
            if abs(split['quantity_after']-split['quantity_before']*10)>.000001:raise ValueError('split quantity parity')
        if kind=='acquisition' and trade['exit_execution']!=95:raise ValueError('cash entitlement != official terms')
        report={'case':kind,'native_run_id':run_id,'output':str(output),'engine':engine,
            'formal_pit_portfolio':False,'status':'PASS','evidence':evidence,'metrics':metrics,
            'manifest_sha256':file_hash(path),'raw_result_sha256':file_hash(raw),
            'normalized_sha256':file_hash(output/'normalized-result.json'),'trade':trade,
            'actions':normalized['corporate_actions'],'signal':'hand-authored accounting witness; strategy not evaluated'}
        reports.append(report);print(json.dumps({'case':kind,'run_id':run_id,'status':'PASS','final_equity':metrics['final_equity']}),flush=True)
    target=root/'data/pit/final-acceptance/real-native-goldens.json'
    target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(reports,indent=2),encoding='utf-8')


if __name__=='__main__':main()
