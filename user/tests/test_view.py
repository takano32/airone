import json

from django.test import TestCase, Client
from django.urls import reverse
from user.models import User
from xml.etree import ElementTree


class ViewTest(TestCase):
    def setUp(self):
        self.client = Client()

    def _admin_login(self):
        user = User(username='admin')
        user.set_password('admin')
        user.save()

        self.client.login(username='admin', password='admin')

    def test_index_without_login(self):
        resp = self.client.get(reverse('user:index'))
        self.assertEqual(resp.status_code, 303)

    def test_index_with_user(self):
        self._admin_login()

        resp = self.client.get(reverse('user:index'))
        self.assertEqual(resp.status_code, 200)

        root = ElementTree.fromstring(resp.content.decode('utf-8'))
        self.assertIsNotNone(root.find('.//table'))
        self.assertEqual(len(root.findall('.//tr')), 2)

    def test_create_get_without_login(self):
        resp = self.client.get(reverse('user:create'))
        self.assertEqual(resp.status_code, 303)

    def test_create_get_with_login(self):
        self._admin_login()

        resp = self.client.get(reverse('user:create'))
        self.assertEqual(resp.status_code, 200)

        root = ElementTree.fromstring(resp.content.decode('utf-8'))
        self.assertIsNotNone(root.find('.//form'))

    def test_create_post_without_login(self):
        params = {
            'name': 'hoge',
            'email': 'hoge@fuga.com',
            'passwd': 'puyo',
        }
        resp = self.client.post(reverse('user:create'),
                                json.dumps(params),
                                'application/json')
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(User.objects.count(), 0)

    def test_create_post_with_login(self):
        self._admin_login()

        params = {
            'name': 'hoge',
            'email': 'hoge@fuga.com',
            'passwd': 'puyo',
        }
        resp = self.client.post(reverse('user:create'),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(User.objects.count(), 2)
        self.assertEqual(User.objects.last().username, 'hoge')
        self.assertNotEqual(User.objects.last().password, 'puyo')

    def test_create_user_without_mandatory_param(self):
        self._admin_login()

        params = {
            'email': 'hoge@fuga.com',
            'passwd': 'puyo',
        }
        resp = self.client.post(reverse('user:create'),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 400)
        self.assertEqual(User.objects.count(), 1)

    def test_create_user_with_empty_param(self):
        self._admin_login()

        params = {
            'user': 'hoge',
            'email': '',
            'passwd': 'puyo',
        }
        resp = self.client.post(reverse('user:create'),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 400)
        self.assertEqual(User.objects.count(), 1)
