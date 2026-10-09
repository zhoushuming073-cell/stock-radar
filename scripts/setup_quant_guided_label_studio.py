"""Create isolated real/smoke projects through Label Studio's existing local API.

No storage sync, no automatic human labels; credentials stay in private data/.
"""
from pathlib import Path
import argparse
import json
from hashlib import sha256
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import xml.etree.ElementTree as ET
from radar.vision.quant_contracts import verify_quant_dataset as verify_quant


def control_contract(xml):
    tree=ET.fromstring(xml)
    return [(node.tag,{k:v for k,v in node.attrib.items() if k in
        ('name','toName','choice','required','value')},[x.attrib.get('value') for x in node if x.tag=='Choice'])
        for node in tree.iter() if node.tag in ('Image','Choices')]


def setup(root,bundle,base,update_empty_config=False,update_layout=False):
    root=Path(root).resolve(); bundle=Path(bundle).resolve(); verify_quant(bundle)
    base=base.rstrip('/')
    if base not in ('http://localhost:8123','http://127.0.0.1:8123'):
        raise ValueError('local Label Studio only; no cloud upload')
    login=json.loads((root/'data/vision-research/label-studio/local-login.json').read_text(encoding='utf-8-sig'))
    session=requests.Session(); session.get(base+'/user/login/',timeout=30).raise_for_status()
    session.mount(base,HTTPAdapter(max_retries=Retry(total=3,backoff_factor=.4,status_forcelist=[500,502,503,504],allowed_methods=['GET'])))
    csrf=session.cookies.get('csrftoken')
    response=session.post(base+'/user/login/',data={'email':login['username'],'password':login['password'],'csrfmiddlewaretoken':csrf},
                           headers={'Referer':base+'/user/login/'},timeout=30)
    response.raise_for_status()
    if '/user/login/' in response.url: raise ValueError('local login failed; password never printed')
    headers={'X-CSRFToken':session.cookies.get('csrftoken'),'Referer':base+'/'}
    def api(method,path,data=None):
        r=session.request(method,base+path,json=data,headers=headers,timeout=90)
        if not r.ok: raise RuntimeError(f'Label Studio {method} {path}: HTTP {r.status_code}')
        return r.json()
    ls=api('GET','/api/projects?page_size=100'); existing=ls if isinstance(ls,list) else ls['results']
    # Before snapshot binds OLD annotations, not the naturally changing shared SQLite file.
    old={str(p['id']):api('GET',f"/api/projects/{p['id']}/export?exportType=JSON&download_all_tasks=true")
         for p in existing if p['title'].startswith('Vision ')}
    before=bundle/'old-projects-before.json'
    if not before.exists(): before.write_text(json.dumps(old,ensure_ascii=False),encoding='utf-8')
    xml=(root/'labeling/quant-guided-v1.xml').read_text(encoding='utf-8').strip()
    xmlhash=sha256(xml.encode()).hexdigest()
    tasks=json.loads((bundle/'label-studio-single-tasks.json').read_text(encoding='utf-8'))
    byimage={}; repeat=None
    for t in tasks:
        if t['data']['image'] in byimage: repeat=(byimage[t['data']['image']],t); break
        byimage[t['data']['image']]=t
    if repeat is None: raise ValueError('hidden repeat not found')
    # Ten UNIQUE images, plus one deliberate repeat. Labels are added only by browser tests.
    smoke=[repeat[0]]; images={repeat[0]['data']['image']}
    for t in tasks:
        if t['data']['image'] not in images and len(smoke)<10: smoke.append(t); images.add(t['data']['image'])
    smoke.append(repeat[1])
    projects={}
    for origin,upload in [('human',tasks),('smoke',smoke)]:
        title='Quant-guided v1 READY — '+('Human Ground Truth' if origin=='human' else 'SMOKE WSGI')
        matches=[p for p in existing if p['title']==title]
        if len(matches)>1: raise ValueError('duplicate project title')
        if matches:
            p=api('GET',f"/api/projects/{matches[0]['id']}/")
            if sha256(p['label_config'].strip().encode()).hexdigest()!=xmlhash:
                exported=api('GET',f"/api/projects/{p['id']}/export?exportType=JSON&download_all_tasks=true")
                layout_only=update_layout and control_contract(p['label_config'])==control_contract(xml)
                if not layout_only and (not update_empty_config or any(t.get('annotations') for t in exported)):
                    raise ValueError('published label config differs; create explicit new version')
                p=api('PATCH',f"/api/projects/{p['id']}/",{'label_config':xml})
        else:
            p=api('POST','/api/projects/',{'title':title,'label_config':xml,
              'description':'T-close Observe and Entry are independent. '+('Actual human judgments only.' if origin=='human' else 'Mechanical browser fixtures only; never model ground truth.')})
            api('POST',f"/api/projects/{p['id']}/import",[{**t,'meta':{'label_version':'quant-human-v1','label_origin':origin}} for t in upload])
        storage=api('GET',f"/api/storages/localfiles/?project={p['id']}")
        if not storage:
            api('POST','/api/storages/localfiles/',{'project':p['id'],'path':str(bundle/'images'),'title':'Blind PNG authorization — never sync',
                'use_blob_urls':True,'regex_filter':'.*\\.png$'})
        exported=api('GET',f"/api/projects/{p['id']}/export?exportType=JSON&download_all_tasks=true")
        expected={t['data']['task_id'] for t in upload}
        if {t['data']['task_id'] for t in exported}!=expected or len(exported)!=len(expected): raise ValueError('LS task cardinality mismatch')
        projects[origin]={'id':p['id'],'url':base+f"/projects/{p['id']}/data",'tasks':len(exported),'label_config_sha256':xmlhash}
    after={pid:api('GET',f'/api/projects/{pid}/export?exportType=JSON&download_all_tasks=true') for pid in old}
    # Ignore volatile display/counters; bind data, annotations and cancelled annotations.
    def stable(x): return {k:[{'id':t['id'],'data':t['data'],'annotations':t.get('annotations',[])} for t in v] for k,v in x.items()}
    if stable(old)!=stable(after): raise ValueError('old project tasks/annotations changed')
    projects['old_projects_preserved']=len(old)
    (bundle/'label-studio-projects.json').write_text(json.dumps(projects,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(projects,ensure_ascii=False,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--root',type=Path,default=Path.cwd())
    p.add_argument('--bundle',type=Path,default=Path('data/vision-research/quant-guided-v1/ready'))
    p.add_argument('--base',default='http://localhost:8123'); p.add_argument('--update-empty-config',action='store_true')
    p.add_argument('--update-layout',action='store_true',help='Allow visual-only XML changes when ALL label controls remain identical')
    a=p.parse_args(); setup(a.root,a.bundle,a.base,a.update_empty_config,a.update_layout)
