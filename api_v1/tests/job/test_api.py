import json

from airone.lib.test import AironeViewTest
from airone.lib.types import AttrTypeValue
from datetime import datetime, timedelta

from job.models import Job
from user.models import User
from entry import tasks
from entry.models import Entry
from entity.models import Entity, EntityAttr
from django.contrib.auth.models import User as DjangoUser
from django.urls import reverse

from unittest.mock import patch
from unittest.mock import Mock

from job.settings import CONFIG

# constants using this tests
_TEST_MAX_LIST_NAV = 2


class APITest(AironeViewTest):
    def setUp(self):
        super(APITest, self).setUp()

        # save original configuration not to make affect other tests by chaning this
        self.old_config = CONFIG.conf

        CONFIG.conf['MAX_LIST_NAV'] = _TEST_MAX_LIST_NAV

    def tearDown(self):
        super(APITest, self).tearDown()

        # retrieve original configuration for Job.settings.CONFIG
        CONFIG.conf = self.old_config

    def test_get_jobs(self):
        user = self.guest_login()

        entity = Entity.objects.create(name='entity', created_user=user)
        entry = Entry.objects.create(name='entry', created_user=user, schema=entity)

        # create three jobs
        jobs = [Job.new_create(user, entry) for _ in range(0, 3)]

        resp = self.client.get('/api/v1/job/')
        self.assertEqual(resp.status_code, 200)

        # checks expected parameters are set correctly
        results = resp.json()
        self.assertEqual(results['constant']['operation'], {
            'create': Job.OP_CREATE,
            'edit': Job.OP_EDIT,
            'delete': Job.OP_DELETE,
            'copy': Job.OP_COPY,
        })
        self.assertEqual(results['constant']['status'], {
            'processing': Job.STATUS_PROCESSING,
            'done': Job.STATUS_DONE,
            'error': Job.STATUS_ERROR,
            'timeout': Job.STATUS_TIMEOUT,
        })

        # checks the parameter MAXLIST_NAV is applied
        self.assertEqual(Job.objects.filter(user=user).count(), 3)
        self.assertEqual(len(results['result']), _TEST_MAX_LIST_NAV)

        # After cheeting created_at time back to CONFIG.RECENT_SECONDS or more,
        # this checks that nothing result will be returned.
        for job in jobs:
            before_time = job.created_at
            job.created_at = (job.created_at - timedelta(seconds=(CONFIG.RECENT_SECONDS + 1)))
            job.save(update_fields=['created_at'])

        resp = self.client.get('/api/v1/job/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()['result']), 0)

    def test_rerun_jobs(self):
        user = self.guest_login()

        entity = Entity.objects.create(name='entity', created_user=user)
        attr = EntityAttr.objects.create(name='attr',
                                         created_user=user,
                                         type=AttrTypeValue['string'],
                                         parent_entity=entity)
        entity.attrs.add(attr)

        # make a job to create an entry
        entry = Entry.objects.create(name='entry', schema=entity, created_user=user)
        job = Job.new_create(user, entry, params={
            'attrs': [
                {'id': str(attr.id), 'value': [{'data': 'hoge', 'index': 0}], 'referral_key': []}
            ]
        })

        # send request to run job
        resp = self.client.post('/api/v1/job/run/%d' % job.id)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.content, b'"Success to run command"')

        job = Job.objects.get(id=job.id)
        self.assertEqual(job.status, Job.STATUS_DONE)
        self.assertEqual(entry.attrs.count(), 1)

        attrv = entry.attrs.first().get_latest_value()
        self.assertEqual(attrv.value, 'hoge')

        # send request to run job with finished job-id
        resp = self.client.post('/api/v1/job/run/%d' % job.id)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.content, b'"Target job has already been done"')

        # send request to run job with invalid job-id
        resp = self.client.post('/api/v1/job/run/%d' % 9999)
        self.assertEqual(resp.status_code, 400)

        # make and send a job to update entry
        job = Job.new_edit(user, entry, params={
            'attrs': [
                {'id': str(entry.attrs.first().id), 'value': [{'data': 'fuga', 'index': 0}], 'referral_key': []}
            ]
        })
        resp = self.client.post('/api/v1/job/run/%d' % job.id)

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.content, b'"Success to run command"')
        self.assertEqual(Job.objects.get(id=job.id).status, Job.STATUS_DONE)
        self.assertEqual(entry.attrs.first().get_latest_value().value, 'fuga')

        # make and send a job to copy entry
        job = Job.new_copy(user, entry, params='new_entry')
        resp = self.client.post('/api/v1/job/run/%d' % job.id)

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.content, b'"Success to run command"')
        self.assertEqual(Job.objects.get(id=job.id).status, Job.STATUS_DONE)

        # checks it's success to clone entry
        new_entry = Entry.objects.get(name='new_entry', schema=entity)
        self.assertEqual(new_entry.attrs.first().get_latest_value().value, 'fuga')

        # make and send a job to delete entry
        job = Job.new_delete(user, entry)
        resp = self.client.post('/api/v1/job/run/%d' % job.id)

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.content, b'"Success to run command"')
        self.assertFalse(Entry.objects.get(id=entry.id).is_active)

    def test_rerun_deleted_job(self):
        user = self.guest_login()

        entity = Entity.objects.create(name='entity', created_user=user)
        entry = Entry.objects.create(name='entry', created_user=user, schema=entity)
        job = Job.new_create(user, entry)

        # delete target entry
        entry.delete()

        resp = self.client.post('/api/v1/job/run/%d' % job.id)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.content, b'"Job target has already been deleted"')
