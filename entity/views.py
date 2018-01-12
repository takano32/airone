import logging
import re
import io

from django.http import HttpResponse
from django.http.response import JsonResponse
from django.db.models import Q
from django.core.exceptions import PermissionDenied

from .models import Entity
from .models import EntityAttr
from user.models import User, History
from entry.models import Entry, Attribute, AttributeValue
from entity.admin import EntityResource, EntityAttrResource

from airone.lib.types import AttrTypes, AttrTypeObj, AttrTypeValue
from airone.lib.http import HttpResponseSeeOther
from airone.lib.http import http_get, http_post
from airone.lib.http import check_permission
from airone.lib.http import render
from airone.lib.http import get_download_response
from airone.lib.http import http_file_upload
from airone.lib.http import check_superuser
from airone.lib.acl import get_permitted_objects
from airone.lib.acl import ACLType
from airone.lib.profile import airone_profile

Logger = logging.getLogger(__name__)


@airone_profile
@http_get
def index(request):
    user = User.objects.get(id=request.user.id)

    entity_objects = Entity.objects.order_by('name').filter(is_active=True)
    context = {
        'entities': [x for x in entity_objects if user.has_permission(x, ACLType.Readable)]
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
@check_permission(Entity, ACLType.Writable)
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

    attrs = [] # EntityAttrs of entity to be editted
    for attr_base in entity.attrs.filter(is_active=True).order_by('index'):
        # skip not-writable EntityAttr
        if user.has_permission(attr_base, ACLType.Writable):
            attrs.append(attr_base)

    entities = []
    [entities.append({
        'id': e.id,
        'name': e.name,
        'attrs': [{
            'id': attr.id,
            'name': attr.name,
            'type': attr.type,
            'is_mandatory': attr.is_mandatory,
            'referral': attr.referral.all(),
        } for attr in e.attrs.all()],
    }) for e in Entity.objects.filter(is_active=True) if user.has_permission(e, ACLType.Readable)]

    context = {
        'entity': entity,
        'entities': entities,
        'attr_types': AttrTypes,
        'attributes': attrs,
    }
    return render(request, 'edit_entity.html', context)

@airone_profile
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
@check_permission(Entity, ACLType.Writable)
def do_edit(request, entity_id, recv_data):
    user = User.objects.get(id=request.user.id)

    if not Entity.objects.filter(id=entity_id).count():
        return HttpResponse('Failed to get entity of specified id', status=400)

    # validation checks
    for attr in recv_data['attrs']:
        # formalize recv_data format
        if 'ref_ids' not in attr:
            attr['ref_ids'] = []

        if int(attr['type']) & AttrTypeValue['object'] and not attr['ref_ids']:
            return HttpResponse('Need to specify enabled referral ids', status=400)

        if any([Entity.objects.filter(id=x).count() == 0 for x in attr['ref_ids']]):
            return HttpResponse('Specified referral is invalid', status=400)

    entity = Entity.objects.get(id=entity_id)

    # register history to modify Entity
    history = user.seth_entity_mod(entity)

    # check operation history detail
    if entity.name != recv_data['name']:
        history.mod_entity(entity, 'old name: "%s"' % (entity.name))

    # update status parameters
    if recv_data['is_toplevel']:
        entity.set_status(Entity.STATUS_TOP_LEVEL)
    else:
        entity.del_status(Entity.STATUS_TOP_LEVEL)

    # update entity metatada informations to new ones
    entity.name = recv_data['name']
    entity.note = recv_data['note']
    entity.save()

    # update processing for each attrs
    for attr in recv_data['attrs']:
        # This is the variable to describe update detail of EntityAttr to register the History
        detail_attr = []

        if 'deleted' in attr:
            # In case of deleting attribute which has been already existed
            attr_obj = EntityAttr.objects.get(id=attr['id'])

            # reset the cache of referred entry that each attribute_value refer to
            referred_ids = set()
            if attr_obj.type & AttrTypeValue['object']:

                attrs = Attribute.objects.filter(schema=attr_obj.id, is_active=True)
                for attrv in sum([list(a.get_latest_values()) for a in attrs], []):
                    if attr_obj.type & AttrTypeValue['array']:
                        [referred_ids.add(x.referral.id) for x in attrv.data_array.all()]
                    else:
                        referred_ids.add(attrv.referral.id)

            # delete all related Attributes of target EntityAttr
            [x.delete() for x in Attribute.objects.filter(schema=attr_obj.id, is_active=True)]

            # reset referred_entries cache
            for entry in [Entry.objects.get(id=x) for x in referred_ids]:
                entry.get_referred_objects(use_cache=False)

            attr_obj.delete()

            # register History to register deleting EntityAttr
            history.del_attr(attr_obj)

        elif 'id' in attr and EntityAttr.objects.filter(id=attr['id']).count():
            # In case of updating attribute which has been already existed
            attr_obj = EntityAttr.objects.get(id=attr['id'])

            # register operaion history if the parameters are changed
            if attr_obj.name != attr['name']:
                history.mod_attr(attr_obj, 'old name: "%s"' % (attr_obj.name))

            if attr_obj.is_mandatory != attr['is_mandatory']:
                if attr['is_mandatory']:
                    history.mod_attr(attr_obj, 'set mandatory flag')
                else:
                    history.mod_attr(attr_obj, 'unset mandatory flag')

            params = {
                'name': attr['name'],
                'type': attr['type'],
                'refs': [int(x) for x in attr['ref_ids']],
                'index': attr['row_index'],
                'is_mandatory': attr['is_mandatory'],
            }
            if attr_obj.is_updated(**params):
                # Clear the latest flag for each latest values if the attribute type is changed
                if attr_obj.type != int(attr['type']):
                    def clear_latest_flag(attrv):
                        attrv.del_status(AttributeValue.STATUS_LATEST)

                        # If the target attrv has data_array,
                        # this also clear latest flag for each leaf values
                        if attrv.data_array and attrv.data_array.count():
                            [x.del_status(AttributeValue.STATUS_LATEST) for x in attrv.data_array.all()]

                        attrv.save()

                    active_attrs = Attribute.objects.filter(schema=attr_obj, is_active=True)

                    [clear_latest_flag(v) for v in
                            sum([list(a.get_latest_values()) for a in active_attrs], [])]

                attr_obj.name = attr['name']
                attr_obj.type = attr['type']
                attr_obj.is_mandatory = attr['is_mandatory']
                attr_obj.index = int(attr['row_index'])

                # the case of an attribute that has referral entry
                attr_obj.referral.clear()
                if int(attr['type']) & AttrTypeValue['object']:
                    [attr_obj.referral.add(Entity.objects.get(id=x)) for x in attr['ref_ids']]

                attr_obj.save()

        else:
            # In case of creating new attribute
            attr_obj = EntityAttr.objects.create(name=attr['name'],
                                                 type=int(attr['type']),
                                                 is_mandatory=attr['is_mandatory'],
                                                 index=int(attr['row_index']),
                                                 created_user=user,
                                                 parent_entity=entity)

            # append referral objects
            if int(attr['type']) & AttrTypeValue['object']:
                [attr_obj.referral.add(Entity.objects.get(id=x)) for x in attr['ref_ids']]

            # add a new attribute on the existed Entries
            entity.attrs.add(attr_obj)

            # register History to register adding EntityAttr
            history.add_attr(attr_obj)

    return JsonResponse({
        'entity_id': entity.id,
        'entity_name': entity.name,
        'msg': 'Success to update Entity "%s"' % entity.name,
    })

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
@check_superuser
def do_create(request, recv_data):
    # validation checks
    for attr in recv_data['attrs']:
        # formalize recv_data format
        if 'ref_ids' not in attr:
            attr['ref_ids'] = []

        if int(attr['type']) & AttrTypeValue['object'] and not attr['ref_ids']:
            return HttpResponse('Need to specify enabled referral ids', status=400)

        if any([Entity.objects.filter(id=x).count() == 0 for x in attr['ref_ids']]):
            return HttpResponse('Specified referral is invalid', status=400)

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

    # register history to modify Entity
    history = user.seth_entity_add(entity)

    for attr in recv_data['attrs']:
        attr_base = EntityAttr.objects.create(name=attr['name'],
                                              type=int(attr['type']),
                                              is_mandatory=attr['is_mandatory'],
                                              created_user=user,
                                              parent_entity=entity,
                                              index=int(attr['row_index']))

        if int(attr['type']) & AttrTypeValue['object']:
            [attr_base.referral.add(Entity.objects.get(id=x)) for x in attr['ref_ids']]

        entity.attrs.add(attr_base)

        # register history to modify Entity
        history.add_attr(attr_base)

    return JsonResponse({
        'entity_id': entity.id,
        'entity_name': entity.name,
        'msg': 'Success to create Entity "%s"' % entity.name,
    })

@http_get
def export(request):
    user = User.objects.get(id=request.user.id)

    output = io.StringIO()

    output.write("Entity: \n")
    output.write(EntityResource().export(get_permitted_objects(user,
                                                               Entity,
                                                               ACLType.Readable)).yaml)

    output.write("\n")
    output.write("EntityAttr: \n")
    output.write(EntityAttrResource().export(get_permitted_objects(user,
                                                                   EntityAttr,
                                                                   ACLType.Readable)).yaml)

    return get_download_response(output, 'entity.yaml')

@http_post([])
@check_permission(Entity, ACLType.Full)
def do_delete(request, entity_id, recv_data):
    user = User.objects.get(id=request.user.id)
    ret = {}

    if not Entity.objects.filter(id=entity_id).count():
        return HttpResponse('Failed to get entity of specified id', status=400)

    entity = Entity.objects.get(id=entity_id)

    # save deleting target name before do it
    ret['name'] = entity.name

    if Entry.objects.filter(schema=entity,is_active=True).count() != 0:
        return HttpResponse('cannot delete Entity because one or more Entries are not deleted', status=400)

    entity.delete()
    history = user.seth_entity_del(entity)

    # Delete all attributes which target Entity have
    for attr in entity.attrs.all():
        attr.delete()
        history.del_attr(attr)

    return JsonResponse(ret)

@http_get
def history(request, entity_id):
    user = User.objects.get(id=request.user.id)

    if not Entity.objects.filter(id=entity_id).count():
        return HttpResponse('Failed to get entity of specified id', status=400)

    # entity to be editted is given by url
    entity = Entity.objects.get(id=entity_id)

    context = {
        'entity': entity,
        'history': History.objects.filter(target_obj=entity, is_detail=False).order_by('-time'),
    }

    return render(request, 'history_entity.html', context)
