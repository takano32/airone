from django.http import HttpResponse

from airone.lib import http_get, http_post, check_permission
from airone.lib.http import render

from entity.models import Entity, AttributeBase
from entry.models import Entry, Attribute, AttributeValue
from user.models import User


@http_get
@check_permission(Entity, 'readable')
def index(request, entity_id):
    if not Entity.objects.filter(id=entity_id).count():
        return HttpResponse('Failed to get entity of specified id', status=400)

    context = {
        'entity': Entity.objects.get(id=entity_id),
        'entries': Entry.objects.all(),
    }
    return render(request, 'list_entry.html', context)

@http_get
def create(request, entity_id):
    if not Entity.objects.filter(id=entity_id).count():
        return HttpResponse('Failed to get entity of specified id', status=400)

    entity = Entity.objects.get(id=entity_id)
    context = {
        'entity': entity,
        'attributes': entity.attr_bases.all()
    }
    return render(request, 'create_entry.html', context)

@http_post([
    {'name': 'entry_name', 'type': str, 'checker': lambda x: x['entry_name']},
    {'name': 'attrs', 'type': list, 'meta': [
        {'name': 'id', 'type': str},
        {'name': 'value', 'type': str,
         'checker': lambda x: (
             AttributeBase.objects.filter(id=x['id']).count() > 0 and
             (AttributeBase.objects.get(id=x['id']).is_mandatory and x['value'] or
              not AttributeBase.objects.get(id=x['id']).is_mandatory)
         )},
    ]}
])
def do_create(request, entity_id, recv_data):
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
                         is_mandatory=attr_base.is_mandatory,
                         created_user=user)
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

@http_get
def edit(request, entry_id):
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

@http_post([
    {'name': 'attrs', 'type': list, 'meta': [
        {'name': 'id', 'type': str},
        {'name': 'value', 'type': str,
         'checker': lambda x: (
             AttributeBase.objects.filter(id=x['id']).count() > 0 and
             (AttributeBase.objects.get(id=x['id']).is_mandatory and x['value'] or
              not AttributeBase.objects.get(id=x['id']).is_mandatory)
         )},
    ]},
])
def do_edit(request, recv_data):
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

@http_get
def history(request, entry_id):
    if not Entry.objects.filter(id=entry_id).count():
        return HttpResponse('Failed to get an Entry object of specified id', status=400)

    entry = Entry.objects.get(id=entry_id)

    # get history of Entry object
    value_history = sum([[{
        'attr_name': attr.name,
        'attr_value': attr_value.value,
        'created_time': attr_value.created_time,
        'created_user': attr_value.created_user.username,
    } for attr_value in attr.values.all()] for attr in entry.attrs.all()], [])

    context = {
        'entry': entry,
        'value_history': sorted(value_history, key=lambda x: x['created_time']),
    }
    return render(request, 'list_history_of_entry.html', context)
