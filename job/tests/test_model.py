import json

from airone.lib.test import AironeTestCase

from django.conf import settings
from job.models import Job
from entry.models import Entry
from entity.models import Entity
from unittest.mock import patch
from user.models import User


class ModelTest(AironeTestCase):
    def setUp(self):
        self.guest = User.objects.create(username='guest', password='passwd', is_superuser=False)
        self.admin = User.objects.create(username='admin', password='passwd', is_superuser=True)
        self.entity = Entity.objects.create(name='entity', created_user=self.guest)

    def tearDown(self):
        settings.AIRONE['JOB_TIMEOUT'] = Job.DEFAULT_JOB_TIMEOUT

    def test_create_object(self):
        entry = Entry.objects.create(name='entry', created_user=self.guest, schema=self.entity)

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
        entry = Entry.objects.create(name='entry', created_user=self.guest, schema=self.entity)

        params = {
            'entities': self.entity.id,
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
        job = Job.new_create(self.guest, self.entity)

        # check default status
        self.assertEqual(job.status, Job.STATUS_PREPARING)

        job.set_status(Job.STATUS_DONE)

        # check status is changed by set_status method
        self.assertEqual(Job.objects.get(id=job.id).status, Job.STATUS_DONE)

    def test_cache(self):
        job = Job.new_create(self.guest, self.entity)

        registering_values = [
            1234,
            'foo\nbar\nbaz',
            ['foo', 'bar'],
            {'hoge': 'fuga', 'foo': ['a', 'b']}
        ]
        for value in registering_values:
            job.set_cache(json.dumps(value))
            self.assertEqual(job.get_cache(), json.dumps(value))

    def test_dependent_job(self):
        entry = Entry.objects.create(name='entry', created_user=self.guest, schema=self.entity)

        (job1, job2) = [Job.new_edit(self.guest, entry) for x in range(2)]
        self.assertIsNone(job1.dependent_job)
        self.assertEqual(job2.dependent_job, job1)

        # When a job don't has target parameter, dependent_job is not set because
        # there is no problem when these tasks are run simultaneouslly.
        jobs = [Job.new_export(self.guest) for x in range(2)]
        self.assertTrue(all([j.dependent_job == None for j in jobs]))

        # overwrite timeout timeout value for testing
        settings.AIRONE['JOB_TIMEOUT'] = -1

        # Because jobs[1] is created after the expiry of jobs[0]
        jobs = [Job.new_edit(self.guest, entry) for x in range(2)]
        self.assertTrue(all([j.dependent_job == None for j in jobs]))

    def test_job_is_timeout(self):
        job = Job.new_create(self.guest, self.entity)
        self.assertFalse(job.is_timeout())

        # overwrite timeout timeout value for testing
        settings.AIRONE['JOB_TIMEOUT'] = -1

        self.assertTrue(job.is_timeout())

    @patch('job.models.time.sleep')
    def test_waiting_job_until_dependent_one_is_finished(self, mock_sleep):
        # create two jobs which have dependency
        (job1, job2) = [Job.new_create(self.guest, self.entity) for _x in range(2)]
        self.assertFalse(job1.is_finished())
        self.assertFalse(job2.is_finished())

        def side_effect(*args, **kwargs):
            job1.text = 'finished manually from side_effect'
            job1.status = Job.STATUS_DONE
            job1.save(update_fields=['status', 'text'])

        mock_sleep.side_effect = side_effect
        job2.wait_dependent_job()

        self.assertTrue(job1.is_finished())
        self.assertEqual(job1.text, 'finished manually from side_effect')
