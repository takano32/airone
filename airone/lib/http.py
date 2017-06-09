import json

from django.http import HttpResponseRedirect
from django.http import HttpResponse
from django.shortcuts import render as django_render

from entity import models as entity_models
from acl.models import ACLBase
from user.models import User


class HttpResponseSeeOther(HttpResponseRedirect):
    status_code = 303

def http_get(func):
    def wrapper(*args, **kwargs):
        request = args[0]
        if request.method != 'GET':
            return HttpResponse('Invalid HTTP method is specified', status=400)

        if not request.user.is_authenticated():
            return HttpResponseSeeOther('/dashboard/login')

        return func(*args, **kwargs)
    return wrapper

def check_permission(model, permission_level):
    def _decorator(func):
        def permission_checker(*args, **kwargs):
            # the arguments length is assured by the Django URL dispatcher
            (request, object_id) = args

            if not model.objects.filter(id=object_id).count():
                return HttpResponse('Failed to get entity of specified id', status=400)

            target_obj = model.objects.get(id=object_id)
            if not isinstance(target_obj, ACLBase):
                return HttpResponse('[InternalError] "%s" has no permisison' % target_obj, status=500)

            perm = getattr(target_obj, permission_level)
            user = User.objects.get(id=request.user.id)

            if (target_obj.is_public or
                # checks that current uesr is created this document
                target_obj.created_user == user or
                # checks user permission
                [perm <= x for x in user.permissions.all()] or
                # checks group permission
                sum([[perm <= x for x in g.permissions.all()] for g in user.groups.all()], [])):

                # only requests that have correct permission are executed
                return func(*args, **kwargs)
            return HttpResponse('You don\'t have permission to access this object', status=400)
        return permission_checker
    return _decorator

def http_post(validator):
    def _decorator(func):
        def http_post_handler(*args, **kwargs):
            request = args[0]

            if request.method != 'POST':
                return HttpResponse('Invalid HTTP method is specified', status=400)

            if not request.user.is_authenticated():
                return HttpResponse('You have to login to execute this operation', status=401)

            try:
                kwargs['recv_data'] = json.loads(request.body.decode('utf-8'))
            except json.decoder.JSONDecodeError:
                return HttpResponse('Failed to parse string to JSON', status=400)

            if not _is_valid(kwargs['recv_data'], validator):
                return HttpResponse('Invalid parameters are specified', status=400)

            return func(*args, **kwargs)
        return http_post_handler
    return _decorator

def render(request, template, context={}):
    # added default parameters for navigate
    context['navigator'] = {'entities': entity_models.Entity.objects.all()}

    return django_render(request, template, context)

def _is_valid(params, meta_info):
    if not isinstance(params, dict):
        return False
    # These are existance checks of each parameters
    if not all([x['name'] in params for x in meta_info]):
        return False
    # These are type checks of each parameters
    if not all([isinstance(params[x['name']], x['type']) for x in meta_info]):
        return False
    # These are value checks of each parameters
    for _meta in meta_info:
        # The case specified value is str
        if (_meta['type'] == str and 'checker' in _meta and not _meta['checker'](params)):
            return False

        # The case specified value is list
        if _meta['type'] == list:
            if 'checker' in _meta and not _meta['checker'](params):
                return False

            if ('meta' in _meta and
                not all([_is_valid(x , _meta['meta']) for x in params[_meta['name']]])):
                return False

    return True
