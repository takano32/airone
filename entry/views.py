from django.http import HttpResponse

from airone.lib.http import http_get, http_post, check_permission, render
from airone.lib.types import AttrTypeStr, AttrTypeObj

from entity.models import Entity, AttributeBase
from entry.models import Entry, Attribute, AttributeValue
from user.models import User


@http_get
@check_permission(Entity, 'readable')
def index(request, entity_id):
    if not Entity.objects.filter(id=entity_id).count():
        return HttpResponse('Failed to get entity of specified id', status=400)

    entity = Entity.objects.get(id=entity_id)
    context = {
        'entity': entity,
        'entries': Entry.objects.filter(schema=entity),
    }
    return render(request, 'list_entry.html', context)

@http_get
def create(request, entity_id):
    if not Entity.objects.filter(id=entity_id).count():
        return HttpResponse('Failed to get entity of specified id', status=400)

    entity = Entity.objects.get(id=entity_id)
    context = {
        'entity': entity,
        'attributes': [{
            'id': x.id,
            'name': x.name,
            'referrals': x.referral and Entry.objects.filter(schema=x.referral) or [],
        } for x in entity.attr_bases.all()]
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
        attr = entry.add_attribute_from_base(attr_base, user)

        # make an initial AttributeValue object if the initial value is specified
        for info in [x for x in recv_data['attrs'] if int(x['id']) == attr_base.id and x['value']]:
            attr_value = AttributeValue(created_user=user)
            if attr.type == AttrTypeStr().type:
                attr_value.value = value=info['value']
            elif attr.type == AttrTypeObj().type and Entry.objects.filter(id=info['value']).count():
                attr_value.referral = Entry.objects.get(id=info['value'])

            attr_value.save()

            # set AttributeValue to Attribute
            attr.values.add(attr_value)

    return HttpResponse('')

@http_get
def edit(request, entry_id):
    context = {}
    if not Entry.objects.filter(id=entry_id).count():
        return HttpResponse('Failed to get an Entry object of specified id', status=400)

    # set specified entry object information
    context['entry'] = entry = Entry.objects.get(id=entry_id)

    # set attribute information of target entry
    context['attributes'] = []
    for attr in entry.attrs.all():
        attrinfo = {}

        attrinfo['id'] = attr.id
        attrinfo['name'] = attr.name

        # set Entries which are specified in the referral parameter
        attrinfo['referrals'] = []
        if attr.referral:
            attrinfo['referrals'] = Entry.objects.filter(schema=attr.referral)

        # set last-value of current attributes
        attrinfo['last_value'] = ''
        if attr.values.count() > 0:
            last_value = attr.values.last()

            if attr.type == AttrTypeStr().type:
                attrinfo['last_value'] = last_value.value
            elif attr.type == AttrTypeObj().type and last_value.referral:
                attrinfo['last_value'] = last_value.referral.id

        context['attributes'].append(attrinfo)

    return render(request, 'edit_entry.html', context)

@http_post([
    {'name': 'entry_name', 'type': str, 'checker': lambda x: (
        x['entry_name']
    )},
    {'name': 'entry_id', 'type': str, 'checker': lambda x: (
        Entry.objects.filter(id=x['entry_id']).count() == 1
    )},
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
    # update name of Entry object
    Entry.objects.filter(id=recv_data['entry_id']).update(name=recv_data['entry_name'])

    # This checks there is no Entry that has same name

    for info in recv_data['attrs']:
        attr = Attribute.objects.get(id=info['id'])

        # Check a new update value is specified, or not
        if (attr.values.count() == 0 and info['value'] or
            attr.values.count() > 0 and (
                attr.values.last().value != info['value'] or
                attr.values.last().referral and attr.values.last().referral.id != info['value']
            )):

            # Add a new AttributeValue object only at updating value
            attr_value = AttributeValue(created_user=User.objects.get(id=request.user.id))

            # set attribute value according to the attribute-type
            if attr.type == AttrTypeStr().type:
                attr_value.value = value=info['value']
            elif attr.type == AttrTypeObj().type and Entry.objects.filter(id=info['value']).count():
                attr_value.referral = Entry.objects.get(id=info['value'])

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
