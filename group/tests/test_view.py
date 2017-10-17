import json, yaml

from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import Group

from user.models import User
from airone.lib.test import AironeViewTest

from xml.etree import ElementTree


class ViewTest(AironeViewTest):
    def test_index_without_login(self):
        resp = self.client.get(reverse('group:index'))
        self.assertEqual(resp.status_code, 303)

    def test_index(self):
        self.admin_login()

        resp = self.client.get(reverse('group:index'))
        self.assertEqual(resp.status_code, 200)

        root = ElementTree.fromstring(resp.content.decode('utf-8'))
        self.assertEqual(len(root.findall('.//tbody/tr')), 0,
                         "no group should be displayed at initial state")

    def test_index_with_objects(self):
        self.admin_login()

        user = self._create_user('fuga')
        group = self._create_group('hoge')

        user.groups.add(group)

        resp = self.client.get(reverse('group:index'))
        self.assertEqual(resp.status_code, 200)

        root = ElementTree.fromstring(resp.content.decode('utf-8'))
        self.assertEqual(len(root.findall('.//tbody/tr')), 1,
                         "1 group should be displayed after created")
        self.assertEqual(len(root.findall('.//tbody/tr/td/ul/li')), 1,
                         "1 user should be displayed after created")

    def test_index_with_inactive_user(self):
        self.admin_login()

        group = self._create_group('hoge')
        user1 = self._create_user('user1')
        user1.groups.add(group)
        user1.save()

        user2 = self._create_user('user2')
        user2.groups.add(group)
        user2.set_active(False)
        user2.save()
                
        resp = self.client.get(reverse('group:index'))
        self.assertEqual(resp.status_code, 200)

        root = ElementTree.fromstring(resp.content.decode('utf-8'))
        self.assertEqual(len(root.findall('.//tbody/tr/td/ul/li')), 1,
                         "1 active user should be displayed")
        
    def test_create_get(self):
        self.admin_login()

        resp = self.client.get(reverse('group:create'))
        self.assertEqual(resp.status_code, 200)

        root = ElementTree.fromstring(resp.content.decode('utf-8'))
        self.assertIsNotNone(root.find('.//form'))

    def test_create_post_without_login(self):
        resp = self.client.post(reverse('group:do_create'), json.dumps({}), 'application/json')
        self.assertEqual(resp.status_code, 401)

    def test_create_post(self):
        self.admin_login()

        group_count = self._get_group_count()
        
        user1 = self._create_user('hoge')
        user2 = self._create_user('fuga')

        params = {
            'name': 'test-group',
            'users': [user1.id, user2.id],
        }
        resp = self.client.post(reverse('group:do_create'),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 303)
        self.assertEqual(self._get_group_count(), group_count+1,
                         "group should be created after post")
        self.assertEqual(Group.objects.last().name, 'test-group',
                         "name of created group should be 'test-group'")

    def test_create_port_without_mandatory_params(self):
        self.admin_login()

        group_count = self._get_group_count()

        params = {
            'name': 'test-group',
            'users': [],
        }
        resp = self.client.post(reverse('group:do_create'),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 400)
        self.assertEqual(self._get_group_count(), group_count,
                         "group should not be created")

    def test_create_port_with_invalid_params(self):
        self.admin_login()

        group_count = self._get_group_count()

        params = {
            'name': 'test-group',
            'users': [1999, 2999],
        }
        resp = self.client.post(reverse('group:do_create'),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 400)
        self.assertEqual(self._get_group_count(), group_count,
                         "group should not be created")

    def test_create_duplicate_name_of_group(self):
        self.admin_login()

        duplicated_name = 'hoge'

        # create group in advance
        group = self._create_group(name=duplicated_name)
        user1 = self._create_user('hoge')
        user1.groups.add(group)

        group_count = self._get_group_count()

        # try to create group with same name
        params = {
            'name': duplicated_name,
            'users': [user1.id],
        }
        resp = self.client.post(reverse('group:do_create'),
                                json.dumps(params),
                                'application/json')
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(self._get_group_count(), group_count,
                         "group should not be created")

    def test_delete_group(self):
        self.admin_login()

        group1 = self._create_group("group1")
        group2 = self._create_group("group2")

        group_count = self._get_group_count()

        user1 = self._create_user("user1")
        user1.groups.add(group1)
        user1.groups.add(group2)

        user2 = self._create_user("user2")
        user2.groups.add(group1)

        params = {
            "name": "group1",
        }
        resp = self.client.post(reverse('group:do_delete'),
                                json.dumps(params),
                                'application/json')

        
        user1 = User.objects.get(username="user1")
        user2 = User.objects.get(username="user2")
        
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self._get_group_count(), group_count - 1,
                         "group should be decreased")
        self.assertEqual(Group.objects.filter(name="group1").count(), 0,
                         "group1 should not exist")
        self.assertEqual(Group.objects.filter(name="group2").count(), 1,
                         "group2 should exist")
        self.assertEqual(user1.groups.count(), 1,
                         "user1 should have 1 group")
        self.assertEqual(user2.groups.count(), 0,
                         "user2 should have 0 group")

    def test_export(self):
        self.admin_login()

        group1 = self._create_group("group1")
        group2 = self._create_group("group2")

        user1 = self._create_user("user1")
        user1.groups.add(group1)
        user1.groups.add(group2)

        user2 = self._create_user("user2")
        user2.groups.add(group1)

        resp = self.client.get(reverse('group:export'))
        self.assertEqual(resp.status_code, 200)

        obj = yaml.load(resp.content)
        self.assertTrue(isinstance(obj, dict))

        self.assertEqual(len(obj['User']), 3)
        self.assertEqual(len(obj['Group']), 2)

    def test_create_group_by_guest_user(self):
        user = self.guest_login()

        params = {
            'name': 'test-group',
            'users': [user.id],
        }
        resp = self.client.post(reverse('group:do_create'),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 400)
        self.assertEqual(Group.objects.filter(name='test-group').count(), 0)

    def test_delete_group_by_guest_user(self):
        user = self.guest_login()
        group = self._create_group("test-group")

        user.groups.add(group)

        params = {
            "name": "test-group",
        }
        resp = self.client.post(reverse('group:do_delete'),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 400)
        self.assertEqual(Group.objects.filter(name='test-group').count(), 1)
        self.assertTrue(user.groups.filter(name='test-group').count(), 1)
        
    # utility functions
    def _create_user(self, name):
        user = User(username=name)
        user.save()
        return user

    def _create_group(self, name):
        group = Group(name=name)
        group.save()
        return group

    def _get_user_count(self):
        return User.objects.count()

    def _get_active_user_count(self):
        return User.objects.filter(is_active=True).count()

    def _get_group_count(self):
        return Group.objects.count()
