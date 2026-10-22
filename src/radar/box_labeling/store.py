"""Private immutable label revisions and numeric-only export."""
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from hashlib import sha256
import json
import sqlite3
import numpy as np

DATASET_VERSION = 'box-label-tasks-v1'


def packed(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def digest(value):return sha256(value).hexdigest()

LABEL_VERSION = 'box-structure-label-v1'
SHAPES = {'BOX','NOT_BOX','UNCERTAIN'}
POSITIONS = {'LOWER','MIDDLE','UPPER','BREAKDOWN','UNCERTAIN'}
CONFIDENCES = {'HIGH','MEDIUM','LOW'}
REASONS = {'repeated_support_zone','repeated_resistance_zone','clean_oscillation',
           'noisy_but_intact','transient_undercut_recovered','boundary_instability',
           'insufficient_oscillation','monotonic_trend','structural_breakdown',
           'ambiguous_multiscale_context'}


class GateError(ValueError):
    pass


def validate(payload):
    if set(payload) != {'shape','position','confidence','reasons','note','expected_revision','label_version'}:
        raise GateError('invalid label fields')
    if payload['label_version'] != LABEL_VERSION or payload['shape'] not in SHAPES or payload['position'] not in POSITIONS or payload['confidence'] not in CONFIDENCES:
        raise GateError('invalid label choice/version')
    if not isinstance(payload['reasons'],list) or len(set(payload['reasons'])) != len(payload['reasons']) or not set(payload['reasons']) <= REASONS:
        raise GateError('invalid reason')
    if not isinstance(payload['note'],str) or len(payload['note'])>300:
        raise GateError('invalid note')
    if type(payload['expected_revision']) is not int or payload['expected_revision']<0:
        raise GateError('invalid revision')
    return payload


class BoxStore:
    label_version = LABEL_VERSION
    annotation_prefix = 'annotations'
    label_fields = ('shape','position','confidence','reasons','note')
    validator = staticmethod(validate)
    def __init__(self, root, origin='human'):
        if origin not in ('human','smoke'):
            raise GateError('invalid origin')
        self.root=Path(root).resolve(); self.origin=origin
        raw=(self.root/'manifest.json').read_bytes()
        receipt=json.loads((self.root/'receipt.json').read_bytes())
        if receipt['version'] != DATASET_VERSION or receipt['manifest_hash'] != digest(raw):
            raise GateError('manifest drift')
        self.receipt=receipt
        self.rows=json.loads(raw)
        self.tasks={r['task_id']:r for r in self.rows}
        if len(self.tasks)!=len(self.rows):raise GateError('duplicate task ID')
        with self.connection() as c:
            c.execute('''CREATE TABLE IF NOT EXISTS annotation
                (id TEXT PRIMARY KEY, task TEXT NOT NULL, user INTEGER NOT NULL,
                 revision INTEGER NOT NULL, created_at TEXT NOT NULL, body TEXT NOT NULL,
                 UNIQUE(task,user,revision))''')
            c.execute('''CREATE TABLE IF NOT EXISTS event
                (id INTEGER PRIMARY KEY AUTOINCREMENT, task TEXT NOT NULL, user INTEGER NOT NULL,
                 kind TEXT NOT NULL, created_at TEXT NOT NULL)''')

    @contextmanager
    def connection(self, write=False):
        c=sqlite3.connect(self.root/f'{self.annotation_prefix}-{self.origin}.sqlite3',timeout=30)
        c.row_factory=sqlite3.Row
        try:
            if write:c.execute('BEGIN IMMEDIATE')
            yield c;c.commit()
        except Exception:c.rollback();raise
        finally:c.close()

    def _task(self,tid):
        try:return self.tasks[tid]
        except KeyError:raise GateError('unknown task') from None

    def _latest(self,c,tid,user):
        row=c.execute('SELECT revision,body FROM annotation WHERE task=? AND user=? ORDER BY revision DESC LIMIT 1',(tid,user)).fetchone()
        return (row['revision'],json.loads(row['body'])) if row else (0,None)

    def list(self,user):
        with self.connection() as c:
            return [{'task_id':r['task_id'],'saved':self._latest(c,r['task_id'],user)[0]>0}
                    for r in self.rows]

    def task(self,tid,user):
        r=self._task(tid)
        charts={}
        for scale,item in r['scales'].items():
            raw=(self.root/'charts'/item['chart_file']).read_bytes()
            if digest(raw)!=item['chart_hash']:raise GateError('chart drift')
            charts[scale]=raw.decode()
        with self.connection() as c:rev,latest=self._latest(c,tid,user)
        # This is the complete human-visible payload. No private identity, score, date, split or future.
        return {'task_id':tid,'charts':charts,'coverage':{k:{'bars':v['length'],'target':{'daily':42,'weekly':52,'monthly':48}[k]}
                    for k,v in r['scales'].items()},'revision':rev,
                'label':latest['label'] if latest else None,'label_version':self.label_version}

    def save(self,tid,user,payload):
        r=self._task(tid);self.validator(payload)
        with self.connection(True) as c:
            rev,_=self._latest(c,tid,user)
            if rev!=payload['expected_revision']:raise GateError('stale annotation revision')
            record={'annotation_id':uuid4().hex,'task_id':tid,'user_id':user,
                    'revision':rev+1,'created_at':datetime.now(timezone.utc).isoformat(),
                    'label_version':self.label_version,'dataset_version':DATASET_VERSION,
                    'candidate_plugin_version':r['candidate_plugin_version'],
                    'config_hash':r['config_hash'],'decision_date':r['decision_date'],
                    'security_id':r['security_id'],
                    'tensor_hashes':{k:v['tensor_hash'] for k,v in r['scales'].items()},
                    'render_hashes':{k:v['chart_hash'] for k,v in r['scales'].items()},
                    'label':{k:payload[k] for k in self.label_fields}}
            c.execute('INSERT INTO annotation VALUES (?,?,?,?,?,?)',
                      (record['annotation_id'],tid,user,rev+1,record['created_at'],packed(record).decode()))
            return {'task_id':tid,'revision':rev+1,'label':record['label']}

    def skip(self,tid,user):
        self._task(tid)
        with self.connection(True) as c:
            c.execute('INSERT INTO event(task,user,kind,created_at) VALUES (?,?,?,?)',
                      (tid,user,'skip',datetime.now(timezone.utc).isoformat()))
        return {'skipped':True}

    def export_numeric(self,user,output):
        """Read authoritative labels and tensor files. Never look up outcomes/market DB."""
        examples=[]
        with self.connection() as c:
            for r in self.rows:
                rev,latest=self._latest(c,r['task_id'],user)
                if not rev:continue
                refs={}
                for scale,meta in r['scales'].items():
                    tensor=np.load(self.root/'numeric'/meta['tensor_file'],allow_pickle=False)
                    if digest((self.root/'raw'/meta['raw_file']).read_bytes()) != meta['raw_hash']:
                        raise GateError('raw numeric history drift')
                    if digest(tensor.tobytes()) != meta['tensor_hash'] or tensor.shape != (meta['length'],5):
                        raise GateError('numeric tensor drift')
                    refs[scale]={'path':str((self.root/'numeric'/meta['tensor_file']).resolve()),
                                 'sha256':meta['tensor_hash'],'available':meta['available'],
                                 'length':meta['length']}
                examples.append({'sample_id':r['task_id'],'security_id':r['security_id'],
                    'decision_date':r['decision_date'],'split':r['split'],'scales':refs,
                    'shape_label':latest['label']['shape'],
                    'position_label':latest['label']['position'],
                    'confidence':latest['label']['confidence'],
                    'dataset_version':DATASET_VERSION,
                    'normalization_version':r['normalization_version'],
                    'candidate_plugin_version':r['candidate_plugin_version'],
                    'source_hashes':{k:v['raw_hash'] for k,v in r['scales'].items()},
                    'label_revision':rev})
        result={'version':'box-numeric-export-v1','origin':self.origin,
                'manifest_hash':self.receipt['manifest_hash'],'examples':examples}
        output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
        if output.exists() and output.read_bytes()!=packed(result):
            raise GateError('export path has different content; choose a new path')
        output.write_bytes(packed(result))
        return {'examples':len(examples),'sha256':digest(output.read_bytes()),'path':str(output)}
