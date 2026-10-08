"""Fail-closed verification of private pilot artifacts and visible task mapping."""
from hashlib import sha256
import json
from pathlib import Path
import re
import pandas as pd
from PIL import Image
from radar.pit.shape import canonical_hash
from .contracts import validate_sample_manifest, validate_pair_manifest

def file_hash(path):
    h=sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def _inside(bundle,relative):
    p=(bundle/relative).resolve()
    if not p.is_relative_to(bundle.resolve()):raise ValueError('artifact escaped bundle')
    return p

def verify(bundle):
    bundle=Path(bundle).resolve()
    manifest=validate_sample_manifest(pd.read_parquet(bundle/'sample-manifest.parquet'))
    pairs=validate_pair_manifest(pd.read_parquet(bundle/'pair-manifest.parquet'))
    receipt=json.loads((bundle/'bundle-receipt.json').read_text(encoding='utf-8'))
    for flag in ['future_outcomes_read','strategy2_scores_read','unknown_membership_included']:
        if receipt.get(flag) is not False:raise ValueError('forbidden research inputs or membership')
    if receipt.get('source_read_only_and_unchanged') is not True:raise ValueError('source read-only proof missing')
    for name in ['sample-manifest.parquet','pair-manifest.parquet','label-studio-single-tasks.json','label-studio-pair-tasks.json']:
        if file_hash(bundle/name)!=receipt.get('artifact_hashes',{}).get(name):raise ValueError('artifact hash mismatch: '+name)
    singles=manifest[manifest.task_kind=='single']; repeats=manifest[manifest.task_kind=='single_repeat']
    if singles.security_id.duplicated().any() or singles.blind_id.duplicated().any():raise ValueError('unique samples must use unique securities and images')
    expected={'single_unique':len(singles),'single_repeats':len(repeats),'unique_securities':singles.security_id.nunique(),'pairs':len(pairs)}
    if any(receipt.get(k)!=v for k,v in expected.items()):raise ValueError('receipt count mismatch')
    by_task=manifest.set_index('task_id'); by_blind=singles.set_index('blind_id')
    if {p.name for p in (bundle/'images').glob('*.png')}!={r.blind_id+'.png' for r in singles.itertuples()}:
        raise ValueError('image folder/manifest mismatch')
    for row in repeats.itertuples():
        if row.repeat_group!=row.blind_id or row.blind_id not in by_blind.index:raise ValueError('repeat has no matching original')
        original=by_blind.loc[row.blind_id]
        for col in ['security_id','decision_date','window_length','image_path','image_sha256','ohlcv_hash','normalized_hash','split_assignment']:
            if getattr(row,col)!=original[col]:raise ValueError('repeat content differs from original')
    dimensions=set()
    for row in singles.itertuples():
        if not re.fullmatch('[0-9a-f]{24}',row.blind_id):raise ValueError('non-opaque image ID')
        if row.image_path!=f'images/{row.blind_id}.png':raise ValueError('image path identity leak')
        image=_inside(bundle,row.image_path)
        if not image.is_file() or file_hash(image)!=row.image_sha256:raise ValueError('image hash mismatch')
        with Image.open(image) as png:
            dimensions.add(png.size)
            if set(png.info)-{'Software','Renderer','dpi'}:raise ValueError('unapproved PNG metadata')
            if png.info.get('Renderer')!=row.renderer_version:raise ValueError('renderer identity differs')
        for suffix,hash_field in [('ohlcv','ohlcv_hash'),('normalized','normalized_hash')]:
            f=pd.read_parquet(_inside(bundle,f'windows/{row.blind_id}-{suffix}.parquet'))
            if len(f)!=row.window_length or pd.to_datetime(f.date).max()!=row.decision_date:raise ValueError('window length or decision cutoff mismatch')
            if not f.date.is_monotonic_increasing or f.date.duplicated().any():raise ValueError('non-canonical window order')
            if canonical_hash(f)!=getattr(row,hash_field):raise ValueError('canonical window hash mismatch')
            allowed={'date','open','high','low','close','volume'}
            if suffix=='ohlcv':allowed|={'symbol','basis','source'}
            if set(f)-allowed:raise ValueError('future/identity field entered canonical input')
    if len(dimensions)!=1:raise ValueError('inconsistent image dimensions')
    identities=set()
    for r in pairs.itertuples():
        if r.left_task_id not in by_task.index or r.right_task_id not in by_task.index:raise ValueError('foreign pair reference')
        left,right=by_task.loc[r.left_task_id],by_task.loc[r.right_task_id]
        if left.security_id==right.security_id:raise ValueError('same-security pair')
        if left.task_kind!='single' or right.task_kind!='single':raise ValueError('repeat used as pair base')
        for side,sample in [('left',left),('right',right)]:
            if getattr(r,side+'_blind_id')!=sample.blind_id or r.window_length!=sample.window_length or r.split_assignment!=sample.split_assignment:raise ValueError('pair manifest content mismatch')
        identity=tuple(sorted([r.left_blind_id,r.right_blind_id]))
        if identity in identities:raise ValueError('duplicate unordered pair')
        identities.add(identity)
    prefix=receipt['local_files_prefix']
    if not prefix.startswith('/data/local-files/?d=') or '..' in prefix:raise ValueError('invalid local image prefix')
    for filename,key,rows,fields in [('label-studio-single-tasks.json','task_id',by_task,{'task_id','image'}),('label-studio-pair-tasks.json','pair_id',pairs.set_index('pair_id'),{'pair_id','image_a','image_b'})]:
        tasks=json.loads((bundle/filename).read_text(encoding='utf-8'));ids=[]
        for task in tasks:
            if set(task)!={'data'} or set(task['data'])!=fields:raise ValueError('visible identity/outcome fields')
            data=task['data'];ident=data[key];ids.append(ident)
            if not re.fullmatch(('single-' if key=='task_id' else 'pair-')+'[0-9a-f]{24}',ident):raise ValueError('non-opaque task ID')
            if ident not in rows.index:raise ValueError('foreign task')
            row=rows.loc[ident]
            paths=({'image':row.image_path} if key=='task_id' else {'image_a':by_task.loc[row.left_task_id].image_path,'image_b':by_task.loc[row.right_task_id].image_path})
            if any(data[k]!=prefix+'/'+path for k,path in paths.items()):raise ValueError('task image mapping mismatch')
        if len(ids)!=len(set(ids)) or set(ids)!=set(rows.index):raise ValueError('task/manifest cardinality mismatch')
    return {'status':'PASS','single_tasks':len(manifest),'pairs':len(pairs),'unique_images':len(singles),'repeats':len(repeats),'splits':sorted(manifest.split_assignment.unique()),'image_hashes_verified':len(manifest),'canonical_windows_verified':2*len(singles),'visible_identity_or_outcome_fields':0,'dimensions':list(dimensions.pop()),'source_read_only_and_unchanged':True}
