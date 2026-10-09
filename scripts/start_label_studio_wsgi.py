"""Existing Label Studio CLI bootstrap, stable single-user Windows WSGI hosting.

Reuses its migrations, credentials, routes and storage; no alternate label app.
One Waitress worker avoids the observed threaded SQLite export close race.
"""
from django.conf import settings
from django.core.wsgi import get_wsgi_application
from label_studio import server
from waitress import serve
from whitenoise import WhiteNoise


def run(host,port):
    if host not in ('127.0.0.1','localhost'): raise ValueError('loopback only')
    app=WhiteNoise(get_wsgi_application(),root=settings.STATIC_ROOT,prefix=settings.STATIC_URL)
    serve(app,host=host,port=int(port),threads=1)


if __name__=='__main__':
    server._app_run=run
    server.main()
