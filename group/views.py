import json

from django.core.exceptions import ObjectDoesNotExist
from django.contrib.auth.models import Group
from django.http import HttpResponse

from airone.lib import HttpResponseSeeOther
from airone.lib import http_get, http_post
from airone.lib.http import render

from user.models import User


@http_get
def index(request):
    context = {}
    context['groups'] = [{
        'name': x.name,
    } for x in Group.objects.all()]

    return render(request, 'list_group.html', context)

@http_get
def create(request):
    context = {
        'users': User.objects.all(),
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
