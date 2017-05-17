import json
import logging

from django.shortcuts import render, redirect
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpResponse

from user.models import User
from .models import Group

logger = logging.getLogger(__name__)


def index(request):
    context = {}
    context['groups'] = [{
        'name': x.name,
        'created_time': x.created_time,
        'users': [ y.name for y in x.users.all() ],
    } for x in Group.objects.all()]

    return render(request, 'group_list.html', context)

def create(request):
    if request.method == 'POST':
        new_group = None
        try:
            received_json = json.loads(request.body.decode('utf-8'))

            # validate parameters
            if not _is_valid(received_json):
                raise KeyError()

            new_group = Group(name=received_json['name'])
            new_group.save()
            for userid in received_json['users']:
                new_group.users.add(User.objects.get(id=userid))

            return redirect('/group/')
        except KeyError:
            if new_group:
                new_group.delete()

            return HttpResponse('Invalid parameters are specified', status=500)
        except ObjectDoesNotExist:
            if new_group:
                new_group.delete()

            return HttpResponse('Invalid userid is specified', status=500)
        except json.decoder.JSONDecodeError:
            return HttpResponse('Failed to parse string to JSON', status=500)

    else:
        context = {
            'users': User.objects.all(),
        }
        return render(request, 'group_create.html', context)

def _is_valid(params):
    is_valid = True

    try:
        is_valid &= isinstance(params, dict)
        is_valid &= len(params) > 0
        is_valid &= 'name' in params
        is_valid &= 'users' in params
        is_valid &= isinstance(params['name'], str)
        is_valid &= isinstance(params['users'], list)
        is_valid &= len(params['name']) > 0
        is_valid &= len(params['users']) > 0
    except Exception as e:
        logger.warning(e)
        return False

    return is_valid
