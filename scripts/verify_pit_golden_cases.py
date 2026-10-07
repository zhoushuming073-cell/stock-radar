"""Read-only real-world witnesses against the built master and actual OHLCV/features."""
import argparse
import json
from pathlib import Path

import duckdb
import pandas as pd

from radar.lab.universe import LocalSecurityMaster
from radar.pit.features import file_hash
from radar.pit.lean_plan import execution_design_status

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build',type=Path,required=True)
    a=p.parse_args()
    m=LocalSecurityMaster(a.build/'security-master.csv',a.build/'security-master-manifest.json')
    def row(symbol,day):return m.eligible_on(day).set_index('symbol').loc[symbol]
    assert row('FB','2022-06-08').security_id==row('META','2022-06-09').security_id
    assert row('BBBY','2023-05-02').security_id!=row('BBBY','2025-08-29').security_id
    assert row('OSTK','2023-11-03').security_id==row('BYON','2023-11-06').security_id==row('BBBY','2025-08-29').security_id
    assert row('PLTR','2024-11-25').exchange=='NYSE' and row('PLTR','2024-11-26').exchange=='NASDAQ'
    assert row('PLTR','2024-11-25').security_id==row('PLTR','2024-11-26').security_id
    assert 'BABA' in set(m.observed_on('2024-06-10').symbol) and 'BABA' not in set(m.eligible_on('2024-06-10').symbol)
    db=Path(m.feature_store['database']);assert file_hash(db)==m.feature_store['database_sha256']
    evidence=[]
    with duckdb.connect(str(db),read_only=True) as c:
        rename=c.execute("""SELECT b.security_id,b.symbol,b.date,b.close,f.ret_1
            FROM daily_bars b JOIN daily_features f ON b.symbol=f.symbol AND b.date=f.date
            WHERE b.symbol IN ('FB','META') AND b.date IN ('2022-06-08','2022-06-09') ORDER BY b.date""").fetchall()
        assert len(rename)==2 and rename[0][0]==rename[1][0]=='SEC-0001326801-CLASS-A'
        assert abs(rename[1][4]-(rename[1][3]/rename[0][3]-1))<1e-12
        reuse_counts={identity:c.execute('SELECT COUNT(*) FROM daily_bars WHERE security_id=?',[identity]).fetchone()[0]
                      for identity in ['SEC-0000886158-COMMON','SEC-0001130713-COMMON']}
        for symbol,expected,end,cik in [('ATVI',532,'2023-10-12','0000718877'),('TWTR',292,'2022-10-27','0001418091'),('SPLK',638,'2024-03-15','0001353283')]:
            identity='SEC-'+cik+'-COMMON'
            count,last=c.execute('SELECT COUNT(*),MAX(date) FROM daily_bars WHERE security_id=?',[identity]).fetchone()
            assert count==expected and str(last)==end
            assert pd.isna(c.execute('SELECT ret_1 FROM daily_features WHERE security_id=? ORDER BY date LIMIT 1',[identity]).fetchone()[0])
            warm=c.execute('SELECT COUNT(*) FROM daily_features WHERE security_id=? AND tradability_pass',[identity]).fetchone()[0]
            assert warm>0
            assert symbol not in set(m.eligible_on(pd.Timestamp(end)+pd.Timedelta(days=4)).symbol)
            evidence.append({'symbol':symbol,'security_id':identity,'real_ohlcv_rows':count,'last_tradable_session':end,
                             'tradability_pass_feature_rows':warm,'first_return_unavailable':True,'terminal_economics':'unresolved'})
        split=c.execute("SELECT date,close FROM daily_bars WHERE symbol='NVDA' AND date IN ('2024-06-07','2024-06-10') ORDER BY date").fetchall()
        assert len(split)==2 and .8<float(split[1][1]/split[0][1])<1.2
    report={'universe_version':m.manifest['source_version'],'fingerprint':m.fingerprint,'feature_database_sha256':file_hash(db),
            'verifier_code_sha256':file_hash(Path(__file__)),
            'real_rename_feature_continuity':{'security_id':rename[0][0],'last_fb_close':rename[0][3],
                'first_meta_close':rename[1][3],'first_meta_ret_1':rename[1][4],'verified_against_actual_prices':True},
            'real_bbby_price_rows_by_identity':reuse_counts,
            'verified_real_cases':['FB/META Class A rename','ATVI retirement/merger','TWTR retirement/merger','SPLK retirement/merger',
                'BBBY issuer reuse','OSTK/BYON/BBBY rename chain','PLTR exchange transfer','NVDA split boundary','BABA ADS exclusion'],
            'real_price_feature_witnesses':evidence,'lean_design':execution_design_status(),
            'limitations':'split continuity is a boundary witness, not validation of the full dividend/factor execution pipeline'}
    out=Path('data/pit/reports')/m.manifest['source_version'];out.mkdir(parents=True,exist_ok=True)
    (out/'golden-cases.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))
