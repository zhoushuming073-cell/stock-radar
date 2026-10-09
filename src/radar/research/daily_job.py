"""One bounded silent local scanner job; status independent of market ingestion."""
from pathlib import Path
from threading import Lock,Thread
from datetime import datetime,timezone
import json
import subprocess
import sys
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
        private=root/'data/research/daily-quant';private.mkdir(parents=True,exist_ok=True)
        try:
            with (private/'worker.log').open('w',encoding='utf-8') as log:
                result=subprocess.run([sys.executable,str(root/'scripts/scan_quant_daily.py')],
                    cwd=root,stdout=log,stderr=subprocess.STDOUT,timeout=3600,
                    creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            state='succeeded' if result.returncode==0 else 'failed'
            error=None if result.returncode==0 else 'Scanner failed; see private worker.log'
        except Exception as e:state='failed';error=str(e)
        with _lock:
            _status.update(state=state,error=error,finished_at=datetime.now(timezone.utc).isoformat())
            (private/'status.json').write_text(json.dumps(_status),encoding='utf-8')
    Thread(target=run,daemon=True).start()
    return status()

