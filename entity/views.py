import json
import re

from django.shortcuts import render, redirect
from django.http import HttpResponse

from .models import Entity
from .models import AttributeBase
from acl.models import ACL
from .lib import AttrTypes


def index(request):
    context = {}
    context['entities'] = [{
        'name': x.name,
        'attrs': [y for y in x.attr_bases.all()],
        'rowspan': len(x.attr_bases.all()),
    } for x in Entity.objects.all()]

    return render(request, 'list_entities.html', context)

def create(request):
    if request.method == 'GET':
        context = {
            'attr_types': AttrTypes
        }
        return render(request, 'create_entity.html', context)
    elif request.method == 'POST':
        try:
            received_json = json.loads(request.body.decode('utf-8'))
        except json.decoder.JSONDecodeError:
            return HttpResponse('Failed to parse string to JSON', status=400)

        # validate input parameters
        if not _is_valid(received_json):
            return HttpResponse('Invalid parameters are specified', status=400)

        # create AttributeBase objects
        entity = Entity(name=received_json['name'],
                        note=received_json['note'])
        entity.save()

        for attr in received_json['attrs']:
            if _is_valid_attr(attr):
                attr_base = AttributeBase(name=attr['name'],
                                          type=int(attr['type']),
                                          is_mandatory=attr['is_mandatory'])
                attr_base.save()
                entity.attr_bases.add(attr_base)

        return redirect('/entity/')
    else:
        HttpResponse('Invalid HTTP method is specified', status=400)

def _is_valid(params):
    if not isinstance(params, dict):
        return False
    if ('name' not in params) or ('attrs' not in params):
        return False
    if (not isinstance(params['name'], str)) or (not isinstance(params['attrs'], list)):
        return False
    if not params["name"]:
        return False
    if not params["attrs"]:
        return False
    if not [x for x in params["attrs"] if _is_valid_attr(x)]:
        return False
    return True

def _is_valid_attr(attr):
    if not isinstance(attr, dict):
        return False
    if 'name' not in attr:
        return False
    if not attr['name']:
        return False
    if re.match(r'^\s*$', attr['name']):
        return False
    return True
