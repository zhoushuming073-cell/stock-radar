"""Authenticated local Label Studio extension, isolated from v3 labels."""
from functools import wraps
from pathlib import Path
import importlib
import json
import os
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.urls import path, include, clear_url_caches
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST
from .store import BoxStore, GateError
from .ontology_v11 import BoxStoreV11

_root=None


def guarded(fn):
    @wraps(fn)
    @login_required
    @csrf_protect
    def call(request,origin,**kwargs):
        if origin not in ('human','smoke'):
            return JsonResponse({'error':'namespace'},status=404)
        try:
            response=fn(request,origin,**kwargs)
        except (ValueError,KeyError,TypeError) as exc:
            response=JsonResponse({'error':str(exc)},status=409)
        except FileNotFoundError:
            response=JsonResponse({'error':'dataset unavailable'},status=503)
        response['Cache-Control']='private, no-store'
        response['X-Content-Type-Options']='nosniff'
        return response
    call._dont_enforce_csrf_checks=False
    return call


def store(origin):return BoxStore(_root,origin)


def store_v11(origin):return BoxStoreV11(_root,origin)


@guarded
@require_GET
@ensure_csrf_cookie
def page(request,origin):
    return HttpResponse((Path(__file__).parent/'box_ui.html').read_text(encoding='utf-8'),content_type='text/html; charset=utf-8')


@guarded
@require_GET
def tasks(request,origin):return JsonResponse({'tasks':store(origin).list(request.user.pk)})


@guarded
@require_GET
def task(request,origin,tid):return JsonResponse(store(origin).task(tid,request.user.pk))


def body(request):
    if len(request.body)>2000:raise GateError('body too large')
    return json.loads(request.body)


@guarded
@require_POST
def save(request,origin,tid):return JsonResponse(store(origin).save(tid,request.user.pk,body(request)))


@guarded
@require_POST
def skip(request,origin,tid):
    if body(request)!={}:raise GateError('skip has no client-controlled state')
    return JsonResponse(store(origin).skip(tid,request.user.pk))


@guarded
@require_GET
@ensure_csrf_cookie
def page_v11(request,origin):
    return HttpResponse((Path(__file__).parent/'box_ui_v11.html').read_text(encoding='utf-8'),content_type='text/html; charset=utf-8')


@guarded
@require_GET
def tasks_v11(request,origin):return JsonResponse({'tasks':store_v11(origin).list(request.user.pk)})


@guarded
@require_GET
def task_v11(request,origin,tid):return JsonResponse(store_v11(origin).task(tid,request.user.pk))


@guarded
@require_POST
def save_v11(request,origin,tid):return JsonResponse(store_v11(origin).save(tid,request.user.pk,body(request)))


@guarded
@require_POST
def skip_v11(request,origin,tid):
    if body(request)!={}:raise GateError('skip has no client-controlled state')
    return JsonResponse(store_v11(origin).skip(tid,request.user.pk))


def install(root):
    global _root
    _root=Path(os.environ.get('STOCK_RADAR_BOX_DATA_ROOT',Path(root)/'data/box-label-v1')).resolve()
    module=importlib.import_module(settings.ROOT_URLCONF)
    routes=[path('',page),path('tasks',tasks),path('task/<str:tid>',task),
            path('task/<str:tid>/save',save),path('task/<str:tid>/skip',skip)]
    routes_v11=[path('',page_v11),path('tasks',tasks_v11),path('task/<str:tid>',task_v11),
            path('task/<str:tid>/save',save_v11),path('task/<str:tid>/skip',skip_v11)]
    module.urlpatterns.insert(0,path('box-label/v1/<str:origin>/',include(routes)))
    module.urlpatterns.insert(0,path('box-label/v1.1/<str:origin>/',include(routes_v11)))
    clear_url_caches()
