import json

from django.test import TestCase, Client
from django.urls import reverse
from user.models import User
from xml.etree import ElementTree


class ViewTest(TestCase):
    def setUp(self):
        self._client = Client()
        self._create_user('admin')

    def _create_user(self, name):
        user = User(username=name)
        user.set_password(name)
        user.save()

    def _admin_login(self):
        self.client.login(username='admin', password='admin')

    def _get_active_user_count(self):
        return User.objects.filter(is_active=True).count()
        
    def test_index_without_login(self):
        resp = self.client.get(reverse('user:index'))
        self.assertEqual(resp.status_code, 303)

    def test_index_with_user(self):
        self._admin_login()

        resp = self.client.get(reverse('user:index'))
        self.assertEqual(resp.status_code, 200)

        root = ElementTree.fromstring(resp.content.decode('utf-8'))
        self.assertIsNotNone(root.find('.//table'))
        self.assertEqual(len(root.findall('.//tbody/tr')), self._get_active_user_count())

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
        count = User.objects.count()
        
        params = {
            'name': 'hoge',
            'email': 'hoge@fuga.com',
            'passwd': 'puyo',
        }
        resp = self.client.post(reverse('user:do_create'),
                                json.dumps(params),
                                'application/json')
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(User.objects.count(), count) # user should not be created

    def test_create_post_with_login(self):
        count = User.objects.count()
        self._admin_login()

        params = {
            'name': 'hoge',
            'email': 'hoge@fuga.com',
            'passwd': 'puyo',
        }
        resp = self.client.post(reverse('user:do_create'),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(User.objects.count(), count+1) # user should be created
        self.assertEqual(User.objects.last().username, 'hoge')
        self.assertNotEqual(User.objects.last().password, 'puyo')

    def test_create_user_without_mandatory_param(self):
        count = User.objects.count()
        self._admin_login()

        params = {
            'email': 'hoge@fuga.com',
            'passwd': 'puyo',
        }
        resp = self.client.post(reverse('user:do_create'),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 400)
        self.assertEqual(User.objects.count(), count) # user should not be created

    def test_create_user_with_empty_param(self):
        count = User.objects.count()
        self._admin_login()

        params = {
            'user': 'hoge',
            'email': '',
            'passwd': 'puyo',
        }
        resp = self.client.post(reverse('user:do_create'),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 400)
        self.assertEqual(User.objects.count(), count) # user should be created

    def test_delete_post(self):
        name = "someuser"
        
        self._admin_login()

        self._create_user(name)
        user_count = User.objects.count()
        active_user_count = self._get_active_user_count()

        params = {
            'name': name
        }
        resp = self.client.post(reverse('user:do_delete'),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 200)
        # user should not deleted from DB
        self.assertEqual(User.objects.count(), user_count) 
        # active user should be decreased
        self.assertEqual(self._get_active_user_count(), active_user_count-1)

        # username should be "__deleted__" + name
        user = User.objects.get(username="__deleted__"+name)
        self.assertTrue(isinstance(user, User))
        # user should be inactive
        self.assertFalse(user.is_active)
