import logging
import re
import io

from django.http import HttpResponse
from django.db.models import Q
from django.core.exceptions import PermissionDenied

from .models import Entity
from .models import EntityAttr
from user.models import User
from entry.models import Entry, Attribute
from entity.admin import EntityResource, EntityAttrResource

from airone.lib.types import AttrTypes, AttrTypeObj, AttrTypeValue
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
        'entities': [x for x in Entity.objects.filter(is_active=True) if user.has_permission(x, 'readable')]
    }
    return render(request, 'list_entities.html', context)

@http_get
def create(request):
    context = {
        'entities': Entity.objects.filter(is_active=True),
        'attr_types': AttrTypes
    }
    return render(request, 'create_entity.html', context)

@http_get
@check_permission(Entity, 'writable')
def edit(request, entity_id):
    user = User.objects.get(id=request.user.id)

    if not Entity.objects.filter(id=entity_id).count():
        return HttpResponse('Failed to get entity of specified id', status=400)

    # entity to be editted is given by url
    entity = Entity.objects.get(id=entity_id)

    # when an entity in referral attribute is deleted
    # user should be able to select new entity or keep it unchanged
    # candidate entites for referral are:
    # - active(not deleted) entity
    # - current value of any attributes even if the entity has been deleted

    # query of candidate entities for referral
    query = Q(is_active=True) # active entity should be displayed
    attrs = [] # EntityAttrs of entity to be editted

    for attr_base in entity.attrs.order_by('index').all():
        # skip not-writable EntityAttr
        if not user.has_permission(attr_base, 'writable'):
            continue
        # logical-OR current value of referral to query of candidate entites
        if attr_base.referral:
            query = query | Q(id=attr_base.referral.id)
        attrs.append(attr_base)

    entities = Entity.objects.filter(query)

    context = {
        'entity': entity,
        'entities': entities,
        'attr_types': AttrTypes,
        'attributes': attrs,
    }
    return render(request, 'edit_entity.html', context)

@http_post([
    {'name': 'name', 'type': str, 'checker': lambda x: x['name']},
    {'name': 'note', 'type': str},
    {'name': 'is_toplevel', 'type': bool},
    {'name': 'attrs', 'type': list, 'meta': [
        {'name': 'name', 'type': str, 'checker': lambda x: (
            x['name'] and not re.match(r'^\s*$', x['name'])
        )},
        {'name': 'type', 'type': str, 'checker': lambda x: (
            any([y == int(x['type']) for y in AttrTypes])
        )},
        {'name': 'is_mandatory', 'type': bool},
        {'name': 'row_index', 'type': str, 'checker': lambda x: (
            re.match(r"^[0-9]*$", x['row_index'])
        )}
    ]}
])
@check_permission(Entity, 'writable')
def do_edit(request, entity_id, recv_data):
    user = User.objects.get(id=request.user.id)

    if not Entity.objects.filter(id=entity_id).count():
        return HttpResponse('Failed to get entity of specified id', status=400)

    entity = Entity.objects.get(id=entity_id)

    # update status parameters
    if recv_data['is_toplevel']:
        entity.set_status(Entity.STATUS_TOP_LEVEL)
    else:
        entity.del_status(Entity.STATUS_TOP_LEVEL)

    entity.name = recv_data['name']
    entity.note = recv_data['note']
    entity.save()

    for attr in recv_data['attrs']:
        if (int(attr['type']) & AttrTypeValue['object'] and
            ('ref_id' not in attr or not Entity.objects.filter(id=attr['ref_id']).count())):
            return HttpResponse('Failed to get entity that is referred', status=400)

        is_deleted = is_new_attr_base = False
        if 'id' in attr and EntityAttr.objects.filter(id=attr['id']).count():
            # update attributes which is already created
            attr_base = EntityAttr.objects.get(id=attr['id'])

            attr_base.name = attr['name']
            attr_base.type = attr['type']
            attr_base.is_mandatory = attr['is_mandatory']
            attr_base.index = int(attr['row_index'])

            if 'deleted' in attr:
                is_deleted = True
        else:
            # add an new attributes
            is_new_attr_base = True
            attr_base = EntityAttr(name=attr['name'],
                                      type=int(attr['type']),
                                      is_mandatory=attr['is_mandatory'],
                                      index=int(attr['row_index']),
                                      created_user=user,
                                      parent_entity=entity)

        # the case of an attribute that has referral entry
        if int(attr['type']) & AttrTypeValue['object']:
            attr_base.referral = Entity.objects.get(id=attr['ref_id'])
        else:
            attr_base.referral = None

        if not is_deleted:
            # create or update an EntityAttr and related Attributes
            attr_base.save()

            if is_new_attr_base:
                # add a new attribute on the existed Entries
                entity.attrs.add(attr_base)

                for entry in Entry.objects.filter(schema=entity):
                    entry.add_attribute_from_base(attr_base, user)
            else:
                # update Attributes which are already created
                [x.update_from_base(attr_base)
                        for x in Attribute.objects.filter(schema_id=attr_base.id)]
        else:
            # delete all related Attributes of target EntityAttr
            [x.delete() for x in Attribute.objects.filter(schema_id=attr_base.id)]

            attr_base.delete()

    return HttpResponseSeeOther('/entity/')

@http_post([
    {'name': 'name', 'type': str, 'checker': lambda x: (
        x['name'] and not Entity.objects.filter(name=x['name']).count()
    )},
    {'name': 'note', 'type': str},
    {'name': 'is_toplevel', 'type': bool},
    {'name': 'attrs', 'type': list, 'meta': [
        {'name': 'name', 'type': str, 'checker': lambda x: (
            x['name'] and not re.match(r'^\s*$', x['name'])
        )},
        {'name': 'type', 'type': str, 'checker': lambda x: (
            any([y == int(x['type']) for y in AttrTypes])
        )},
        {'name': 'is_mandatory', 'type': bool},
        {'name': 'row_index', 'type': str, 'checker': lambda x: (
            re.match(r"^[0-9]*$", x['row_index'])
        )}
    ]},
])
def do_create(request, recv_data):
    # get user object that current access
    user = User.objects.get(id=request.user.id)

    # create EntityAttr objects
    entity = Entity(name=recv_data['name'],
                    note=recv_data['note'],
                    created_user=user)

    # set status parameters
    if recv_data['is_toplevel']:
        entity.set_status(Entity.STATUS_TOP_LEVEL)

    entity.save()

    for attr in recv_data['attrs']:
        if (int(attr['type']) & AttrTypeValue['object'] and
            ('ref_id' not in attr or not Entity.objects.filter(id=attr['ref_id']).count())):
            return HttpResponse('Failed to get entity that is referred', status=400)

        attr_base = EntityAttr(name=attr['name'],
                                  type=int(attr['type']),
                                  is_mandatory=attr['is_mandatory'],
                                  created_user=user,
                                  parent_entity=entity,
                                  index=int(attr['row_index']))

        if int(attr['type']) & AttrTypeValue['object']:
            attr_base.referral = Entity.objects.get(id=attr['ref_id'])

        attr_base.save()
        entity.attrs.add(attr_base)

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
    output.write("EntityAttr: \n")
    output.write(EntityAttrResource().export(get_permitted_objects(user,
                                                                 EntityAttr,
                                                                 'readable')).yaml)

    return get_download_response(output, 'entity.yaml')

@http_post([])
@check_permission(Entity, 'full')
def do_delete(request, entity_id, recv_data):
    if not Entity.objects.filter(id=entity_id).count():
        return HttpResponse('Failed to get entity of specified id', status=400)

    entity = Entity.objects.get(id=entity_id)

    if Entry.objects.filter(schema=entity,is_active=True).count() != 0:
        return HttpResponse('cannot delete Entity because one or more Entries are not deleted', status=400)

    entity.is_active=False
    entity.save()

    # Delete all attributes which target Entity have
    for attr in entity.attrs.all():
        attr.is_active = False
        attr.save()

    return HttpResponse()
