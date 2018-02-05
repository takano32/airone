import logging
import re
import yaml

from airone.lib.http import render
from airone.lib.http import http_get
from airone.lib.http import http_file_upload
from airone.lib.http import HttpResponseSeeOther
from airone.lib.profile import airone_profile
from django.http import HttpResponse
from entity.admin import EntityResource, EntityAttrResource
from entry.admin import EntryResource, AttrResource, AttrValueResource
from entity.models import Entity, EntityAttr
from entry.models import Entry, Attribute, AttributeValue
from user.models import User
from .settings import CONFIG

IMPORT_INFOS = [
    {'model': 'Entity', 'resource': EntityResource},
    {'model': 'EntityAttr', 'resource': EntityAttrResource},
    {'model': 'Entry', 'resource': EntryResource},
    {'model': 'Attribute', 'resource': AttrResource},
    {'model': 'AttributeValue', 'resource': AttrValueResource},
]

Logger = logging.getLogger(__name__)


@airone_profile
def index(request):
    context = {}
    if request.user.is_authenticated() and User.objects.filter(id=request.user.id).count():
        user = User.objects.get(id=request.user.id)

        history = []
        for attr_value in AttributeValue.objects.order_by('created_time').reverse()[:CONFIG.LAST_ENTRY_HISTORY]:
            parent_attr = attr_value.parent_attr
            parent_entry = parent_attr.parent_entry

            if parent_attr.is_active and parent_entry.is_active:
                history.append({
                    'entry': parent_entry,
                    'attr_type': parent_attr,
                    'attr_value': attr_value,
                    'attr_value_array': attr_value.data_array.all(),
                })

        context['last_entries'] = history

    return render(request, 'dashboard_user_top.html', context)

@http_get
def import_data(request):
    return render(request, 'import.html', {})

@http_file_upload
def do_import_data(request, context):
    user = User.objects.get(id=request.user.id)

    if request.FILES['file'].size >= CONFIG.LIMIT_FILE_SIZE:
        return HttpResponse("File size over", status=400)

    try:
        data = yaml.load(context)
    except yaml.parser.ParserError:
        return HttpResponse("Couldn't parse uploaded file", status=400)

    def _do_import(resource, iter_data):
        results = []
        for data in iter_data:
            try:
                result = resource.import_data_from_request(data, user)

                results.append({'result': result, 'data': data})
            except RuntimeError as e:
                Logger.warning(('(%s) %s ' % (resource, data)) + str(e))

        if results:
            resource.after_import_completion(results)

    for info in IMPORT_INFOS:
        if info['model'] in data:
            _do_import(info['resource'], data[info['model']])

    return HttpResponseSeeOther('/dashboard/')

@http_get
def search(request):
    results = []
    target_models = [Entry, AttributeValue]

    query = request.GET.get('query')
    if not query:
        return HttpResponse("Invalid query parameter is specified", status=400)

    return render(request, 'show_search_results.html', {
        'results': sum([x.search(query) for x in target_models], [])
    })

@http_get
def advanced_search(request):
    attrs = [{
        'id': attr.id,
        'type': attr.type,
        'name': "%s / %s" % (attr.parent_entity.name, attr.name),
        'referral': ','.join([str(x.id) for x in attr.referral.all()]),
    } for attr in EntityAttr.objects.filter(is_active=True)]

    return render(request, 'advanced_search.html', {
        'attrs': sorted(attrs, key=lambda x: x['name']),
        'entities': Entity.objects.filter(is_active=True),
    })
