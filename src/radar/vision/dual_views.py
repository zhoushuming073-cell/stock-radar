"""Django extension: existing Label Studio login/session/CSRF middleware."""
from functools import wraps
from pathlib import Path
import json,importlib
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse,JsonResponse
from django.urls import path,include,clear_url_caches
from django.views.decorators.csrf import ensure_csrf_cookie,csrf_protect
from django.views.decorators.http import require_GET,require_POST
from pydantic import ValidationError
from .dual_store import DualStore,GateError

_root=None

def guarded(function):
    @wraps(function)
    @login_required
    @csrf_protect
    def call(request,origin,**kw):
        if origin not in ('human','smoke'):return JsonResponse({'error':'namespace'},status=404)
        try:
            result=function(request,origin,**kw)
            result['Cache-Control']='private, no-store';result['X-Content-Type-Options']='nosniff'
            return result
        except (ValueError,ValidationError) as e:return JsonResponse({'error':str(e)},status=409)
        except FileNotFoundError:return JsonResponse({'error':'dataset unavailable'},status=503)
    # Label Studio's DisableCSRF middleware honors this documented per-view hook.
    # Protect only our extension; retain existing Label Studio behavior.
    call._dont_enforce_csrf_checks=False
    return call

def store():return DualStore(_root/'.local/vision-dual-stage-v3')
def body(request):
    if len(request.body)>10000:raise GateError('body too large')
    return json.loads(request.body)

@guarded
@require_GET
@ensure_csrf_cookie
def page(request,origin):
    return HttpResponse((Path(__file__).parent/'dual_ui.html').read_text(encoding='utf-8'),content_type='text/html; charset=utf-8')

@guarded
@require_GET
def tasks(request,origin):return JsonResponse({'tasks':store().list_tasks(origin,request.user.pk),'origin':origin})

@guarded
@require_GET
def left(request,origin,tid):return JsonResponse(store().left(tid,origin,request.user.pk))

@guarded
@require_GET
def right(request,origin,tid):return JsonResponse(store().right(tid,origin,request.user.pk))

@guarded
@require_POST
def save(request,origin,tid):return JsonResponse(store().save(tid,origin,request.user.pk,body(request)))

@guarded
@require_POST
def review(request,origin,tid):return JsonResponse(store().save(tid,origin,request.user.pk,body(request),review=True))

@guarded
@require_POST
def reveal(request,origin,tid):
    if body(request)!={}:raise GateError('reveal has no client-controlled state')
    return JsonResponse(store().reveal(tid,origin,request.user.pk))

@guarded
@require_POST
def skip(request,origin,tid):
    if body(request)!={}:raise GateError('skip has no outcome')
    return JsonResponse(store().skip(tid,origin,request.user.pk))

@guarded
@require_GET
def export(request,origin):return JsonResponse(store().export(origin,request.user.pk))

def install(root):
    global _root
    _root=Path(root)
    routes=[path('',page),path('tasks',tasks),path('export',export),path('task/<str:tid>/left',left),path('task/<str:tid>/right',right),path('task/<str:tid>/blind',save),path('task/<str:tid>/review',review),path('task/<str:tid>/reveal',reveal),path('task/<str:tid>/skip',skip)]
    module=importlib.import_module(settings.ROOT_URLCONF)
    module.urlpatterns.insert(0,path('quant-review/v3/<str:origin>/',include(routes)))
    clear_url_caches()
