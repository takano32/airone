import csv
import custom_view
import io
import json
import logging
import yaml

from airone.lib.acl import ACLType
from airone.lib.types import AttrTypeValue
from airone.celery import app
from entity.models import Entity, EntityAttr
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
def create_entry_attrs(self, user_id, entry_id, job_id):
    job = Job.objects.get(id=job_id)

    if job.status != Job.STATUS_DONE and job.status != Job.STATUS_PROCESSING:
        # At the first time, update job status to prevent executing this job duplicately
        job.status = Job.STATUS_PROCESSING
        job.save(update_fields=['status'])

        user = User.objects.get(id=user_id)
        entry = Entry.objects.get(id=entry_id)
        recv_data = json.loads(job.params)
        # Create new Attributes objects based on the specified value
        for entity_attr in entry.schema.attrs.filter(is_active=True):
            # skip for unpermitted attributes
            if not entity_attr.is_active or not user.has_permission(entity_attr, ACLType.Readable):
                continue

            # create Attibute object that contains AttributeValues
            attr = entry.add_attribute_from_base(entity_attr, user)
            if not any([int(x['id']) == attr.schema.id for x in recv_data['attrs']]):
                continue

            # make an initial AttributeValue object if the initial value is specified
            attr_data = [x for x in recv_data['attrs'] if int(x['id']) == attr.schema.id][0]

            # register new AttributeValue to the "attr"
            try:
                attr.add_value(user, _convert_data_value(attr, attr_data))
            except ValueError as e:
                Logger.warning('(%s) attr_data: %s' % (e, str(attr_data)))

        # Delete duplicate attrs because this processing may execute concurrently
        for entity_attr in entry.schema.attrs.filter(is_active=True):
            if entry.attrs.filter(schema=entity_attr, is_active=True).count() > 1:
                query = entry.attrs.filter(schema=entity_attr, is_active=True)
                query.exclude(id=query.first().id).delete()

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
def edit_entry_attrs(self, user_id, entry_id, job_id):
    job = Job.objects.get(id=job_id)

    if job.status != Job.STATUS_DONE and job.status != Job.STATUS_PROCESSING:
        # At the first time, update job status to prevent executing this job duplicately
        job.status = Job.STATUS_PROCESSING
        job.save(update_fields=['status'])

        user = User.objects.get(id=user_id)
        entry = Entry.objects.get(id=entry_id)

        recv_data = json.loads(job.params)
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
    job = Job.objects.get(id=job_id)

    if job.status != Job.STATUS_DONE:
        entry = Entry.objects.get(id=entry_id)
        entry.delete()

        # update job status and save it
        job.status = Job.STATUS_DONE
        job.save()

@app.task(bind=True)
def copy_entry(self, user_id, src_entry_id, job_id):
    job = Job.objects.get(id=job_id)

    if job.status != Job.STATUS_DONE:
        # update job status
        job.set_status(Job.STATUS_PROCESSING)

        user = User.objects.get(id=user_id)
        src_entry = Entry.objects.get(id=src_entry_id)

        params = json.loads(job.params)
        dest_entry = Entry.objects.filter(schema=src_entry.schema, name=params['new_name']).first()
        if not dest_entry:
            dest_entry = src_entry.clone(user, name=params['new_name'])
            dest_entry.register_es()

        if custom_view.is_custom_after_copy_entry(src_entry.schema.name):
            custom_view.call_custom_after_copy_entry(src_entry.schema.name, user, src_entry, dest_entry, params['post_data'])

        job.target = dest_entry
        job.status = Job.STATUS_DONE
        job.text = 'original entry: %s' % src_entry.name

        job.save()

@app.task(bind=True)
def import_entries(self, job_id):
    job = Job.objects.get(id=job_id)

    if (job.status != Job.STATUS_DONE and
        job.status != Job.STATUS_PROCESSING and
        job.status != Job.STATUS_ERROR):
        user = job.user

        entity = Entity.objects.get(id=job.target.id)
        if not user.has_permission(entity, ACLType.Writable):
            job.status = Job.STATUS_ERROR
            job.text = 'Permission denied to import. You need Writable permission for "%s"' % entity.name
            job.save(update_fields=['text', 'status'])
            return

        whole_data = json.loads(job.params).get(entity.name)
        if not whole_data:
            job.status = Job.STATUS_ERROR
            job.text = 'Uploaded file has no entry data of %s' % entity.name
            job.save(update_fields=['text', 'status'])
            return

        job.status = Job.STATUS_PROCESSING
        job.save(update_fields=['status'])

        total_count = len(whole_data)
        # create or update entry
        for (index, entry_data) in enumerate(whole_data):
            job.text = 'Now importing... (progress: [%5d/%5d])' % (index + 1, total_count)
            job.save(update_fields=['text'])

            entry = Entry.objects.filter(name=entry_data['name'], schema=entity).first()
            if not entry:
                entry = Entry.objects.create(name=entry_data['name'], schema=entity, created_user=user)
            else:
                if not user.has_permission(entry, ACLType.Writable):
                    continue

            entry.complement_attrs(user)
            for attr_name, value in entry_data['attrs'].items():
                # If user doesn't have readable permission for target Attribute, it won't be created.
                if not entry.attrs.filter(schema__name=attr_name).exists():
                    continue

                entity_attr = EntityAttr.objects.get(name=attr_name, parent_entity=entry.schema)
                attr = entry.attrs.get(schema=entity_attr)
                if (not user.has_permission(entity_attr, ACLType.Writable) or
                    not user.has_permission(attr, ACLType.Writable)):
                    continue

                input_value = attr.convert_value_to_register(value)
                if user.has_permission(attr.schema, ACLType.Writable) and attr.is_updated(input_value):
                    attr.add_value(user, input_value)

            # register entry to the Elasticsearch
            entry.register_es()

        job.status = Job.STATUS_DONE
        job.text = ''
        job.save()

@app.task(bind=True)
def export_entries(self, job_id):
    job = Job.objects.get(id=job_id)

    if job.status == Job.STATUS_DONE or job.status == Job.STATUS_PROCESSING:
        return

    job.set_status(Job.STATUS_PROCESSING)

    user = job.user
    entity = Entity.objects.get(id=job.target.id)
    params = json.loads(job.params)

    exported_data = []
    for entry in Entry.objects.filter(schema=entity, is_active=True):
        if user.has_permission(entry, ACLType.Readable):
            exported_data.append(entry.export(user))

    output = None
    if params['export_format'] == 'csv':
        # newline is blank because csv module performs universal newlines
        # https://docs.python.org/ja/3/library/csv.html#id3
        output = io.StringIO(newline='')
        writer = csv.writer(output)

        attrs = [x.name for x in entity.attrs.filter(is_active=True)]
        writer.writerow(['Name', *attrs])

        def data2str(data):
            if not data:
                return ''
            return str(data)

        for data in exported_data:
            writer.writerow([
                data['name'],
                *[data2str(data['attrs'][x]) for x in attrs if x in data['attrs']]
            ])
    else:
        output = io.StringIO()
        output.write(yaml.dump({entity.name: exported_data}, default_flow_style=False, allow_unicode=True))

    if output:
        job.set_cache(output.getvalue())

    job.set_status(Job.STATUS_DONE)
