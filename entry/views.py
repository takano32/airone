import io

from django.http import HttpResponse
from django.db.models import Q

from airone.lib.http import http_get, http_post, check_permission, render
from airone.lib.http import get_download_response
from airone.lib.types import AttrTypeStr, AttrTypeObj, AttrTypeText
from airone.lib.types import AttrTypeArrStr, AttrTypeArrObj
from airone.lib.types import AttrTypeValue
from airone.lib.acl import get_permitted_objects
from airone.lib.acl import ACLType
from airone.lib.profile import airone_profile

from entity.models import Entity, EntityAttr
from entity.admin import EntityResource
from entry.models import Entry, Attribute, AttributeValue
from entry.admin import EntryResource, AttrResource, AttrValueResource
from user.models import User


def _get_latest_attributes(self, user):
    ret_attrs = []
    for attr in [x for x in self.attrs.filter(is_active=True) if user.has_permission(x, ACLType.Readable)]:
        attrinfo = {}

        attrinfo['id'] = attr.id
        attrinfo['name'] = attr.schema.name
        attrinfo['type'] = attr.schema.type
        attrinfo['is_mandatory'] = attr.schema.is_mandatory
        attrinfo['index'] = attr.schema.index

        # set last-value of current attributes
        attrinfo['last_value'] = ''
        attrinfo['last_referral'] = None
        if attr.values.count() > 0:
            last_value = attr.values.last()

            if attr.schema.type == AttrTypeStr or attr.schema.type == AttrTypeText:
                attrinfo['last_value'] = last_value.value
            elif attr.schema.type == AttrTypeObj and last_value.referral:
                attrinfo['last_referral'] = last_value.referral
            elif attr.schema.type == AttrTypeArrStr:
                attrinfo['last_value'] = [x.value for x in last_value.data_array.all()]
            elif attr.schema.type == AttrTypeArrObj:
                attrinfo['last_value'] = [x.referral for x in last_value.data_array.all()]

        # set Entries which are specified in the referral parameter
        attrinfo['referrals'] = []
        if attr.schema.referral:
            # when an entry in referral attribute is deleted,
            # user should be able to select new referral or keep it unchanged.
            # so candidate entries of referral attribute are:
            # - active(not deleted) entries (new referral)
            # - last value even if the entry has been deleted (keep it unchanged)
            query = Q(schema=attr.schema.referral, is_active=True)
            if attrinfo['last_referral']:
                query = query | Q(id=attrinfo['last_referral'].id)
            attrinfo['referrals'] = Entry.objects.filter(query)

        ret_attrs.append(attrinfo)

    return sorted(ret_attrs, key=lambda x: x['index'])

@airone_profile
@http_get
@check_permission(Entity, ACLType.Readable)
def index(request, entity_id):
    if not Entity.objects.filter(id=entity_id).count():
        return HttpResponse('Failed to get entity of specified id', status=400)

    entity = Entity.objects.get(id=entity_id)
    context = {
        'entity': entity,
        'entries': Entry.objects.order_by('name').filter(schema=entity,is_active=True),
    }
    return render(request, 'list_entry.html', context)

@http_get
@check_permission(Entity, ACLType.Writable)
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
        } for x in entity.attrs.filter(is_active=True) if user.has_permission(x, ACLType.Writable)]
    }
    return render(request, 'create_entry.html', context)

@http_post([
    {'name': 'entry_name', 'type': str, 'checker': lambda x: x['entry_name']},
    {'name': 'attrs', 'type': list, 'meta': [
        {'name': 'id', 'type': str},
        {'name': 'value', 'type': str,
         'checker': lambda x: (
             EntityAttr.objects.filter(id=x['id']).count() > 0 and
             (EntityAttr.objects.get(id=x['id']).is_mandatory and x['value'] or
              not EntityAttr.objects.get(id=x['id']).is_mandatory)
         )},
    ]}
])
@check_permission(Entity, ACLType.Writable)
def do_create(request, entity_id, recv_data):
    # get objects to be referred in the following processing
    user = User.objects.get(id=request.user.id)
    entity = Entity.objects.get(id=entity_id)

    # checks that a same name entry corresponding to the entity is existed, or not.
    if Entry.objects.filter(schema=entity_id, name=recv_data['entry_name']).count():
        return HttpResponse('Duplicate name entry is existed', status=400)

    # Create a new Entry object
    entry = Entry(name=recv_data['entry_name'],
                  created_user=user,
                  schema=entity)
    entry.save()

    # Checks specified value exceeds the limit of AttributeValue
    if any([len(x['value'].encode('utf-8')) > AttributeValue.MAXIMUM_VALUE_SIZE
            for x in recv_data['attrs']]):
        return HttpResponse('Passed value is exceeded the limit', status=400)

    def get_attr_values(attr, data):
        return [x['value'] for x in data if int(x['id']) == attr.id and x['value']]

    # Create new Attributes objects based on the specified value
    for entity_attr in entity.attrs.filter(is_active=True):
        # skip for unpermitted attributes
        if not entity_attr.is_active or not user.has_permission(entity_attr, ACLType.Readable):
            continue

        # create Attibute object that contains AttributeValues
        attr = entry.add_attribute_from_base(entity_attr, user)

        # make an initial AttributeValue object if the initial value is specified
        recv_values = get_attr_values(entity_attr, recv_data['attrs'])
        if recv_values:
            attr_value = AttributeValue.objects.create(created_user=user, parent_attr=attr)
            if entity_attr.type == AttrTypeStr or entity_attr.type == AttrTypeText:
                # set attribute value
                attr_value.value = value=recv_values[0]
            elif entity_attr.type == AttrTypeObj:
                value = recv_values[0]

                # set attribute value
                if Entry.objects.filter(id=value).count():
                    attr_value.referral = Entry.objects.get(id=value)
            elif entity_attr.type == AttrTypeArrStr:
                attr_value.set_status(AttributeValue.STATUS_DATA_ARRAY_PARENT)

                # set attribute value
                for value in recv_values:
                    _attr_value = AttributeValue.objects.create(created_user=user,
                                                                parent_attr=attr,
                                                                value=value)
                    attr_value.data_array.add(_attr_value)

            elif entity_attr.type == AttrTypeArrObj:
                attr_value.set_status(AttributeValue.STATUS_DATA_ARRAY_PARENT)

                # set attribute value
                for referral in [Entry.objects.get(id=x) for x in recv_values
                                 if Entry.objects.filter(id=x).count()]:
                    _attr_value = AttributeValue.objects.create(created_user=user,
                                                                parent_attr=attr,
                                                                referral=referral)

                    # Set a flag that means this is the latest value
                    _attr_value.set_status(AttributeValue.STATUS_LATEST)

                    attr_value.data_array.add(_attr_value)

            # Set a flag that means this is the latest value
            attr_value.set_status(AttributeValue.STATUS_LATEST)

            attr_value.save()

            # set AttributeValue to Attribute
            attr.values.add(attr_value)

    return HttpResponse('')

@http_get
@check_permission(Entry, ACLType.Writable)
def edit(request, entry_id):
    user = User.objects.get(id=request.user.id)

    if not Entry.objects.filter(id=entry_id).count():
        return HttpResponse('Failed to get an Entry object of specified id', status=400)

    # set specified entry object information
    entry = Entry.objects.get(id=entry_id)
    entry.complement_attrs(user)

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
                Attribute.objects.filter(id=x['id']).count() > 0 and
                (Attribute.objects.get(id=x['id']).schema.is_mandatory and y or
                not Attribute.objects.get(id=x['id']).schema.is_mandatory)
            for y in x['value']])
         )},
    ]},
])
@check_permission(Entry, ACLType.Writable)
def do_edit(request, entry_id, recv_data):
    user = User.objects.get(id=request.user.id)
    entry = Entry.objects.get(id=entry_id)

    # checks that a same name entry corresponding to the entity is existed.
    query = Q(schema=entry.schema, name=recv_data['entry_name']) & ~Q(id=entry.id)
    if Entry.objects.filter(query).count():
        return HttpResponse('Duplicate name entry is existed', status=400)

    # Checks specified value exceeds the limit of AttributeValue
    if any([any([len(str(y).encode('utf-8')) > AttributeValue.MAXIMUM_VALUE_SIZE
                 for y in x['value']])
            for x in recv_data['attrs']]):
        return HttpResponse('Passed value is exceeded the limit', status=400)

    # update name of Entry object
    entry.name = recv_data['entry_name']
    entry.save()

    for info in recv_data['attrs']:
        attr = Attribute.objects.get(id=info['id'])

        if not attr.schema.type & AttrTypeValue['array']:
            # expand attr value when it has only one value
            if info['value']:
                info['value'] = info['value'][0]
            else:
                info['value'] = ''

        # Check a new update value is specified, or not
        if attr.is_updated(info['value']):

            # Clear the flag that means target AttrValues are latet from the Values
            # that are already created.
            for old_value in attr.values.all():
                old_value.del_status(AttributeValue.STATUS_LATEST)

                if attr.schema.type & AttrTypeValue['array']:
                    # also clear the latest flags on the values in data_array
                    [x.del_status(AttributeValue.STATUS_LATEST) for x in old_value.data_array.all()]

            # Add a new AttributeValue object only at updating value
            attr_value = AttributeValue.objects.create(created_user=user, parent_attr=attr)

            # Set a flag that means this is the latest value
            attr_value.set_status(AttributeValue.STATUS_LATEST)

            # set attribute value according to the attribute-type
            if attr.schema.type == AttrTypeStr or attr.schema.type == AttrTypeText:
                attr_value.value = value=info['value']
            elif attr.schema.type == AttrTypeObj:
                # set None if the referral entry is not specified
                if info['value'] and Entry.objects.filter(id=info['value']).count():
                    attr_value.referral = Entry.objects.get(id=info['value'])
                else:
                    attr_value.referral = None

            elif attr.schema.type & AttrTypeValue['array']:
                # set status of parent data_array
                attr_value.set_status(AttributeValue.STATUS_DATA_ARRAY_PARENT)

                # append existed AttributeValue objects
                for attrv in attr.get_existed_values_of_array(info['value']):
                    attr_value.data_array.add(attrv)

                # create and append updated values
                for value in attr.get_updated_values_of_array(info['value']):

                    # create a new AttributeValue for each values
                    attrv = AttributeValue.objects.create(created_user=user, parent_attr=attr)
                    if attr.schema.type == AttrTypeArrStr:
                        attrv.value = value
                    elif attr.schema.type == AttrTypeArrObj:
                        attrv.referral = Entry.objects.get(id=value)

                    # Set a flag that means this is the latest value
                    attrv.set_status(AttributeValue.STATUS_LATEST)

                    attrv.save()
                    attr_value.data_array.add(attrv)

            attr_value.save()

            # append new AttributeValue
            attr.values.add(attr_value)

    return HttpResponse('')

@http_get
@check_permission(Entry, ACLType.Readable)
def show(request, entry_id):
    user = User.objects.get(id=request.user.id)

    if not Entry.objects.filter(id=entry_id).count():
        return HttpResponse('Failed to get an Entry object of specified id', status=400)

    entry = Entry.objects.get(id=entry_id)

    # create new attributes which are appended after creation of Entity
    entry.complement_attrs(user)

    # create new attributes which are appended after creation of Entity
    for attr_id in (set(entry.schema.attrs.values_list('id', flat=True)) -
                    set([x.schema.id for x in entry.attrs.all()])):

        entity_attr = entry.schema.attrs.get(id=attr_id)
        if not entity_attr.is_active or not user.has_permission(entity_attr, ACLType.Readable):
            continue

        newattr = entry.add_attribute_from_base(entity_attr, user)
        if entity_attr.type & AttrTypeValue['array']:
            # Create a initial AttributeValue for editing processing
            attr_value = AttributeValue.objects.create(created_user=user, parent_attr=newattr)

            # Set a flag that means this is the latest value
            attr_value.set_status(AttributeValue.STATUS_LATEST)

            # Set status of parent data_array
            attr_value.set_status(AttributeValue.STATUS_DATA_ARRAY_PARENT)

            newattr.values.add(attr_value)

    context = {
        'entry': entry,
        'attributes': _get_latest_attributes(entry, user),
        'value_history': sorted(entry.get_value_history(user), key=lambda x: x['created_time']),
        'referred_objects': entry.get_referred_objects(),
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

    objs = [x for x in AttributeValue.objects.all() if user.has_permission(x.parent_attr, ACLType.Readable)]
    output.write("\n")
    output.write("AttributeValue: \n")
    output.write(AttrValueResource().export(objs).yaml)

    return get_download_response(output, 'entry_%s.yaml' % entity.name)

@http_post([]) # check only that request is POST, id will be given by url
@check_permission(Entry, ACLType.Full)
def do_delete(request, entry_id, recv_data):
    user = User.objects.get(id=request.user.id)

    if not Entry.objects.filter(id=entry_id).count():
        return HttpResponse('Failed to get an Entry object of specified id', status=400)

    # update name of Entry object
    entry = Entry.objects.filter(id=entry_id).get()
    entry.delete()

    # register operation History for deleting entry
    user.seth_entry_del(entry)

    # Delete all attributes which target Entry have
    for attr in entry.attrs.all():
        attr.delete()

    return HttpResponse()
