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

    def test_post_with_optional_parameter(self):
        self._admin_login()

        # add an optional AttributeBase to the test Entity object
        self._attr_base_optional = AttributeBase(name='test-optional',
                                                 type=airone_types.AttrTypeStr().type,
                                                 is_mandatory=False)
        self._attr_base_optional.save()
        self._entity.attr_bases.add(self._attr_base_optional)

        params = {
            'entry_name': 'hoge',
            'attrs': [
                {'id': str(self._attr_base.id), 'value': 'hoge'},
                {'id': str(self._attr_base_optional.id), 'value': ''},
            ],
        }
        resp = self.client.post(reverse('entry:do_create', args=[self._entity.id]),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Entry.objects.count(), 1)
        self.assertEqual(Attribute.objects.count(), 2)
        self.assertEqual(AttributeValue.objects.count(), 1)

        entry = Entry.objects.last()
        self.assertEqual(entry.attrs.count(), 2)
        self.assertEqual(entry.attrs.get(name='test').values.count(), 1)
        self.assertEqual(entry.attrs.get(name='test-optional').values.count(), 0)
        self.assertEqual(entry.attrs.get(name='test').values.last().value, 'hoge')

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

    def test_get_edit_without_login(self):
        resp = self.client.get(reverse('entry:edit', args=[0]))
        self.assertEqual(resp.status_code, 303)

    def test_get_edit_with_invalid_entry_id(self):
        self._admin_login()

        Entry(name='fuga', schema=self._entity, created_user=User.objects.last()).save()

        # with invalid entry-id
        resp = self.client.get(reverse('entry:edit', args=[0]))
        self.assertEqual(resp.status_code, 400)

    def test_get_edit_with_valid_entry_id(self):
        self._admin_login()

        # making test Entry set
        entry = Entry(name='fuga', schema=self._entity, created_user=User.objects.last())
        entry.save()

        for attr_name in ['foo', 'bar']:
            attr = Attribute(name=attr_name,
                             type=airone_types.AttrTypeStr().type,
                             is_mandatory=True)
            attr.save()

            for value in ['hoge', 'fuga']:
                attr_value = AttributeValue(value=value, created_user=User.objects.last())
                attr_value.save()

                attr.values.add(attr_value)

            entry.attrs.add(attr)

        # with invalid entry-id
        resp = self.client.get(reverse('entry:edit', args=[entry.id]))
        self.assertEqual(resp.status_code, 200)

        e_input = ElementTree.fromstring(resp.content.decode('utf-8')).find('.//table/tr/td/input')
        self.assertIsNotNone(e_input)
        self.assertEqual(Attribute.objects.get(id=e_input.attrib['attr_id']).values.last().value,
                         e_input.attrib['value'])

    def test_get_edit_with_optional_attr(self):
        self._admin_login()

        # making test Entry set
        entry = Entry(name='fuga', schema=self._entity, created_user=User.objects.last())
        entry.save()

        attr = Attribute(name='foo', is_mandatory=False, type=airone_types.AttrTypeStr().type)
        attr.save()
        entry.attrs.add(attr)

        # with invalid entry-id
        resp = self.client.get(reverse('entry:edit', args=[entry.id]))
        self.assertEqual(resp.status_code, 200)

        e_input = ElementTree.fromstring(resp.content.decode('utf-8')).find('.//table/tr/td/input')
        self.assertIsNotNone(e_input)
        self.assertEqual(e_input.attrib['value'], '')

    def test_post_edit_without_login(self):
        params = {'attrs': [{'id': '0', 'value': 'hoge'}]}
        resp = self.client.post(reverse('entry:do_edit'),
                                json.dumps(params), 'application/json')

        self.assertEqual(resp.status_code, 401)
        self.assertEqual(AttributeValue.objects.count(), 0)

    def test_post_edit_with_invalid_param(self):
        self._admin_login()

        params = {'attrs': [{'id': '0', 'value': 'hoge'}]}
        resp = self.client.post(reverse('entry:do_edit'),
                                json.dumps(params), 'application/json')

        self.assertEqual(resp.status_code, 400)
        self.assertEqual(AttributeValue.objects.count(), 0)

    def test_post_edit_with_valid_param(self):
        self._admin_login()

        # making test Entry set
        entry = Entry(name='fuga', schema=self._entity, created_user=User.objects.last())
        entry.save()

        for attr_name in ['foo', 'bar']:
            attr = Attribute(name=attr_name,
                             type=airone_types.AttrTypeStr().type,
                             is_mandatory=True)
            attr.save()

            attr_value = AttributeValue(value='hoge', created_user=User.objects.last())
            attr_value.save()

            attr.values.add(attr_value)
            entry.attrs.add(attr)

        params = {
            'attrs': [
                {'id': str(Attribute.objects.get(name='foo').id), 'value': 'hoge'}, # same value
                {'id': str(Attribute.objects.get(name='bar').id), 'value': 'fuga'},
            ],
        }
        resp = self.client.post(reverse('entry:do_edit'), json.dumps(params), 'application/json')

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(AttributeValue.objects.count(), 3)
        self.assertEqual(Attribute.objects.get(name='foo').values.count(), 1)
        self.assertEqual(Attribute.objects.get(name='bar').values.count(), 2)
        self.assertEqual(Attribute.objects.get(name='foo').values.last().value, 'hoge')
        self.assertEqual(Attribute.objects.get(name='bar').values.last().value, 'fuga')

    def test_post_edit_with_optional_params(self):
        self._admin_login()

        # making test Entry set
        entry = Entry(name='fuga', schema=self._entity, created_user=User.objects.last())
        entry.save()

        for attr_name in ['foo', 'bar']:
            attr = Attribute(name=attr_name,
                             type=airone_types.AttrTypeStr().type,
                             is_mandatory=False)
            attr.save()
            entry.attrs.add(attr)

        params = {
            'attrs': [
                {'id': str(Attribute.objects.get(name='foo').id), 'value': ''}, # blank value
                {'id': str(Attribute.objects.get(name='bar').id), 'value': 'fuga'},
            ],
        }
        resp = self.client.post(reverse('entry:do_edit'), json.dumps(params), 'application/json')

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(AttributeValue.objects.count(), 1)
        self.assertEqual(Attribute.objects.get(name='foo').values.count(), 0)
        self.assertEqual(Attribute.objects.get(name='bar').values.count(), 1)
        self.assertEqual(Attribute.objects.get(name='bar').values.last().value, 'fuga')
