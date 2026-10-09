"""Small transactional annotation/event store, mounted in existing Label Studio.

No public filesystem route and no future-reader dependency in Stage A.
"""
from contextlib import contextmanager
from datetime import datetime,timezone
from hashlib import sha256
from pathlib import Path
import json,sqlite3
from uuid import uuid4
from .dual_contracts import Annotation,BlindRequest,ReviewRequest,FutureOutcome

class GateError(ValueError):pass

def encode(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
def hash_bytes(raw):return sha256(raw).hexdigest()

class DualStore:
    def __init__(self,directory):
        self.root=Path(directory);raw=(self.root/'manifest.json').read_bytes();receipt=json.loads((self.root/'receipt.json').read_text())
        if hash_bytes(raw)!=receipt['manifest_hash']:raise GateError('manifest drift')
        self.manifest_hash=receipt['manifest_hash'];self.tasks={r['task_id']:r for r in json.loads(raw)}
        with self.connection() as c:
            c.executescript('''CREATE TABLE IF NOT EXISTS annotations (seq INTEGER PRIMARY KEY AUTOINCREMENT,task TEXT,user INTEGER,origin TEXT,phase TEXT,revision INTEGER,body TEXT, UNIQUE(task,user,phase,revision));
                CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY AUTOINCREMENT,task TEXT,user INTEGER,origin TEXT,group_id TEXT,kind TEXT,created_at TEXT,body TEXT);''')

    @contextmanager
    def connection(self,write=False):
        c=sqlite3.connect(self.root/'annotations.sqlite3',timeout=30);c.row_factory=sqlite3.Row
        try:
            if write:c.execute('BEGIN IMMEDIATE')
            yield c
            c.commit()
        except Exception:c.rollback();raise
        finally:c.close()

    def task(self,tid,origin):
        r=self.tasks.get(tid)
        if origin not in ('human','smoke') or r is None or r['origin']!=origin:raise GateError('foreign task/namespace')
        return r

    def revealed(self,c,tid,user):return c.execute("SELECT 1 FROM events WHERE task=? AND user=? AND kind='future_revealed'",[tid,user]).fetchone() is not None
    def contaminated(self,c,r,user):return c.execute("SELECT 1 FROM events WHERE group_id=? AND user=? AND kind='future_revealed' AND task<>?",[r['group'],user,r['task_id']]).fetchone() is not None
    def event(self,c,r,user,kind,body=None):
        c.execute('INSERT INTO events(task,user,origin,group_id,kind,created_at,body) VALUES (?,?,?,?,?,?,?)',[r['task_id'],user,r['origin'],r['group'],kind,datetime.now(timezone.utc).isoformat(),encode(body or {})])
    def annotations(self,c,tid,user):return [json.loads(x['body']) for x in c.execute('SELECT body FROM annotations WHERE task=? AND user=? ORDER BY seq',[tid,user])]

    def list_tasks(self,origin,user):
        with self.connection() as c:
            out=[]
            for r in self.tasks.values():
                if r['origin']!=origin:continue
                anns=self.annotations(c,r['task_id'],user)
                out.append({'task_id':r['task_id'],'saved':any(a['phase']=='blind' for a in anns),'revealed':self.revealed(c,r['task_id'],user),'reviewed':any(a['phase']=='review' for a in anns),'contaminated_retest':self.contaminated(c,r,user)})
            # Same-account automated browser exposure is conservatively audited,
            # even across smoke/human namespaces; labels still remain isolated.
            if origin=='human':out.sort(key=lambda t:t['contaminated_retest'])
            return out

    def left(self,tid,origin,user):
        r=self.task(tid,origin);svg=(self.root/'left'/f"{r['group']}.svg").read_bytes()
        if hash_bytes(svg)!=r['X_left_svg']['svg_sha256']:raise GateError('left drift')
        with self.connection() as c:
            anns=[a for a in self.annotations(c,tid,user) if a['phase']=='blind']
            # No Y/read_future/right filesystem/identity metadata in this response.
            return {'task_id':tid,'task_hash':r['task_hash'],'left_svg':svg.decode(),'svg_sha256':hash_bytes(svg),'revision':len(anns),'blind_first':anns[0] if anns else None,'blind_latest':anns[-1] if anns else None,'revealed':self.revealed(c,tid,user),'contaminated_retest':self.contaminated(c,r,user)}

    def save(self,tid,origin,user,payload,review=False):
        r=self.task(tid,origin);p=(ReviewRequest if review else BlindRequest).model_validate(payload)
        if p.task_hash!=r['task_hash']:raise GateError('wrong task hash')
        with self.connection(True) as c:
            seen=self.revealed(c,tid,user);phase='review' if review else ('post_reveal_revision' if seen else 'blind')
            if review and not seen:raise GateError('review requires reveal')
            previous=[a for a in self.annotations(c,tid,user) if a['phase']==phase]
            if len(previous)!=p.expected_revision:raise GateError('stale revision')
            if phase=='post_reveal_revision' and not p.revision_reason.strip():raise GateError('post-reveal revision reason required')
            a=Annotation(task_id=tid,annotation_id=uuid4().hex,origin=origin,user_id=user,revision=len(previous)+1,created_at=datetime.now(timezone.utc).isoformat(),phase=phase,contaminated_retest=self.contaminated(c,r,user),payload=p).model_dump()
            c.execute('INSERT INTO annotations(task,user,origin,phase,revision,body) VALUES(?,?,?,?,?,?)',[tid,user,origin,phase,a['revision'],encode(a)])
            self.event(c,r,user,{'blind':'blind_saved','review':'review_saved','post_reveal_revision':'revision_after_reveal'}[phase],{'annotation_id':a['annotation_id']})
            return a

    def reveal(self,tid,origin,user):
        r=self.task(tid,origin)
        with self.connection(True) as c:
            if not any(a['phase']=='blind' for a in self.annotations(c,tid,user)):raise GateError('persisted blind decision required')
            if not self.revealed(c,tid,user):self.event(c,r,user,'future_revealed')
        return {'revealed':True}

    def right(self,tid,origin,user):
        r=self.task(tid,origin)
        with self.connection() as c:
            if not self.revealed(c,tid,user) or not any(a['phase']=='blind' for a in self.annotations(c,tid,user)):raise GateError('future locked')
            reviews=[a for a in self.annotations(c,tid,user) if a['phase']=='review']
            revisions=[a for a in self.annotations(c,tid,user) if a['phase']=='post_reveal_revision']
        raw=(self.root/'right'/f"{r['group']}.json").read_bytes();svg=(self.root/'right'/f"{r['group']}.svg").read_bytes()
        if hash_bytes(raw)!=r['future_json_hash'] or hash_bytes(svg)!=r['right_hash']:raise GateError('future drift')
        data=json.loads(raw);FutureOutcome.model_validate(data['Y_future'])
        return {'right_svg':svg.decode(),'Y_future':data['Y_future'],'review_revision':len(reviews),'review_latest':reviews[-1] if reviews else None,'post_reveal_revision':len(revisions),'post_reveal_latest':revisions[-1] if revisions else None}

    def skip(self,tid,origin,user):
        r=self.task(tid,origin)
        with self.connection(True) as c:self.event(c,r,user,'skipped')
        return {'skipped':True}

    def export(self,origin,user):
        if origin not in ('human','smoke'):raise GateError('origin required')
        with self.connection() as c:
            annotations=[json.loads(x['body']) for x in c.execute('SELECT body FROM annotations WHERE origin=? AND user=? ORDER BY seq',[origin,user])]
            events=[dict(x) for x in c.execute('SELECT seq,task,user,origin,kind,created_at,body FROM events WHERE origin=? AND user=? ORDER BY seq',[origin,user])]
        return {'version':'dual-export-v3','origin':origin,'user_id':user,'manifest_hash':self.manifest_hash,'annotations':annotations,'events':events}

def import_export(directory,path,origin):
    """Verify against authoritative persisted ledger; never mutate the annotation DB."""
    import pandas as pd
    root=Path(directory);raw=Path(path).read_bytes();data=json.loads(raw);store=DualStore(root)
    if set(data)!={'version','origin','user_id','manifest_hash','annotations','events'} or data['version']!='dual-export-v3' or data['origin']!=origin or data['manifest_hash']!=store.manifest_hash:raise GateError('invalid export contract')
    for a in data['annotations']:
        Annotation.model_validate(a);store.task(a['task_id'],origin)
        if a['origin']!=origin:raise GateError('namespace conflict')
    if encode(data)!=encode(store.export(origin,data['user_id'])):raise GateError('export differs from persisted authoritative history')
    out=root/'labels'/origin;out.mkdir(parents=True,exist_ok=True);archive=out/(hash_bytes(raw)+'.json')
    if archive.exists() and archive.read_bytes()!=raw:raise GateError('archive collision')
    if not archive.exists():archive.write_bytes(raw)
    # All revisions retained; each label channel has a separate Parquet artifact.
    counts={}
    for phase in ('blind','review','post_reveal_revision'):
        rows=[{**{k:v for k,v in a.items() if k!='payload'},'payload':encode(a['payload'])} for a in data['annotations'] if a['phase']==phase]
        pd.DataFrame(rows).to_parquet(out/(phase+'.parquet'),index=False);counts[phase]=len(rows)
    return {'origin':origin,'rows':counts,'raw_hash':hash_bytes(raw),'repeat_statistics':repeat_statistics(store,data),'human_consistency_claim':False}

def repeat_statistics(store,export):
    first={}
    for a in export['annotations']:
        if a['phase']=='blind' and a['revision']==1:first[a['task_id']]=a
    groups={};contaminated=0
    for tid,a in first.items():
        if a['contaminated_retest']:contaminated+=1;continue
        g=store.task(tid,export['origin'])['group'];groups.setdefault(g,[]).append(a)
    pairs=[(v[0],a) for v in groups.values() for a in v[1:]]
    return {'origin':export['origin'],'contaminated_retests_excluded':contaminated,'clean_pairs':len(pairs),
        'observe_agreements':sum(a['payload']['observe']==b['payload']['observe'] for a,b in pairs),
        'entry_agreements':sum(a['payload']['entry']==b['payload']['entry'] for a,b in pairs),
        'smoke_is_not_human_consistency':export['origin']=='smoke'}
