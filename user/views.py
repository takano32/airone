import json

from django.shortcuts import render
from django.template import loader
from django.http import HttpResponse, Http404

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

            user = User(name=received_json['name'],
                        userid=received_json['userid'],
                        passwd=received_json['passwd'])
            user.save()

            #return HttpResponse('')
            return render(request, 'user_create.html')
        except KeyError:
            return HttpResponse('Invalid parameters are specified', status=500)
        except json.decoder.JSONDecodeError:
            return HttpResponse('Failed to parse string to JSON', status=500)

    else:
        return render(request, 'user_create.html')
