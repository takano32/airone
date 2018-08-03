import logging
import custom_view

from airone.lib.acl import ACLType
from airone.lib.types import AttrTypeValue
from airone.celery import app
from entry.models import Entry, Attribute, AttributeValue
from user.models import User
from datetime import datetime
from job.models import Job

Logger = logging.getLogger(__name__)


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
            result[ref_info['index']]['id'] = ref_info['data']

        if name_info:
            if name_info['index'] not in result:
                result[name_info['index']] = {}
            result[name_info['index']]['name'] = name_info['data']

    return result

def _convert_data_value(attr, info):
    if attr.schema.type & AttrTypeValue['array']:
        recv_value = []
        if 'value' in info and info['value']:
            recv_value = [x['data'] for x in info['value'] if 'data' in x]

        if attr.schema.type & AttrTypeValue['named']:
            return _merge_referrals_by_index(info['value'], info['referral_key']).values()
        else:
            return recv_value

    else:
        recv_value = recv_ref_key = ''

        if 'value' in info and info['value'] and 'data' in info['value'][0]:
            recv_value = info['value'][0]['data']
        if 'referral_key' in info and info['referral_key'] and 'data' in info['referral_key'][0]:
            recv_ref_key = info['referral_key'][0]['data']

        if attr.schema.type & AttrTypeValue['named']:
            return {
                'name': recv_ref_key,
                'id': recv_value,
            }
        elif attr.schema.type & AttrTypeValue['date']:
            if recv_value is None or recv_value == '':
                return None
            else:
                return datetime.strptime(recv_value, '%Y-%m-%d').date()

        elif attr.schema.type & AttrTypeValue['boolean']:
            if recv_value is None or recv_value == '':
                return False
            else:
                return recv_value

        else:
            return recv_value

@app.task(bind=True)
def create_entry_attrs(self, user_id, entry_id, recv_data, job_id):
    user = User.objects.get(id=user_id)
    entry = Entry.objects.get(id=entry_id)
    job = Job.objects.get(id=job_id)

    # Create new Attributes objects based on the specified value
    for entity_attr in entry.schema.attrs.filter(is_active=True):
        # skip for unpermitted attributes
        if not entity_attr.is_active or not user.has_permission(entity_attr, ACLType.Readable):
            continue

        # create Attibute object that contains AttributeValues
        attr = entry.add_attribute_from_base(entity_attr, user)

        # make an initial AttributeValue object if the initial value is specified
        attr_data = [x for x in recv_data['attrs'] if int(x['id']) == attr.schema.id][0]

        # register new AttributeValue to the "attr"
        try:
            attr.add_value(user, _convert_data_value(attr, attr_data))
        except ValueError as e:
            Logger.warning('(%s) attr_data: %s' % (e, str(attr_data)))

    if custom_view.is_custom_after_create_entry(entry.schema.name):
        custom_view.call_custom_after_create_entry(entry.schema.name, recv_data, user, entry)

    # register entry information to Elasticsearch
    entry.register_es()

    # clear flag to specify this entry has been completed to ndcreate
    entry.del_status(Entry.STATUS_CREATING)

    # update job status and save it
    job.status = Job.STATUS_DONE
    job.save()

@app.task(bind=True)
def edit_entry_attrs(self, user_id, entry_id, recv_data, job_id):
    user = User.objects.get(id=user_id)
    entry = Entry.objects.get(id=entry_id)
    job = Job.objects.get(id=job_id)

    for info in recv_data['attrs']:
        attr = Attribute.objects.get(id=info['id'])

        try:
            converted_value = _convert_data_value(attr, info)
        except ValueError as e:
            Logger.warning('(%s) attr_data: %s' % (e, str(info)))
            continue

        # Check a new update value is specified, or not
        if not attr.is_updated(converted_value):
            continue

        # Get current latest value to reconstruct referral cache
        old_value = attr.get_latest_value()

        # Add new AttributeValue instance to Attribute instnace
        new_value = attr.add_value(user, converted_value)

    if custom_view.is_custom_after_edit_entry(entry.schema.name):
        custom_view.call_custom_after_edit_entry(entry.schema.name, recv_data, user, entry)

    # update entry information to Elasticsearch
    entry.register_es()

    # clear flag to specify this entry has been completed to edit
    entry.del_status(Entry.STATUS_EDITING)

    # update job status and save it
    job.status = Job.STATUS_DONE
    job.save()

@app.task(bind=True)
def delete_entry(self, entry_id, job_id):
    entry = Entry.objects.get(id=entry_id)
    job = Job.objects.get(id=job_id)

    entry.delete()

    # update job status and save it
    job.status = Job.STATUS_DONE
    job.save()

@app.task(bind=True)
def copy_entry(self, user_id, src_entry_id, dest_entry_names, jobset):
    user = User.objects.get(id=user_id)
    src_entry = Entry.objects.get(id=src_entry_id)

    for name in dest_entry_names:
        if not Entry.objects.filter(schema=src_entry.schema, name=name).exists():
            dest_entry = src_entry.clone(user, name=name)
            dest_entry.register_es()

        job = Job.objects.get(id=jobset[name])
        job.target = dest_entry
        job.status = Job.STATUS_DONE
        job.text = 'original entry: %s' % src_entry.name

        job.save()
