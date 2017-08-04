import io
import json

from django.core.exceptions import ObjectDoesNotExist
from django.contrib.auth.models import Group
from django.http import HttpResponse

from airone.lib.http import HttpResponseSeeOther
from airone.lib.http import http_get, http_post
from airone.lib.http import render
from airone.lib.http import get_download_response

from user.models import User
from user.admin import UserResource
from .admin import GroupResource


@http_get
def index(request):
    context = {}
    context['groups'] = [{
        'name': x.name,
        'members': User.objects.filter(groups__name=x.name,is_active=True),
    } for x in Group.objects.all()]

    return render(request, 'list_group.html', context)

@http_get
def create(request):
    context = {
        'users': User.objects.filter(is_active=True),
    }
    return render(request, 'create_group.html', context)

@http_post([
    {'name': 'name', 'type': str, 'checker': lambda x: (
        x['name'] and not Group.objects.filter(name=x['name']).count()
    )},
    {'name': 'users', 'type': list, 'checker': lambda x: (
        x['users'] and all([User.objects.filter(id=u).count() for u in x['users']])
    )}
])
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
