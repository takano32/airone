import logging
import re
import io

from django.http import HttpResponse
from django.core.exceptions import PermissionDenied

from .models import Entity
from .models import AttributeBase
from user.models import User
from entry.models import Entry, Attribute
from entity.admin import EntityResource, AttrBaseResource

from airone.lib.types import AttrTypes, AttrTypeObj
from airone.lib.http import HttpResponseSeeOther
from airone.lib.http import http_get, http_post
from airone.lib.http import check_permission
from airone.lib.http import render
from airone.lib.http import get_download_response
from airone.lib.http import http_file_upload
from airone.lib.acl import get_permitted_objects

Logger = logging.getLogger(__name__)


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
        is_deleted = is_new_attr_base = False
        if 'id' in attr and AttributeBase.objects.filter(id=attr['id']).count():
            # update attributes which is already created
            attr_base = AttributeBase.objects.get(id=attr['id'])

            attr_base.name = attr['name']
            attr_base.type = attr['type']
            attr_base.is_mandatory = attr['is_mandatory']

            if 'deleted' in attr:
                is_deleted = True
        else:
            # add an new attributes
            is_new_attr_base = True
            attr_base = AttributeBase(name=attr['name'],
                                      type=int(attr['type']),
                                      is_mandatory=attr['is_mandatory'],
                                      created_user=user,
                                      parent_entity=entity)

        # the case of an attribute that has referral entry
        if int(attr['type']) == AttrTypeObj:
            attr_base.referral = Entity.objects.get(id=attr['ref_id'])
        else:
            attr_base.referral = None

        if not is_deleted:
            # create or update an AttributeBase and related Attributes
            attr_base.save()

            if is_new_attr_base:
                # add a new attribute on the existed Entries
                entity.attr_bases.add(attr_base)

                for entry in Entry.objects.filter(schema=entity):
                    entry.add_attribute_from_base(attr_base, user)
            else:
                # update Attributes which are already created
                [x.update_from_base(attr_base)
                        for x in Attribute.objects.filter(schema_id=attr_base.id)]
        else:
            # delete all related Attributes of target AttributeBase
            [x.delete() for x in Attribute.objects.filter(schema_id=attr_base.id)]

            attr_base.delete()

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
                                  created_user=user,
                                  parent_entity=entity)

        if int(attr['type']) == AttrTypeObj:
            attr_base.referral = Entity.objects.get(id=attr['ref_id'])

        attr_base.save()
        entity.attr_bases.add(attr_base)

    return HttpResponseSeeOther('/entity/')

@http_get
def export(request):
    user = User.objects.get(id=request.user.id)

    output = io.StringIO()

    output.write("Entity: \n")
    output.write(EntityResource().export(get_permitted_objects(user,
                                                               Entity,
                                                               'readable')).yaml)

    output.write("\n")
    output.write("AttributeBase: \n")
    output.write(AttrBaseResource().export(get_permitted_objects(user,
                                                                 AttributeBase,
                                                                 'readable')).yaml)

    return get_download_response(output, 'entity.yaml')
