import json
import importlib
import urllib.parse

from django.http import HttpResponseRedirect
from django.http import HttpResponse
from django.shortcuts import render as django_render
from django.utils.encoding import smart_str

from entity import models as entity_models
from entry import models as entry_models
from acl.models import ACLBase
from user.models import User, History

from airone.lib.types import AttrTypes, AttrTypeValue
from airone.lib.acl import ACLObjType, ACLType


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

            user = User.objects.get(id=request.user.id)
            target_obj = model.objects.get(id=object_id)
            if not isinstance(target_obj, ACLBase):
                return HttpResponse('[InternalError] "%s" has no permisison' % target_obj, status=500)

            if user.has_permission(target_obj, permission_level):
                # only requests that have correct permission are executed
                return func(*args, **kwargs)

            return HttpResponse('You don\'t have permission to access this object', status=400)
        return permission_checker
    return _decorator

def check_superuser(func):
    def wrapper(*args, **kwargs):
        request = args[0]

        if not request.user.is_authenticated():
            return HttpResponseSeeOther('/dashboard/login')

        if not request.user.is_superuser:
            return HttpResponse('This page needs Admnistrator permission to access', status=400)

        return func(*args, **kwargs)
    return wrapper

def http_post(validator=[]):
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

def http_file_upload(func):
    def wrapper(*args, **kwargs):
        request = args[0]

        if request.method != 'POST':
            return HttpResponse('Invalid HTTP method is specified', status=400)

        try:
            # get uploaded file data context and pass it to the arguemnt of HTTP handler
            kwargs['context'] = ''.join([x.decode('utf-8') for x in request.FILES['file'].chunks()])

            return func(*args, **kwargs)
        except UnicodeDecodeError:
            return HttpResponse('Uploaded file is invalid', status=400)

    return wrapper

def render(request, template, context={}):
    if User.objects.filter(id=request.user.id).count():
        user = User.objects.get(id=request.user.id)

        # added default parameters for navigate
        entity_objects = entity_models.Entity.objects.order_by('name').filter(is_active=True)
        context['navigator'] = {
            'entities': [x for x in entity_objects if user.has_permission(x, ACLType.Readable)],
            'acl_objtype': {
                'entity': ACLObjType.Entity,
                'entry': ACLObjType.Entry,
                'attrbase': ACLObjType.EntityAttr,
                'attr': ACLObjType.EntryAttr,
            }
        }

    # set constants for operation history
    context['OPERATION_HISTORY'] = {
        'ADD_ENTITY': History.ADD_ENTITY,
        'ADD_ATTR': History.ADD_ATTR,
        'MOD_ENTITY': History.MOD_ENTITY,
        'MOD_ATTR': History.MOD_ATTR,
        'DEL_ENTITY': History.DEL_ENTITY,
        'DEL_ATTR': History.DEL_ATTR,
        'DEL_ENTRY': History.DEL_ENTRY,
    }

    # set constant values which are defined in each applications
    context['config'] = {}
    for app in ['entry']:
        config = importlib.import_module('%s.settings' % app).CONFIG
        context['config'][app] = config.TEMPLATE_CONFIG

    context['attr_type'] = {}
    for attr_type in AttrTypes:
        context['attr_type'][attr_type.NAME] = attr_type.TYPE
    context['attr_type_value'] = AttrTypeValue

    # set Construct for Entity status
    context['STATUS_ENTITY'] = {}
    context['STATUS_ENTITY']['TOP_LEVEL'] = entity_models.Entity.STATUS_TOP_LEVEL

    # set Construct for Entry status
    context['STATUS_ENTRY'] = {}
    context['STATUS_ENTRY']['CREATING'] = entry_models.Entry.STATUS_CREATING
    context['STATUS_ENTRY']['EDITING'] = entry_models.Entry.STATUS_EDITING

    return django_render(request, template, context)

def get_download_response(io_stream, fname):
    response = HttpResponse(io_stream.getvalue(),
                            content_type="application/force-download")
    response["Content-Disposition"] = 'attachment; filename="{fn}"'.format(fn=urllib.parse.quote(smart_str(fname)))
    return response

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
