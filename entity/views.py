import json
import re

from django.http import HttpResponse
from django.core.exceptions import PermissionDenied

from .models import Entity
from .models import AttributeBase
from user.models import User
from entry.models import Entry, Attribute

from airone.lib.types import AttrTypes, AttrTypeObj
from airone.lib.http import HttpResponseSeeOther
from airone.lib.http import http_get, http_post
from airone.lib.http import check_permission
from airone.lib.http import render


@http_get
def index(request):
    user = User.objects.get(id=request.user.id)

    context = {
        'entities': [x for x in Entity.objects.all() if user.has_permission(x, 'readable')]
    }
    return render(request, 'list_entities.html', context)

@http_get
def create(request):
    context = {
        'entities': Entity.objects.all(),
        'attr_types': AttrTypes
    }
    return render(request, 'create_entity.html', context)

@http_get
@check_permission(Entity, 'writable')
def edit(request, entity_id):
    user = User.objects.get(id=request.user.id)

    if not Entity.objects.filter(id=entity_id).count():
        return HttpResponse('Failed to get entity of specified id', status=400)

    entity = Entity.objects.get(id=entity_id)
    context = {
        'entity': entity,
        'entities': Entity.objects.all(),
        'attr_types': AttrTypes,
        'attributes': [x for x in entity.attr_bases.all() if user.has_permission(x, 'writable')],
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
            any([y == int(x['type']) for y in AttrTypes]) and (
                int(x['type']) != AttrTypeObj or (
                    int(x['type']) == AttrTypeObj and
                    'ref_id' in x and Entity.objects.filter(id=x['ref_id']).count()
                )
            )
        )},
        {'name': 'is_mandatory', 'type': bool}
    ]}
])
@check_permission(Entity, 'writable')
def do_edit(request, entity_id, recv_data):
    user = User.objects.get(id=request.user.id)

    if not Entity.objects.filter(id=entity_id).count():
        return HttpResponse('Failed to get entity of specified id', status=400)

    entity = Entity.objects.get(id=entity_id)

    entity.name = recv_data['name']
    entity.note = recv_data['note']
    entity.save()

    for attr in recv_data['attrs']:
        is_new_attr_base = False
        if 'id' in attr and AttributeBase.objects.filter(id=attr['id']).count():
            attr_base = AttributeBase.objects.get(id=attr['id'])

            attr_base.name = attr['name']
            attr_base.type = attr['type']
            attr_base.is_mandatory = attr['is_mandatory']
        else:
            is_new_attr_base = True
            attr_base = AttributeBase(name=attr['name'],
                                      type=int(attr['type']),
                                      is_mandatory=attr['is_mandatory'],
                                      created_user=user)

        if int(attr['type']) == AttrTypeObj:
            attr_base.referral = Entity.objects.get(id=attr['ref_id'])
        else:
            attr_base.referral = None

        attr_base.save()

        if is_new_attr_base:
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
            any([y == int(x['type']) for y in AttrTypes]) and (
                int(x['type']) != AttrTypeObj or (
                    int(x['type']) == AttrTypeObj and
                    'ref_id' in x and Entity.objects.filter(id=x['ref_id']).count()
                )
            )
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

        if int(attr['type']) == AttrTypeObj:
            attr_base.referral = Entity.objects.get(id=attr['ref_id'])

        attr_base.save()
        entity.attr_bases.add(attr_base)

    return HttpResponseSeeOther('/entity/')
