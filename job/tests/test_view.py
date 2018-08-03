from airone.lib.test import AironeViewTest
from datetime import datetime, timedelta

from job.models import Job
from user.models import User
from entry.models import Entry
from entity.models import Entity
from django.contrib.auth.models import User as DjangoUser

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
        someone = User.objects.create(username='someone', password='pass')
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
