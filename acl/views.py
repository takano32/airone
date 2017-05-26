import json

from django.shortcuts import render
from django.http import HttpResponse

from airone.lib import ACLType
from user.models import Member
from acl.models import ACL, ACLBase
from entity.models import Entity


def index(request, obj_id):
    if not obj_id:
        return HttpResponse('The "target_id" parameter is must to be specified', status=400)

    if not ACLBase.objects.filter(id=obj_id).count():
        return HttpResponse('Failed to find target object to set ACL', status=400)

    # This is an Entity or AttributeBase
    target_obj = ACLBase.objects.get(id=obj_id)

    context = {
        'object_id': target_obj.id,
        'object_name': target_obj.name,
        'members': Member.objects.all(),
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

        # filters enabled ACL data
        acl_data = [x for x in recv_data['acl'] if x['value']]

        document = ACLBase.objects.get(id=recv_data['object_id'])

        for acl_data in [x for x in recv_data['acl'] if x['value']]:
            member = Member.objects.get(id=acl_data['member_id'])

            # clear target old-field which is previously set if needed
            document.acl.unset_member(member)

            if int(acl_data['value']) == ACLType.Readable:
                document.acl.readable.add(member)
            elif int(acl_data['value']) == ACLType.Writable:
                document.acl.writable.add(member)
            elif int(acl_data['value']) == ACLType.Deletable:
                document.acl.deletable.add(member)

        return HttpResponse("")
    else:
        return HttpResponse("This page doesn't support this method", status=400)

def _is_valid(params):
    if not isinstance(params, dict):
        return False

    # These are existance checks of each parameters
    if 'acl' not in params or 'object_id' not in params:
        return False

    # These are type checks of each parameters
    if not isinstance(params['acl'], list) or not isinstance(params['object_id'], str):
        return False

    # These are value checks of each parameters
    if [x for x in params['acl'] if not _is_valid_acl(x)]:
        return False
    if not params['object_id']:
        return False
    if not ACLBase.objects.filter(id=params['object_id']).count():
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
    if not Member.objects.filter(id=params['member_id']).count():
        return False
    if not [x for x in ACLType() if int(params['value']) == x]:
        return False

    return True
