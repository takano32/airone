import json

from django.shortcuts import render
from django.template import loader
from django.http import HttpResponse
from django.db import utils

from airone.lib import HttpResponseSeeOther
from airone.lib import http_get, http_post

from .models import User


@http_get
def index(request):
    if not request.user.is_authenticated():
        return HttpResponseSeeOther('/dashboard/login')

    context = {
        'users': User.objects.all(),
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
