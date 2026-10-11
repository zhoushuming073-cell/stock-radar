"""Existing Label Studio CLI bootstrap, stable single-user Windows WSGI hosting.

Reuses its migrations, credentials, routes and storage; no alternate label app.
One worker and persistent SQLite connections address the observed export errors.
"""
from django.conf import settings
from django.core.wsgi import get_wsgi_application
from label_studio import server
from waitress import serve
from whitenoise import WhiteNoise
from pathlib import Path
import os,sys


def run(host,port):
    if host not in ('127.0.0.1','localhost'): raise ValueError('loopback only')
    # Single-user SQLite worker: keep one healthy connection for its lifetime.
    # With age=0, delayed streaming-response finalizers can close a connection
    # while the next export serializer is using it. No database content changes.
    settings.DATABASES['default']['CONN_MAX_AGE']=None
    settings.DATABASES['default']['CONN_HEALTH_CHECKS']=True
    base_app=get_wsgi_application()
    code_root=Path(__file__).resolve().parents[1]
    root=Path(os.environ.get('STOCK_RADAR_RESEARCH_ROOT',code_root)).resolve()
    sys.path.insert(0,str(code_root/'src'))
    from radar.vision.dual_views import install
    install(root)
    from radar.box_labeling.web import install as install_box
    install_box(root)
    app=WhiteNoise(base_app,root=settings.STATIC_ROOT,prefix=settings.STATIC_URL)
    from radar.vision.dual_http import guard_local_files
    app=guard_local_files(app,root/'data')
    serve(app,host=host,port=int(port),threads=1)


if __name__=='__main__':
    server._app_run=run
    server.main()
