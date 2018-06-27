import mock
import re
import sys
import json

from airone.lib.test import AironeViewTest
from airone.lib.types import AttrTypeValue
from django.urls import reverse
from django.contrib.auth.models import User as DjangoUser
from io import StringIO

from entity.models import Entity, EntityAttr
from entry.models import Entry, AttributeValue

from xml.etree import ElementTree

class ViewTest(AironeViewTest):
    def setUp(self):
        self.admin = self.admin_login()

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

    def test_show_advanced_search(self):
        # create entity which has attr
        entity1 = Entity.objects.create(name="entity-1", created_user=self.admin)
        entity1.attrs.add(EntityAttr.objects.create(**{
            'name': 'attr-1-1',
            'type': AttrTypeValue['string'],
            'created_user': self.admin,
            'parent_entity': entity1,
        }))
        entity1.save()

        # create entity which doesn't have attr
        entity2 = Entity.objects.create(name="entity-2", created_user=self.admin)
        entity2.save()

        resp = self.client.get(reverse('dashboard:advanced_search'))
        self.assertEqual(resp.status_code, 200)

        root = ElementTree.fromstring(resp.content.decode('utf-8'))

        # find entity options
        options = root.findall(".//select[@id='all_entity']/option")
        # entity-1 should be displayed
        self.assertEquals(1, len(list(filter(lambda o: o.text=="entity-1", options))))
        # entity-2 should not be displayed
        self.assertEquals(0, len(list(filter(lambda o: o.text=="entity-2", options))))


    def test_show_advanced_search_results(self):
        for entity_index in range(0, 2):
            entity = Entity.objects.create(name='entity-%d' % entity_index, created_user=self.admin)
            entity.attrs.add(EntityAttr.objects.create(**{
                'name': 'attr',
                'type': AttrTypeValue['string'],
                'created_user': self.admin,
                'parent_entity': entity,
            }))

            for entry_index in range(0, 10):
                entry = Entry.objects.create(name='entry-%d' % (entry_index),
                                             schema=entity, created_user=self.admin)
                entry.complement_attrs(self.admin)

                # add an AttributeValue
                entry.attrs.first().add_value(self.admin, 'data-%d' % entry_index)

                # register entry to the Elasticsearch
                entry.register_es()

        # test to show advanced_search_result page
        resp = self.client.get(reverse('dashboard:advanced_search_result'), {
            'entity[]': [x.id for x in Entity.objects.filter(name__regex='^entity-')],
            'attr[]': ['attr'],
        })
        self.assertEqual(resp.status_code, 200)

        # test to export results of advanced_search
        resp = self.client.post(reverse('dashboard:export_search_result'), {
            'entities': json.dumps([x.id for x in Entity.objects.filter(name__regex='^entity-')]),
            'attrinfo': json.dumps([{'name': 'attr', 'keyword': 'data-5'}])
        })
        self.assertEqual(resp.status_code, 200)

        csv_contents = [x for x in resp.content.decode('utf-8').split('\n') if x]
        self.assertEqual(len(csv_contents), 3)
        self.assertEqual(csv_contents[0], 'Name,attr')
        self.assertEqual(csv_contents[1], 'entry-5,data-5')
        self.assertEqual(csv_contents[2], 'entry-5,data-5')
