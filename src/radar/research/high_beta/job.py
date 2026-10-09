"""Separate bounded, silent Q2 v1.2 job; does not overwrite baseline scans."""
from datetime import datetime,timezone
from pathlib import Path
import json
import subprocess
import sys
from threading import Lock,Thread

_lock=Lock()
_status={'state':'idle'}


def status():
    with _lock:return dict(_status)


def start(root):
    root=Path(root)
    with _lock:
        if _status['state']=='running':return dict(_status)
        _status.clear();_status.update(state='running',started_at=datetime.now(timezone.utc).isoformat())
    def run():
        directory=root/'data/research/high-beta-channel-v1.2';directory.mkdir(parents=True,exist_ok=True)
        try:
            with (directory/'worker.log').open('w',encoding='utf-8') as log:
                r=subprocess.run([sys.executable,str(root/'scripts/scan_high_beta_channel.py'),'--workers','4'],
                    cwd=root,stdout=log,stderr=subprocess.STDOUT,timeout=3600,
                    creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            state='succeeded' if r.returncode==0 else 'failed';error=None if r.returncode==0 else 'Q2 v1.2 failed; see private worker.log'
        except Exception as e:state='failed';error=str(e)
        with _lock:
            _status.update(state=state,error=error,finished_at=datetime.now(timezone.utc).isoformat())
            (directory/'status.json').write_text(json.dumps(_status),encoding='utf-8')
    Thread(target=run,daemon=True).start()
    return status()
