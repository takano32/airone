import json

from django.shortcuts import render
from django.template import loader
from django.http import HttpResponse
from django.db import utils

from .models import User


def index(request):
    context = {
        'users': User.objects.all(),
    }
    return render(request, 'user_list.html', context)

def create(request):
    if request.method == 'POST':
        try:
            received_json = json.loads(request.body.decode('utf-8'))

            if User.objects.filter(email=received_json['email']).count():
                return HttpResponse('Specified Email address has been already registered',
                                    status=400)

            User(username=received_json['name'],
                 password=received_json['passwd'],
                 email=received_json['email']).save()

            return render(request, 'user_create.html')
        except KeyError:
            return HttpResponse('Invalid parameters are specified', status=400)
        except json.decoder.JSONDecodeError:
            return HttpResponse('Failed to parse string to JSON', status=400)

    else:
        return render(request, 'user_create.html')
