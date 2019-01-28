import json

from airone.lib.test import AironeTestCase

from job.models import Job
from user.models import User
from entry.models import Entry
from entity.models import Entity


class ModelTest(AironeTestCase):
    def setUp(self):
        self.guest = User.objects.create(username='guest', password='passwd', is_superuser=False)
        self.admin = User.objects.create(username='admin', password='passwd', is_superuser=True)

    def test_create_object(self):
        entity = Entity.objects.create(name='entity', created_user=self.guest)
        entry = Entry.objects.create(name='entry', created_user=self.guest, schema=entity)

        jobinfos = [
            {'method': 'new_create', 'op': Job.OP_CREATE},
            {'method': 'new_edit','op': Job.OP_EDIT},
            {'method': 'new_delete', 'op': Job.OP_DELETE},
            {'method': 'new_copy', 'op': Job.OP_COPY},
        ]
        for info in jobinfos:
            job = getattr(Job, info['method'])(self.guest, entry)

            self.assertEqual(job.user, self.guest)
            self.assertEqual(job.target, entry)
            self.assertEqual(job.target_type, Job.TARGET_ENTRY)
            self.assertEqual(job.status, Job.STATUS_PREPARING)
            self.assertEqual(job.operation, info['op'])

    def test_get_object(self):
        entity = Entity.objects.create(name='entity', created_user=self.guest)
        entry = Entry.objects.create(name='entry', created_user=self.guest, schema=entity)

        params = {
            'entities': entity.id,
            'attrinfo': {'name': 'foo', 'keyword': ''},
            'export_style': '"yaml"',
        }

        # check there is no job
        self.assertFalse(Job.get_job_with_params(self.guest, params).exists())

        # create a new job
        job = Job.new_export(self.guest, text='hoge', params=params)
        self.assertEqual(job.target_type, Job.TARGET_UNKNOWN)
        self.assertEqual(job.operation, Job.OP_EXPORT)
        self.assertEqual(job.text, 'hoge')

        # check created job is got by specified params
        self.assertEqual(Job.get_job_with_params(self.guest, params).count(), 1)
        self.assertEqual(Job.get_job_with_params(self.guest, params).last(), job)

        # check the case when different params is specified then it returns None
        params['attrinfo']['name'] = ''
        self.assertFalse(Job.get_job_with_params(self.guest, params).exists())

    def test_set_status(self):
        entity = Entity.objects.create(name='entity', created_user=self.guest)
        job = Job.new_create(self.guest, entity)

        # check default status
        self.assertEqual(job.status, Job.STATUS_PREPARING)

        job.set_status(Job.STATUS_DONE)

        # check status is changed by set_status method
        self.assertEqual(Job.objects.get(id=job.id).status, Job.STATUS_DONE)

    def test_cache(self):
        entity = Entity.objects.create(name='entity', created_user=self.guest)
        job = Job.new_create(self.guest, entity)

        registering_values = [
            1234,
            'foo\nbar\nbaz',
            ['foo', 'bar'],
            {'hoge': 'fuga', 'foo': ['a', 'b']}
        ]
        for value in registering_values:
            job.set_cache(json.dumps(value))
            self.assertEqual(job.get_cache(), json.dumps(value))
