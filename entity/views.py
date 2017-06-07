import json
import re

from django.shortcuts import render
from django.http import HttpResponse
from django.core.exceptions import PermissionDenied

from .models import Entity
from .models import AttributeBase
from airone.lib import AttrTypes
from airone.lib import HttpResponseSeeOther
from airone.lib import http_get, http_post


@http_get
def index(request):
    context = {}
    context['entities'] = [{
        'name': x.name,
        'note': x.note,
    } for x in Entity.objects.all()]

    return render(request, 'list_entities.html', context)

@http_get
def create(request):
    context = {
        'attr_types': AttrTypes
    }
    return render(request, 'create_entity.html', context)

@http_post([
    {'name': 'name', 'type': str, 'checker': lambda x: (
        x['name'] and not Entity.objects.filter(name=x['name']).count()
    )},
    {'name': 'note', 'type': str},
    {'name': 'attrs', 'type': list, 'meta': [
        {'name': 'name', 'type': str, 'checker': lambda x: (
            x['name'] and not re.match(r'^\s*$', x['name'])
        )},
        {'name': 'type', 'type': str, 'checker': lambda x: (
            any([int(x['type']) == y.type for y in AttrTypes])
        )},
        {'name': 'is_mandatory', 'type': bool}
    ]}
])
def do_create(request, recv_data):
    # create AttributeBase objects
    entity = Entity(name=recv_data['name'],
                    note=recv_data['note'])
    entity.save()

    for attr in recv_data['attrs']:
        attr_base = AttributeBase(name=attr['name'],
                                  type=int(attr['type']),
                                  is_mandatory=attr['is_mandatory'])
        attr_base.save()
        entity.attr_bases.add(attr_base)

    return HttpResponseSeeOther('/entity/')
