import io
import logging
import re
import csv
import yaml

import urllib.parse

from airone.lib.http import render
from airone.lib.http import http_get, http_post_form
from airone.lib.http import http_file_upload
from airone.lib.http import HttpResponseSeeOther
from airone.lib.http import get_download_response
from airone.lib.profile import airone_profile
from airone.lib.types import AttrTypeValue
from django.http import HttpResponse
from django.http.response import JsonResponse
from django.conf import settings
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
    if request.user.is_authenticated() and User.objects.filter(id=request.user.id).exists():
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
    entities = [x for x in Entity.objects.filter(is_active=True).order_by('name')
                if x.attrs.filter(is_active=True).exists()]

    return render(request, 'advanced_search.html', {
        'entities': entities,
    })

@http_get
@airone_profile
def advanced_search_result(request):
    user = User.objects.get(id=request.user.id)

    recv_entity = request.GET.getlist('entity[]')
    recv_attr = request.GET.getlist('attr[]')

    if not recv_entity or not recv_attr:
        return HttpResponse("The attr[] and entity[] parameters are required", status=400)

    if not all([Entity.objects.filter(id=x, is_active=True).exists() for x in recv_entity]):
        return HttpResponse("Invalid entity ID is specified", status=400)

    return render(request, 'advanced_search_result.html', {
        'attrs': recv_attr,
        'results': Entry.search_entries(user,
                                        recv_entity,
                                        [{'name': x} for x in recv_attr],
                                        CONFIG.MAXIMUM_SEARCH_RESULTS),
        'max_num': CONFIG.MAXIMUM_SEARCH_RESULTS,
        'entities': ','.join([str(x) for x in recv_entity]),
    })

@airone_profile
@http_post_form([
    {'name': 'entities', 'type': list,
     'checker': lambda x: all([Entity.objects.filter(id=y) for y in x['entities']])},
    {'name': 'attrinfo', 'type': list},
])
def export_search_result(request, recv_data):
    user = User.objects.get(id=request.user.id)

    resp = Entry.search_entries(user,
                                recv_data['entities'],
                                recv_data['attrinfo'],
                                settings.ES_CONFIG['MAXIMUM_RESULTS_NUM'])

    
    output = io.StringIO(newline='')
    writer = csv.writer(output)
    
    # write first line of CSV
    writer.writerow(['Name'] + [x['name'] for x in recv_data['attrinfo']])
    
    for entry_info in resp['ret_values']:
        line_data = [entry_info['entry']['name']]

        for attrinfo in recv_data['attrinfo']:

            value = entry_info['attrs'][attrinfo['name']]

            vtype = None
            if (value is not None) and ('type' in value):
                vtype = value['type']

            vval = None
            if (value is not None) and ('value' in value):
                vval = value['value']
            
            if not value or 'value' not in value or not value['value']:
                line_data.append('')

            elif (vtype == AttrTypeValue['string'] or
                vtype == AttrTypeValue['text'] or
                vtype == AttrTypeValue['boolean']):

                line_data.append(str(vval))

            elif (vtype == AttrTypeValue['object'] or
                  vtype == AttrTypeValue['group']):

                line_data.append(str(vval['name']))

            elif vtype == AttrTypeValue['named_object']:

                [(k, v)] = vval.items()
                line_data.append(str({k: v['name']}))

            elif vtype == AttrTypeValue['array_string']:

                line_data.append(str(vval))

            elif vtype == AttrTypeValue['array_object']:

                line_data.append(str([x['name'] for x in vval]))

            elif vtype == AttrTypeValue['array_named_object']:

                items = []
                for vset in vval:
                    [(k, v)] = vset.items()
                    items.append({k: v['name']})

                line_data.append(str(items))

        writer.writerow(line_data)

    return get_download_response(output, 'search_results.csv')
