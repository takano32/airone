from airone.lib.test import AironeViewTest
from datetime import datetime, timedelta

from job.models import Job
from user.models import User
from entry.models import Entry
from entity.models import Entity
from django.contrib.auth.models import User as DjangoUser

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
