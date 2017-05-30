import json

from django.test import TestCase, Client
from django.urls import reverse

from entity.models import Entity, AttributeBase
from entry.models import Entry, Attribute, AttributeValue
from user.models import User

from airone.lib import types as airone_types
from xml.etree import ElementTree


class ViewTest(TestCase):
    def setUp(self):
        self.client = Client()

        # create test entity which is a base of creating entry
        self._entity = Entity(name='hoge')
        self._entity.save()

        # set AttributeBase for the test Entity object
        self._attr_base = AttributeBase(name='test',
                                  type=airone_types.AttrTypeStr().type,
                                  is_mandatory=True)
        self._attr_base.save()

        # save AttributeBase object to it
        self._entity.attr_bases.add(self._attr_base)

    def _admin_login(self):
        # create test user to authenticate
        user = User(username='admin')
        user.set_password('admin')
        user.save()

        self.client.login(username='admin', password='admin')

    def test_get_index_without_login(self):
        resp = self.client.get(reverse('entry:index', args=[self._entity.id]))
        self.assertEqual(resp.status_code, 303)

    def test_get_index_with_login(self):
        self._admin_login()

        resp = self.client.get(reverse('entry:index', args=[self._entity.id]))
        self.assertEqual(resp.status_code, 200)

        root = ElementTree.fromstring(resp.content.decode('utf-8'))
        self.assertIsNone(root.find('.//table'))

    def test_get_index_with_entries(self):
        self._admin_login()

        Entry(name='fuga', schema=self._entity, created_user=User.objects.last()).save()

        resp = self.client.get(reverse('entry:index', args=[self._entity.id]))
        self.assertEqual(resp.status_code, 200)

        root = ElementTree.fromstring(resp.content.decode('utf-8'))
        self.assertIsNotNone(root.find('.//table/tr/td'))

    def test_get_create_page_without_login(self):
        resp = self.client.get(reverse('entry:create', args=[self._entity.id]))
        self.assertEqual(resp.status_code, 303)

    def test_get_create_page_with_login(self):
        self._admin_login()

        resp = self.client.get(reverse('entry:create', args=[self._entity.id]))

        self.assertEqual(resp.status_code, 200)

        root = ElementTree.fromstring(resp.content.decode('utf-8'))
        self.assertIsNotNone(root.find('.//table/tr/td'))

    def test_post_without_login(self):
        params = {
            'entry_name': 'hoge',
            'attrs': [
                {'id': str(self._attr_base.id), 'value': 'fuga'},
            ],
        }
        resp = self.client.post(reverse('entry:do_create', args=[self._entity.id]),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 401)
        self.assertEqual(Entry.objects.count(), 0)
        self.assertEqual(Attribute.objects.count(), 0)
        self.assertEqual(AttributeValue.objects.count(), 0)

    def test_post_with_login(self):
        self._admin_login()

        params = {
            'entry_name': 'hoge',
            'attrs': [
                {'id': str(self._attr_base.id), 'value': 'hoge'},
            ],
        }
        resp = self.client.post(reverse('entry:do_create', args=[self._entity.id]),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Entry.objects.count(), 1)
        self.assertEqual(Attribute.objects.count(), 1)
        self.assertEqual(AttributeValue.objects.count(), 1)

        entry = Entry.objects.last()
        self.assertEqual(entry.attrs.count(), 1)
        self.assertEqual(entry.attrs.last(), Attribute.objects.last())
        self.assertEqual(entry.attrs.last().values.count(), 1)
        self.assertEqual(entry.attrs.last().values.last(), AttributeValue.objects.last())

    def test_post_with_lack_of_params(self):
        self._admin_login()

        params = {
            'entry_name': '',
            'attrs': [
                {'id': str(self._attr_base.id), 'value': 'hoge'},
            ],
        }
        resp = self.client.post(reverse('entry:do_create', args=[self._entity.id]),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 400)
        self.assertEqual(Entry.objects.count(), 0)
        self.assertEqual(Attribute.objects.count(), 0)
        self.assertEqual(AttributeValue.objects.count(), 0)

    def test_post_with_invalid_param(self):
        self._admin_login()

        params = {
            'entry_name': 'hoge',
            'attrs': [
                {'id': str(self._attr_base.id), 'value': 'hoge'},
                {'id': '9999', 'value': 'invalid value'},
            ],
        }
        resp = self.client.post(reverse('entry:do_create', args=[self._entity.id]),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 400)
        self.assertEqual(Entry.objects.count(), 0)
        self.assertEqual(Attribute.objects.count(), 0)
        self.assertEqual(AttributeValue.objects.count(), 0)
