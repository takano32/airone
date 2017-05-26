import json

from django.test import TestCase, Client
from django.urls import reverse
from django.core import exceptions

from entity.models import Entity
from user.models import User
from acl.models import ACLBase, ACL

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
        User(name='hoge').save()

        resp = self.client.get(reverse('acl:index', args=[self._entity.id]))
        self.assertEqual(resp.status_code, 200)

        root = ElementTree.fromstring(resp.content.decode('utf-8'))
        self.assertIsNotNone(root.find('.//table/tr/td'))

    def test_get_acl_set(self):
        resp = self.client.get(reverse('acl:set'))
        self.assertEqual(resp.status_code, 400)

    def test_post_acl_set(self):
        user = User(name='hoge')
        user.save()

        params = {
            'object_id': str(self._entity.id),
            'acl': [
                {'member_id': str(user.id), 'value': str(ACLType.Writable)},
            ]
        }
        resp = self.client.post(reverse('acl:set'), json.dumps(params), 'application/json')

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self._entity.acl.readable.count(), 0)
        self.assertEqual(self._entity.acl.writable.count(), 1)
        self.assertEqual(self._entity.acl.deletable.count(), 0)
        self.assertEqual(self._entity.acl.writable.first().name, user.name)
        self.assertEqual(ACL.objects.count(), 1)
        self.assertEqual(ACL.objects.first(), self._entity.acl)

    def test_update_acl(self):
        u_hoge = User(name='hoge')
        u_hoge.save()
        u_fuga = User(name='fuga')
        u_fuga.save()

        # set ACL object in advance, there are two members in the deletable parameter
        self._entity.acl.deletable = [u_hoge, u_fuga]

        params = {
            'object_id': str(self._entity.id),
            'acl': [
                {'member_id': str(u_hoge.id), 'value': str(ACLType.Readable)},
            ]
        }
        resp = self.client.post(reverse('acl:set'), json.dumps(params), 'application/json')
        self.assertEqual(resp.status_code, 200)

        self.assertEqual(self._entity.acl.readable.count(), 1)
        self.assertEqual(self._entity.acl.writable.count(), 0)
        self.assertEqual(self._entity.acl.deletable.count(), 1)
        self.assertEqual(self._entity.acl.readable.first().name, u_hoge.name)
        self.assertEqual(ACL.objects.count(), 1)
        self.assertEqual(ACL.objects.first(), self._entity.acl)

    def test_post_acl_set_without_object_id(self):
        user = User(name='hoge')
        user.save()

        params = {
            'acl': [
                {'member_id': str(user.id), 'value': str(ACLType.Writable)},
            ]
        }
        resp = self.client.post(reverse('acl:set'), json.dumps(params), 'application/json')

        self.assertEqual(resp.status_code, 400)

    def test_post_acl_set_without_acl_params(self):
        user = User(name='hoge')
        user.save()

        params = {
            'object_id': str(self._entity.id)
        }
        resp = self.client.post(reverse('acl:set'), json.dumps(params), 'application/json')

        self.assertEqual(resp.status_code, 400)

    def test_post_acl_set_with_invalid_acl(self):
        params = {
            'object_id': str(self._entity.id),
            'acl': [
                {'member_id': '9999', 'value': str(ACLType.Writable)},
            ]
        }
        resp = self.client.post(reverse('acl:set'), json.dumps(params), 'application/json')

        self.assertEqual(resp.status_code, 400)
