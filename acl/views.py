import json

from django.shortcuts import render
from django.http import HttpResponse
from django.contrib.auth.models import Group

from airone.lib import ACLType, ACLObjType
from airone.lib import http_get, http_post

from entity.models import Entity
from user.models import User
from .models import ACLBase


@http_get
def index(request, obj_id):
    if not ACLBase.objects.filter(id=obj_id).count():
        return HttpResponse('Failed to find target object to set ACL', status=400)

    # This is an Entity or AttributeBase
    target_obj = ACLBase.objects.get(id=obj_id)

    context = {
        'object': target_obj,
        'acltypes': [{'id':x.id, 'name':x.name} for x in ACLType()],
        'members': [{'id': x.id, 'name': x.username, 'type': 'user'} for x in User.objects.all()] +
                   [{'id': x.id, 'name': x.name, 'type': 'group'} for x in Group.objects.all()]
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
         'checker': lambda x: [y for y in ACLType() if int(x['value']) == y.id]},
    ]},
])
def set(request, recv_data):
    acl_obj = getattr(_get_acl_model(recv_data['object_type']),
                      'objects').get(id=recv_data['object_id'])

    _is_public = False
    if 'is_public' in recv_data:
        acl_obj.is_public = True
    else:
        acl_obj.is_public = False

    # update the Public/Private flag parameter
    acl_obj.save()

    for acl_data in [x for x in recv_data['acl'] if x['value']]:
        if acl_data['member_type'] == 'user':
            member = User.objects.get(id=acl_data['member_id'])
        else:
            member = Group.objects.get(id=acl_data['member_id'])

        acl_type = [x for x in ACLType() if x.id == int(acl_data['value'])][0]

        # update member permissios for the ACLBased object
        _set_permission(member, acl_obj, acl_type)

    return HttpResponse("")

def _get_acl_model(object_id):
    if int(object_id) == ACLObjType.Entity:
        return Entity
    elif int(object_id) == ACLObjType.AttrBase:
        return AttributeBase
    else:
        return ACLBase

def _set_permission(member, acl_obj, acl_type):
    # clear unset permissions of target ACLbased object
    for _acltype in ACLType():
        if _acltype != acl_type:
            member.permissions.remove(getattr(acl_obj, _acltype.name))

    # set new permissoin to be specified
    member.permissions.add(getattr(acl_obj, acl_type.name))
