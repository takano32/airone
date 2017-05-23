import json

from django.test import TestCase, Client
from django.urls import reverse
from user.models import User
from group.models import Group
from xml.etree import ElementTree


class ViewTest(TestCase):
    def setUp(self):
        self.client = Client()

    def test_index(self):
        resp = self.client.get(reverse('group:index'))
        self.assertEqual(resp.status_code, 200)

        root = ElementTree.fromstring(resp.content.decode('utf-8'))
        self.assertIsNone(root.find('.//table'))

    def test_index_with_objects(self):
        user = User(name='fuga', userid='puyo')
        user.save()
        group = Group(name='hoge')
        group.save()

        group.users.add(user)

        resp = self.client.get(reverse('group:index'))
        self.assertEqual(resp.status_code, 200)

        root = ElementTree.fromstring(resp.content.decode('utf-8'))
        self.assertIsNotNone(root.find('.//table'))
        self.assertEqual(len(root.findall('.//tr')), 2)

    def test_create_get(self):
        resp = self.client.get(reverse('group:create'))
        self.assertEqual(resp.status_code, 200)

        root = ElementTree.fromstring(resp.content.decode('utf-8'))
        self.assertIsNotNone(root.find('.//form'))

    def test_create_post(self):
        user1 = User(name='hgoe', userid='HOGE')
        user1.save()
        user2 = User(name='fuga', userid='FUGA')
        user2.save()

        params = {
            'name': 'test-group',
            'users': [user1.id, user2.id],
        }
        resp = self.client.post(reverse('group:create'),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 303)
        self.assertIsNotNone(Group.objects.first())
        self.assertEqual(Group.objects.first().name, 'test-group')

    def test_create_port_without_mandatory_params(self):
        params = {
            'name': 'test-group',
            'users': [],
        }
        resp = self.client.post(reverse('group:create'),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 400)
        self.assertIsNone(Group.objects.first())

    def test_create_port_with_invalid_params(self):
        params = {
            'name': 'test-group',
            'users': [1999, 2999],
        }
        resp = self.client.post(reverse('group:create'),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 400)
        self.assertIsNone(Group.objects.first())
