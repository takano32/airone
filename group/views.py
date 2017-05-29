import json

from django.shortcuts import render
from django.core.exceptions import ObjectDoesNotExist
from django.contrib.auth.models import Group
from django.http import HttpResponse

from airone.lib import HttpResponseSeeOther
from user.models import User


def index(request):
    context = {}
    context['groups'] = [{
        'name': x.name,
    } for x in Group.objects.all()]

    return render(request, 'group_list.html', context)

def create(request):
    if request.method == 'POST':
        new_group = None
        try:
            received_json = json.loads(request.body.decode('utf-8'))
        except json.decoder.JSONDecodeError:
            return HttpResponse('Failed to parse string to JSON', status=400)

        # validate input parameters
        if not _is_valid(received_json):
            return HttpResponse('Invalid parameters are specified', status=400)

        try:
            new_group = Group(name=received_json['name'])
            new_group.save()

            for user in [User.objects.get(id=x) for x in received_json['users']]:
                user.groups.add(new_group)

            return HttpResponseSeeOther('/group/')
        except ObjectDoesNotExist:
            return HttpResponse('Invalid userid is specified', status=400)

    else:
        context = {
            'users': User.objects.all(),
        }
        return render(request, 'group_create.html', context)

def _is_valid(params):
    if not isinstance(params, dict):
        return False
    if ('name' not in params) or ('users' not in params):
        return False
    if (not isinstance(params['name'], str)) or (not isinstance(params['users'], list)):
        return False
    if not params["name"]:
        return False
    if not params["users"]:
        return False
    if [x for x in params['users'] if not User.objects.filter(id=x).count()]:
        return False
    return True
