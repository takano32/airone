import json
import yaml
import mock
import re

from django.test import TestCase, Client
from django.urls import reverse
from entity.models import Entity, AttributeBase
from entry.models import Entry, Attribute
from user.models import User
from xml.etree import ElementTree
from airone.lib.test import AironeViewTest
from airone.lib.types import AttrTypeStr, AttrTypeObj
from airone.lib.acl import ACLType
from django.contrib.auth.models import Permission


class ViewTest(AironeViewTest):
    def test_index_without_login(self):
        resp = self.client.get(reverse('entity:index'))
        self.assertEqual(resp.status_code, 303)

    def test_index(self):
        self.admin_login()

        resp = self.client.get(reverse('entity:index'))
        self.assertEqual(resp.status_code, 200)

        root = ElementTree.fromstring(resp.content.decode('utf-8'))
        self.assertIsNone(root.find('.//tbody/tr'))

    def test_index_with_objects(self):
        user = self.admin_login()

        entity = Entity(name='test-entity', created_user=user)
        entity.save()

        resp = self.client.get(reverse('entity:index'))
        self.assertEqual(resp.status_code, 200)

        root = ElementTree.fromstring(resp.content.decode('utf-8'))
        self.assertIsNotNone(root.find('.//tbody/tr'))
        self.assertEqual(len(root.findall('.//tbody/tr')), 1)

    def test_create_get(self):
        self.admin_login()

        resp = self.client.get(reverse('entity:create'))
        self.assertEqual(resp.status_code, 200)

        root = ElementTree.fromstring(resp.content.decode('utf-8'))
        self.assertIsNotNone(root.find('.//form'))

    def test_create_post_without_login(self):
        resp = self.client.post(reverse('entity:do_create'), json.dumps({}), 'application/json')
        self.assertEqual(resp.status_code, 401)

    def test_create_post(self):
        self.admin_login()

        params = {
            'name': 'hoge',
            'note': 'fuga',
            'attrs': [
                {'name': 'foo', 'type': str(AttrTypeStr), 'is_mandatory': True},
                {'name': 'bar', 'type': str(AttrTypeStr), 'is_mandatory': False},
            ],
        }
        resp = self.client.post(reverse('entity:do_create'),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 303)
        self.assertEqual(Entity.objects.first().name, 'hoge')
        self.assertEqual(len(AttributeBase.objects.all()), 2)

    def test_create_post_without_name_param(self):
        self.admin_login()

        params = {
            'note': 'fuga',
            'attrs': [
                {'name': 'foo', 'type': str(AttrTypeStr), 'is_mandatory': True},
                {'name': 'bar', 'type': str(AttrTypeStr), 'is_mandatory': False},
            ],
        }
        resp = self.client.post(reverse('entity:do_create'),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 400)
        self.assertIsNone(Entity.objects.first())

    def test_create_post_with_invalid_attrs(self):
        self.admin_login()

        params = {
            'name': 'hoge',
            'note': 'fuga',
            'attrs': [
                {'name': 'foo', 'type': str(AttrTypeStr), 'is_mandatory': True},
                {'name': '', 'type': str(AttrTypeStr), 'is_mandatory': True},
            ],
        }
        resp = self.client.post(reverse('entity:do_create'),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 400)
        self.assertIsNone(Entity.objects.first())

    def test_create_port_with_invalid_params(self):
        self.admin_login()

        params = {
            'name': 'hoge',
            'note': 'fuga',
            'attrs': 'puyo',
        }
        resp = self.client.post(reverse('entity:do_create'),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 400)
        self.assertIsNone(Entity.objects.first())

    def test_get_edit_without_login(self):
        resp = self.client.get(reverse('entity:edit', args=[0]))
        self.assertEqual(resp.status_code, 303)

    def test_get_edit_with_invalid_entity_id(self):
        self.admin_login()

        resp = self.client.get(reverse('entity:edit', args=[999]))
        self.assertEqual(resp.status_code, 400)

    def test_get_edit_with_valid_entity_id(self):
        user = self.admin_login()
        entity = Entity.objects.create(name='hoge', created_user=user)

        resp = self.client.get(reverse('entity:edit', args=[entity.id]))
        self.assertEqual(resp.status_code, 200)

        root = ElementTree.fromstring(resp.content.decode('utf-8'))
        self.assertIsNotNone(root.find('.//tr/td/select'))

    def test_post_edit_without_login(self):
        resp = self.client.post(reverse('entity:do_edit', args=[0]), '{}', 'application/json')
        self.assertEqual(resp.status_code, 401)

    def test_post_edit_with_invalid_params(self):
        self.admin_login()

        params = {
            'name': 'hoge',
            'note': 'fuga',
            'attrs': [
                {'name': 'foo', 'type': str(AttrTypeStr), 'is_mandatory': True},
            ],
        }
        resp = self.client.post(reverse('entity:do_edit', args=[999]),
                                json.dumps(params),
                                'application/json')
        self.assertEqual(resp.status_code, 400)

    def test_post_edit_with_valid_params(self):
        user = self.admin_login()

        entity = Entity.objects.create(name='hoge', note='fuga', created_user=user)
        attr = AttributeBase.objects.create(name='puyo',
                                            created_user=user,
                                            is_mandatory=True,
                                            type=AttrTypeStr,
                                            parent_entity=entity)
        entity.attr_bases.add(attr)

        params = {
            'name': 'foo',
            'note': 'bar',
            'attrs': [
                {'name': 'foo', 'type': str(AttrTypeStr), 'is_mandatory': True, 'id': attr.id},
                {'name': 'bar', 'type': str(AttrTypeStr), 'is_mandatory': True},
            ],
        }
        resp = self.client.post(reverse('entity:do_edit', args=[entity.id]),
                                json.dumps(params),
                                'application/json')
        self.assertEqual(resp.status_code, 303)
        self.assertEqual(Entity.objects.get(id=entity.id).name, 'foo')
        self.assertEqual(Entity.objects.get(id=entity.id).note, 'bar')
        self.assertEqual(Entity.objects.get(id=entity.id).attr_bases.count(), 2)
        self.assertEqual(Entity.objects.get(id=entity.id).attr_bases.get(id=attr.id).name, 'foo')
        self.assertEqual(Entity.objects.get(id=entity.id).attr_bases.last().name, 'bar')

    def test_post_edit_after_creating_entry(self):
        user = self.admin_login()

        entity = Entity.objects.create(name='hoge', note='fuga', created_user=user)
        attrbase = AttributeBase.objects.create(name='puyo',
                                                created_user=user,
                                                is_mandatory=True,
                                                type=AttrTypeStr,
                                                parent_entity=entity)
        entity.attr_bases.add(attrbase)

        entry = Entry.objects.create(name='entry', schema=entity, created_user=user)
        entry.add_attribute_from_base(attrbase, user)

        params = {
            'name': 'foo',
            'note': 'bar',
            'attrs': [
                {'name': 'foo', 'type': str(AttrTypeStr), 'is_mandatory': True, 'id': attrbase.id},
                {'name': 'bar', 'type': str(AttrTypeStr), 'is_mandatory': True},
            ],
        }
        resp = self.client.post(reverse('entity:do_edit', args=[entity.id]),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 303)
        self.assertEqual(Entry.objects.get(id=entry.id).attrs.count(), 2)

    def test_post_edit_string_attribute(self):
        user = self.admin_login()

        entity = Entity.objects.create(name='hoge', note='fuga', created_user=user)
        attr = AttributeBase.objects.create(name='puyo',
                                            type=AttrTypeStr,
                                            created_user=user,
                                            parent_entity=entity)
        entity.attr_bases.add(attr)

        params = {
            'name': 'foo',
            'note': 'bar',
            'attrs': [{
                'name': 'baz',
                'type': str(AttrTypeObj),
                'ref_id': entity.id,
                'is_mandatory': True,
                'id': attr.id
            }],
        }
        resp = self.client.post(reverse('entity:do_edit', args=[entity.id]),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 303)
        self.assertEqual(AttributeBase.objects.get(id=attr.id).type, AttrTypeObj)
        self.assertEqual(AttributeBase.objects.get(id=attr.id).referral.id, entity.id)

    def test_post_edit_referral_attribute(self):
        user = self.admin_login()

        entity = Entity.objects.create(name='hoge', note='fuga', created_user=user)
        attrbase = AttributeBase.objects.create(name='puyo',
                                                type=AttrTypeObj,
                                                referral=entity,
                                                created_user=user,
                                                parent_entity=entity)
        entity.attr_bases.add(attrbase)

        entry = Entry.objects.create(name='entry', schema=entity, created_user=user)
        attr = entry.add_attribute_from_base(attrbase, user)

        params = {
            'name': 'foo',
            'note': 'bar',
            'attrs': [{
                'name': 'baz',
                'type': str(AttrTypeStr),
                'is_mandatory': True,
                'id': attrbase.id
            }],
        }
        resp = self.client.post(reverse('entity:do_edit', args=[entity.id]),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 303)
        self.assertEqual(AttributeBase.objects.get(id=attrbase.id).type, AttrTypeStr)
        self.assertIsNone(AttributeBase.objects.get(id=attrbase.id).referral)

        # checks that the related Attribute is also changed
        self.assertEqual(Attribute.objects.get(id=attr.id).name, 'baz')
        self.assertEqual(Attribute.objects.get(id=attr.id).type, AttrTypeStr)
        self.assertTrue(Attribute.objects.get(id=attr.id).is_mandatory)
        self.assertIsNone(Attribute.objects.get(id=attr.id).referral)

    def test_post_create_with_invalid_referral_attr(self):
        self.admin_login()

        params = {
            'name': 'hoge',
            'note': 'fuga',
            'attrs': [
                {'name': 'a', 'type': str(AttrTypeObj), 'is_mandatory': False},
            ],
        }
        resp = self.client.post(reverse('entity:do_create'),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 400)

    def test_post_create_with_valid_referral_attr(self):
        user = self.admin_login()

        entity = Entity(name='test-entity', created_user=user)
        entity.save()

        params = {
            'name': 'hoge',
            'note': 'fuga',
            'attrs': [
                {'name': 'a', 'type': str(AttrTypeObj), 'ref_id': entity.id, 'is_mandatory': False},
            ],
        }
        resp = self.client.post(reverse('entity:do_create'),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 303)
        self.assertEqual(Entity.objects.last().name, 'hoge')
        self.assertEqual(AttributeBase.objects.last().name, 'a')
        self.assertIsNotNone(AttributeBase.objects.last().referral)
        self.assertEqual(AttributeBase.objects.last().referral.id, entity.id)

    def test_post_edit_delete_attribute(self):
        user = self.admin_login()

        entity = Entity.objects.create(name='entity', created_user=user)
        for name in ['foo', 'bar']:
            entity.attr_bases.add(AttributeBase.objects.create(name=name,
                                                               type=AttrTypeStr,
                                                               created_user=user,
                                                               parent_entity=entity))

        entry = Entry.objects.create(name='entry', schema=entity, created_user=user)
        [entry.add_attribute_from_base(x, user) for x in entity.attr_bases.all()]

        permission_count = Permission.objects.count()
        params = {
            'name': 'new-entity',
            'note': 'hoge',
            'attrs': [
                {'name': 'foo', 'type': str(AttrTypeStr), 'id': entity.attr_bases.first().id,
                 'is_mandatory': False},
                {'name': 'bar', 'type': str(AttrTypeStr), 'id': entity.attr_bases.last().id,
                 'is_mandatory': False, 'deleted': True},
            ],
        }
        resp = self.client.post(reverse('entity:do_edit', args=[entity.id]),
                                json.dumps(params), 'application/json')

        self.assertEqual(resp.status_code, 303)
        self.assertEqual(Permission.objects.count(),
                         permission_count - len(ACLType.availables()) * 2)
        self.assertEqual(entity.attr_bases.count(), 1)
        self.assertEqual(entry.attrs.count(), 1)
        self.assertEqual(entity.attr_bases.last().name, 'foo')
        self.assertEqual(entry.attrs.last().name, 'foo')

    def test_export_data(self):
        user = self.admin_login()

        entity1 = Entity.objects.create(name='entity1', note='hoge', created_user=user)
        for name in ['foo', 'bar']:
            entity1.attr_bases.add(AttributeBase.objects.create(name=name,
                                                                type=AttrTypeStr,
                                                                created_user=user,
                                                                parent_entity=entity1))

        entity2 = Entity.objects.create(name='entity2', created_user=user)
        entity2.attr_bases.add(AttributeBase.objects.create(name='attr',
                                                            type=AttrTypeObj,
                                                            referral=entity1,
                                                            created_user=user,
                                                            parent_entity=entity2))

        resp = self.client.get(reverse('entity:export'))
        self.assertEqual(resp.status_code, 200)

        obj = yaml.load(resp.content)
        self.assertTrue(isinstance(obj, dict))
        self.assertEqual(sorted(obj.keys()), ['AttributeBase', 'Entity'])
        self.assertEqual(len(obj['AttributeBase']), 3)
        self.assertEqual(len(obj['Entity']), 2)
        self.assertTrue(list(filter(lambda x: (
                x['name'] == 'foo' and
                x['entity'] == 'entity1' and
                x['type'] == AttrTypeStr and
                x['refer'] == ''
            ), obj['AttributeBase'])))
        self.assertTrue(list(filter(lambda x: (
                x['name'] == 'attr' and
                x['entity'] == 'entity2' and
                x['type'] == AttrTypeObj and
                x['refer'] == 'entity1'
            ), obj['AttributeBase'])))
        self.assertTrue(list(filter(lambda x: (
                x['name'] == 'entity1' and
                x['note'] == 'hoge' and
                x['created_user'] == 'admin'
            ), obj['Entity'])))

    def test_export_with_unpermitted_object(self):
        user = self.admin_login()
        user2 = User.objects.create(username='user2')

        # create an entity object which is created by logined-user
        entity1 = Entity.objects.create(name='entity1', created_user=user)
        entity1.attr_bases.add(AttributeBase.objects.create(name='attr1',
                                                            type=AttrTypeStr,
                                                            created_user=user,
                                                            parent_entity=entity1))

        # create a public object which is created by the another_user
        entity2 = Entity.objects.create(name='entity2', created_user=user2)
        entity2.attr_bases.add(AttributeBase.objects.create(name='attr2',
                                                            type=AttrTypeStr,
                                                            created_user=user2,
                                                            parent_entity=entity1))

        # create private objects which is created by the another_user
        for name in ['foo', 'bar']:
            e = Entity.objects.create(name=name, created_user=user2, is_public=False)
            e.attr_bases.add(AttributeBase.objects.create(name='private_attr',
                                                          type=AttrTypeStr,
                                                          created_user=user2,
                                                          parent_entity=e,
                                                          is_public=False))

        resp = self.client.get(reverse('entity:export'))
        self.assertEqual(resp.status_code, 200)

        obj = yaml.load(resp.content)
        self.assertEqual(len(obj['Entity']), 2)
        self.assertEqual(len(obj['AttributeBase']), 2)
        self.assertTrue([x for x in obj['Entity'] if x['name'] == entity1.name])
        self.assertTrue([x for x in obj['Entity'] if x['name'] == entity2.name])
        self.assertFalse([x for x in obj['AttributeBase'] if x['name'] == 'private_attr'])

    def test_import(self):
        user = self.admin_login()

        fp = self.open_fixture_file('entity.yaml')
        resp = self.client.post(reverse('entity:do_import'), {'file': fp})
        self.assertEqual(resp.status_code, 303)
        fp.close()

        self.assertEqual(Entity.objects.count(), 3)
        self.assertEqual(Entity.objects.get(name='foo').id, 1)
        self.assertEqual(AttributeBase.objects.last().name, 'attr5')
        self.assertEqual(Entity.objects.get(name='foo').attr_bases.count(), 3)

    def test_import_with_unnecessary_param(self):
        user = self.admin_login()
        warning_messages = []

        fp = self.open_fixture_file('entity_with_unnecessary_param.yaml')
        with mock.patch('entity.views.Logger') as lg_mock:
            def side_effect(message):
                warning_messages.append(message)

            lg_mock.warning = mock.Mock(side_effect=side_effect)

            resp = self.client.post(reverse('entity:do_import'), {'file': fp})
            self.assertEqual(resp.status_code, 303)
        fp.close()

        # checks that warning messagees were outputted
        self.assertEqual(len(warning_messages), 2)
        self.assertTrue(re.match(r'^.*Entity.*Unnecessary key is specified$',
                                 warning_messages[0]))
        self.assertTrue(re.match(r'^.*AttributeBase.*Unnecessary key is specified$',
                                 warning_messages[1]))

        self.assertEqual(Entity.objects.count(), 1)
        self.assertEqual(AttributeBase.objects.count(), 2)

    def test_import_without_mandatory_param(self):
        user = self.admin_login()
        warning_messages = []

        fp = self.open_fixture_file('entity_without_mandatory_param.yaml')
        with mock.patch('entity.views.Logger') as lg_mock:
            def side_effect(message):
                warning_messages.append(message)

            lg_mock.warning = mock.Mock(side_effect=side_effect)

            resp = self.client.post(reverse('entity:do_import'), {'file': fp})
            self.assertEqual(resp.status_code, 303)
        fp.close()

        # checks that warning messagees were outputted
        self.assertEqual(len(warning_messages), 2)
        self.assertTrue(re.match(r"^.*Entity.*Mandatory key doesn't exist$",
                                 warning_messages[0]))
        self.assertTrue(re.match(r"^.*AttributeBase.*Mandatory key doesn't exist$",
                                 warning_messages[1]))

        self.assertEqual(Entity.objects.count(), 1)
        self.assertEqual(AttributeBase.objects.count(), 2)
