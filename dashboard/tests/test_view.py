import mock
import re
import sys

from airone.lib.test import AironeViewTest
from django.urls import reverse
from django.contrib.auth.models import User as DjangoUser
from io import StringIO

from entry.models import Entry, AttributeValue

from xml.etree import ElementTree

class ViewTest(AironeViewTest):
    def setUp(self):
        self.admin_login()

        # preparing test Entity/Entry objects
        fp = self.open_fixture_file('entry.yaml')
        resp = self.client.post(reverse('dashboard:do_import'), {'file': fp})

    def test_search_without_query(self):
        resp = self.client.get(reverse('dashboard:search'))
        self.assertEqual(resp.status_code, 400)

    def test_search_entity_and_entry(self):
        query = 'ent'

        resp = self.client.get(reverse('dashboard:search'), {'query': query})
        self.assertEqual(resp.status_code, 200)

        root = ElementTree.fromstring(resp.content.decode('utf-8'))

        # '+1' means description of table
        self.assertEquals(len(root.findall('.//table/tr')),
                          Entry.objects.filter(name__icontains=query).count() + 1)

    def test_search_entry_from_value(self):
        resp = self.client.get(reverse('dashboard:search'), {'query': 'hoge'})
        self.assertEqual(resp.status_code, 200)

        root = ElementTree.fromstring(resp.content.decode('utf-8'))
        self.assertEquals(len(root.findall('.//table/tr')), 2)

    def test_search_invalid_objects(self):
        resp = self.client.get(reverse('dashboard:search'), {'query': 'hogefuga'})
        self.assertEqual(resp.status_code, 200)

        root = ElementTree.fromstring(resp.content.decode('utf-8'))
        self.assertEquals(len(root.findall('.//table/tr')), 0)

    def test_show_dashboard_with_django_user(self):
        # create test user which is authenticated by Django, not AirOne
        user = DjangoUser(username='django-user')
        user.set_password('passwd')
        user.save()

        # login as the django-user
        self.client.login(username='django-user', password='passwd')

        resp = self.client.get(reverse('dashboard:index'))
        self.assertEqual(resp.status_code, 200)

    def test_show_dashboard_with_anonymous(self):
        # logout test-user, this means current user is Anonymous
        self.client.logout()

        resp = self.client.get(reverse('dashboard:index'))
        self.assertEqual(resp.status_code, 200)

    def test_enable_profiler(self):
        self.client.logout()

        # set StringIO to capteure stdout context
        sys.stdout = StringIO()
        with mock.patch('airone.lib.profile.settings') as st_mock:
            # set to enable AirOne Profiler
            st_mock.AIRONE = {'ENABLE_PROFILE': True}

            resp = self.client.get(reverse('dashboard:index'))
            self.assertEqual(resp.status_code, 200)
            self.assertTrue(re.match("^\[Profiling result\] \(([0-9\.]*)\) .*$",
                                     sys.stdout.getvalue()))

        # reset stdout setting
        sys.stdout = sys.__stdout__
