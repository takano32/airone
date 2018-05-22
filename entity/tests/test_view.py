import json
import yaml
import mock
import re

from django.test import TestCase, Client
from django.urls import reverse
from entity.models import Entity, EntityAttr
from entry.models import Entry, Attribute
from user.models import User, History
from xml.etree import ElementTree
from airone.lib.test import AironeViewTest
from airone.lib.types import AttrTypeStr, AttrTypeObj, AttrTypeText
from airone.lib.types import AttrTypeArrStr, AttrTypeArrObj
from airone.lib.types import AttrTypeValue
from airone.lib.acl import ACLType
from django.contrib.auth.models import Permission


class ViewTest(AironeViewTest):
    """
    This has simple tests that check basic functionality
    """

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
            'is_toplevel': True,
            'attrs': [
                {'name': 'foo', 'type': str(AttrTypeStr), 'is_mandatory': True, 'row_index': '1'},
                {'name': 'bar', 'type': str(AttrTypeText), 'is_mandatory': True, 'row_index': '2'},
                {'name': 'baz', 'type': str(AttrTypeArrStr), 'is_mandatory': False, 'row_index': '3'},
                {'name': 'attr_bool', 'type': str(AttrTypeValue['boolean']), 'is_mandatory': False, 'row_index': '4'},
                {'name': 'attr_group', 'type': str(AttrTypeValue['group']), 'is_mandatory': False, 'row_index': '5'},
                {'name': 'attr_date', 'type': str(AttrTypeValue['date']), 'is_mandatory': False, 'row_index': '6'},
            ],
        }
        resp = self.client.post(reverse('entity:do_create'),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 200)

        # tests for Entity object
        entity = Entity.objects.first()
        self.assertEqual(entity.name, 'hoge')
        self.assertTrue(entity.status & Entity.STATUS_TOP_LEVEL)

        # tests for EntityAttribute objects
        self.assertEqual(len(EntityAttr.objects.all()), 6)

        # tests for operation history is registered correctly
        self.assertEqual(History.objects.count(), 7)
        self.assertEqual(History.objects.filter(operation=History.ADD_ENTITY).count(), 1)
        self.assertEqual(History.objects.filter(operation=History.ADD_ATTR).count(), 6)

    def test_create_post_without_name_param(self):
        self.admin_login()

        params = {
            'note': 'fuga',
            'is_toplevel': False,
            'attrs': [
                {'name': 'foo', 'type': str(AttrTypeStr), 'is_mandatory': True, 'row_index': '1'},
                {'name': 'bar', 'type': str(AttrTypeStr), 'is_mandatory': False, 'row_index': '2'},
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
            'is_toplevel': False,
            'attrs': [
                {'name': '', 'type': str(AttrTypeStr), 'is_mandatory': True, 'row_index': '1'},
            ],
        }
        resp = self.client.post(reverse('entity:do_create'),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 400)

        params = {
            'name': 'hoge',
            'note': 'fuga',
            'is_toplevel': False,
            'attrs': [
                {'name': 'foo', 'type': str(AttrTypeStr), 'is_mandatory': True, 'row_index': 'abcd'},
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
            'is_toplevel': False,
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
        self.assertIsNotNone(root.find('.//tr/td/div/div/select'))

    def test_post_edit_without_login(self):
        resp = self.client.post(reverse('entity:do_edit', args=[0]), '{}', 'application/json')
        self.assertEqual(resp.status_code, 401)

    def test_post_edit_with_invalid_params(self):
        self.admin_login()

        params = {
            'name': 'hoge',
            'note': 'fuga',
            'is_toplevel': False,
            'attrs': [
                {'name': 'foo', 'type': str(AttrTypeStr), 'is_mandatory': True, 'row_index': '1'},
            ],
        }
        resp = self.client.post(reverse('entity:do_edit', args=[999]),
                                json.dumps(params),
                                'application/json')
        self.assertEqual(resp.status_code, 400)

    def test_post_edit_with_valid_params(self):
        user = self.admin_login()

        entity = Entity.objects.create(name='hoge', note='fuga', created_user=user)
        attr = EntityAttr.objects.create(name='puyo',
                                         created_user=user,
                                         is_mandatory=True,
                                         type=AttrTypeStr,
                                         parent_entity=entity)
        entity.attrs.add(attr)

        params = {
            'name': 'foo',
            'note': 'bar',
            'is_toplevel': True,
            'attrs': [
                {'name': 'foo', 'type': str(AttrTypeStr), 'is_mandatory': False, 'id': attr.id, 'row_index': '1'},
                {'name': 'bar', 'type': str(AttrTypeStr), 'is_mandatory': True, 'row_index': '2'},
            ],
        }
        resp = self.client.post(reverse('entity:do_edit', args=[entity.id]),
                                json.dumps(params),
                                'application/json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Entity.objects.get(id=entity.id).name, 'foo')
        self.assertEqual(Entity.objects.get(id=entity.id).note, 'bar')
        self.assertEqual(Entity.objects.get(id=entity.id).attrs.count(), 2)
        self.assertEqual(Entity.objects.get(id=entity.id).attrs.get(id=attr.id).name, 'foo')
        self.assertEqual(Entity.objects.get(id=entity.id).attrs.last().name, 'bar')
        self.assertTrue(Entity.objects.get(id=entity.id).status & Entity.STATUS_TOP_LEVEL)

        # tests for operation history is registered correctly
        self.assertEqual(History.objects.count(), 5)
        self.assertEqual(History.objects.filter(operation=History.MOD_ENTITY).count(), 2)
        self.assertEqual(History.objects.filter(operation=History.ADD_ATTR).count(), 1)
        self.assertEqual(History.objects.filter(operation=History.MOD_ATTR).count(), 2)

    def test_post_edit_after_creating_entry(self):
        user = self.admin_login()

        entity = Entity.objects.create(name='hoge', note='fuga', created_user=user)
        attrbase = EntityAttr.objects.create(name='puyo',
                                             created_user=user,
                                             is_mandatory=True,
                                             type=AttrTypeStr,
                                             parent_entity=entity)
        entity.attrs.add(attrbase)

        entry = Entry.objects.create(name='entry', schema=entity, created_user=user)
        entry.add_attribute_from_base(attrbase, user)

        params = {
            'name': 'foo',
            'note': 'bar',
            'is_toplevel': False,
            'attrs': [
                {'name': 'foo', 'type': str(AttrTypeStr), 'is_mandatory': True, 'id': attrbase.id, 'row_index': '1'},
                {'name': 'bar', 'type': str(AttrTypeStr), 'is_mandatory': True, 'row_index': '2'},
            ],
        }
        resp = self.client.post(reverse('entity:do_edit', args=[entity.id]),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(entity.attrs.count(), 2)
        self.assertEqual(entry.attrs.count(), 1)

    def test_post_edit_string_attribute(self):
        user = self.admin_login()

        entity = Entity.objects.create(name='hoge', note='fuga', created_user=user)
        attr = EntityAttr.objects.create(name='puyo',
                                         type=AttrTypeStr,
                                         created_user=user,
                                         parent_entity=entity)
        entity.attrs.add(attr)

        params = {
            'name': 'foo',
            'note': 'bar',
            'is_toplevel': False,
            'attrs': [{
                'name': 'baz',
                'type': str(AttrTypeObj),
                'ref_ids': [entity.id],
                'is_mandatory': True,
                'row_index': '1',
                'id': attr.id
            }],
        }
        resp = self.client.post(reverse('entity:do_edit', args=[entity.id]),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(EntityAttr.objects.get(id=attr.id).type, AttrTypeObj)
        self.assertEqual(EntityAttr.objects.get(id=attr.id).referral.count(), 1)
        self.assertEqual(EntityAttr.objects.get(id=attr.id).referral.last().id, entity.id)

    def test_post_edit_referral_attribute(self):
        user = self.admin_login()

        entity = Entity.objects.create(name='hoge', note='fuga', created_user=user)
        attrbase = EntityAttr.objects.create(name='puyo',
                                             type=AttrTypeObj,
                                             created_user=user,
                                             parent_entity=entity)
        attrbase.referral.add(entity)
        entity.attrs.add(attrbase)

        entry = Entry.objects.create(name='entry', schema=entity, created_user=user)
        attr = entry.add_attribute_from_base(attrbase, user)

        params = {
            'name': 'foo',
            'note': 'bar',
            'is_toplevel': False,
            'attrs': [{
                'name': 'baz',
                'type': str(AttrTypeStr),
                'is_mandatory': True,
                'row_index': '1',
                'id': attrbase.id
            }],
        }
        resp = self.client.post(reverse('entity:do_edit', args=[entity.id]),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(EntityAttr.objects.get(id=attrbase.id).type, AttrTypeStr)
        self.assertEqual(EntityAttr.objects.get(id=attrbase.id).referral.count(), 0)

        # checks that the related Attribute is also changed
        self.assertEqual(Attribute.objects.get(id=attr.id).schema, attrbase)
        self.assertEqual(Attribute.objects.get(id=attr.id).schema.name, 'baz')
        self.assertEqual(Attribute.objects.get(id=attr.id).schema.type, AttrTypeStr)
        self.assertTrue(Attribute.objects.get(id=attr.id).schema.is_mandatory)
        self.assertEqual(Attribute.objects.get(id=attr.id).schema.referral.count(), 0)

    def test_post_edit_to_array_referral_attribute(self):
        user = self.admin_login()

        entity = Entity.objects.create(name='hoge', note='fuga', created_user=user)
        attr = EntityAttr.objects.create(name='puyo',
                                            type=AttrTypeStr,
                                            created_user=user,
                                            parent_entity=entity)
        entity.attrs.add(attr)

        params = {
            'name': 'foo',
            'note': 'bar',
            'is_toplevel': False,
            'attrs': [{
                'name': 'baz',
                'type': str(AttrTypeArrObj),
                'ref_ids': [entity.id],
                'is_mandatory': True,
                'row_index': '1',
                'id': attr.id
            }],
        }
        resp = self.client.post(reverse('entity:do_edit', args=[entity.id]),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(EntityAttr.objects.get(id=attr.id).type, AttrTypeArrObj)
        self.assertEqual(EntityAttr.objects.get(id=attr.id).referral.count(), 1)
        self.assertEqual(EntityAttr.objects.get(id=attr.id).referral.last().id, entity.id)

    def test_post_create_with_invalid_referral_attr(self):
        self.admin_login()

        params = {
            'name': 'hoge',
            'note': 'fuga',
            'is_toplevel': False,
            'attrs': [
                {'name': 'a', 'type': str(AttrTypeObj), 'is_mandatory': False, 'row_index': '1'},
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
            'is_toplevel': False,
            'attrs': [
                {'name': 'a', 'type': str(AttrTypeObj), 'ref_ids': [entity.id], 'is_mandatory': False, 'row_index': '1'},
                {'name': 'b', 'type': str(AttrTypeArrObj), 'ref_ids': [entity.id], 'is_mandatory': False, 'row_index': '2'},
            ],
        }
        resp = self.client.post(reverse('entity:do_create'),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Entity.objects.last().name, 'hoge')

        attrs = EntityAttr.objects.all()
        self.assertEqual(len(attrs), 2)
        self.assertTrue(all([x.referral.filter(id=entity.id).count() for x in attrs]))

    def test_post_delete_attribute(self):
        user = self.admin_login()

        entity = Entity.objects.create(name='entity', created_user=user)
        for name in ['foo', 'bar']:
            entity.attrs.add(EntityAttr.objects.create(name=name,
                                                       type=AttrTypeStr,
                                                       created_user=user,
                                                       parent_entity=entity))

        entry = Entry.objects.create(name='entry', schema=entity, created_user=user)
        [entry.add_attribute_from_base(x, user) for x in entity.attrs.all()]

        permission_count = Permission.objects.count()
        params = {
            'name': 'new-entity',
            'note': 'hoge',
            'is_toplevel': False,
            'attrs': [
                {'name': 'foo', 'type': str(AttrTypeStr), 'id': entity.attrs.first().id,
                 'is_mandatory': False, 'row_index': '1'},
                {'name': 'bar', 'type': str(AttrTypeStr), 'id': entity.attrs.last().id,
                 'is_mandatory': False, 'deleted': True, 'row_index': '2'},
            ],
        }
        resp = self.client.post(reverse('entity:do_edit', args=[entity.id]),
                                json.dumps(params), 'application/json')

        self.assertEqual(resp.status_code, 200)

        # Note: delete() method won't actual delete only set delete flag
        self.assertEqual(Permission.objects.count(), permission_count)
        self.assertEqual(entity.attrs.count(), 2)
        self.assertEqual(entry.attrs.count(), 2)

        # tests for operation history is registered correctly
        self.assertEqual(History.objects.count(), 3)
        self.assertEqual(History.objects.filter(operation=History.MOD_ENTITY).count(), 2)
        self.assertEqual(History.objects.filter(operation=History.DEL_ATTR).count(), 1)

    def test_export_data(self):
        user = self.admin_login()

        entity1 = Entity.objects.create(name='entity1', note='hoge', created_user=user)
        for name in ['foo', 'bar']:
            entity1.attrs.add(EntityAttr.objects.create(name=name,
                                                        type=AttrTypeStr,
                                                        created_user=user,
                                                        parent_entity=entity1))

        entity2 = Entity.objects.create(name='entity2', created_user=user)
        attr = EntityAttr.objects.create(name='attr',
                                         type=AttrTypeObj,
                                         created_user=user,
                                         parent_entity=entity2)
        attr.referral.add(entity1)
        entity2.attrs.add(attr)
        entity2.save()

        resp = self.client.get(reverse('entity:export'))
        self.assertEqual(resp.status_code, 200)

        obj = yaml.load(resp.content)
        self.assertTrue(isinstance(obj, dict))
        self.assertEqual(sorted(obj.keys()), ['Entity', 'EntityAttr'])
        self.assertEqual(len(obj['EntityAttr']), 3)
        self.assertEqual(len(obj['Entity']), 2)

        self.assertTrue(list(filter(lambda x: (
                x['name'] == 'foo' and
                x['entity'] == 'entity1' and
                x['type'] == AttrTypeStr and
                x['refer'] == ''
            ), obj['EntityAttr'])))
        self.assertTrue(list(filter(lambda x: (
                x['name'] == 'attr' and
                x['entity'] == 'entity2' and
                x['type'] == AttrTypeObj and
                x['refer'] == 'entity1'
            ), obj['EntityAttr'])))
        self.assertTrue(list(filter(lambda x: (
                x['name'] == 'entity1' and
                x['note'] == 'hoge' and
                x['created_user'] == 'admin'
            ), obj['Entity'])))

    def test_export_with_unpermitted_object(self):
        user = self.guest_login()
        user2 = User.objects.create(username='user2')

        # create an entity object which is created by logined-user
        entity1 = Entity.objects.create(name='entity1', created_user=user)
        entity1.attrs.add(EntityAttr.objects.create(name='attr1',
                                                    type=AttrTypeStr,
                                                    created_user=user,
                                                    parent_entity=entity1))

        # create a public object which is created by the another_user
        entity2 = Entity.objects.create(name='entity2', created_user=user2)
        entity2.attrs.add(EntityAttr.objects.create(name='attr2',
                                                    type=AttrTypeStr,
                                                    created_user=user2,
                                                    parent_entity=entity1))

        # create private objects which is created by the another_user
        for name in ['foo', 'bar']:
            e = Entity.objects.create(name=name, created_user=user2, is_public=False)
            e.attrs.add(EntityAttr.objects.create(name='private_attr',
                                                  type=AttrTypeStr,
                                                  created_user=user2,
                                                  parent_entity=e,
                                                  is_public=False))

        resp = self.client.get(reverse('entity:export'))
        self.assertEqual(resp.status_code, 200)

        obj = yaml.load(resp.content)
        self.assertEqual(len(obj['Entity']), 2)
        self.assertEqual(len(obj['EntityAttr']), 2)
        self.assertTrue([x for x in obj['Entity'] if x['name'] == entity1.name])
        self.assertTrue([x for x in obj['Entity'] if x['name'] == entity2.name])
        self.assertFalse([x for x in obj['EntityAttr'] if x['name'] == 'private_attr'])

    def test_export_with_deleted_object(self):
        user = self.admin_login()

        entity1 = Entity.objects.create(name='entity1', created_user=user)
        entity1.attrs.add(EntityAttr.objects.create(name='attr1',
                                                    type=AttrTypeStr,
                                                    created_user=user,
                                                    parent_entity=entity1))

        # This Entity object won't be exported because this is logically deleted
        entity1 = Entity.objects.create(name='entity2', created_user=user, is_active=False)

        resp = self.client.get(reverse('entity:export'))
        self.assertEqual(resp.status_code, 200)

        obj = yaml.load(resp.content)
        self.assertEqual(len(obj['Entity']), 1)
        self.assertEqual(obj['Entity'][0]['name'], 'entity1')

    def test_post_delete(self):
        user1 = self.admin_login()

        entity1 = Entity.objects.create(name='entity1', created_user=user1)
        entity1.save()

        attr = EntityAttr.objects.create(name='attr-test',
                                         created_user=user1,
                                         is_mandatory=True,
                                         type=AttrTypeStr,
                                         parent_entity=entity1)
        entity1.attrs.add(attr)

        entity_count = Entity.objects.all().count()

        params = {}
        resp = self.client.post(reverse('entity:do_delete', args=[entity1.id]),
                                json.dumps(params), 'application/json')

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Entity.objects.all().count(), entity_count,
                         "Entity should not be deleted from database")

        entity1 = Entity.objects.get(name__icontains='entity1_deleted_')
        self.assertFalse(entity1.is_active)
        for attr in entity1.attrs.all():
            self.assertFalse(attr.is_active)

    def test_post_delete_without_permission(self):
        user1 = self.guest_login()
        user2 = User.objects.create(username='mokeke')

        entity1 = Entity.objects.create(name='entity1', created_user=user2)
        entity1.is_public = False
        entity1.save()

        entity_count = Entity.objects.all().count()

        params = {}
        resp = self.client.post(reverse('entity:do_delete', args=[entity1.id]),
                                json.dumps(params), 'application/json')

        self.assertEqual(resp.status_code, 400)
        self.assertEqual(Entity.objects.all().count(), entity_count,
                         "Entity should not be deleted from database")

        entity1 = Entity.objects.get(name='entity1')
        self.assertIsNotNone(entity1)
        self.assertTrue(entity1.is_active)

    def test_post_delete_with_active_entry(self):
        user = self.admin_login()

        entity = Entity.objects.create(name='entity1', created_user=user)

        attrbase = EntityAttr.objects.create(name='puyo',
                                             created_user=user,
                                             is_mandatory=True,
                                             type=AttrTypeStr,
                                             parent_entity=entity)
        entity.attrs.add(attrbase)

        entry = Entry.objects.create(name='entry1', schema=entity, created_user=user)
        entry.add_attribute_from_base(attrbase, user)
        entry.save()

        entity_count = Entity.objects.all().count()

        params = {}
        resp = self.client.post(reverse('entity:do_delete', args=[entity.id]),
                                json.dumps(params), 'application/json')

        self.assertEqual(resp.status_code, 400)
        self.assertEqual(Entity.objects.all().count(), entity_count,
                         "Entity should not be deleted from database")

        entity = Entity.objects.get(name='entity1')
        self.assertIsNotNone(entity)
        self.assertTrue(entity.is_active)
        self.assertTrue(EntityAttr.objects.get(name='puyo').is_active)

    def test_post_create_entity_with_guest(self):
        self.guest_login()

        params = {
            'name': 'hoge',
            'note': 'fuga',
            'is_toplevel': True,
            'attrs': [],
        }
        resp = self.client.post(reverse('entity:do_create'),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(Entity.objects.filter(name='hoge'))

    def test_create_entity_attr_with_multiple_referral(self):
        user = self.admin_login()

        r_entity1 = Entity.objects.create(name='referred_entity1', created_user=user)
        r_entity2 = Entity.objects.create(name='referred_entity2', created_user=user)

        params = {
            'name': 'entity',
            'note': 'note',
            'is_toplevel': False,
            'attrs': [
                {
                    'name': 'attr',
                    'type': str(AttrTypeObj),
                    'ref_ids': [r_entity1.id, r_entity2.id],
                    'is_mandatory': False,
                    'row_index': '1'
                },
            ],
        }
        resp = self.client.post(reverse('entity:do_create'),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 200)

        entity = Entity.objects.get(name='entity')

        self.assertEqual(entity.attrs.count(), 1)
        self.assertEqual(entity.attrs.last().referral.count(), 2)
        self.assertEqual(entity.attrs.last().referral.filter(id=r_entity1.id).count(), 1)
        self.assertEqual(entity.attrs.last().referral.filter(id=r_entity2.id).count(), 1)

    def test_change_attribute_type(self):
        user = self.admin_login()

        ref_entity = Entity.objects.create(name='ref_entity', created_user=user)

        entity = Entity.objects.create(name='entity', created_user=user)
        for name in ['foo', 'bar']:
            attr = EntityAttr.objects.create(name=name,
                                             type=AttrTypeStr,
                                             created_user=user,
                                             parent_entity=entity)
            entity.attrs.add(attr)

        (attr1, attr2) = entity.attrs.all()

        entry = Entry.objects.create(name='entry', schema=entity, created_user=user)
        entry.complement_attrs(user)

        entry.attrs.get(schema=attr1).add_value(user, 'hoge')
        entry.attrs.get(schema=attr2).add_value(user, 'fuga')

        params = {
            'name': 'new-entity',
            'note': 'hoge',
            'is_toplevel': False,
            'attrs': [
                # change attribute name and mandatory parameter
                {'name': 'new', 'type': str(attr1.type), 'id': attr1.id,
                 'is_mandatory': not attr1.is_mandatory, 'row_index': '1'},
                # change only attribute type
                {'name': attr2.name, 'type': str(AttrTypeValue['object']), 'id': attr2.id,
                 'is_mandatory': attr2.is_mandatory, 'row_index': '2', 'ref_ids': [ref_entity.id]}
            ]
        }
        resp = self.client.post(reverse('entity:do_edit', args=[entity.id]),
                                json.dumps(params),
                                'application/json')
        self.assertEqual(resp.status_code, 200)

        # When name and mandatory parameters are changed, the attribute value will not be changed.
        attrv = entry.attrs.get(schema=attr1).get_latest_value()
        self.assertIsNotNone(attrv)
        self.assertEqual(attrv.value, 'hoge')

        # When a type of attribute value is clear, a new Attribute value will be created
        attrv = entry.attrs.get(schema=attr2).get_latest_value()
        self.assertEqual(attrv.value, '')
