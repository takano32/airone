import json

from django.shortcuts import render
from django.http import HttpResponse
from django.contrib.auth.models import Group

from airone.lib import ACLType, ACLObjType
from entity.models import Entity
from user.models import User
from .models import ACLBase


def index(request, obj_id):
    if not obj_id:
        return HttpResponse('The "target_id" parameter is must to be specified', status=400)

    if not ACLBase.objects.filter(id=obj_id).count():
        return HttpResponse('Failed to find target object to set ACL', status=400)

    # This is an Entity or AttributeBase
    target_obj = ACLBase.objects.get(id=obj_id)

    context = {
        'object_id': target_obj.id,
        'object_type': target_obj.objtype,
        'object_name': target_obj.name,
        'acltypes': [{'id':x.id, 'name':x.name} for x in ACLType()],
        'members': [{'id': x.id, 'name': x.username, 'type': 'user'} for x in User.objects.all()] +
                   [{'id': x.id, 'name': x.name, 'type': 'group'} for x in Group.objects.all()]
    }
    return render(request, 'edit_acl.html', context)

def set(request):
    if request.method == 'POST':
        try:
            recv_data = json.loads(request.body.decode('utf-8'))
        except json.decoder.JSONDecodeError:
            return HttpResponse('Failed to parse string to JSON', status=400)

        # validation check for the received data
        if not _is_valid(recv_data):
            return HttpResponse('Invalid parameters are specified', status=400)


        acl_obj = getattr(_get_acl_model(recv_data['object_type']),
                          'objects').get(id=recv_data['object_id'])

        for acl_data in [x for x in recv_data['acl'] if x['value']]:
            if acl_data['member_type'] == 'user':
                member = User.objects.get(id=acl_data['member_id'])
            else:
                member = Group.objects.get(id=acl_data['member_id'])

            acl_type = [x for x in ACLType() if x.id == int(acl_data['value'])][0]

            # update member permissios for the ACLBased object
            _set_permission(member, acl_obj, acl_type)

        return HttpResponse("")
    else:
        return HttpResponse("This page doesn't support this method", status=400)

def _get_acl_model(object_id):
    if int(object_id) == ACLObjType.Entity:
        return Entity
    elif int(object_id) == ACLObjType.AttrBase:
        return AttributeBase

def _set_permission(member, acl_obj, acl_type):
    # clear unset permissions of target ACLbased object
    for _acltype in ACLType():
        if _acltype != acl_type:
            member.permissions.remove(getattr(acl_obj, _acltype.name))

    # set new permissoin to be specified
    member.permissions.add(getattr(acl_obj, acl_type.name))

def _is_valid(params):
    if not isinstance(params, dict):
        return False

    # These are existance checks of each parameters
    if 'acl' not in params or 'object_id' not in params or 'object_type' not in params:
        return False

    # These are type checks of each parameters
    if (not isinstance(params['acl'], list) or
        not isinstance(params['object_id'], str) or
        not isinstance(params['object_type'], str)):
        return False

    # These are value checks of each parameters
    if [x for x in params['acl'] if not _is_valid_acl(x)]:
        return False
    if not params['object_id']:
        return False
    if not ACLBase.objects.filter(id=params['object_id']).count():
        return False
    if not any([x for x in ACLObjType() if int(params['object_type']) == x]):
        return False

    return True

def _is_valid_acl(params):
    if not isinstance(params, dict):
        return False

    # These are existance checks of each parameters
    if 'member_id' not in params or 'value' not in params:
        return False

    # These are type checks of each parameters
    if not isinstance(params['member_id'], str):
        return False
    if not (isinstance(params['value'], str) or not params['value']):
        return False

    # These are value checks of each parameters
    if not params['member_id']:
        return False
    if params['member_type'] != 'user' and params['member_type'] != 'group':
        return False
    if not any([x.objects.filter(id=params['member_id']).count() for x in [User, Group]]):
        return False
    if not [x for x in ACLType() if int(params['value']) == x.id]:
        return False

    return True
