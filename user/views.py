import json

from django.template import loader
from django.http import HttpResponse
from django.db import utils

from airone.lib.http import HttpResponseSeeOther
from airone.lib.http import http_get, http_post
from airone.lib.http import render
from airone.lib.http import check_superuser
from airone.lib.http import _is_valid

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
    is_superuser = False
    if 'is_superuser' in recv_data:
        is_superuser = True

    user = User(username=recv_data['name'],
                email=recv_data['email'],
                is_superuser=is_superuser)

    # store encrypted password in the database
    user.set_password(recv_data['passwd'])
    user.save()

    return render(request, 'create_user.html')

@http_get
@check_superuser
def edit(request, user_id):

    user = User.objects.get(id=user_id)

    context = {
        'user_id': int(user_id),
        'user_name': user.username,
        'user_email': user.email,
        'user_password': user.password,
        'user_is_superuser': user.is_superuser,
    }

    return render(request, 'edit_user.html', context)

@http_post([
    {'name': 'name', 'type': str, 'checker': lambda x: x['name']},
    {'name': 'email', 'type': str, 'checker': lambda x: x['email']},
])
@check_superuser
def do_edit(request, user_id, recv_data):

    old_data = User.objects.get(id=user_id)
    # validate duplication of username
    if old_data.username != recv_data['name']:
        if User.objects.filter(username=recv_data['name']).count():
            return HttpResponse("username is duplicated", status=400)
    # validate duplication of email
    if old_data.email != recv_data['email']:
        if User.objects.filter(email=recv_data['email']).count():
            return HttpResponse("email is duplicated", status=400)

    is_superuser = False
    if 'is_superuser' in recv_data:
        is_superuser = True

    user = User(id=user_id,
                username=recv_data['name'],
                email=recv_data['email'],
                is_superuser=is_superuser
                )
    user.save(update_fields=['username','email','is_superuser'])

    # if new password was send, update password
    if 'passwd' in recv_data:
        # validate password format
        validate =[{'name': 'passwd', 'type': str, 'checker': lambda x: x['passwd']}]
        if not _is_valid(recv_data,validate):
            return HttpResponse('Invalid parameters are specified', status=400)

        # store encrypted password in the database
        user.set_password(recv_data['passwd'])
        user.save(update_fields=['password'])

    return render(request, 'edit_user.html')

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
