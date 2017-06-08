import json

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
        self.assertIsNone(root.find('.//tbody/tr'))

    def test_index_with_objects(self):
        self.admin_login()

        user = User(username='fuga')
        user.save()
        group = Group(name='hoge')
        group.save()

        user.groups.add(group)

        resp = self.client.get(reverse('group:index'))
        self.assertEqual(resp.status_code, 200)

        root = ElementTree.fromstring(resp.content.decode('utf-8'))
        self.assertIsNotNone(root.find('.//tbody/tr'))
        self.assertEqual(len(root.findall('.//tbody/tr')), 1)

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

        user1 = User(username='hgoe')
        user1.save()
        user2 = User(username='fuga')
        user2.save()

        params = {
            'name': 'test-group',
            'users': [user1.id, user2.id],
        }
        resp = self.client.post(reverse('group:do_create'),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 303)
        self.assertIsNotNone(Group.objects.first())
        self.assertEqual(Group.objects.first().name, 'test-group')

    def test_create_port_without_mandatory_params(self):
        self.admin_login()

        params = {
            'name': 'test-group',
            'users': [],
        }
        resp = self.client.post(reverse('group:do_create'),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 400)
        self.assertIsNone(Group.objects.first())

    def test_create_port_with_invalid_params(self):
        self.admin_login()

        params = {
            'name': 'test-group',
            'users': [1999, 2999],
        }
        resp = self.client.post(reverse('group:do_create'),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 400)
        self.assertIsNone(Group.objects.first())

    def test_create_duplicate_name_of_group(self):
        user = self.admin_login()
        duplicated_name = 'hoge'

        # create Group object previously
        Group(name=duplicated_name).save()

        params = {
            'name': duplicated_name,
            'users': [user.id],
        }
        resp = self.client.post(reverse('group:do_create'),
                                json.dumps(params),
                                'application/json')
        self.assertEqual(resp.status_code, 400)
