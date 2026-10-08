"""Read-only reference/schema inventory. This command never deletes assets."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import os
import re
from pathlib import Path
import subprocess

import duckdb

from radar.pit.features import file_hash


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def cleanup_eligible(asset,root):
    """Advisory preflight only; never executes or bypasses a delete policy."""
    root=Path(root).resolve();path=root/asset['path']
    if asset.get('recommended_action')!='DELETE_CANDIDATE' or asset.get('category') not in ('D','E'):
        return False
    if asset.get('current_references') or asset.get('strict_pit_evidence_dependency'):
        return False
    if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(root):return False
    if (path.parent/'manifest.json').exists():return False
    if not asset.get('reproducible') or asset.get('source_still_available') is not True:return False
    return file_hash(path)==asset['sha256']


def files_under(root):
    for base,dirs,files in os.walk(root,followlinks=False):
        dirs[:]=[d for d in dirs if not (Path(base)/d).is_symlink()]
        for name in files:
            p=Path(base)/name
            if not p.is_symlink():yield p


def sizes(root):
    out=Counter(repo_bytes=0,data_bytes=0,archive_bytes=0,temp_cache_bytes=0)
    for p in files_under(root):
        n=p.stat().st_size;out['repo_bytes']+=n
        rel=p.relative_to(root).as_posix()
        if rel.startswith('data/'):out['data_bytes']+=n
        if rel.startswith(('archive/','scripts/archive/')):out['archive_bytes']+=n
        if '.tmp/' in rel or rel.endswith(('.tmp','.wal')):out['temp_cache_bytes']+=n
    return dict(out)


def inventory(root):
    root=Path(root).resolve()
    tracked=subprocess.check_output(['git','ls-files','-z'],cwd=root).decode('utf-8').split('\0')
    texts={}
    for rel in tracked:
        p=root/rel
        if p.is_file() and p.suffix in ('.py','.md','.json','.yaml','.toml','.ipynb') and p.stat().st_size<10_000_000:
            texts[rel]=p.read_text(encoding='utf-8',errors='replace')
    # Include generated manifests/pointers: references there are real indirect
    # dependencies, even though data stores are intentionally ignored by Git.
    for p in (root/'data').rglob('*.json'):
        if p.stat().st_size<2_000_000 and any(k in p.name for k in ('manifest','current','receipt','source-lock')):
            texts[p.relative_to(root).as_posix()]=p.read_text(encoding='utf-8',errors='replace')
    # Invert references once; repeated scans of multi-megabyte manifests for
    # every tiny file would turn a conservative inventory into excessive IO.
    from collections import defaultdict
    path_refs=defaultdict(set);version_refs=defaultdict(set);name_refs=defaultdict(set)
    for owner,text in texts.items():
        normalized=text.replace('\\\\','/').replace('\\','/')
        for token in re.findall(r'data/[^\s\"\'`<>|,\]\)\}]+',normalized):path_refs[token.rstrip('.;')].add(owner)
        for token in set(re.findall(r'\b[0-9a-f]{64}\b',text)):version_refs[token].add(owner)
        for token in set(re.findall(r'[\w.-]+\.(?:py|md|json|csv|raw|duckdb|sqlite3?|parquet|ipynb|yaml)',text)):name_refs[token].add(owner)
    sp=read(root/'data/pit/shape-research/current.json');hp=read(root/'data/pit/construction/current.json')
    shape=Path(sp['directory']);hist=Path(hp['directory'])
    sm=read(shape/'manifest.json');hm=read(hist/'manifest.json')
    active={str((shape/'shape.duckdb').resolve()),str((hist/'historical.duckdb').resolve())}
    for m in (sm,hm):
        for v in m.get('inputs',{}).values():
            if isinstance(v,dict) and v.get('path'):active.add(str(Path(v['path']).resolve()))
    for name in ('market.duckdb','phase2-research.duckdb','phase2-research-v2-frozen.duckdb','phase2-source-snapshot.duckdb'):
        active.add(str((root/'data'/name).resolve()))
    active.update(str(p.resolve()) for p in (root/'data').glob('security-master*'))
    assets=[];schema=[]
    # Inventory individual DB/metadata assets; very large LEAN/bare-Git trees
    # remain auditable bundles rather than tens of thousands of noisy records.
    candidates=[]
    for p in files_under(root):
        rel=p.relative_to(root).as_posix()
        if rel.startswith(('.git/','.venv/','site/')) or '/.git/' in rel:continue
        if rel.startswith('data/strategy-lab/lean/') or '.git/' in rel:continue
        if rel.startswith('data/') or (rel in tracked and any(k in rel.lower() for k in ('pit','shape','quantconnect','research'))):
            if p.suffix.lower() in ('.duckdb','.sqlite','.sqlite3','.parquet','.csv','.json','.raw','.py','.md','.ipynb','.yaml','.yml','.tmp','.wal','.log'):
                candidates.append(p)
    print(f'Inventory {len(candidates)} assets; hashing bytes and inspecting schemas',flush=True)
    for i,p in enumerate(candidates):
        rel=p.relative_to(root).as_posix();n=p.stat().st_size
        exact=sorted((path_refs[rel] | (version_refs[p.parent.name] if len(p.parent.name)==64 else set()))-{rel})
        generic=sorted(name_refs[p.name]-{rel})[:30]
        shape_dep=str(p.resolve()) in {str((shape/'shape.duckdb').resolve()),*[str(Path(v['path']).resolve()) for v in sm['inputs'].values()]}
        strict_dep=str(p.resolve()) in active or '/raw/' in rel or '/research-grade/' in rel
        category='B';action='KEEP';reason='Audit/provenance or explicit historic reproduction reference'
        if str(p.resolve()) in active or rel.startswith(('data/strategy-lab/','src/','config/')):
            category='A';reason='Active or indirect runtime/build dependency'
        elif '/raw/' in rel:
            category='C';action='KEEP_COLD';reason='Unique raw reference; already isolated from runtime, not worth relocating locked evidence paths'
        elif rel.startswith('data/pit/construction/versions/') and not (p.parent/'manifest.json').exists() and not exact:
            category='E';action='DELETE_CANDIDATE';reason='Unpublished failed construction output; no manifest, no exact consumer, inputs preserved'
        elif rel.startswith('data/pit/shape-research/versions/') and not (p.parent/'manifest.json').exists():
            category='E';action='POLICY_BLOCKED_KEEP';reason='Prior blocked deletion scope; do not retry or bypass approval policy'
            if p.suffix=='.tmp':category='D'
        elif rel.startswith('data/pit/shape-research/versions/') and p.parent!=shape and not exact:
            category='C';action='ARCHIVE_CANDIDATE';reason='Superseded local published Shape snapshot; keep manifest/hash and cold copy for investigation'
        elif rel.startswith('data/') and not exact:
            action='REVIEW_KEEP';reason='No exact reference found, but dynamic/directory consumers or unique source cannot be disproved'
        # Never delete a tracked file or content-addressed evidence raw source.
        if rel in tracked and action=='DELETE_CANDIDATE':category='B';action='KEEP';reason='Git-tracked audit source'
        entry={'path':rel,'type':p.suffix.lstrip('.'),'size':n,'modified_time':datetime.fromtimestamp(p.stat().st_mtime,timezone.utc).isoformat(),
               'sha256':file_hash(p),'current_references':exact,'generic_references':generic,'reference_scope':'Exact path/version plus generated manifests; basename references are conservative hints, not ownership',
               'producer':'build_shape_research.py' if '/shape-research/' in rel else 'build_pit_database.py' if '/construction/versions/' in rel else 'Existing pinned source/pipeline; see references',
               'consumer':exact or generic,'reproducible':category in ('D','E'),'source_still_available':True if category in ('D','E') else 'not assumed',
               'expensive_to_recreate':n>100_000_000,'current_strategy_dependency':category=='A','shape_research_dependency':shape_dep,
               'strict_pit_evidence_dependency':strict_dep,'category':category,'recommended_action':action,'reason':reason}
        assets.append(entry)
        if p.suffix=='.duckdb' and p.is_file():
            try:
                c=duckdb.connect(str(p),read_only=True)
                for name,kind in c.execute("select table_name,table_type from information_schema.tables where table_schema='main'").fetchall():
                    refs=[k for k,t in texts.items() if name in t][:80]
                    count=c.execute('select count(*) from "'+name.replace('"','""')+'"').fetchone()[0] if kind=='BASE TABLE' else None
                    schema.append({'database':rel,'object':name,'type':kind,'row_count':count,'action':'KEEP','reason':'Preserve published immutable DB/hash or failed output as file-level unit; no in-place table deletion','dependency_check':refs,'database_pre_hash':entry['sha256']})
                c.close()
            except Exception as exc:
                schema.append({'database':rel,'object':None,'action':'REVIEW_KEEP','error':str(exc)[:200]})
        elif p.suffix in ('.sqlite','.sqlite3'):
            import sqlite3
            try:
                connection=sqlite3.connect('file:'+p.as_posix()+'?mode=ro',uri=True)
                for name,kind in connection.execute("SELECT name,type FROM sqlite_master WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%'"):
                    count=connection.execute('SELECT count(*) FROM "'+name.replace('"','""')+'"').fetchone()[0] if kind=='table' else None
                    schema.append({'database':rel,'object':name,'type':kind,'row_count':count,'action':'KEEP','reason':'Run registry/audit store; dynamic consumers preserved','dependency_check':exact or generic,'database_pre_hash':entry['sha256']})
                connection.close()
            except Exception as exc:schema.append({'database':rel,'action':'REVIEW_KEEP','error':str(exc)[:200]})
        elif p.suffix=='.parquet':
            import pyarrow.parquet as pq
            try:
                meta=pq.ParquetFile(p)
                schema.append({'database':rel,'object':'parquet','type':'parquet','row_count':meta.metadata.num_rows,'columns':meta.schema.names,'action':'KEEP','reason':'Current/dynamic/cache source not proven dead','dependency_check':exact or generic,'database_pre_hash':entry['sha256']})
            except Exception as exc:schema.append({'database':rel,'action':'REVIEW_KEEP','error':str(exc)[:200]})
        if i and i%250==0:print(f'Inventoried {i}/{len(candidates)}',flush=True)
    groups=Counter(a['category'] for a in assets)
    out={'created_at':datetime.now(timezone.utc).isoformat(),'baseline_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root).decode().strip(),
         'workspace_root':str(root),'additional_workspace_scan':'Sibling strategy-export and owner uploads treated as user data: preserve, no cleanup authorization inferred',
         'before':sizes(root),'active_research_database_bytes':(shape/'shape.duckdb').stat().st_size,'categories':dict(groups),'assets':assets,
         'excluded_bundles':['.venv and .git included in repository size only; not cleanup targets','data/strategy-lab/lean: run registry can dynamically reference every artifact; KEEP','bare source Git clones: unique historical evidence; KEEP_COLD'],
         'policy_blocked_paths':[a['path'] for a in assets if a['recommended_action']=='POLICY_BLOCKED_KEEP']}
    ev=root/'reports/evidence';ev.mkdir(exist_ok=True)
    (ev/'database-asset-inventory-2026-10-08.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
    (ev/'database-schema-cleanup-manifest.json').write_text(json.dumps({'objects':schema,'in_place_tables_removed':0,'in_place_views_removed':0},ensure_ascii=False,indent=2),encoding='utf-8')
    plan=['# Database cleanup plan — 2026-10-08','',f'Baseline: `{out["baseline_commit"]}`. Inventory before mutation: {len(assets)} assets.','',
          'Only exact unreferenced, unpublished construction outputs are deletion candidates. Published stores, current source locks, raw evidence, runs, owner uploads and all tracked reports stay. Previously blocked Shape paths will not be retried.','',
          '| Asset | Class | Action | Bytes | Reason |','| --- | --- | --- | ---: | --- |']
    for a in assets:
        if a['recommended_action'] in ('DELETE_CANDIDATE','ARCHIVE_CANDIDATE','POLICY_BLOCKED_KEEP'):
            plan.append(f'| `{a["path"]}` | {a["category"]} | {a["recommended_action"]} | {a["size"]} | {a["reason"]} |')
    plan.extend(['','Dynamic/basename-only references are REVIEW_KEEP. Existing PIT audit scripts remain explicit commands outside runtime, because tests, code locks or report reproduction reference them. Raw directories already constitute cold storage; moving locked raw paths would damage reproducibility.','',
                 'No automatic table/view drop, tracked evidence deletion or all-market data expansion. File-level actions require the recorded pre-hash, exact workspace containment, no published manifest and no live pointer. Results recorded separately.'])
    (root/'reports/database-cleanup-plan-2026-10-08.md').write_text('\n'.join(plan)+'\n',encoding='utf-8')
    print(json.dumps({'assets':len(assets),'categories':dict(groups),'before':out['before']}),flush=True)
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path.cwd());inventory(p.parse_args().root)
