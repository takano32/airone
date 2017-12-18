import json

from django.test import TestCase, Client
from django.urls import reverse
from user.models import User
from xml.etree import ElementTree


class ViewTest(TestCase):
    def setUp(self):
        self._client = Client()
        self._create_user('guest', 'guest@guest.com')
        self._create_user('admin', 'admin@admin.com', True)

    def _create_user(self, name, email='email', is_superuser=False):
        user = User(username=name, email=email, is_superuser=is_superuser)
        user.set_password(name)
        user.save()

    def _admin_login(self):
        self.client.login(username='admin', password='admin')

    def _guest_login(self):
        self.client.login(username='guest', password='guest')

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
        self.assertFalse(User.objects.last().is_superuser)

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

    def test_edit_get_without_login(self):
        resp = self.client.get(reverse('user:edit', args=[0]))
        self.assertEqual(resp.status_code, 303)

    def test_edit_get_with_login(self):
        self._admin_login()

        user = User.objects.get(username='guest')
        resp = self.client.get(reverse('user:edit', args=[user.id]))
        self.assertEqual(resp.status_code, 200)

        root = ElementTree.fromstring(resp.content.decode('utf-8'))
        self.assertIsNotNone(root.find('.//form'))

    def test_edit_post_without_login(self):

        params = {
            'id':    int(1), # guest user id
            'name':  'hoge', # update guest => hoge
            'email': 'hoge@hoge.com',
            'is_superuser': True,
        }
        resp = self.client.post(reverse('user:do_edit',args=[params['id']]),
                                json.dumps(params), 'application/json')
        self.assertEqual(resp.status_code, 401)

    def test_edit_post_with_login(self):
        self._admin_login()
        count = User.objects.count()

        params = {
            'id':    int(1), # guest user id
            'name':  'hoge', # update guest => hoge
            'email': 'hoge@hoge.com',
            'is_superuser': True,
        }
        resp = self.client.post(reverse('user:do_edit',args=[params['id']]),
                                json.dumps(params),'application/json')
        user = User.objects.get(id=params['id'])
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(User.objects.count(), count) # user should be updated
        self.assertEqual(user.username, params['name'])
        self.assertEqual(user.email, params['email'])
        self.assertTrue(user.is_superuser)

    def test_edit_user_with_duplicated_name(self):
        self._admin_login()

        params = {
            'id':   int(1),           # guest user id
            'name': 'admin',          # duplicated
            'email':'guest@guest.com',
        }
        resp = self.client.post(reverse('user:do_edit',args=[params['id']]),
                                json.dumps(params),'application/json')
        user = User.objects.get(id=params['id'])
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(user.username, 'guest') # Not updated

    def test_edit_user_with_duplicated_email(self):
        self._admin_login()
        # create test user
        self._create_user('hoge', 'hoge@hoge.com')

        params = {
            'id':   int(1),          # guest user id
            'name': 'guest',
            'email':'hoge@hoge.com', # duplicated
        }
        resp = self.client.post(reverse('user:do_edit',args=[params['id']]),
                                json.dumps(params),'application/json')
        new_user = User.objects.get(id=params['id'])
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(new_user.username, params['name'])
        self.assertNotEqual(new_user.email, params['email'])

    def test_edit_user_into_superuser(self):
        self._admin_login()
        # create test user
        self._create_user('hoge', 'hoge@hoge.com')

        params = {
            'id':   int(3), # test user id
            'name': 'hoge',
            'email':'hoge@hoge.com',
            'is_superuser':True,
        }
        resp = self.client.post(reverse('user:do_edit',args=[params['id']]),
                                json.dumps(params),'application/json')
        new_user = User.objects.get(id=params['id'])
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(new_user.username, params['name'])
        self.assertEqual(new_user.email, params['email'])
        self.assertTrue(new_user.is_superuser)

    def test_edit_superuser_into_user(self):
        self._admin_login()

        # create test user
        self._create_user('hoge', 'hoge@hoge.com', True)

        params = {
            'id':int(3), # test user id
            'name': 'hoge',
            'email':'hoge@hoge.com',
            # If is_superuser doesn't exist, it becomes False
        }
        resp = self.client.post(reverse('user:do_edit',args=[params['id']]),
                                json.dumps(params),'application/json')
        new_user = User.objects.get(id=params['id'])
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(new_user.username, params['name'])
        self.assertEqual(new_user.email, params['email'])
        self.assertFalse(new_user.is_superuser)

    def test_edit_passwd_get_without_login(self):
        resp = self.client.get(reverse('user:edit_passwd', args=[0]))
        self.assertEqual(resp.status_code, 303)

    def test_edit_passwd_get_with_login(self):
        self._admin_login()

        user = User.objects.get(username='guest')
        resp = self.client.get(reverse('user:edit_passwd', args=[user.id]))
        self.assertEqual(resp.status_code, 200)

        root = ElementTree.fromstring(resp.content.decode('utf-8'))
        self.assertIsNotNone(root.find('.//form'))

    def test_edit_passwd_post_without_login(self):

        params = {
            'id':int(1), # guest user id
            'old_passwd':'guest',
            'new_passwd':'hoge',
            'chk_passwd':'hoge',
        }
        resp = self.client.post(reverse('user:do_edit_passwd',args=[params['id']]),
                                json.dumps(params), 'application/json')
        self.assertEqual(resp.status_code, 401)

    def test_edit_passwd_post_with_login(self):
        self._admin_login()
        count = User.objects.count()

        params = {
            'id':int(1), # guest user id
            'old_passwd':'guest',
            'new_passwd':'hoge',
            'chk_passwd':'hoge',
        }
        resp = self.client.post(reverse('user:do_edit_passwd',args=[params['id']]),
                                json.dumps(params),'application/json')
        user = User.objects.get(id=params['id'])
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(User.objects.count(), count) # user should be updated
        self.assertTrue(user.check_password(params['new_passwd']))

    def test_edit_passwd_with_empty_pass(self):
        self._admin_login()

        params = {
            'id':int(1),# guest user id
            'old_passwd':'guest',
            'new_passwd':'',
            'chk_passwd':'hoge',
        }
        resp = self.client.post(reverse('user:do_edit_passwd',args=[params['id']]),
                                json.dumps(params),'application/json')
        user = User.objects.get(id=params['id'])
        self.assertEqual(resp.status_code, 400)
        self.assertTrue(user.check_password('guest')) # Not updated

    def test_edit_passwd_with_wrong_old_pass(self):
        self._admin_login()

        params = {
            'id':int(1),# guest user id
            'old_passwd':'hoge',
            'new_passwd':'hoge',
            'chk_passwd':'hoge',
        }
        resp = self.client.post(reverse('user:do_edit_passwd',args=[params['id']]),
                                json.dumps(params),'application/json')
        user = User.objects.get(id=params['id'])
        self.assertEqual(resp.status_code, 400)
        self.assertTrue(user.check_password('guest')) # Not updated

    def test_edit_passwd_with_new_and_old_pass_duplicated(self):
        self._admin_login()

        params = {
            'id':int(1),# guest user id
            'old_passwd':'guest',
            'new_passwd':'guest',
            'chk_passwd':'guest',
        }
        resp = self.client.post(reverse('user:do_edit_passwd',args=[params['id']]),
                                json.dumps(params),'application/json')
        user = User.objects.get(id=params['id'])
        self.assertEqual(resp.status_code, 400)

    def test_edit_passwd_with_new_and_chk_pass_not_equal(self):
        self._admin_login()

        params = {
            'id':int(1),# guest user id
            'old_passwd':'guest',
            'new_passwd':'hoge',
            'chk_passwd':'fuga',
        }
        resp = self.client.post(reverse('user:do_edit_passwd',args=[params['id']]),
                                json.dumps(params),'application/json')
        user = User.objects.get(id=params['id'])
        self.assertEqual(resp.status_code, 400)
        self.assertTrue(user.check_password('guest')) # Not updated

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

        # user should be inactive
        user = User.objects.get(username__icontains="%s_deleted_" % name)
        self.assertFalse(user.is_active)

    def test_create_user_by_guest_user(self):
        self._guest_login()

        params = {
            'name': 'hoge',
            'email': 'hoge@fuga.com',
            'passwd': 'puyo',
        }
        resp = self.client.post(reverse('user:do_create'),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 400)

    def test_create_admin_user(self):
        self._admin_login()

        params = {
            'name': 'hoge',
            'email': 'hoge@fuga.com',
            'passwd': 'puyo',
            'is_superuser': 'on',
        }
        resp = self.client.post(reverse('user:do_create'),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(User.objects.last().is_superuser)

    def test_delete_post_by_guest_user(self):
        self._guest_login()

        self._create_user('testuser')
        user_count = User.objects.count()
        active_user_count = self._get_active_user_count()

        params = {
            'name': 'testuser'
        }
        resp = self.client.post(reverse('user:do_delete'),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 400)
        self.assertTrue(User.objects.get(username='testuser').is_active)
