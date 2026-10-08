"""Verify the already-authorized cold move and record retained blocked assets.

No delete, move, schema mutation or new download is performed here.
"""
from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
from hashlib import sha256

from radar.pit.features import file_hash


def read(p):return json.loads(Path(p).read_text(encoding='utf8'))
def size(directory):
    return sum(os.path.getsize(os.path.join(base,name)) for base,_,files in os.walk(directory)
               for name in files if not os.path.islink(os.path.join(base,name)))


def record(root):
    root=Path(root).resolve();inventory=read(root/'reports/evidence/database-asset-inventory-2026-10-08.json')
    profile=read(root/'config/research_infrastructure_v1.json')
    prefix='data/pit/shape-research/versions/25137ad2123ffc57cc7873dcd0dab5307152e61f036d39b12900b4c3315c507e/'
    destination='archive/legacy-pit/shape-25137ad2123ffc57cc7873dcd0dab5307152e61f036d39b12900b4c3315c507e/'
    moved=[];blocked=[]
    for a in inventory['assets']:
        if a['path'].startswith(prefix):
            new=destination+a['path'][len(prefix):]
            assert not (root/a['path']).exists() and (root/new).is_file()
            assert file_hash(root/new)==a['sha256'] and (root/new).stat().st_size==a['size']
            moved.append({'original':a['path'],'destination':new,'bytes':a['size'],'sha256':a['sha256'],
                          'hash_verified':True,'external_consumers':a['external_references'],'action':'ARCHIVED'})
        if a['recommended_action']=='POLICY_BLOCKED_KEEP':
            blocked.append({'path':a['path'],'bytes':a['size'],'sha256':a['sha256'],'desired_action':'DELETE',
                'action':'POLICY_BLOCKED_KEEP','reason':a['reason'],'runtime_dependency':False,
                'runtime_dependency_basis':'no published manifest/current pointer; named versions have no exact external consumer'})
    # Verify all pinned source inputs and the untouched original research API.
    checks={}
    strict_directory=Path(read(root/'data/pit/construction/current.json')['directory']).relative_to(root)
    for directory in [profile['core_directory'],profile['fresh_directory'],strict_directory]:
        for item in read(root/directory/'manifest.json')['inputs'].values():
            p=Path(item['path']);got=file_hash(p)
            checks[str(p.relative_to(root)).replace('\\','/') ]={'before':item['sha256'],'after':got,'unchanged':got==item['sha256']}
            assert got==item['sha256'],str(p)
    baseline={a['path']:a for a in inventory['assets']}
    for path in ['data/phase2-research.duckdb','src/radar/strategy/full_strategy2.py',
                 'src/radar/features/base.py','src/radar/features/strategy2.py','config/research.yaml']:
        got=file_hash(root/path)
        if path in baseline:
            expected=baseline[path]['sha256']
            checks[path]={'before':expected,'after':got,'unchanged':expected==got};assert expected==got
        else:
            original=subprocess.check_output(['git','show',inventory['baseline_commit']+':'+path],cwd=root)
            normalized=(root/path).read_bytes().replace(b'\r\n',b'\n')
            assert normalized==original.replace(b'\r\n',b'\n'),path
            checks[path]={'baseline_git_normalized_sha256':sha256(original.replace(b'\r\n',b'\n')).hexdigest(),
                          'current_normalized_sha256':sha256(normalized).hexdigest(),'current_physical_sha256':got,
                          'unchanged':True,'comparison_basis':'Git baseline content and normalized newlines; baseline physical bytes were not recorded for this runtime source'}
    qc=[a for a in inventory['assets'] if a['path'].startswith('reports/evidence/qc-')]
    for a in qc:
        got=file_hash(root/a['path']);assert got==a['sha256']
        checks[a['path']]={'before':a['sha256'],'after':got,'unchanged':True}
    for item in read(root/'reports/evidence/qc-protected-verification-2026-10-08.json')['files']:
        path=item['path'].replace('\\','/');expected=item.get('current_sha256',item['sha256'])
        got=file_hash(root/path);assert got==expected,path
        checks[path]={'before':expected,'after':got,'unchanged':True,'comparison_basis':'prior current QC protection receipt'}
    schema=read(root/'reports/evidence/database-schema-cleanup-manifest.json')
    for obj in schema['objects']:
        if obj['database'].startswith(prefix):
            obj['action']='ARCHIVE_WITH_DATABASE';obj['archive_database']=destination+obj['database'][len(prefix):]
            obj['reason']='Whole immutable superseded database archived with every object and hash retained'
    (root/'reports/evidence/database-schema-cleanup-manifest.json').write_text(json.dumps(schema,ensure_ascii=False,indent=2),encoding='utf8')
    failed_new=[]
    for directory in (root/'data/pit/shape-research/fresh-oos').iterdir():
        if directory.is_dir() and not (directory/'manifest.json').exists():
            for p in directory.rglob('*'):
                if p.is_file():failed_new.append({'path':p.relative_to(root).as_posix(),'bytes':p.stat().st_size,
                    'sha256':file_hash(p),'action':'REVIEW_KEEP','reason':'New unpublished build failure; no deletion retry in blocked cleanup session'})
    after={'repo_bytes':size(root),'data_bytes':size(root/'data'),'archive_bytes':size(root/'archive'),
           'temp_cache_bytes':sum(p.stat().st_size for p in (root/'data').rglob('*') if p.is_file() and p.suffix in ('.tmp','.wal')),
           'active_research_database_bytes':(root/profile['core_directory']/'shape.duckdb').stat().st_size,
           'fresh_sidecar_bytes':(root/profile['fresh_directory']/'fresh.duckdb').stat().st_size}
    result={'measured_at':datetime.now(timezone.utc).isoformat(),'measurement':'logical file bytes including .git/.venv; before final receipt/report and Git commit',
            'baseline_commit':inventory['baseline_commit'],'asset_count_before':len(inventory['assets']),
            'reviewed_categories':dict(Counter(a['category'] for a in inventory['assets'])),
            'schema_objects_audited':len(schema['objects']),
            'before':{**inventory['before'],'active_research_database_bytes':inventory['active_research_database_bytes'],'fresh_sidecar_bytes':0},
            'after':after,'deleted_file_count':0,'deleted_bytes':0,'disk_space_freed':0,
            'archived_file_count':len(moved),'archived_bytes':sum(a['bytes'] for a in moved),'archived':moved,
            'in_place_tables_removed':0,'in_place_views_removed':0,'scripts_archived':0,'scripts_deleted':0,
            'blocked':blocked,'blocked_bytes':sum(a['bytes'] for a in blocked),
            'actual_rejection':'Exact audited 32b31d.../historical.duckdb Remove-Item command returned blocked by policy; no command executed or alternative delete attempted',
            'protected_hash_checks':checks,'new_failed_builds_retained':failed_new,
            'code_cleanup':'Existing scripts have tests/report/code locks or uncertain dynamic consumers; retained explicit audit commands, absent from automatic production dispatch. No unverifiable obsolete importer deleted.',
            'raw_cold_storage':'Pinned raw paths retained in existing data/pit/raw cold directories; no automatic runtime scan',
            'archive_runtime_policy':'Excluded from package imports, pytest testpaths, daily update, Scanner, Shape, LEAN; no recursive archive discovery'}
    (root/'reports/evidence/database-cleanup-results-2026-10-08.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({k:v for k,v in result.items() if k in ('before','after','deleted_file_count','archived_bytes','blocked_bytes','reviewed_categories')},ensure_ascii=False))
    return result


if __name__=='__main__':record(Path.cwd())
