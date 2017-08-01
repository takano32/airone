import logging
import re
import yaml

from airone.lib.http import render
from airone.lib.http import http_get
from airone.lib.http import http_file_upload
from airone.lib.http import HttpResponseSeeOther
from user.models import User
from entity.admin import EntityResource, AttrBaseResource
from entry.admin import EntryResource, AttrResource, AttrValueResource
from entity.models import Entity, AttributeBase
from entry.models import Entry, Attribute, AttributeValue

IMPORT_INFOS = [
    {'model': 'Entity', 'resource': EntityResource},
    {'model': 'AttributeBase', 'resource': AttrBaseResource},
    {'model': 'Entry', 'resource': EntryResource},
    {'model': 'Attribute', 'resource': AttrResource},
    {'model': 'AttributeValue', 'resource': AttrValueResource},
]

Logger = logging.getLogger(__name__)


def index(request):
    return render(request, 'dashboard_user_top.html')

@http_get
def import_data(request):
    return render(request, 'import.html', {})

@http_file_upload
def do_import_data(request, context):
    user = User.objects.get(id=request.user.id)

    try:
        data = yaml.load(context)
    except yaml.parser.ParserError:
        return HttpResponse("Couldn't parse uploaded file", status=400)

    def _do_import(resource, iter_data):
        for data in iter_data:
            try:
                resource.import_data_from_request(data, user)
            except RuntimeError as e:
                Logger.warning(('(%s) %s ' % (resource, data)) + str(e))

    for info in IMPORT_INFOS:
        if info['model'] in data:
            _do_import(info['resource'], data[info['model']])

    return HttpResponseSeeOther('/dashboard/')
