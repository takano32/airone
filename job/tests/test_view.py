import json

from airone.lib.test import AironeViewTest
from datetime import datetime, timedelta

from job.models import Job
from user.models import User
from entry import tasks
from entry.models import Entry
from entity.models import Entity
from django.contrib.auth.models import User as DjangoUser
from django.urls import reverse

from unittest.mock import patch
from unittest.mock import Mock

from job.settings import CONFIG

# constants using this tests
_TEST_MAX_LIST_VIEW = 2


class ViewTest(AironeViewTest):
    def setUp(self):
        super(ViewTest, self).setUp()

        # save original configuration not to make affect other tests by chaning this
        self.old_config = CONFIG.conf

        CONFIG.conf['MAX_LIST_VIEW'] = _TEST_MAX_LIST_VIEW

    def tearDown(self):
        super(ViewTest, self).tearDown()

        # retrieve original configuration for Job.settings.CONFIG
        CONFIG.conf = self.old_config

    def test_get_jobs(self):
        user = self.guest_login()

        entity = Entity.objects.create(name='entity', created_user=user)
        entry = Entry.objects.create(name='entry', created_user=user, schema=entity)

        # create three jobs
        jobs = [Job.new_create(user, entry) for _ in range(0, _TEST_MAX_LIST_VIEW + 1)]
        self.assertEqual(Job.objects.filter(user=user).count(), _TEST_MAX_LIST_VIEW + 1)

        # checks number of the returned objects are as expected
        resp = self.client.get('/job/')
        self.assertEqual(resp.status_code, 200)

        self.assertEqual(len(resp.context['jobs']), _TEST_MAX_LIST_VIEW)

        # checks all job objects will be returned
        resp = self.client.get('/job/?nolimit=1')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.context['jobs']), _TEST_MAX_LIST_VIEW + 1)

        # checks no job object will be returned because of different user
        self.admin_login()
        resp = self.client.get('/job/?nolimit=1')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.context['jobs']), 0)

    def test_get_jobs_deleted_target(self):
        user = self.guest_login()

        entity = Entity.objects.create(name='entity', created_user=user)
        entry = Entry.objects.create(name='entry', created_user=user, schema=entity)
        job = Job.new_create(user, entry)

        resp = self.client.get('/job/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.context['jobs']), 1)

        # check the case show jobs after deleting job target
        entry.delete()

        resp = self.client.get('/job/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['jobs'], [])

    @patch('entry.views.create_entry_attrs.delay', Mock(side_effect=tasks.create_entry_attrs))
    def test_rerun_job_which_is_under_processing(self):
        # send a request to re-run creating entry which is under processing
        user = self.guest_login()

        entity = Entity.objects.create(name='entity', created_user=user)

        params = {
            'entry_name': 'new_entry',
            'attrs': [],
        }

        def side_effect():
            # send re-run request for executing job by calling API
            job = Job.objects.last()
            self.assertEqual(job.status, Job.STATUS_PROCESSING)

            # check that backend processing never run by calling API
            resp = self.client.post('/api/v1/job/run/%d' % job.id)
            self.assertEqual(resp.status_code, 400)
            self.assertEqual(resp.content, b'"Target job is under processing"')

        with patch.object(Entry, 'register_es', Mock(side_effect=side_effect)):
            resp = self.client.post(reverse('entry:do_create', args=[entity.id]),
                                    json.dumps(params),
                                    'application/json')

            self.assertEqual(resp.status_code, 200)

    def test_job_download_failure(self):
        user = self.guest_login()
        entity = Entity.objects.create(name='entity', created_user=user)

        job = Job.new_create(user, entity, 'hoge')

        # When user send a download request of Job with invalid Job-id, then HTTP 400 is returned
        resp = self.client.get('/job/download/%d' % (job.id + 1))
        self.assertEqual(resp.status_code, 400)

        # When user send a download request of non export Job, then HTTP 400 is returned
        resp = self.client.get('/job/download/%d' % job.id)
        self.assertEqual(resp.status_code, 400)

        # When user send a download request of export Job by differenct user from creating one,
        # then HTTP 400 is returned
        job = Job.new_export(user, 'fuga')
        user = self.admin_login()
        resp = self.client.get('/job/download/%d' % job.id)
        self.assertEqual(resp.status_code, 400)

    def test_job_download(self):
        user = self.guest_login()

        # initialize an export Job
        job = Job.new_export(user, 'hoge')
        job.set_cache('abcd')

        # check job contents could be downloaded
        resp = self.client.get('/job/download/%d' % job.id)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Disposition'], 'attachment; filename="hoge"')
        self.assertEqual(resp.content.decode('utf8'), 'abcd')
