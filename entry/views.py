import json

from django.shortcuts import render
from django.http import HttpResponse

from airone.lib import HttpResponseSeeOther

from entity.models import Entity, AttributeBase
from entry.models import Entry, Attribute, AttributeValue
from user.models import User


def index(request, entity_id):
    if request.method != 'GET':
        return HttpResponse('Invalid HTTP method is specified', status=400)

    if not request.user.is_authenticated():
        return HttpResponseSeeOther('/dashboard/login')

    if not Entity.objects.filter(id=entity_id).count():
        return HttpResponse('Failed to get entity of specified id', status=400)

    context = {
        'entity': Entity.objects.get(id=entity_id),
        'entries': Entry.objects.all(),
    }
    return render(request, 'list_entries.html', context)

def create(request, entity_id):
    if request.method != 'GET':
        return HttpResponse('Invalid HTTP method is specified', status=400)

    if not request.user.is_authenticated():
        return HttpResponseSeeOther('/dashboard/login')

    if not Entity.objects.filter(id=entity_id).count():
        return HttpResponse('Failed to get entity of specified id', status=400)

    entity = Entity.objects.get(id=entity_id)
    context = {
        'entity': entity,
        'attributes': entity.attr_bases.all()
    }
    return render(request, 'create_entry.html', context)

def do_create(request, entity_id):
    if request.method != 'POST':
        return HttpResponse('Invalid HTTP method is specified', status=400)

    if not request.user.is_authenticated():
        return HttpResponse('You have to login to execute this operation', status=401)

    if not Entity.objects.filter(id=entity_id).count():
        return HttpResponse('Failed to get entity of specified id', status=400)

    try:
        recv_data = json.loads(request.body.decode('utf-8'))
    except json.decoder.JSONDecodeError:
        return HttpResponse('Failed to parse string to JSON', status=401)

    meta = [
        {'name': 'entry_name', 'type': str},
        {'name': 'attrs', 'type': list, 'meta': [
            {'name': 'id', 'type': str,
             'checker': lambda x: AttributeBase.objects.filter(id=x).count() > 0},
            {'name': 'value', 'type': str},
        ]},
    ]
    if not _is_valid(recv_data, meta):
        return HttpResponse('Invalid parameters are specified', status=400)

    # get an User object
    user = User.objects.get(id=request.user.id)

    # Create Entry
    entry = Entry(name=recv_data['entry_name'],
                  created_user=user,
                  schema=Entity.objects.get(id=entity_id))
    entry.save()

    # Create Attributes
    for attr_info in recv_data['attrs']:
        # make an initial AttributeValue object
        attr_value = AttributeValue(value=attr_info['value'], created_user=user)
        attr_value.save()

        # get AttributeBase object to create Attribute
        attr_base = AttributeBase(id=attr_info['id'])

        # create Attibute object that contains AttributeValues
        attr = Attribute(name=attr_base.name,
                         type=attr_base.type,
                         is_mandatory=attr_base.is_mandatory)
        attr.save()

        # set AttributeValue to Attribute
        attr.values.add(attr_value)

        # set Attribute to Entry
        entry.attrs.add(attr)

    return HttpResponse('')

def edit(request, entry_id):
    if request.method != 'GET':
        return HttpResponse('Invalid HTTP method is specified', status=400)

    if not request.user.is_authenticated():
        return HttpResponseSeeOther('/dashboard/login')

    if not Entry.objects.filter(id=entry_id).count():
        return HttpResponse('Failed to get an Entry object of specified id', status=400)

    entry = Entry.objects.get(id=entry_id)
    context = {
        'entry': entry,
        'attributes': [{
            'id': x.id,
            'name': x.name,
            'last_value': x.values.last().value,
        } for x in entry.attrs.all()],
    }
    return render(request, 'edit_entry.html', context)

def do_edit(request):
    if request.method != 'POST':
        return HttpResponse('Invalid HTTP method is specified', status=400)

    if not request.user.is_authenticated():
        return HttpResponse('You have to login to execute this operation', status=401)

    try:
        recv_data = json.loads(request.body.decode('utf-8'))
    except json.decoder.JSONDecodeError:
        return HttpResponse('Failed to parse string to JSON', status=401)

    meta = [
        {'name': 'attrs', 'type': list, 'meta': [
            {'name': 'id', 'type': str,
             'checker': lambda x: AttributeBase.objects.filter(id=x).count() > 0},
            {'name': 'value', 'type': str},
        ]},
    ]
    if not _is_valid(recv_data, meta):
        return HttpResponse('Invalid parameters are specified', status=400)

    for attr_info in recv_data['attrs']:
        attr = Attribute.objects.get(id=attr_info['id'])

        # Add a new AttributeValue object only at updating value
        if attr.values.last().value != attr_info['value']:
            attr_value = AttributeValue(value=attr_info['value'],
                                        created_user=User.objects.get(id=request.user.id))
            attr_value.save()

            # append new AttributeValue
            attr.values.add(attr_value)

    return HttpResponse('')

def _is_valid(params, meta_info):
    if not isinstance(params, dict):
        return False
    # These are existance checks of each parameters
    if not all([x['name'] in params for x in meta_info]):
        return False
    # These are type checks of each parameters
    if not all([isinstance(params[x['name']], x['type']) for x in meta_info]):
        return False
    # These are value checks of each parameters
    for _meta in meta_info:
        # The case specified value is str
        if _meta['type'] == str:
            # Check specified value is exists
            if not params[_meta['name']]:
                return False

            # Check if meta has checker function
            if 'checker' in _meta and not _meta['checker'](params[_meta['name']]):
                return False

        # The case specified value is list
        if (_meta['type'] == list and 
            not all([_is_valid(x , _meta['meta']) for x in params[_meta['name']]])):
            return False

    return True
