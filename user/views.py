import json

from django.shortcuts import render
from django.template import loader
from django.http import HttpResponse
from django.db import utils

from airone.lib import HttpResponseSeeOther
from .models import User


def index(request):
    if not request.user.is_authenticated():
        return HttpResponseSeeOther('/dashboard/login')

    context = {
        'users': User.objects.all(),
    }
    return render(request, 'user_list.html', context)

def create(request):
    if request.method == 'POST':
        if not request.user.is_authenticated():
            return HttpResponse('You have to login to execute this operation', status=401)

        try:
            received_json = json.loads(request.body.decode('utf-8'))
        except json.decoder.JSONDecodeError:
            return HttpResponse('Failed to parse string to JSON', status=401)

        # validation check for the received data
        if not _is_valid(received_json):
            return HttpResponse('Invalid parameters are specified', status=400)

        if User.objects.filter(email=received_json['email']).count():
            return HttpResponse('Specified Email address has been already registered',
                                status=400)

        user = User(username=received_json['name'],
                    email=received_json['email'])

        # store encrypted password in the database
        user.set_password(received_json['passwd'])
        user.save()
    else:
        if not request.user.is_authenticated():
            return HttpResponseSeeOther('/dashboard/login')

    return render(request, 'user_create.html')

def _is_valid(params):
    param_keys = ['name', 'email', 'passwd']

    if not isinstance(params, dict):
        return False
    # These are existance checks of each parameters
    if not all([(x in params) for x in param_keys]):
        return False
    # These are type checks of each parameters
    if not all([isinstance(params[x], str) for x in param_keys]):
        return False
    # These are value checks of each parameters
    if not all([params[x] for x in param_keys]):
        return False

    return True
