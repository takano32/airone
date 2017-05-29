import json

from django.test import TestCase, Client
from django.urls import reverse
from user.models import User
from xml.etree import ElementTree


class ViewTest(TestCase):
    def setUp(self):
        self.client = Client()

    def test_index(self):
        resp = self.client.get(reverse('user:index'))
        self.assertEqual(resp.status_code, 200)

        root = ElementTree.fromstring(resp.content.decode('utf-8'))
        self.assertIsNone(root.find('.//table'))

    def test_index_with_user(self):
        User(username='hoge').save()

        resp = self.client.get(reverse('user:index'))
        self.assertEqual(resp.status_code, 200)

        root = ElementTree.fromstring(resp.content.decode('utf-8'))
        self.assertIsNotNone(root.find('.//table'))
        self.assertEqual(len(root.findall('.//tr')), 2)

    def test_create_get(self):
        resp = self.client.get(reverse('user:create'))
        self.assertEqual(resp.status_code, 200)

        root = ElementTree.fromstring(resp.content.decode('utf-8'))
        self.assertIsNotNone(root.find('.//form'))

    def test_create_post(self):
        params = {
            'name': 'hoge',
            'email': 'hoge@fuga.com',
            'passwd': 'puyo',
        }
        resp = self.client.post(reverse('user:create'),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 200)
        self.assertIsNotNone(User.objects.first())
        self.assertEqual(User.objects.first().username, 'hoge')
