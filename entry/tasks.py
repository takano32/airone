from airone.lib.acl import ACLType
from airone.lib.types import AttrTypeValue
from airone.celery import app
from entry.models import Entry, Attribute, AttributeValue
from user.models import User


def _merge_referrals_by_index(ref_list, name_list):
    """This is a helper function to set array_named_object value.
    This re-formats data construction with index parameter of argument.
    """

    # pad None to align the length of each lists
    def be_aligned(list1, list2):
        padding_length = len(list2) - len(list1)
        if padding_length > 0:
            for i in range(0, padding_length):
                list1.append(None)

    for args in [(ref_list, name_list), (name_list, ref_list)]:
        be_aligned(*args)

    result = {}
    for ref_info, name_info in zip(ref_list, name_list):
        if ref_info:
            if ref_info['index'] not in result:
                result[ref_info['index']] = {}
            result[ref_info['index']]['ref_info'] = ref_info['data']

        if name_info:
            if name_info['index'] not in result:
                result[name_info['index']] = {}
            result[name_info['index']]['name_info'] = name_info['data']

    return result

@app.task(bind=True)
def create_entry_attrs(self, user_id, entry_id, recv_data):
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
        attr_data = [x for x in recv_data['attrs'] if int(x['id']) == attr.schema.id][0]

        # initialize attrv variable
        attrv = None
        def make_attrv(**params):
            return AttributeValue.objects.create(created_user=user, parent_attr=attr, **params)

        if ((entity_attr.type == AttrTypeValue['string'] or
             entity_attr.type == AttrTypeValue['text']) and attr_data['value']):

            # set attribute value
            attrv = make_attrv(value=attr_data['value'][0]['data'])

        elif entity_attr.type == AttrTypeValue['object'] and attr_data['value']:
            entry_id = attr_data['value'][0]['data']

            # set attribute value
            if Entry.objects.filter(id=entry_id).count():
                attrv = make_attrv(referral=Entry.objects.get(id=entry_id))

        elif entity_attr.type == AttrTypeValue['array_string'] and attr_data['value']:
            attrv = make_attrv(status=AttributeValue.STATUS_DATA_ARRAY_PARENT)

            # set attribute value
            for value in attr_data['value']:
                attrv.data_array.add(make_attrv(value=value['data'],
                                                status=AttributeValue.STATUS_LATEST))

        elif entity_attr.type == AttrTypeValue['array_object'] and attr_data['value']:
            attrv = make_attrv(status=AttributeValue.STATUS_DATA_ARRAY_PARENT)

            # set attribute value
            for referral in [Entry.objects.get(id=x['data']) for x in attr_data['value']
                             if Entry.objects.filter(id=x['data']).count()]:
                attrv.data_array.add(make_attrv(referral=referral,
                                                status=AttributeValue.STATUS_LATEST))

        elif entity_attr.type == AttrTypeValue['boolean'] and attr_data['value']:
            attrv = make_attrv(boolean=attr_data['value'][0]['data'])

        elif (entity_attr.type == AttrTypeValue['named_object'] and
              (attr_data['value'] or attr_data['referral_key'])):
            attrv = make_attrv()

            if attr_data['referral_key']:
                attrv.value = attr_data['referral_key'][0]['data']

            if attr_data['value'] and Entry.objects.filter(id=attr_data['value'][0]['data']).count():
                attrv.referral = Entry.objects.get(id=attr_data['value'][0]['data'])

        elif entity_attr.type == AttrTypeValue['array_named_object']:
            attrv = make_attrv(status=AttributeValue.STATUS_DATA_ARRAY_PARENT)

            merged_referrals = _merge_referrals_by_index(attr_data['value'], attr_data['referral_key'])
            for data in merged_referrals.values():
                referral = None
                if 'ref_info' in data and Entry.objects.filter(id=data['ref_info']).count():
                    referral = Entry.objects.get(id=data['ref_info'])

                attrv.data_array.add(make_attrv(**{
                    'value': data['name_info'] if 'name_info' in data else '',
                    'referral': referral,
                    'status': AttributeValue.STATUS_LATEST,
                }))

        if attrv:
            # Set a flag that means this is the latest value
            attrv.set_status(AttributeValue.STATUS_LATEST)

            attrv.save()

            # reconstructs referral_cache for each entries that target attrv refer to
            attrv.reconstruct_referral_cache()

            # set AttributeValue to Attribute
            attr.values.add(attrv)

    # clear flag to specify this entry has been completed to ndcreate
    entry.del_status(Entry.STATUS_CREATING)

@app.task(bind=True)
def edit_entry_attrs(self, user_id, entry_id, recv_data):
    user = User.objects.get(id=user_id)
    entry = Entry.objects.get(id=entry_id)

    for info in recv_data['attrs']:
        attr = Attribute.objects.get(id=info['id'])
        def make_attrv(**params):
            return AttributeValue.objects.create(created_user=user,
                                                 parent_attr=attr,
                                                 status=AttributeValue.STATUS_LATEST,
                                                 **params)

        if attr.schema.type & AttrTypeValue['array']:
            recv_value = recv_ref_key = []

            if 'value' in info and info['value']:
                recv_value = [x['data'] for x in info['value'] if 'data' in x]
            if 'referral_key' in info and info['referral_key']:
                recv_ref_key = [x['data'] for x in info['referral_key'] if 'data' in x]
        else:
            recv_value = recv_ref_key = ''

            if 'value' in info and info['value'] and 'data' in info['value'][0]:
                recv_value = info['value'][0]['data']
            if 'referral_key' in info and info['referral_key'] and 'data' in info['referral_key'][0]:
                recv_ref_key = info['referral_key'][0]['data']

        # Check a new update value is specified, or not
        if not attr.is_updated(recv_value, recv_ref_key):
            continue

        # Clear the flag that means target AttrValues are latet from the Values
        # that are already created.
        cond_latest = {
            'where': ['status & %d > 0' % AttributeValue.STATUS_LATEST],
        }
        for old_value in attr.values.extra(**cond_latest):
            old_value.del_status(AttributeValue.STATUS_LATEST)

            # Sync db to update status value of AttributeValue,
            # because the referred cache reconstruct processing checks this status value.
            old_value.save()

            if attr.schema.type & AttrTypeValue['array']:
                # also clear the latest flags on the values in data_array
                [x.del_status(AttributeValue.STATUS_LATEST) for x in old_value.data_array.all()]

            # update referral_cache because of chaning the destination of reference
            old_value.reconstruct_referral_cache()

        # Add a new AttributeValue object only at updating value
        attr_value = AttributeValue.objects.create(created_user=user, parent_attr=attr)

        # Set a flag that means this is the latest value
        attr_value.set_status(AttributeValue.STATUS_LATEST)

        # set attribute value according to the attribute-type
        if (attr.schema.type == AttrTypeValue['string'] or
            attr.schema.type == AttrTypeValue['text']):

            attr_value.value = recv_value

        elif attr.schema.type == AttrTypeValue['object']:
            # set None if the referral entry is not specified
            if recv_value and Entry.objects.filter(id=recv_value).count():
                attr_value.referral = Entry.objects.get(id=recv_value)
            else:
                attr_value.referral = None

        elif attr.schema.type == AttrTypeValue['boolean']:
            attr_value.boolean = recv_value

        elif attr.schema.type == AttrTypeValue['named_object']:
            attr_value.value = recv_ref_key

            if recv_value and Entry.objects.filter(id=recv_value).count():
                attr_value.referral = Entry.objects.get(id=recv_value)
            else:
                attr_value.referral = None

        elif attr.schema.type & AttrTypeValue['array']:
            # set status of parent data_array
            attr_value.set_status(AttributeValue.STATUS_DATA_ARRAY_PARENT)

            # create and append updated values
            if attr.schema.type == AttrTypeValue['array_string']:
                [attr_value.data_array.add(make_attrv(value=v))
                        for v in recv_value]

            elif attr.schema.type == AttrTypeValue['array_object']:
                [attr_value.data_array.add(make_attrv(referral=Entry.objects.get(id=v)))
                        for v in recv_value]

            elif attr.schema.type == AttrTypeValue['array_named_object']:
                for data in _merge_referrals_by_index(info['value'], info['referral_key']).values():
                    referral = None
                    if 'ref_info' in data and Entry.objects.filter(id=data['ref_info']).count():
                        referral = Entry.objects.get(id=data['ref_info'])

                    attr_value.data_array.add(make_attrv(**{
                        'value': data['name_info'] if 'name_info' in data else '',
                        'referral': referral,
                    }))

        attr_value.save()

        # reconstructs referral_cache for each entries that target attrv refer to
        attr_value.reconstruct_referral_cache()

        # append new AttributeValue
        attr.values.add(attr_value)

    # clear flag to specify this entry has been completed to create
    entry.del_status(Entry.STATUS_EDITING)

@app.task(bind=True)
def delete_entry(self, entry_id):
    entry = Entry.objects.get(id=entry_id)

    entry.delete()
