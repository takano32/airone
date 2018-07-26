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
            self.assertEqual(job.status, Job.STATUS_PROCESSING)
            self.assertEqual(job.operation, info['op'])
