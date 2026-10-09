from hashlib import sha256
from pathlib import Path
import json
import numpy as np
import pandas as pd
import pytest
from hypothesis import given,strategies as st
from radar.pit.shape import tensor
from radar.vision.dual_contracts import BlindRequest,ReviewRequest,FutureOutcome,Annotation
from radar.vision.dual_render import left_svg,right_svg,geometry_hash
from radar.vision.dual_outcomes import outcome,read_future
from radar.vision.dual_store import DualStore,GateError,import_export,encode

HASH='a'*64
def digest(b):return sha256(b).hexdigest()
def prefix():return pd.DataFrame({'date':pd.bdate_range('2023-01-01',periods=60),'open':np.linspace(80,100,60),'high':np.linspace(81,101,60),'low':np.linspace(79,99,60),'close':np.linspace(80.5,100.5,60),'volume':np.linspace(.2,1,60)})
def bars():return [{'open':100.,'high':102.,'low':99.,'close':101.,'volume':1000.} for _ in range(10)]
def request(r,revision=0):return {'version':'h-blind-v3','task_hash':r['task_hash'],'expected_revision':revision,'observe':'观察','entry':'等回落或进一步确认','confidence':'中','reasons':[],'revision_reason':''}

@pytest.fixture
def store(tmp_path):
    (tmp_path/'left').mkdir();(tmp_path/'right').mkdir();svg=left_svg(prefix());group='b'*64;rows=[]
    y=outcome(bars(),100.,HASH,prior_low=70.)
    for i,origin in enumerate(['human','human','smoke','smoke']):
        rows.append({'task_id':f'{i+1:024x}','origin':origin,'group':group,'task_hash':digest(svg),'X_left_svg':{'svg_sha256':digest(svg)},'right_hash':digest(right_svg(bars(),100.,100.))})
    raw=json.dumps({'Y_future':y}).encode();(tmp_path/'right'/f'{group}.json').write_bytes(raw)
    for r in rows:r['future_json_hash']=digest(raw)
    (tmp_path/'left'/f'{group}.svg').write_bytes(svg);(tmp_path/'right'/f'{group}.svg').write_bytes(right_svg(bars(),100.,100.))
    raw=json.dumps(rows).encode();(tmp_path/'manifest.json').write_bytes(raw);(tmp_path/'receipt.json').write_text(json.dumps({'manifest_hash':digest(raw)}))
    return DualStore(tmp_path)

def human(store):return next(r for r in store.tasks.values() if r['origin']=='human')

@given(st.floats(min_value=.01,max_value=1000,allow_nan=False,allow_infinity=False))
def test_future_cannot_change_left_geometry_or_numeric(multiplier):
    f=prefix();raw=tensor(f).tobytes();svg=left_svg(f);g=geometry_hash(svg)
    b=bars()
    for r in b:
        for k in ('open','high','low','close'):r[k]*=multiplier
    right_svg(b,100.,100.)
    assert left_svg(f)==svg and geometry_hash(left_svg(f))==g and tensor(f).tobytes()==raw

@pytest.mark.parametrize('field',['symbol','security_id','future_return','score','Y_future'])
def test_left_rejects_disguised_metadata(field):
    f=prefix();f[field]='secret'
    with pytest.raises(ValueError):left_svg(f)

def test_no_absolute_dates_identity_or_future_in_left():
    svg=left_svg(prefix()).decode()
    assert '2023' not in svg and 'security' not in svg and 'target' not in svg
    assert 'T close' in svg and svg.count('rect')>=120

def test_separate_future_axis():
    a=left_svg(prefix());b=bars();b[0].update(open=100.,high=10000.,low=1.,close=500.)
    right=right_svg(b,100.,100.)
    assert a==left_svg(prefix()) and b'T+1 open hypothetical fill' in right and b'independent' in right

@pytest.mark.parametrize('kind',['missing_entry','missing_later','zero_entry','split','double','gap_target','gap_adverse','target','adverse','neither'])
def test_outcome_boundaries(kind):
    b=bars();flags=[]
    if kind=='missing_entry':b[0]=None
    if kind=='missing_later':b[4]=None
    if kind=='zero_entry':b[0]['volume']=0.
    if kind=='split':flags=['corporate_split_horizon_unsupported']
    if kind=='double':b[0].update(high=106.,low=96.)
    if kind=='gap_target':b[1].update(open=106.,high=107.,low=96.,close=106.)
    if kind=='gap_adverse':b[1].update(open=96.,high=107.,low=95.,close=96.)
    if kind=='target':b[0]['high']=106.
    if kind=='adverse':b[0]['low']=96.
    y=outcome(b,100.,HASH,flags,prior_low=98.)
    expected={'missing_entry':('unavailable','not_evaluable'),'missing_later':('censored','not_evaluable'),'zero_entry':('unavailable','not_evaluable'),'split':('unavailable','not_evaluable'),'double':('ambiguous','both_same_bar'),'gap_target':('available','target_first'),'gap_adverse':('available','adverse_first'),'target':('available','target_first'),'adverse':('available','adverse_first'),'neither':('available','neither_hit')}
    assert (y['status'],y['event'])==expected[kind]
    if kind=='double':assert y['conservative_event']=='adverse_first'
    if kind=='neither':assert not y['new_low'] and y['returns']['1']==pytest.approx(.01)

@pytest.mark.parametrize('bad',[float('nan'),float('inf'),-1.,0.])
def test_bad_future_price_rejected(bad):
    b=bars();b[0]['open']=bad
    with pytest.raises(ValueError):outcome(b,100.,HASH)

def test_future_reader_does_not_query_prices_across_split():
    class Result:
        def df(self):return pd.DataFrame({'date':pd.bdate_range('2024-08-29',periods=10)})
    class Connection:
        def execute(self,sql,args):
            assert 'FROM sessions' in sql,'post-boundary price read forbidden'
            return Result()
    class Core:connection=Connection()
    class DB:core=Core();profile={'semantics':{'frozen_splits':{'train':['2021-09-01','2024-08-29']}}}
    b,f,h=read_future(DB(),{'decision_date':'2024-08-28','split_assignment':'train'})
    assert all(v is None for v in b) and f==['horizon_crosses_split']

@pytest.mark.parametrize('split',['test','fresh_oos','unknown'])
def test_future_test_fresh_refused(split):
    with pytest.raises(ValueError):read_future(None,{'decision_date':'2025-01-01','split_assignment':split})

def test_before_save_and_before_reveal_blocked(store):
    r=human(store)
    with pytest.raises(GateError):store.right(r['task_id'],'human',1)
    with pytest.raises(GateError):store.reveal(r['task_id'],'human',1)
    store.skip(r['task_id'],'human',1)
    with pytest.raises(GateError):store.right(r['task_id'],'human',1)
    store.save(r['task_id'],'human',1,request(r))
    with pytest.raises(GateError):store.right(r['task_id'],'human',1)
    store.reveal(r['task_id'],'human',1)
    assert store.right(r['task_id'],'human',1)['Y_future']['horizon']==10

def test_right_is_per_annotator(store):
    r=human(store);store.save(r['task_id'],'human',1,request(r));store.reveal(r['task_id'],'human',1)
    with pytest.raises(GateError):store.right(r['task_id'],'human',2)

def test_future_files_never_read_by_stage_A(store,monkeypatch):
    original=Path.read_bytes
    def guarded(path):
        if 'right' in path.parts:raise AssertionError('future read in Stage A')
        return original(path)
    monkeypatch.setattr(Path,'read_bytes',guarded)
    a=store.left(human(store)['task_id'],'human',1)
    assert not {'Y_future','right_hash','security_id','decision_date','outcome_status'}&a.keys()

def test_first_blind_is_immutable_after_reveal(store):
    r=human(store);first=store.save(r['task_id'],'human',1,request(r));store.reveal(r['task_id'],'human',1)
    later=request(r);later.update(observe='不观察',revision_reason='review changed my view')
    store.save(r['task_id'],'human',1,later)
    assert store.left(r['task_id'],'human',1)['blind_first']==first
    assert [a['phase'] for a in store.export('human',1)['annotations']]==['blind','post_reveal_revision']

def test_revision_reason_and_stale_write(store):
    r=human(store);store.save(r['task_id'],'human',1,request(r))
    with pytest.raises(GateError):store.save(r['task_id'],'human',1,request(r))
    store.reveal(r['task_id'],'human',1)
    with pytest.raises(GateError):store.save(r['task_id'],'human',1,request(r))

def test_repeat_after_reveal_is_contaminated(store):
    a,b=[r for r in store.tasks.values() if r['origin']=='human'];store.save(a['task_id'],'human',1,request(a));store.reveal(a['task_id'],'human',1)
    ann=store.save(b['task_id'],'human',1,request(b));assert ann['contaminated_retest']

def test_clean_repeat_before_either_reveal(store):
    a,b=[r for r in store.tasks.values() if r['origin']=='human']
    assert not store.save(a['task_id'],'human',1,request(a))['contaminated_retest']
    assert not store.save(b['task_id'],'human',1,request(b))['contaminated_retest']

def test_review_must_follow_reveal_and_cannot_be_blind(store):
    r=human(store);p={'version':'h-review-v3','task_hash':r['task_hash'],'expected_revision':0,'reasons':['入场偏贵'],'note':''}
    with pytest.raises(GateError):store.save(r['task_id'],'human',1,p,review=True)
    store.save(r['task_id'],'human',1,request(r));store.reveal(r['task_id'],'human',1)
    assert store.save(r['task_id'],'human',1,p,review=True)['phase']=='review'
    with pytest.raises(ValueError):store.save(r['task_id'],'human',1,p)

@pytest.mark.parametrize('problem',['wrong_task','wrong_origin','wrong_hash','wrong_choice','wrong_version','future_field'])
def test_foreign_and_invalid_inputs_rejected(store,problem):
    r=human(store);tid=r['task_id'];origin='human';p=request(r)
    if problem=='wrong_task':tid='f'*24
    if problem=='wrong_origin':origin='smoke'
    if problem=='wrong_hash':p['task_hash']='c'*64
    if problem=='wrong_choice':p['observe']='machine says buy'
    if problem=='wrong_version':p['version']='v1'
    if problem=='future_field':p['Y_future']=.10
    with pytest.raises(ValueError):store.save(tid,origin,1,p)
    assert not store.export('human',1)['annotations']

def test_strict_roundtrip_idempotence_and_namespace(store,tmp_path):
    r=human(store);store.save(r['task_id'],'human',1,request(r));p=tmp_path/'export.json';p.write_text(encode(store.export('human',1)),encoding='utf-8')
    assert import_export(store.root,p,'human')['rows']['blind']==1
    assert import_export(store.root,p,'human')['rows']['blind']==1
    with pytest.raises(GateError):import_export(store.root,p,'smoke')
    assert len(store.export('human',1)['annotations'])==1
    assert not store.export('smoke',1)['annotations']

@pytest.mark.parametrize('tamper',['task','choice','version','revision','event'])
def test_export_forgery_rejected(store,tmp_path,tamper):
    r=human(store);store.save(r['task_id'],'human',1,request(r));e=store.export('human',1)
    if tamper=='task':e['annotations'][0]['task_id']='f'*24
    if tamper=='choice':e['annotations'][0]['payload']['observe']='invalid'
    if tamper=='version':e['annotations'][0]['payload']['version']='invalid'
    if tamper=='revision':e['annotations'][0]['revision']=2
    if tamper=='event':e['events']=[]
    p=tmp_path/'bad.json';p.write_text(encode(e),encoding='utf-8')
    with pytest.raises(ValueError):import_export(store.root,p,'human')

def test_left_and_future_hash_checks(store):
    r=human(store);p=store.root/'left'/f"{r['group']}.svg";p.write_bytes(b'bad')
    with pytest.raises(GateError):store.left(r['task_id'],'human',1)

def test_covert_active_svg_rejected():
    with pytest.raises(ValueError):geometry_hash(b'<svg><script>secret</script></svg>')
    with pytest.raises(ValueError):geometry_hash(b'<svg><rect onclick="evil()"/></svg>')

def test_repeat_statistics_excludes_revealed_retest(store):
    from radar.vision.dual_store import repeat_statistics
    a,b=[r for r in store.tasks.values() if r['origin']=='human']
    store.save(a['task_id'],'human',1,request(a));store.reveal(a['task_id'],'human',1)
    store.save(b['task_id'],'human',1,request(b))
    result=repeat_statistics(store,store.export('human',1))
    assert result['clean_pairs']==0 and result['contaminated_retests_excluded']==1

def test_changed_future_has_identical_stage_A_response(store):
    r=human(store);before=encode(store.left(r['task_id'],'human',1))
    for suffix in ('json','svg'):
        (store.root/'right'/f"{r['group']}.{suffix}").write_bytes(b'dramatically changed future')
    assert encode(store.left(r['task_id'],'human',1))==before

@pytest.mark.parametrize('requested',['../.local/right.svg','%2e%2e%2f.local%2fright.svg'])
def test_local_files_traversal_has_opaque_rejection(tmp_path,requested):
    from radar.vision.dual_http import guard_local_files
    headers=[]
    def forbidden_call(*args):raise AssertionError('should not reach legacy file server')
    app=guard_local_files(forbidden_call,tmp_path/'data')
    result=app({'PATH_INFO':'/data/local-files/','QUERY_STRING':'d='+requested},lambda status,h:headers.append(status))
    assert headers==['403 Forbidden'] and result==[b'Forbidden local file']

def test_local_files_existing_pilot_route_preserved(tmp_path):
    from radar.vision.dual_http import guard_local_files
    app=guard_local_files(lambda e,s:[b'existing pilot'],tmp_path/'data')
    assert app({'PATH_INFO':'/data/local-files/','QUERY_STRING':'d=vision-research/pilot-v1/img.png'},None)==[b'existing pilot']

def test_same_user_cross_namespace_future_exposure_is_contaminated(store):
    s=next(r for r in store.tasks.values() if r['origin']=='smoke');h=human(store)
    store.save(s['task_id'],'smoke',1,request(s));store.reveal(s['task_id'],'smoke',1)
    assert store.left(h['task_id'],'human',1)['contaminated_retest']
    assert not store.left(h['task_id'],'human',2)['contaminated_retest']
    assert not store.export('human',1)['annotations']
    assert all(t['contaminated_retest'] for t in store.list_tasks('human',1))
