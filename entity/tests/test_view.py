import json

from django.test import TestCase, Client
from django.urls import reverse
from entity.models import Entity, AttributeBase
from xml.etree import ElementTree


class ViewTest(TestCase):
    def setUp(self):
        self.client = Client()

    def test_index(self):
        resp = self.client.get(reverse('entity:index'))
        self.assertEqual(resp.status_code, 200)

        root = ElementTree.fromstring(resp.content.decode('utf-8'))
        self.assertIsNone(root.find('.//table'))

    def test_index_with_objects(self):
        entity = Entity(name='test-entity')
        entity.save()

        resp = self.client.get(reverse('entity:index'))
        self.assertEqual(resp.status_code, 200)

        root = ElementTree.fromstring(resp.content.decode('utf-8'))
        self.assertIsNotNone(root.find('.//table'))
        self.assertEqual(len(root.findall('.//table/tr')), 2)

    def test_create_get(self):
        resp = self.client.get(reverse('entity:create'))
        self.assertEqual(resp.status_code, 200)

        root = ElementTree.fromstring(resp.content.decode('utf-8'))
        self.assertIsNotNone(root.find('.//form'))

    def test_create_post(self):
        params = {
            'name': 'hoge',
            'note': 'fuga',
            'attrs': [
                {'name': 'foo', 'type': 1, 'is_mandatory': True},
                {'name': 'bar', 'type': 2, 'is_mandatory': False},
            ],
        }
        resp = self.client.post(reverse('entity:create'),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 303)
        self.assertEqual(Entity.objects.first().name, 'hoge')
        self.assertEqual(len(AttributeBase.objects.all()), 2)

    def test_create_post_without_name_param(self):
        params = {
            'note': 'fuga',
            'attrs': [
                {'name': 'foo', 'type': 1, 'is_mandatory': True},
                {'name': 'bar', 'type': 2, 'is_mandatory': False},
            ],
        }
        resp = self.client.post(reverse('entity:create'),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 400)
        self.assertIsNone(Entity.objects.first())

    def test_create_post_with_invalid_attrs(self):
        params = {
            'name': 'hoge',
            'note': 'fuga',
            'attrs': [
                {'name': 'foo', 'type': 1, 'is_mandatory': True},
                {'name': '', 'type': 1, 'is_mandatory': True},
            ],
        }
        resp = self.client.post(reverse('entity:create'),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 400)
        self.assertIsNone(Entity.objects.first())

    def test_create_port_with_invalid_params(self):
        params = {
            'name': 'hoge',
            'note': 'fuga',
            'attrs': 'puyo',
        }
        resp = self.client.post(reverse('entity:create'),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 400)
        self.assertIsNone(Entity.objects.first())
