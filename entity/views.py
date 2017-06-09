import json
import re

from django.http import HttpResponse
from django.core.exceptions import PermissionDenied

from .models import Entity
from .models import AttributeBase
from user.models import User
from entry.models import Entry, Attribute

from airone.lib.types import AttrTypes
from airone.lib.http import HttpResponseSeeOther
from airone.lib.http import http_get, http_post
from airone.lib.http import render


@http_get
def index(request):
    context = {}
    context['entities'] = Entity.objects.all()

    return render(request, 'list_entities.html', context)

@http_get
def create(request):
    context = {
        'attr_types': AttrTypes
    }
    return render(request, 'create_entity.html', context)

@http_get
def edit(request, entity_id):
    if not Entity.objects.filter(id=entity_id).count():
        return HttpResponse('Failed to get entity of specified id', status=400)

    entity = Entity.objects.get(id=entity_id)
    context = {
        'entity': entity,
        'attr_types': AttrTypes,
        'attributes': entity.attr_bases.all(),
    }
    return render(request, 'edit_entity.html', context)

@http_post([
    {'name': 'name', 'type': str, 'checker': lambda x: x['name']},
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
def do_edit(request, entity_id, recv_data):
    user = User.objects.get(id=request.user.id)

    if not Entity.objects.filter(id=entity_id).count():
        return HttpResponse('Failed to get entity of specified id', status=400)

    entity = Entity.objects.get(id=entity_id)

    entity.name = recv_data['name']
    entity.note = recv_data['note']
    entity.save()

    for attr in recv_data['attrs']:
        if 'id' in attr and AttributeBase.objects.filter(id=attr['id']).count():
            attr_base = AttributeBase.objects.get(id=attr['id'])

            attr_base.name = attr['name']
            attr_base.type = attr['type']
            attr_base.is_mandatory = attr['is_mandatory']
            attr_base.save()
        else:
            attr_base = AttributeBase(name=attr['name'],
                                      type=int(attr['type']),
                                      is_mandatory=attr['is_mandatory'],
                                      created_user=user)
            attr_base.save()
            entity.attr_bases.add(attr_base)

            # add a new attribute on the existed Entries
            for entry in Entry.objects.filter(schema=entity):
                entry.add_attribute_from_base(attr_base, user)

    return HttpResponseSeeOther('/entity/')

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
    # get user object that current access
    user = User.objects.get(id=request.user.id)

    # create AttributeBase objects
    entity = Entity(name=recv_data['name'],
                    note=recv_data['note'],
                    created_user=user)
    entity.save()

    for attr in recv_data['attrs']:
        attr_base = AttributeBase(name=attr['name'],
                                  type=int(attr['type']),
                                  is_mandatory=attr['is_mandatory'],
                                  created_user=user)
        attr_base.save()
        entity.attr_bases.add(attr_base)

    return HttpResponseSeeOther('/entity/')
