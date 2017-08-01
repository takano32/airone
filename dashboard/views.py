import logging
import re
import yaml

from airone.lib.http import render
from airone.lib.http import http_get
from airone.lib.http import http_file_upload
from airone.lib.http import HttpResponseSeeOther
from user.models import User
from entity.models import Entity, AttributeBase
from entry.models import Entry, Attribute, AttributeValue

_IMPORT_MODELS = [
    'Entity', 'AttributeBase',
    'Entry', 'Attribute', 'AttributeValue',
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

    def _do_import(model, iter_data):
      for data in iter_data:
          try:
              model.import_data(data, user)
          except RuntimeError as e:
              Logger.warning(('(%s) %s ' % (model, data)) + str(e))

    for model_str in _IMPORT_MODELS:
        if model_str in data:
            _do_import(eval(model_str), data[model_str])

    return HttpResponseSeeOther('/dashboard/')
