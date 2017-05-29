import json

from django.test import TestCase, Client
from django.contrib.auth.models import Group
from django.urls import reverse
from django.core import exceptions

from entity.models import Entity
from user.models import User
from acl.models import ACLBase

from airone.lib import ACLType
from xml.etree import ElementTree


class ViewTest(TestCase):
    def setUp(self):
        self.client = Client()

        self._entity = Entity(name='test')
        self._entity.save()

    def test_index(self):
        resp = self.client.get(reverse('acl:index', args=[self._entity.id]))
        self.assertEqual(resp.status_code, 200)

        root = ElementTree.fromstring(resp.content.decode('utf-8'))
        self.assertIsNotNone(root.find('.//form'))

    def test_index_with_objects(self):
        User(username='hoge').save()

        resp = self.client.get(reverse('acl:index', args=[self._entity.id]))
        self.assertEqual(resp.status_code, 200)

        root = ElementTree.fromstring(resp.content.decode('utf-8'))
        self.assertIsNotNone(root.find('.//table/tr/td'))

    def test_get_acl_set(self):
        resp = self.client.get(reverse('acl:set'))
        self.assertEqual(resp.status_code, 400)

    def test_post_acl_set(self):
        user = User(username='hoge')
        user.save()

        params = {
            'object_id': str(self._entity.id),
            'object_type': str(self._entity.objtype),
            'acl': [
                {
                    'member_id': str(user.id),
                    'member_type': 'user',
                    'value': str(ACLType.Writable.id)},
            ]
        }
        resp = self.client.post(reverse('acl:set'), json.dumps(params), 'application/json')

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(user.permissions.count(), 1)
        self.assertEqual(user.permissions.last(), self._entity.writable)

    def test_update_acl(self):
        group = Group(name='fuga')
        group.save()

        # set ACL object in advance, there are two members in the deletable parameter
        group.permissions.add(self._entity.deletable)

        params = {
            'object_id': str(self._entity.id),
            'object_type': str(self._entity.objtype),
            'acl': [
                {
                    'member_id': str(group.id),
                    'member_type': 'group',
                    'value': str(ACLType.Readable.id)
                }
            ]
        }
        resp = self.client.post(reverse('acl:set'), json.dumps(params), 'application/json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(group.permissions.count(), 1)
        self.assertEqual(group.permissions.last(), self._entity.readable)

    def test_post_acl_set_without_object_id(self):
        user = User(username='hoge')
        user.save()

        params = {
            'acl': [
                {'member_id': str(user.id), 'value': str(ACLType.Writable)},
            ]
        }
        resp = self.client.post(reverse('acl:set'), json.dumps(params), 'application/json')

        self.assertEqual(resp.status_code, 400)

    def test_post_acl_set_without_acl_params(self):
        user = User(username='hoge')
        user.save()

        params = {
            'object_id': str(self._entity.id)
        }
        resp = self.client.post(reverse('acl:set'), json.dumps(params), 'application/json')

        self.assertEqual(resp.status_code, 400)

    def test_post_acl_set_with_invalid_member_id(self):
        params = {
            'object_id': str(self._entity.id),
            'acl': [
                {'member_id': '9999', 'value': str(ACLType.Writable)},
            ]
        }
        resp = self.client.post(reverse('acl:set'), json.dumps(params), 'application/json')

        self.assertEqual(resp.status_code, 400)

    def test_post_acl_set_with_invalid_acl(self):
        user = User(username='hoge')
        user.save()

        params = {
            'object_id': str(self._entity.id),
            'acl': [
                {'member_id': str(user.id), 'value': 'abcd'},
            ]
        }
        resp = self.client.post(reverse('acl:set'), json.dumps(params), 'application/json')

        self.assertEqual(resp.status_code, 400)
