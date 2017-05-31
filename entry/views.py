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
    return render(request, 'list_entry.html', context)

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
        {'name': 'entry_name', 'type': str, 'checker': lambda x: x['entry_name']},
        {'name': 'attrs', 'type': list, 'meta': [
            {'name': 'id', 'type': str},
            {'name': 'value', 'type': str,
             'checker': lambda x: (
                 AttributeBase.objects.filter(id=x['id']).count() > 0 and
                 (AttributeBase.objects.get(id=x['id']).is_mandatory and x['value'] or
                  not AttributeBase.objects.get(id=x['id']).is_mandatory)
             )},
        ]},
    ]
    if not _is_valid(recv_data, meta):
        return HttpResponse('Invalid parameters are specified', status=400)

    # get objects to be referred in the following processing
    user = User.objects.get(id=request.user.id)
    entity = Entity.objects.get(id=entity_id)

    # Create a new Entry object
    entry = Entry(name=recv_data['entry_name'],
                  created_user=user,
                  schema=entity)
    entry.save()

    # Create new Attributes objects based on the specified value
    for attr_base in entity.attr_bases.all():
        # create Attibute object that contains AttributeValues
        attr = Attribute(name=attr_base.name,
                         type=attr_base.type,
                         is_mandatory=attr_base.is_mandatory)
        attr.save()

        # make an initial AttributeValue object if the initial value is specified
        for info in [x for x in recv_data['attrs'] if int(x['id']) == attr_base.id and x['value']]:
            attr_value = AttributeValue(value=info['value'], created_user=user)
            attr_value.save()

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
            'last_value': x.values.count() > 0 and x.values.last().value or '',
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
            {'name': 'id', 'type': str},
            {'name': 'value', 'type': str,
             'checker': lambda x: (
                 AttributeBase.objects.filter(id=x['id']).count() > 0 and
                 (AttributeBase.objects.get(id=x['id']).is_mandatory and x['value'] or
                  not AttributeBase.objects.get(id=x['id']).is_mandatory)
             )},
        ]},
    ]
    if not _is_valid(recv_data, meta):
        return HttpResponse('Invalid parameters are specified', status=400)

    for attr_info in recv_data['attrs']:
        attr = Attribute.objects.get(id=attr_info['id'])

        # Check a new update value is specified, or not
        if (attr.values.count() == 0 and attr_info['value'] or
            attr.values.count() > 0 and attr.values.last().value != attr_info['value']):

            # Add a new AttributeValue object only at updating value
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
        if (_meta['type'] == str and 'checker' in _meta and not _meta['checker'](params)):
            return False

        # The case specified value is list
        if (_meta['type'] == list and 
            not all([_is_valid(x , _meta['meta']) for x in params[_meta['name']]])):
            return False

    return True
