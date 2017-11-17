import json

from django.template import loader
from django.http import HttpResponse
from django.db import utils

from airone.lib.http import HttpResponseSeeOther
from airone.lib.http import http_get, http_post
from airone.lib.http import render
from airone.lib.http import check_superuser

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
@check_superuser
def do_create(request, recv_data):
    is_admin = False
    if 'is_admin' in recv_data:
        is_admin = True

    user = User(username=recv_data['name'],
                email=recv_data['email'],
                is_superuser=is_admin)

    # store encrypted password in the database
    user.set_password(recv_data['passwd'])
    user.save()

    return render(request, 'create_user.html')

@http_post([
    {'name': 'name', 'type': str, 'checker': lambda x: (
        x['name'] and (User.objects.filter(username=x['name']).count() == 1)
    )},
])
@check_superuser
def do_delete(request, recv_data):
    user = User.objects.get(username=recv_data['name'])

    # inactivate user
    user.delete()

    # return empty response 
    return HttpResponse()
