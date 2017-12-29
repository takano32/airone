import json
import logging

from django.http import HttpResponse
from django.http.response import JsonResponse
from django.contrib.auth.models import Permission

from airone.lib.acl import ACLType, ACLObjType
from airone.lib.http import http_get, http_post, render

from entity.models import Entity, EntityAttr
from entry.models import Entry, Attribute
from group.models import Group
from user.models import User
from .models import ACLBase

Logger = logging.getLogger(__name__)


@http_get
def index(request, obj_id):
    if not ACLBase.objects.filter(id=obj_id).count():
        return HttpResponse('Failed to find target object to set ACL', status=400)

    # This is an Entity or EntityAttr
    target_obj = ACLBase.objects.get(id=obj_id).get_subclass_object()

    # get ACLTypeID of target_obj if a permission is set
    def get_current_permission(member):
        permissions = [x for x in member.permissions.all() if x.get_objid() == target_obj.id]
        if permissions:
            return permissions[0].get_aclid()
        else:
            return 0

    # Some type of objects needs object that refers target_obj (e.g. Attribute)
    # for showing breadcrumb navigation.
    parent_obj = None
    try:
        if isinstance(target_obj, Attribute):
            parent_obj = target_obj.parent_entry
        elif isinstance(target_obj, EntityAttr):
            parent_obj = target_obj.parent_entity
    except StopIteration:
        Logger.warning('failed to get related parent object')

    context = {
        'object': target_obj,
        'parent': parent_obj,
        'acltypes': [{'id':x.id, 'name':x.label} for x in ACLType.all()],
        'members': [{'id': x.id,
                     'name': x.username,
                     'current_permission': get_current_permission(x),
                     'type': 'user'} for x in User.objects.filter(is_active=True)] +
                   [{'id': x.id,
                     'name': x.name,
                     'current_permission': get_current_permission(x),
                     'type': 'group'} for x in Group.objects.filter(is_active=True)]
    }
    return render(request, 'edit_acl.html', context)

@http_post([
    {'name': 'object_id', 'type': str,
     'checker': lambda x: ACLBase.objects.filter(id=x['object_id']).count()},
    {'name': 'object_type', 'type': str,
     'checker': lambda x: x['object_type']},
    {'name': 'acl', 'type': list, 'meta': [
        {'name': 'member_type', 'type': str,
         'checker': lambda x: x['member_type'] == 'user' or x['member_type'] == 'group'},
        {'name': 'member_id', 'type': str,
         'checker': lambda x: any(
             [k.objects.filter(id=x['member_id']).count() for k in [User, Group]]
          )},
        {'name': 'value', 'type': (str, type(None)),
         'checker': lambda x: [y for y in ACLType.all() if int(x['value']) == y]},
    ]},
    {'name': 'default_permission', 'type': str, 'checker': lambda x: any(
        [y == int(x['default_permission']) for y in ACLType.all()]
    )},
])
def set(request, recv_data):
    acl_obj = getattr(_get_acl_model(recv_data['object_type']),
                      'objects').get(id=recv_data['object_id'])

    acl_obj.is_public = False
    if 'is_public' in recv_data:
        acl_obj.is_public = True

    acl_obj.default_permission = int(recv_data['default_permission'])

    # update the Public/Private flag parameter
    acl_obj.save()

    for acl_data in [x for x in recv_data['acl'] if x['value']]:
        if acl_data['member_type'] == 'user':
            member = User.objects.get(id=acl_data['member_id'])
        else:
            member = Group.objects.get(id=acl_data['member_id'])

        acl_type = [x for x in ACLType.all() if x == int(acl_data['value'])][0]

        # update permissios for the target ACLBased object
        _set_permission(member, acl_obj, acl_type)

        # update permissios/acl for the related ACLBase object
        if isinstance(acl_obj, Entity):
            # update permissions of members
            [_set_permission(member, x, acl_type)
                    for x in Entry.objects.filter(schema=acl_obj)]

            # update flag of aclbase object
            Entry.objects.filter(schema=acl_obj).update(is_public=acl_obj.is_public)

        elif isinstance(acl_obj, EntityAttr):
            # update permissions of members
            [_set_permission(member, x, acl_type)
                    for x in Attribute.objects.filter(schema=acl_obj)]

            # update flag of aclbase object
            Attribute.objects.filter(schema=acl_obj).update(is_public=acl_obj.is_public)

    redirect_url = '/'
    if isinstance(acl_obj, Entity):
        redirect_url = '/entity/'
    elif isinstance(acl_obj, EntityAttr):
        redirect_url = '/entity/edit/%s' % acl_obj.parent_entity.id
    elif isinstance(acl_obj, Entry):
        redirect_url = '/entry/show/%s' % acl_obj.id
    elif isinstance(acl_obj, Attribute):
        redirect_url = '/entry/edit/%s' % acl_obj.parent_entry.id

    return JsonResponse({
        'redirect_url': redirect_url,
        'msg': 'Success to update ACL of "%s"' % acl_obj.name,
    })

def _get_acl_model(object_id):
    if int(object_id) == ACLObjType.Entity:
        return Entity
    if int(object_id) == ACLObjType.Entry:
        return Entry
    elif int(object_id) == ACLObjType.EntityAttr:
        return EntityAttr
    elif int(object_id) == ACLObjType.EntryAttr:
        return Attribute
    else:
        return ACLBase

def _set_permission(member, acl_obj, acl_type):
    # clear unset permissions of target ACLbased object
    for _acltype in ACLType.all():
        if _acltype != acl_type and _acltype != ACLType.Nothing:
            member.permissions.remove(getattr(acl_obj, _acltype.name))

    # set new permissoin to be specified except for 'Nothing' permission
    if acl_type != ACLType.Nothing:
        member.permissions.add(getattr(acl_obj, acl_type.name))
