import json

from django.template import loader
from django.http import HttpResponse
from django.db import utils

from airone.lib.http import HttpResponseSeeOther
from airone.lib.http import http_get, http_post
from airone.lib.http import render

from .models import User


@http_get
def index(request):
    if not request.user.is_authenticated():
        return HttpResponseSeeOther('/dashboard/login')

    context = {
        'users': User.objects.filter(is_active=True),
    }
    return render(request, 'list_user.html', context)

@http_get
def create(request):
    return render(request, 'create_user.html')

@http_post([
    {'name': 'name', 'type': str, 'checker': lambda x: (
        x['name'] and not User.objects.filter(username=x['name']).count()
    )},
    {'name': 'email', 'type': str, 'checker': lambda x: (
        x['email'] and not User.objects.filter(email=x['email']).count()
    )},
    {'name': 'passwd', 'type': str, 'checker': lambda x: x['passwd']},
])
def do_create(request, recv_data):
    user = User(username=recv_data['name'],
                email=recv_data['email'])

    # store encrypted password in the database
    user.set_password(recv_data['passwd'])
    user.save()

    return render(request, 'create_user.html')

@http_post([
    {'name': 'name', 'type': str, 'checker': lambda x: (
        x['name'] and not User.objects.filter(username=x['name']).count()
    )},
])
def do_delete(request, recv_data):
    user = User.objects.get(username=recv_data['name'])

    # inactivate user
    user.set_active(False)
    user.save()

    # return empty response 
    return HttpResponse()
