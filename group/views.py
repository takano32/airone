import io
import json

from django.core.exceptions import ObjectDoesNotExist
from django.contrib.auth.models import Group
from django.http import HttpResponse

from airone.lib.http import HttpResponseSeeOther
from airone.lib.http import http_get, http_post
from airone.lib.http import render
from airone.lib.http import get_download_response
from airone.lib.http import check_superuser

from user.models import User
from user.admin import UserResource
from .admin import GroupResource


@http_get
def index(request):
    context = {}
    context['groups'] = [{
        'id': x.id,
        'name': x.name,
        'members': User.objects.filter(groups__name=x.name, is_active=True).order_by('username'),
    } for x in Group.objects.all()]

    return render(request, 'list_group.html', context)

@http_get
@check_superuser
def edit(request, group_id):
    if not Group.objects.filter(id=group_id).count():
        return HttpResponse('Failed to get group of specified id', status=400)

    group = Group.objects.get(id=group_id)

    # set selected group information
    context = {
        'default_group_id': int(group_id),
        'current_group_name': group.name,
        'current_group_members': User.objects.filter(groups__id=group.id,
                                                     is_active=True).order_by('username'),
        'submit_label': '更新',
        'submit_ref': '/group/do_edit/%s' % group_id,
    }

    # set group members for each groups
    context['groups'] = [{
        'id': x.id,
        'name': x.name,
        'members': User.objects.filter(groups__id=x.id, is_active=True).order_by('username'),
    } for x in Group.objects.all()]

    # set all user
    context['groups'].insert(0, {
        'id': 0,
        'name': '-- ALL --',
        'members': User.objects.filter(is_active=True),
    })

    return render(request, 'edit_group.html', context)

@http_post([
    {'name': 'name', 'type': str, 'checker': lambda x: x['name']},
    {'name': 'users', 'type': list, 'checker': lambda x: (
        x['users'] and all([User.objects.filter(id=u).count() for u in x['users']])
    )}
])
@check_superuser
def do_edit(request, group_id, recv_data):
    if not Group.objects.filter(id=group_id).count():
        return HttpResponse('Failed to get group of specified id', status=400)

    group = Group.objects.get(id=group_id)
    if Group.objects.filter(name=recv_data['name']).count():
        same_name_group = Group.objects.get(name=recv_data['name'])

        if group.id != same_name_group.id:
            return HttpResponse('Failed to update because there is another group of same name',
                                status=400)

    # get users who are belonged to the selected group for updating
    old_users = [str(x.id) for x in User.objects.filter(groups__id=group_id, is_active=True)]

    # update group_name with specified one
    group.name = recv_data['name']
    group.save()

    # the processing for deleted users
    for user in [User.objects.get(id=x) for x in set(old_users) - set(recv_data['users'])]:
        user.groups.remove(group)

    # the processing for added users
    for user in [User.objects.get(id=x) for x in set(recv_data['users']) - set(old_users)]:
        user.groups.add(group)

    return HttpResponse('')

@http_get
@check_superuser
def create(request):
    context = {
        'default_group_id': 0,
        'submit_label': '作成',
        'submit_ref': '/group/do_create',
    }

    # set group members for each groups
    context['groups'] = [{
        'id': x.id,
        'name': x.name,
        'members': User.objects.filter(groups__id=x.id, is_active=True).order_by('username'),
    } for x in Group.objects.all()]

    # set all user
    context['groups'].insert(0, {
        'id': 0,
        'name': '-- ALL --',
        'members': User.objects.filter(is_active=True),
    })

    return render(request, 'edit_group.html', context)

@http_post([
    {'name': 'name', 'type': str, 'checker': lambda x: (
        x['name'] and not Group.objects.filter(name=x['name']).count()
    )},
    {'name': 'users', 'type': list, 'checker': lambda x: (
        x['users'] and all([User.objects.filter(id=u).count() for u in x['users']])
    )}
])
@check_superuser
def do_create(request, recv_data):
    new_group = Group(name=recv_data['name'])
    new_group.save()

    for user in [User.objects.get(id=x) for x in recv_data['users']]:
        user.groups.add(new_group)

    return HttpResponseSeeOther('/group/')

@http_post([
    {'name': 'name', 'type': str, 'checker': lambda x: (
        x['name'] and (Group.objects.filter(name=x['name']).count() == 1)
    )},
])
@check_superuser
def do_delete(request, recv_data):
    name = recv_data['name']
    group = Group.objects.get(name=name)

    for user in User.objects.filter(groups__name=name):
        user.groups.remove(group)
        user.save()

    group.delete()

    return HttpResponse()

@http_get
def export(request):
    user = User.objects.get(id=request.user.id)

    output = io.StringIO()

    output.write("Group: \n")
    output.write(GroupResource().export().yaml)

    output.write("\n")
    output.write("User: \n")
    output.write(UserResource().export().yaml)

    return get_download_response(output, 'user_group.yaml')
