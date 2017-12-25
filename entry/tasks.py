from celery import shared_task

from airone.lib.acl import ACLType
from airone.lib.types import AttrTypeValue
from entry.models import Entry, Attribute, AttributeValue
from user.models import User


@shared_task
def create_entry_attrs(user_id, entry_id, recv_data):
    user = User.objects.get(id=user_id)
    entry = Entry.objects.get(id=entry_id)

    # Create new Attributes objects based on the specified value
    for entity_attr in entry.schema.attrs.filter(is_active=True):
        # skip for unpermitted attributes
        if not entity_attr.is_active or not user.has_permission(entity_attr, ACLType.Readable):
            continue

        # create Attibute object that contains AttributeValues
        attr = entry.add_attribute_from_base(entity_attr, user)

        # make an initial AttributeValue object if the initial value is specified
        recv_values = sum([x['value'] for x in recv_data['attrs'] if int(x['id']) == attr.schema.id],
                          [])
        if recv_values:
            attr_value = AttributeValue.objects.create(created_user=user, parent_attr=attr)
            if (entity_attr.type == AttrTypeValue['string'] or
                entity_attr.type == AttrTypeValue['text']):

                # set attribute value
                attr_value.value = value=recv_values[0]

            elif entity_attr.type == AttrTypeValue['object']:
                value = recv_values[0]

                # set attribute value
                if Entry.objects.filter(id=value).count():
                    attr_value.referral = Entry.objects.get(id=value)
            elif entity_attr.type == AttrTypeValue['array_string']:
                attr_value.set_status(AttributeValue.STATUS_DATA_ARRAY_PARENT)

                # set attribute value
                for value in recv_values:
                    _attr_value = AttributeValue.objects.create(created_user=user,
                                                                parent_attr=attr,
                                                                value=value)
                    attr_value.data_array.add(_attr_value)

            elif entity_attr.type == AttrTypeValue['array_object']:
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

            elif entity_attr.type == AttrTypeValue['boolean']:
                attr_value.boolean = recv_values[0]

            # Set a flag that means this is the latest value
            attr_value.set_status(AttributeValue.STATUS_LATEST)

            attr_value.save()

            # set AttributeValue to Attribute
            attr.values.add(attr_value)

    # clear STATUS_PROCESSING flag to specify this entry has been completed to create
    entry.del_status(Entry.STATUS_PROCESSING)

@shared_task
def edit_entry_attrs(user_id, entry_id, recv_data):
    user = User.objects.get(id=user_id)
    entry = Entry.objects.get(id=entry_id)

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
            if (attr.schema.type == AttrTypeValue['string'] or
                attr.schema.type == AttrTypeValue['text']):

                attr_value.value = info['value']

            elif attr.schema.type == AttrTypeValue['object']:

                # set None if the referral entry is not specified
                if info['value'] and Entry.objects.filter(id=info['value']).count():
                    attr_value.referral = Entry.objects.get(id=info['value'])
                else:
                    attr_value.referral = None

            elif attr.schema.type == AttrTypeValue['boolean']:
                attr_value.boolean = info['value']

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
                    if attr.schema.type == AttrTypeValue['array_string']:
                        attrv.value = value
                    if attr.schema.type == AttrTypeValue['array_object']:
                        attrv.referral = Entry.objects.get(id=value)

                    # Set a flag that means this is the latest value
                    attrv.set_status(AttributeValue.STATUS_LATEST)

                    attrv.save()
                    attr_value.data_array.add(attrv)

            attr_value.save()

            # append new AttributeValue
            attr.values.add(attr_value)

    # clear STATUS_PROCESSING flag to specify this entry has been completed to create
    entry.del_status(Entry.STATUS_PROCESSING)
