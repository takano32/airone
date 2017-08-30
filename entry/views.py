import io

from django.http import HttpResponse
from django.db.models import Q

from airone.lib.http import http_get, http_post, check_permission, render
from airone.lib.http import get_download_response
from airone.lib.types import AttrTypeStr, AttrTypeObj, AttrTypeArrStr, AttrTypeArrObj, AttrTypeValue
from airone.lib.acl import get_permitted_objects

from entity.models import Entity, AttributeBase
from entity.admin import EntityResource
from entry.models import Entry, Attribute, AttributeValue
from entry.admin import EntryResource, AttrResource, AttrValueResource
from user.models import User


def _get_latest_attributes(self, user):
    ret_attrs = []
    for attr in [x for x in self.attrs.all() if user.has_permission(x, 'readable')]:
        attrinfo = {}

        attrinfo['id'] = attr.id
        attrinfo['name'] = attr.name
        attrinfo['type'] = attr.type
        attrinfo['is_mandatory'] = attr.is_mandatory

        # set last-value of current attributes
        attrinfo['last_value'] = ''
        attrinfo['last_referral'] = None
        if attr.values.count() > 0:
            last_value = attr.values.last()

            if attr.type == AttrTypeStr:
                attrinfo['last_value'] = last_value.value
            elif attr.type == AttrTypeObj and last_value.referral:
                attrinfo['last_referral'] = last_value.referral
            elif attr.type == AttrTypeArrStr:
                attrinfo['last_value'] = [x.value for x in last_value.data_array.all()]
            elif attr.type == AttrTypeArrObj:
                attrinfo['last_value'] = [x.referral for x in last_value.data_array.all()]

        # set Entries which are specified in the referral parameter
        attrinfo['referrals'] = []
        if attr.referral:
            # when an entry in referral attribute is deleted,
            # user should be able to select new referral or keep it unchanged.
            # so candidate entries of referral attribute are:
            # - active(not deleted) entries (new referral)
            # - last value even if the entry has been deleted (keep it unchanged)
            query = Q(schema=attr.referral,is_active=True)
            if attrinfo['last_referral']:
                query = query | Q(id=attrinfo['last_referral'].id)
            attrinfo['referrals'] = Entry.objects.filter(query)

        ret_attrs.append(attrinfo)

    return ret_attrs

@http_get
@check_permission(Entity, 'readable')
def index(request, entity_id):
    if not Entity.objects.filter(id=entity_id).count():
        return HttpResponse('Failed to get entity of specified id', status=400)

    entity = Entity.objects.get(id=entity_id)
    context = {
        'entity': entity,
        'entries': Entry.objects.filter(schema=entity,is_active=True),
    }
    return render(request, 'list_entry.html', context)

@http_get
@check_permission(Entity, 'writable')
def create(request, entity_id):
    user = User.objects.get(id=request.user.id)

    if not Entity.objects.filter(id=entity_id).count():
        return HttpResponse('Failed to get entity of specified id', status=400)

    entity = Entity.objects.get(id=entity_id)
    context = {
        'entity': entity,
        'attributes': [{
            'id': x.id,
            'type': x.type,
            'name': x.name,
            'is_mandatory': x.is_mandatory,
            'referrals': x.referral and Entry.objects.filter(schema=x.referral,is_active=True) or [],
        } for x in entity.attrs.all() if user.has_permission(x, 'writable')]
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
@check_permission(Entity, 'writable')
def do_create(request, entity_id, recv_data):
    # get objects to be referred in the following processing
    user = User.objects.get(id=request.user.id)
    entity = Entity.objects.get(id=entity_id)

    # Create a new Entry object
    entry = Entry(name=recv_data['entry_name'],
                  created_user=user,
                  schema=entity)
    entry.save()

    def get_attr_values(attr, data):
        return [x['value'] for x in data if int(x['id']) == attr.id and x['value']]

    # Create new Attributes objects based on the specified value
    for attr_base in entity.attrs.all():
        # create Attibute object that contains AttributeValues
        attr = entry.add_attribute_from_base(attr_base, user)

        # make an initial AttributeValue object if the initial value is specified
        recv_values = get_attr_values(attr_base, recv_data['attrs'])
        if recv_values:
            attr_value = AttributeValue.objects.create(created_user=user, parent_attr=attr)
            if attr.type == AttrTypeStr:
                # set attribute value
                attr_value.value = value=recv_values[0]
            elif attr.type == AttrTypeObj:
                value = recv_values[0]

                # set attribute value
                if Entry.objects.filter(id=value).count():
                    attr_value.referral = Entry.objects.get(id=value)
            elif attr.type == AttrTypeArrStr:
                attr_value.set_status(AttributeValue.STATUS_DATA_ARRAY_PARENT)

                # set attribute value
                for value in recv_values:
                    _attr_value = AttributeValue.objects.create(created_user=user,
                                                                parent_attr=attr,
                                                                value=value)
                    attr_value.data_array.add(_attr_value)

            elif attr.type == AttrTypeArrObj:
                attr_value.set_status(AttributeValue.STATUS_DATA_ARRAY_PARENT)

                # set attribute value
                for referral in [Entry.objects.get(id=x) for x in recv_values
                                 if Entry.objects.filter(id=x).count()]:
                    _attr_value = AttributeValue.objects.create(created_user=user,
                                                                parent_attr=attr,
                                                                referral=referral)
                    attr_value.data_array.add(_attr_value)

            attr_value.save()

            # set AttributeValue to Attribute
            attr.values.add(attr_value)

    return HttpResponse('')

@http_get
@check_permission(Entry, 'writable')
def edit(request, entry_id):
    user = User.objects.get(id=request.user.id)

    if not Entry.objects.filter(id=entry_id).count():
        return HttpResponse('Failed to get an Entry object of specified id', status=400)

    # set specified entry object information
    entry = Entry.objects.get(id=entry_id)
    context = {
        'entry': entry,
        'attributes': _get_latest_attributes(entry, user),
    }

    return render(request, 'edit_entry.html', context)

@http_post([
    {'name': 'entry_name', 'type': str, 'checker': lambda x: (
        x['entry_name']
    )},
    {'name': 'attrs', 'type': list, 'meta': [
        {'name': 'id', 'type': str},
        {'name': 'value', 'type': list,
         'checker': lambda x: (
             all([
                AttributeBase.objects.filter(id=x['id']).count() > 0 and
                (AttributeBase.objects.get(id=x['id']).is_mandatory and y or
                not AttributeBase.objects.get(id=x['id']).is_mandatory)
            for y in x['value']])
         )},
    ]},
])
@check_permission(Entry, 'writable')
def do_edit(request, entry_id, recv_data):
    user = User.objects.get(id=request.user.id)

    # update name of Entry object
    Entry.objects.filter(id=entry_id).update(name=recv_data['entry_name'])

    for info in recv_data['attrs']:
        attr = Attribute.objects.get(id=info['id'])

        if not attr.type & AttrTypeValue['array']:
            # expand attr value when it has only one value
            info['value'] = info['value'][0]

        # Check a new update value is specified, or not
        if attr.is_updated(info['value']):
            # Add a new AttributeValue object only at updating value
            attr_value = AttributeValue.objects.create(created_user=user, parent_attr=attr)

            # set attribute value according to the attribute-type
            if attr.type == AttrTypeStr:
                attr_value.value = value=info['value']
            elif attr.type == AttrTypeObj and Entry.objects.filter(id=info['value']).count():
                # set None if the referral entry is not specified
                attr_value.referral = info['value'] and Entry.objects.get(id=info['value']) or None
            elif attr.type & AttrTypeValue['array']:
                # set status of parent data_array
                attr_value.set_status(AttributeValue.STATUS_DATA_ARRAY_PARENT)

                # append existed AttributeValue objects
                for attrv in attr.get_existed_values_of_array(info['value']):
                    attr_value.data_array.add(attrv)

                # create and append updated values
                for value in attr.get_updated_values_of_array(info['value']):

                    # create a new AttributeValue for each values
                    attrv = AttributeValue.objects.create(created_user=user, parent_attr=attr)
                    if attr.type == AttrTypeArrStr:
                        attrv.value = value
                    elif attr.type == AttrTypeArrObj:
                        attrv.referral = Entry.objects.get(id=value)

                    attrv.save()
                    attr_value.data_array.add(attrv)

            attr_value.save()

            # append new AttributeValue
            attr.values.add(attr_value)

    return HttpResponse('')

@http_get
@check_permission(Entry, 'readable')
def show(request, entry_id):
    user = User.objects.get(id=request.user.id)

    if not Entry.objects.filter(id=entry_id).count():
        return HttpResponse('Failed to get an Entry object of specified id', status=400)

    entry = Entry.objects.get(id=entry_id)

    def export_data_array(attrv):
        attr = attrv.parent_attr

        if attr.type == AttrTypeArrStr:
            return [x.value for x in attrv.data_array.all()]
        elif attr.type == AttrTypeArrObj:
            return [x.referral for x in attrv.data_array.all()]

        return []

    # get history of Entry object
    value_history = sum([[{
        'attr_name': attr.name,
        'attr_type': attr.type,
        'attr_value': attr_value.value,
        'attr_value_array': export_data_array(attr_value),
        'attr_referral': attr_value.referral,
        'created_time': attr_value.created_time,
        'created_user': attr_value.created_user.username,
    } for attr_value in attr.values.all()] for attr in entry.attrs.all() if user.has_permission(attr, 'readable')], [])

    context = {
        'entry': entry,
        'attributes': _get_latest_attributes(entry, user),
        'value_history': sorted(value_history, key=lambda x: x['created_time']),
    }
    return render(request, 'show_entry.html', context)

@http_get
def export(request, entity_id):
    output = io.StringIO()
    user = User.objects.get(id=request.user.id)

    if not Entity.objects.filter(id=entity_id).count():
        return HttpResponse('Failed to get entity of specified id', status=400)

    entity = Entity.objects.get(id=entity_id)

    output.write("Entity: \n")
    output.write(EntityResource().export(get_permitted_objects(user, Entity, 'readable')).yaml)

    output.write("\n")
    output.write("Entry: \n")
    output.write(EntryResource().export(get_permitted_objects(user, Entry, 'readable')).yaml)

    output.write("\n")
    output.write("Attribute: \n")
    output.write(AttrResource().export(get_permitted_objects(user, Attribute, 'readable')).yaml)

    objs = [x for x in AttributeValue.objects.all() if user.has_permission(x.parent_attr, 'readable')]
    output.write("\n")
    output.write("AttributeValue: \n")
    output.write(AttrValueResource().export(objs).yaml)

    return get_download_response(output, 'entry_%s.yaml' % entity.name)

@http_post([]) # check only that request is POST, id will be given by url
@check_permission(Entry, 'full')
def do_delete(request, entry_id, recv_data):

    if not Entry.objects.filter(id=entry_id).count():
        return HttpResponse('Failed to get an Entry object of specified id', status=400)

    # update name of Entry object
    entry = Entry.objects.filter(id=entry_id).get()
    entry.is_active=False
    entry.save()

    return HttpResponse()
