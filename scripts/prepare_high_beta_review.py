"""Real, blind monthly/weekly/daily QA; not Human training labels or outcomes."""
from pathlib import Path
from io import BytesIO
import hashlib
import json
import random

import duckdb
import pandas as pd
import yaml
from PIL import Image,ImageDraw

from radar.research.daily import current_inputs
from radar.research.candidates import fingerprint
from radar.research.high_beta.daily import listing_context,source_hash
from radar.research.parallel_channel import _aggregate
from radar.vision.render import render_blind_png,RENDERER_VERSION


def main():
    root=Path(__file__).resolve().parents[1];out=root/'data/research/high-beta-channel-v1.2';directory=out/'review'
    r=json.loads((out/'daily/latest.json').read_text())
    day,_,names,frame=current_inputs(root/'data/market.duckdb',r['as_of'])
    _,classification=listing_context(root,names,day)
    with duckdb.connect(str(root/'data/market.duckdb'),read_only=True) as c:
        refs=c.execute("select symbol,date,close,provider,feed,adjustment from daily_bars where symbol in ('SPY','QQQ') and date<=? order by symbol,date",[day]).df()
    data_hash=fingerprint({'names':names,'bars':pd.util.hash_pandas_object(frame,index=False).astype(str).tolist(),
        'benchmark':pd.util.hash_pandas_object(refs,index=False).astype(str).tolist(),'classification':classification})
    if data_hash!=r['data_hash'] or source_hash()!=r['code_hash']:
        raise ValueError('Source snapshot/code changed; cannot substitute new data into old blind tasks')
    definitions=yaml.safe_load((root/'config/q2_v1_2_diagnostic_set.yaml').read_text())
    known=set(definitions['positive_preferences']+definitions['negative_preferences'])
    pool=[x for x in r['diagnostics'] if x['symbol'] not in known and x['window_metadata']['analysis']['market_qualified']]
    admitted=[x for x in pool if x['status']!='rejected'];boundary=[x for x in pool if x['reason_codes'][0]=='channel_windows_disagree']
    other=[x for x in pool if x not in admitted and x not in boundary];seed=20261009;rng=random.Random(seed);rng.shuffle(other)
    selected=(admitted+boundary+other)[:20];rng.shuffle(selected)
    if len(selected)!=20:raise ValueError('Insufficient unseen eligible samples; no relaxed-gate padding')
    tasks=[];private=[];directory.mkdir(parents=True,exist_ok=True)
    for i,x in enumerate(selected):
        bars=frame.loc[frame.symbol.eq(x['symbol']),['date','open','high','low','close','volume']]
        pictures=[]
        for z in [_aggregate(bars,'ME').tail(18),_aggregate(bars,'W-FRI').tail(26),bars.tail(60)]:
            raw,_=render_blind_png(z[['date','open','high','low','close','volume']]);pictures.append(Image.open(BytesIO(raw)).convert('RGB'))
        canvas=Image.new('RGB',(2880,755),'white');draw=ImageDraw.Draw(canvas)
        for j,picture in enumerate(pictures):
            draw.text((j*960+30,12),['Monthly','Weekly','Daily'][j],fill='#142a47');canvas.paste(picture,(j*960,35))
        task_id=hashlib.sha256((r['data_hash']+str(i)).encode()).hexdigest()[:16]
        b=BytesIO();canvas.save(b,format='PNG');image=b.getvalue();sha=hashlib.sha256(image).hexdigest();path=directory/(task_id+'.png')
        if path.exists() and path.read_bytes()!=image:raise ValueError('Existing blind PNG changed')
        if not path.exists():path.write_bytes(image)
        tasks.append({'id':task_id,'image_file':path.name,'image_sha256':sha})
        private.append({'id':task_id,'symbol':x['symbol'],'machine_status':x['status'],'machine_reasons':x['reason_codes'],'image_sha256':sha})
    manifest={'version':'q2-v1.2-blind-shape-qa-v1','renderer':RENDERER_VERSION,'seed':seed,'task_count':len(tasks),
        'snapshot_hash':fingerprint(r),'data_hash':data_hash,'code_hash':r['code_hash'],'config_hash':r['config_hash'],
        'scope':'Unseen-symbol shape QA; admitted, structural boundary and other market-admitted examples. No future outcomes or generated human judgments.',
        'tasks':tasks}
    # Existing review from an earlier engineering draft is preserved as provenance.
    prior=directory/'manifest.json'
    if prior.exists():
        old=prior.read_bytes();archive=directory/('manifest-'+hashlib.sha256(old).hexdigest()+'.json')
        if not archive.exists():archive.write_bytes(old)
    prior.write_text(json.dumps(manifest,indent=2));(directory/'private-mapping.json').write_text(json.dumps(private,indent=2))
    print(json.dumps({'tasks':len(tasks),'human_labels':0,'manifest_sha256':hashlib.sha256(prior.read_bytes()).hexdigest()}))


if __name__=='__main__':main()
