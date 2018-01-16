import json
import yaml

from django.test import TestCase, Client
from django.urls import reverse
from django.core.cache import cache
from group.models import Group

from entity.models import Entity, EntityAttr
from entry.models import Entry, Attribute, AttributeValue
from user.models import User

from airone.lib.types import AttrTypeStr, AttrTypeObj, AttrTypeText
from airone.lib.types import AttrTypeArrStr, AttrTypeArrObj
from airone.lib.types import AttrTypeValue
from airone.lib.test import AironeViewTest
from airone.lib.acl import ACLType
from xml.etree import ElementTree

from unittest.mock import patch
from unittest.mock import Mock
from entry import tasks


class ViewTest(AironeViewTest):
    def setUp(self):
        super(ViewTest, self).setUp()

        # clear all caches
        cache.clear()

    # override 'admin_login' method to create initial Entity/EntityAttr objects
    def admin_login(self):
        user = super(ViewTest, self).admin_login()

        # create test entity which is a base of creating entry
        self._entity = Entity(name='hoge', created_user=user)
        self._entity.save()

        # set EntityAttr for the test Entity object
        self._entity_attr = EntityAttr(name='test',
                                       type=AttrTypeStr,
                                       is_mandatory=True,
                                       created_user=user,
                                       parent_entity=self._entity)
        self._entity_attr.save()
        self._entity.attrs.add(self._entity_attr)

        return user

    def make_attr(self, name, attrtype=AttrTypeStr, created_user=None, parent_entity=None, parent_entry=None):
        schema = EntityAttr.objects.create(name=name,
                                           type=attrtype,
                                           created_user=(created_user and created_user or self._user),
                                           parent_entity=(parent_entity and parent_entity or self._entity))

        return Attribute.objects.create(name=name,
                                        schema=schema,
                                        created_user=(created_user and created_user or self._user),
                                        parent_entry=(parent_entry and parent_entry or self._entry))

    def test_get_index_without_login(self):
        resp = self.client.get(reverse('entry:index', args=[0]))
        self.assertEqual(resp.status_code, 303)

    def test_get_index_with_login(self):
        self.admin_login()

        resp = self.client.get(reverse('entry:index', args=[self._entity.id]))
        self.assertEqual(resp.status_code, 200)

    def test_get_index_with_entries(self):
        user = self.admin_login()

        Entry(name='fuga', schema=self._entity, created_user=user).save()

        resp = self.client.get(reverse('entry:index', args=[self._entity.id]))
        self.assertEqual(resp.status_code, 200)

    def test_get_permitted_entries(self):
        user = self.guest_login()

        another_user = User.objects.create(username='hoge')
        entity = Entity(name='hoge', created_user=another_user, is_public=False)
        entity.save()

        resp = self.client.get(reverse('entry:index', args=[entity.id]))
        self.assertEqual(resp.status_code, 400)

    def test_get_self_created_entries(self):
        user = self.admin_login()

        self._entity.is_public = False

        resp = self.client.get(reverse('entry:index', args=[self._entity.id]))
        self.assertEqual(resp.status_code, 200)

    def test_get_entries_with_user_permission(self):
        user = self.admin_login()

        entity = Entity.objects.create(name='hoge',
                                       is_public=False,
                                       created_user=User.objects.create(username='hoge'))

        # set permission to the logged-in user
        user.permissions.add(entity.readable)

        resp = self.client.get(reverse('entry:index', args=[entity.id]))
        self.assertEqual(resp.status_code, 200)

    def test_get_entries_with_superior_user_permission(self):
        user = self.admin_login()

        entity = Entity.objects.create(name='hoge',
                                       is_public=False,
                                       created_user=User.objects.create(username='hoge'))

        # set superior permission to the logged-in user
        user.permissions.add(entity.writable)

        resp = self.client.get(reverse('entry:index', args=[entity.id]))
        self.assertEqual(resp.status_code, 200)

    def test_get_with_inferior_user_permission(self):
        user = self.guest_login()

        entity = Entity.objects.create(name='hoge',
                                       is_public=False,
                                       created_user=User.objects.create(username='hoge'))

        # set superior permission to the logged-in user
        user.permissions.add(entity.readable)

        resp = self.client.get(reverse('entry:create', args=[entity.id]))
        self.assertEqual(resp.status_code, 400)

    def test_get_entries_with_group_permission(self):
        user = self.admin_login()

        entity = Entity.objects.create(name='hoge',
                                       is_public=False,
                                       created_user=User.objects.create(username='hoge'))

        # create test group
        group = Group.objects.create(name='test-group')
        user.groups.add(group)

        # set permission to the group which logged-in user belonged to
        group.permissions.add(entity.readable)

        resp = self.client.get(reverse('entry:index', args=[entity.id]))
        self.assertEqual(resp.status_code, 200)

    def test_get_entries_with_superior_group_permission(self):
        user = self.admin_login()

        entity = Entity.objects.create(name='hoge',
                                       is_public=False,
                                       created_user=User.objects.create(username='hoge'))

        # create test group
        group = Group.objects.create(name='test-group')
        user.groups.add(group)

        # set superior permission to the group which logged-in user belonged to
        group.permissions.add(entity.full)

        resp = self.client.get(reverse('entry:index', args=[entity.id]))
        self.assertEqual(resp.status_code, 200)

    def test_get_create_page_without_login(self):
        resp = self.client.get(reverse('entry:create', args=[0]))
        self.assertEqual(resp.status_code, 303)

    def test_get_create_page_with_login(self):
        self.admin_login()

        resp = self.client.get(reverse('entry:create', args=[self._entity.id]))

        self.assertEqual(resp.status_code, 200)

        root = ElementTree.fromstring(resp.content.decode('utf-8'))
        self.assertIsNotNone(root.find('.//table/tr/td'))

    def test_post_without_login(self):
        params = {
            'entry_name': 'hoge',
            'attrs': [
                {'id': '0', 'value': [{'data': 'fuga', 'index': 0}], 'referral_key': []},
            ],
        }
        resp = self.client.post(reverse('entry:do_create', args=[0]),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 401)
        self.assertEqual(Entry.objects.count(), 0)
        self.assertEqual(Attribute.objects.count(), 0)
        self.assertEqual(AttributeValue.objects.count(), 0)

    @patch('entry.views.create_entry_attrs.delay', Mock(side_effect=tasks.create_entry_attrs))
    def test_post_with_login(self):
        self.admin_login()

        params = {
            'entry_name': 'hoge',
            'attrs': [
                {'id': str(self._entity_attr.id), 'value': [{'data': 'hoge', 'index': '0'}], 'referral_key': []},
            ],
        }
        resp = self.client.post(reverse('entry:do_create', args=[self._entity.id]),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Entry.objects.count(), 1)
        self.assertEqual(Attribute.objects.count(), 1)
        self.assertEqual(AttributeValue.objects.count(), 1)

        entry = Entry.objects.last()
        self.assertEqual(entry.attrs.count(), 1)
        self.assertEqual(entry.attrs.last(), Attribute.objects.last())
        self.assertEqual(entry.attrs.last().values.count(), 1)

        attrvalue = AttributeValue.objects.last()
        self.assertEqual(entry.attrs.last().values.last(), attrvalue)
        self.assertTrue(attrvalue.get_status(AttributeValue.STATUS_LATEST))

    @patch('entry.views.create_entry_attrs.delay', Mock(side_effect=tasks.create_entry_attrs))
    def test_post_create_entry_without_permission(self):
        self.guest_login()

        another_user = User.objects.create(username='hoge')
        entity = Entity.objects.create(name='hoge', is_public=False, created_user=another_user)
        attr_base = EntityAttr.objects.create(name='test',
                                              type=AttrTypeStr,
                                              is_mandatory=True,
                                              parent_entity=entity,
                                              created_user=another_user)
        entity.attrs.add(attr_base)

        params = {
            'entry_name': 'entry',
            'attrs': [
                {'id': str(attr_base.id), 'value': [{'data': 'hoge', 'index': 0}], 'referral_key': []},
            ],
        }
        resp = self.client.post(reverse('entry:do_create', args=[entity.id]),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 400)
        self.assertEqual(Entry.objects.count(), 0)
        self.assertEqual(Attribute.objects.count(), 0)
        self.assertEqual(AttributeValue.objects.count(), 0)

    @patch('entry.views.create_entry_attrs.delay', Mock(side_effect=tasks.create_entry_attrs))
    def test_post_with_optional_parameter(self):
        user = self.admin_login()

        # add an optional EntityAttr to the test Entity object
        self._entity_attr_optional = EntityAttr(name='test-optional',
                                                type=AttrTypeStr,
                                                is_mandatory=False,
                                                created_user=user,
                                                parent_entity=self._entity)
        self._entity_attr_optional.save()
        self._entity.attrs.add(self._entity_attr_optional)

        params = {
            'entry_name': 'hoge',
            'attrs': [
                {'id': str(self._entity_attr.id), 'value': [{'data': 'hoge', 'index': 0}], 'referral_key': []},
                {'id': str(self._entity_attr_optional.id), 'value': [], 'referral_key': []},
            ],
        }
        resp = self.client.post(reverse('entry:do_create', args=[self._entity.id]),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Entry.objects.count(), 1)
        self.assertEqual(Attribute.objects.count(), 2)
        self.assertEqual(AttributeValue.objects.count(), 1)

        entry = Entry.objects.last()
        self.assertEqual(entry.attrs.count(), 2)
        self.assertEqual(entry.attrs.get(name='test').values.count(), 1)
        self.assertEqual(entry.attrs.get(name='test-optional').values.count(), 0)
        self.assertEqual(entry.attrs.get(name='test').values.last().value, 'hoge')

    @patch('entry.views.create_entry_attrs.delay', Mock(side_effect=tasks.create_entry_attrs))
    def test_post_with_lack_of_params(self):
        self.admin_login()

        params = {
            'entry_name': '',
            'attrs': [
                {'id': str(self._entity_attr.id), 'value': [{'data': 'hoge', 'index': 0}], 'referral_key': []},
            ],
        }
        resp = self.client.post(reverse('entry:do_create', args=[self._entity.id]),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 400)
        self.assertEqual(Entry.objects.count(), 0)
        self.assertEqual(Attribute.objects.count(), 0)
        self.assertEqual(AttributeValue.objects.count(), 0)

    @patch('entry.views.create_entry_attrs.delay', Mock(side_effect=tasks.create_entry_attrs))
    def test_post_create_with_referral(self):
        user = self.admin_login()

        attr_base = EntityAttr.objects.create(name='attr_with_referral',
                                              created_user=user,
                                              type=AttrTypeObj,
                                              parent_entity=self._entity,
                                              is_mandatory=False)
        attr_base.referral.add(self._entity)
        self._entity.attrs.add(attr_base)

        entry = Entry.objects.create(name='entry', schema=self._entity, created_user=user)

        params = {
            'entry_name': 'new_entry',
            'attrs': [
                {'id': str(self._entity_attr.id), 'value': [{'data': 'hoge', 'index': 0}], 'referral_key': []},
                {'id': str(attr_base.id), 'value': [{'data': str(entry.id), 'index': 0}], 'referral_key': []},
            ],
        }
        resp = self.client.post(reverse('entry:do_create', args=[self._entity.id]),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Entry.objects.count(), 2)
        self.assertEqual(Entry.objects.last().name, 'new_entry')
        self.assertEqual(Entry.objects.last().attrs.last().schema.type, AttrTypeObj)
        self.assertEqual(Entry.objects.last().attrs.last().values.count(), 1)
        self.assertEqual(Entry.objects.last().attrs.last().values.last().value, '')
        self.assertEqual(Entry.objects.last().attrs.last().values.last().referral.id, entry.id)

    @patch('entry.views.create_entry_attrs.delay', Mock(side_effect=tasks.create_entry_attrs))
    def test_post_with_invalid_param(self):
        self.admin_login()

        params = {
            'entry_name': 'hoge',
            'attrs': [
                {'id': str(self._entity_attr.id), 'value': [{'data': 'hoge', 'index': 0}], 'referral_key': []},
                {'id': '9999', 'value': ['invalid value'], 'referral_key': []},
            ],
        }
        resp = self.client.post(reverse('entry:do_create', args=[self._entity.id]),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 400)
        self.assertEqual(Entry.objects.count(), 0)
        self.assertEqual(Attribute.objects.count(), 0)
        self.assertEqual(AttributeValue.objects.count(), 0)

    @patch('entry.views.create_entry_attrs.delay', Mock(side_effect=tasks.create_entry_attrs))
    def test_post_without_entry(self):
        user = self.admin_login()

        attr_base = EntityAttr.objects.create(name='ref_attr',
                                              created_user=user,
                                              type=AttrTypeObj,
                                              parent_entity=self._entity,
                                              is_mandatory=False)
        attr_base.referral.add(self._entity)
        self._entity.attrs.add(attr_base)

        params = {
            'entry_name': 'new_entry',
            'attrs': [
                {'id': str(self._entity_attr.id), 'value': [{'data': 'hoge', 'index': 0}], 'referral_key': []},
                {'id': str(attr_base.id), 'value': [{'data': '0', 'index': 0}], 'referral_key': []},
            ],
        }
        resp = self.client.post(reverse('entry:do_create', args=[self._entity.id]),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 200)

        new_entry = Entry.objects.get(name='new_entry')
        self.assertEqual(new_entry.attrs.get(schema=self._entity_attr).values.count(), 1)
        self.assertEqual(new_entry.attrs.get(schema=self._entity_attr).values.last().value, 'hoge')
        self.assertEqual(new_entry.attrs.get(schema=attr_base).values.count(), 0)

    def test_get_edit_without_login(self):
        resp = self.client.get(reverse('entry:edit', args=[0]))
        self.assertEqual(resp.status_code, 303)

    def test_get_edit_with_invalid_entry_id(self):
        user = self.admin_login()

        Entry(name='fuga', schema=self._entity, created_user=user).save()

        # with invalid entry-id
        resp = self.client.get(reverse('entry:edit', args=[0]))
        self.assertEqual(resp.status_code, 400)

    def test_get_edit_with_valid_entry_id(self):
        user = self.admin_login()

        # making test Entry set
        entry = Entry(name='fuga', schema=self._entity, created_user=user)
        entry.save()

        for attr_name in ['foo', 'bar']:
            attr = self.make_attr(name=attr_name,
                                  parent_entry=entry,
                                  created_user=user)

            for value in ['hoge', 'fuga']:
                attr_value = AttributeValue(value=value, created_user=user, parent_attr=attr)
                attr_value.save()

                attr.values.add(attr_value)

            entry.attrs.add(attr)

        # with invalid entry-id
        resp = self.client.get(reverse('entry:edit', args=[entry.id]))
        self.assertEqual(resp.status_code, 200)

    def test_get_edit_with_optional_attr(self):
        user = self.admin_login()

        # making test Entry set
        entry = Entry(name='fuga', schema=self._entity, created_user=user)
        entry.save()

        attr = self.make_attr(name='attr', created_user=user, parent_entry=entry)
        entry.attrs.add(attr)

        # with invalid entry-id
        resp = self.client.get(reverse('entry:edit', args=[entry.id]))
        self.assertEqual(resp.status_code, 200)

    def test_post_edit_without_login(self):
        params = {'attrs': [{'id': '0', 'value': [], 'referral_key': []}]}
        resp = self.client.post(reverse('entry:do_edit', args=[0]),
                                json.dumps(params), 'application/json')

        self.assertEqual(resp.status_code, 401)
        self.assertEqual(AttributeValue.objects.count(), 0)

    def test_post_edit_with_invalid_param(self):
        self.admin_login()

        params = {'attrs': [{'id': '0', 'value': [], 'referral_key': []}]}
        resp = self.client.post(reverse('entry:do_edit', args=[0]),
                                json.dumps(params), 'application/json')

        self.assertEqual(resp.status_code, 400)
        self.assertEqual(AttributeValue.objects.count(), 0)

    def test_post_edit_creating_entry(self):
        user = self.admin_login()

        entry = Entry.objects.create(name='entry', schema=self._entity, created_user=user)
        entry.set_status(Entry.STATUS_CREATING)

        params = {'entry_name': 'changed-entry'}
        resp = self.client.post(reverse('entry:do_edit', args=[entry.id]),
                                json.dumps(params), 'application/json')

        self.assertEqual(resp.status_code, 400)
        self.assertEqual(Entry.objects.get(id=entry.id).name, 'entry')

    def test_get_show_and_edit_creating_entry(self):
        user = self.admin_login()

        entry = Entry.objects.create(name='entry', schema=self._entity, created_user=user)
        entry.set_status(Entry.STATUS_CREATING)

        resp = self.client.get(reverse('entry:show', args=[entry.id]))
        self.assertEqual(resp.status_code, 400)

        resp = self.client.get(reverse('entry:edit', args=[entry.id]))
        self.assertEqual(resp.status_code, 400)

    @patch('entry.views.edit_entry_attrs.delay', Mock(side_effect=tasks.edit_entry_attrs))
    def test_post_edit_with_valid_param(self):
        user = self.admin_login()

        # making test Entry set
        entry = Entry(name='fuga', schema=self._entity, created_user=user)
        entry.save()

        for attr_name in ['foo', 'bar']:
            attr = self.make_attr(name=attr_name,
                                  created_user=user,
                                  parent_entry=entry)

            attr_value = AttributeValue(value='hoge', created_user=user, parent_attr=attr)
            attr_value.set_status(AttributeValue.STATUS_LATEST)
            attr_value.save()

            attr.values.add(attr_value)
            entry.attrs.add(attr)

        params = {
            'entry_name': 'hoge',
            'attrs': [
                {'id': str(Attribute.objects.get(name='foo').id), 'value': [{'data': 'hoge', 'index': 0}], 'referral_key': []},
                {'id': str(Attribute.objects.get(name='bar').id), 'value': [{'data': 'fuga', 'index': 0}], 'referral_key': []},
            ],
        }
        resp = self.client.post(reverse('entry:do_edit', args=[entry.id]),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(AttributeValue.objects.count(), 3)
        self.assertEqual(Attribute.objects.get(name='foo').values.count(), 1)
        self.assertEqual(Attribute.objects.get(name='bar').values.count(), 2)
        self.assertEqual(Attribute.objects.get(name='foo').values.last().value, 'hoge')
        self.assertEqual(Attribute.objects.get(name='bar').values.last().value, 'fuga')
        self.assertEqual(Entry.objects.get(id=entry.id).name, 'hoge')

        # checks to set corrected status-flag
        foo_value_first = Attribute.objects.get(name='foo').values.first()
        bar_value_first = Attribute.objects.get(name='bar').values.first()
        bar_value_last = Attribute.objects.get(name='bar').values.last()

        self.assertTrue(foo_value_first.get_status(AttributeValue.STATUS_LATEST))
        self.assertFalse(bar_value_first.get_status(AttributeValue.STATUS_LATEST))
        self.assertTrue(bar_value_last.get_status(AttributeValue.STATUS_LATEST))

    @patch('entry.views.edit_entry_attrs.delay', Mock(side_effect=tasks.edit_entry_attrs))
    def test_post_edit_with_optional_params(self):
        user = self.admin_login()

        # making test Entry set
        entry = Entry(name='fuga', schema=self._entity, created_user=user)
        entry.save()

        for attr_name in ['foo', 'bar']:
            attr = self.make_attr(name=attr_name,
                                  created_user=user,
                                  parent_entry=entry)
            entry.attrs.add(attr)

        params = {
            'entry_name': entry.name,
            'attrs': [
                # include blank value
                {'id': str(Attribute.objects.get(name='foo').id), 'value': [{'data': '', 'index': 0}], 'referral_key': []},
                {'id': str(Attribute.objects.get(name='bar').id), 'value': [{'data': 'fuga', 'index': 0}], 'referral_key': []},
            ],
        }
        resp = self.client.post(reverse('entry:do_edit', args=[entry.id]),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(AttributeValue.objects.count(), 1)
        self.assertEqual(Attribute.objects.get(name='foo').values.count(), 0)
        self.assertEqual(Attribute.objects.get(name='bar').values.count(), 1)
        self.assertEqual(Attribute.objects.get(name='bar').values.last().value, 'fuga')
        self.assertEqual(Entry.objects.get(id=entry.id).name, entry.name)

    @patch('entry.views.edit_entry_attrs.delay', Mock(side_effect=tasks.edit_entry_attrs))
    def test_post_edit_with_array_string_value(self):
        user = self.admin_login()

        entity = Entity.objects.create(name='entity', created_user=user)
        entry = Entry.objects.create(name='entry', created_user=user, schema=entity)

        attr = self.make_attr(name='attr',
                              attrtype=AttrTypeArrStr,
                              created_user=user,
                              parent_entry=entry)

        attr_value = AttributeValue.objects.create(created_user=user, parent_attr=attr)
        attr_value.set_status(AttributeValue.STATUS_DATA_ARRAY_PARENT)

        attr_value.data_array.add(AttributeValue.objects.create(value='hoge',
                                                                created_user=user,
                                                                parent_attr=attr))

        attr_value.data_array.add(AttributeValue.objects.create(value='fuga',
                                                                created_user=user,
                                                                parent_attr=attr))

        attr.values.add(attr_value)

        params = {
            'entry_name': entry.name,
            'attrs': [{
                'id': str(attr.id),
                'value': [
                    {'data': 'hoge', 'index': 0},
                    {'data': 'puyo', 'index': 1},
                ],
                'referral_key': [],
            }],
        }
        resp = self.client.post(reverse('entry:do_edit', args=[entry.id]),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 200)

        # checks to set correct status flags
        leaf_values = [x for x in AttributeValue.objects.all()
                       if not x.get_status(AttributeValue.STATUS_DATA_ARRAY_PARENT)]

        parent_values = [x for x in AttributeValue.objects.all()
                         if x.get_status(AttributeValue.STATUS_DATA_ARRAY_PARENT)]
        self.assertEqual(len(leaf_values), 4)
        self.assertEqual(len(parent_values), 2)

        self.assertEqual(attr.values.count(), 2)
        self.assertTrue(attr.values.last().status & AttributeValue.STATUS_DATA_ARRAY_PARENT)

        self.assertEqual(attr.values.last().data_array.count(), 2)
        self.assertTrue(all([x.value in ['hoge', 'puyo'] for x in attr.values.last().data_array.all()]))

    @patch('entry.views.edit_entry_attrs.delay', Mock(side_effect=tasks.edit_entry_attrs))
    def test_post_edit_with_array_object_value(self):
        user = self.admin_login()

        entity = Entity.objects.create(name='entity', created_user=user)
        entry = Entry.objects.create(name='entry', created_user=user, schema=entity)

        e1 = Entry.objects.create(name='E1', created_user=user, schema=entity)
        e2 = Entry.objects.create(name='E2', created_user=user, schema=entity)
        e3 = Entry.objects.create(name='E3', created_user=user, schema=entity)

        attr = self.make_attr(name='attr',
                              attrtype=AttrTypeArrObj,
                              created_user=user,
                              parent_entry=entry)

        attr_value = AttributeValue.objects.create(created_user=user, parent_attr=attr)
        attr_value.set_status(AttributeValue.STATUS_DATA_ARRAY_PARENT)

        attr_value.data_array.add(AttributeValue.objects.create(referral=e1,
                                                                created_user=user,
                                                                parent_attr=attr))

        attr_value.data_array.add(AttributeValue.objects.create(referral=e2,
                                                                created_user=user,
                                                                parent_attr=attr))

        attr.values.add(attr_value)

        params = {
            'entry_name': entry.name,
            'attrs': [{
                'id': str(attr.id),
                'value': [
                    {'data': e2.id, 'index': 0},
                    {'data': e3.id, 'index': 1},
                ],
                'referral_key': [],
            }],
        }
        resp = self.client.post(reverse('entry:do_edit', args=[entry.id]),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 200)

        # checks to set correct status flags
        leaf_values = [x for x in AttributeValue.objects.all()
                       if not x.get_status(AttributeValue.STATUS_DATA_ARRAY_PARENT)]

        parent_values = [x for x in AttributeValue.objects.all()
                         if x.get_status(AttributeValue.STATUS_DATA_ARRAY_PARENT)]
        self.assertEqual(len(leaf_values), 4)
        self.assertEqual(len(parent_values), 2)

        self.assertEqual(attr.values.count(), 2)
        self.assertTrue(attr.values.last().status & AttributeValue.STATUS_DATA_ARRAY_PARENT)

        self.assertEqual(attr.values.last().data_array.count(), 2)
        self.assertTrue(all([x.referral.id in [e2.id, e3.id]
                            for x in attr.values.last().data_array.all()]))

    def test_get_detail_with_invalid_param(self):
        self.admin_login()

        resp = self.client.get(reverse('entry:show', args=[0]))
        self.assertEqual(resp.status_code, 400)

    def test_get_detail_with_valid_param(self):
        user = self.admin_login()

        # making test Entry set
        entry = Entry(name='fuga', schema=self._entity, created_user=user)
        entry.save()

        for attr_name in ['foo', 'bar']:
            attr = self.make_attr(name=attr_name,
                                  created_user=user,
                                  parent_entry=entry)

            for value in ['hoge', 'fuga']:
                attr_value = AttributeValue(value=value, created_user=user, parent_attr=attr)
                attr_value.save()

                attr.values.add(attr_value)

            entry.attrs.add(attr)

        resp = self.client.get(reverse('entry:show', args=[entry.id]))
        self.assertEqual(resp.status_code, 200)

    @patch('entry.views.edit_entry_attrs.delay', Mock(side_effect=tasks.edit_entry_attrs))
    def test_post_edit_with_referral(self):
        user = self.admin_login()

        attr_base = EntityAttr.objects.create(name='attr_with_referral',
                                              created_user=user,
                                              type=AttrTypeObj,
                                              parent_entity=self._entity,
                                              is_mandatory=False)
        attr_base.referral.add(self._entity)
        self._entity.attrs.add(attr_base)

        entry = Entry.objects.create(name='old_entry', schema=self._entity, created_user=user)

        attr = entry.add_attribute_from_base(attr_base, user)
        attr_value = AttributeValue.objects.create(referral=entry,
                                                   created_user=user,
                                                   parent_attr=attr)
        attr.values.add(attr_value)

        new_entry = Entry.objects.create(name='new_entry', schema=self._entity, created_user=user)

        params = {
            'entry_name': 'old_entry',
            'attrs': [
                {'id': str(attr.id), 'value': [{'data': str(new_entry.id), 'index': 0}], 'referral_key': []},
            ],
        }
        resp = self.client.post(reverse('entry:do_edit', args=[entry.id]),
                                json.dumps(params), 'application/json')

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(entry.attrs.last().values.count(), 2)
        self.assertEqual(entry.attrs.last().values.first().value, '')
        self.assertEqual(entry.attrs.last().values.first().referral.id, entry.id)
        self.assertEqual(entry.attrs.last().values.last().value, '')
        self.assertEqual(entry.attrs.last().values.last().referral.id, new_entry.id)

    @patch('entry.views.edit_entry_attrs.delay', Mock(side_effect=tasks.edit_entry_attrs))
    def test_post_edit_without_referral_value(self):
        user = self.admin_login()

        attr_base = EntityAttr.objects.create(name='attr_with_referral',
                                                 created_user=user,
                                                 type=AttrTypeObj,
                                                 parent_entity=self._entity,
                                                 is_mandatory=False)
        attr_base.referral.add(self._entity)
        self._entity.attrs.add(attr_base)

        entry = Entry.objects.create(name='entry', schema=self._entity, created_user=user)

        attr = entry.add_attribute_from_base(attr_base, user)
        attr_value = AttributeValue.objects.create(referral=entry,
                                                   created_user=user,
                                                   parent_attr=attr)
        attr.values.add(attr_value)

        params = {
            'entry_name': 'entry',
            'attrs': [
                {'id': str(attr.id), 'value': [{'data': '0', 'index': 0}], 'referral_key': []},
            ],
        }
        resp = self.client.post(reverse('entry:do_edit', args=[entry.id]),
                                json.dumps(params), 'application/json')

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(attr.values.count(), 2)
        self.assertEqual(attr.values.last().value, '')

    @patch('entry.views.edit_entry_attrs.delay', Mock(side_effect=tasks.edit_entry_attrs))
    def test_post_edit_to_no_referral(self):
        user = self.admin_login()

        entry = Entry.objects.create(name='entry', schema=self._entity, created_user=user)

        attr = self.make_attr(name='attr',
                              attrtype=AttrTypeObj,
                              created_user=user,
                              parent_entry=entry)
        entry.attrs.add(attr)

        attr_value = AttributeValue.objects.create(referral=entry,
                                                   created_user=user,
                                                   parent_attr=attr)
        attr.values.add(attr_value)

        params = {
            'entry_name': entry.name,
            'attrs': [
                # include blank value
                {'id': str(attr.id), 'value': [], 'referral_key': []},
            ],
        }
        resp = self.client.post(reverse('entry:do_edit', args=[entry.id]),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(attr.values.count(), 2)
        self.assertEqual(attr.values.first(), attr_value)
        self.assertIsNone(attr.values.last().referral)

    def test_get_export(self):
        user = self.admin_login()

        entry = Entry(name='fuga', schema=self._entity, created_user=user)
        entry.save()

        for attr_name in ['foo', 'bar']:
            attr = self.make_attr(name=attr_name,
                                  parent_entry=entry,
                                  created_user=user)

            for value in ['hoge', 'fuga']:
                attr_value = AttributeValue(value=value, created_user=user, parent_attr=attr)
                attr_value.save()

                attr.values.add(attr_value)

            entry.attrs.add(attr)

        resp = self.client.get(reverse('entry:export', args=[self._entity.id]))
        self.assertEqual(resp.status_code, 200)

        obj = yaml.load(resp.content)
        self.assertTrue('Entry' in obj)
        self.assertTrue('Attribute' in obj)
        self.assertTrue('AttributeValue' in obj)

        self.assertEqual(len(obj['Entry']), 1)
        self.assertEqual(obj['Entry'][0]['id'], entry.id)
        self.assertEqual(obj['Entry'][0]['name'], entry.name)
        self.assertEqual(obj['Entry'][0]['entity'], self._entity.name)

        self.assertEqual(len(obj['Attribute']), 2)
        self.assertEqual(len(obj['AttributeValue']), 4)

    @patch('entry.views.delete_entry.delay', Mock(side_effect=tasks.delete_entry))
    def test_post_delete_entry(self):
        user = self.admin_login()

        entry = Entry(name='fuga', schema=self._entity, created_user=user)
        entry.save()

        entry.attrs.add(self.make_attr(name='attr-test',
                                       parent_entry=entry,
                                       created_user=user))

        entry_count = Entry.objects.count()

        params = {}

        resp = self.client.post(reverse('entry:do_delete', args=[entry.id]),
                                json.dumps(params), 'application/json')

        self.assertEqual(resp.status_code, 200)

        self.assertEqual(Entry.objects.count(), entry_count)

        entry = Entry.objects.last()
        self.assertFalse(entry.is_active)
        self.assertFalse(Attribute.objects.get(name__icontains='attr-test_deleted_').is_active)

    def test_post_delete_entry_without_permission(self):
        user1 = self.guest_login()
        user2 = User(username='nyaa')
        user2.save()

        entity = Entity.objects.create(name='entity', created_user=user1)
        entry = Entry(name='fuga', schema=entity, created_user=user2, is_public=False)
        entry.save()

        entry_count = Entry.objects.count()

        params = {}

        resp = self.client.post(reverse('entry:do_delete', args=[entry.id]),
                                json.dumps(params), 'application/json')

        self.assertEqual(resp.status_code, 400)

        self.assertEqual(Entry.objects.count(), entry_count)

        entry = Entry.objects.last()
        self.assertTrue(entry.is_active)

    @patch('entry.views.create_entry_attrs.delay', Mock(side_effect=tasks.create_entry_attrs))
    def test_post_create_array_string_attribute(self):
        user = self.admin_login()

        # create a test data set
        entity = Entity.objects.create(name='entity-test',
                                       created_user=user)

        attr_base = EntityAttr.objects.create(name='attr-test',
                                                 type=AttrTypeArrStr,
                                                 is_mandatory=False,
                                                 created_user=user,
                                                 parent_entity=self._entity)
        entity.attrs.add(attr_base)

        params = {
            'entry_name': 'entry-test',
            'attrs': [{
                'id': str(attr_base.id),
                'value': [
                    {'data': 'hoge', 'index': 0},
                    {'data': 'fuga', 'index': 1},
                    {'data': 'puyo', 'index': 2},
                ],
                'referral_key': [],
            }],
        }
        resp = self.client.post(reverse('entry:do_create', args=[entity.id]),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 200)

        self.assertEqual(AttributeValue.objects.count(), 4)

        entry = Entry.objects.last()
        self.assertEqual(entry.name, 'entry-test')
        self.assertEqual(entry.attrs.count(), 1)

        attr = entry.attrs.last()
        self.assertEqual(attr.name, 'attr-test')
        self.assertEqual(attr.values.count(), 1)

        attr_value = attr.values.last()
        self.assertTrue(attr_value.get_status(AttributeValue.STATUS_DATA_ARRAY_PARENT))
        self.assertEqual(attr_value.value, '')
        self.assertIsNone(attr_value.referral)
        self.assertEqual(attr_value.data_array.count(), 3)
        self.assertTrue([x.value == 'hoge' or x.value == 'fuga' or x.value == 'puyo'
            for x in attr_value.data_array.all()])

    @patch('entry.views.create_entry_attrs.delay', Mock(side_effect=tasks.create_entry_attrs))
    def test_post_create_array_object_attribute(self):
        user = self.admin_login()

        # create a test data set
        entity = Entity.objects.create(name='entity-test',
                                       created_user=user)

        attr_base = EntityAttr.objects.create(name='attr-ref-test',
                                              created_user=user,
                                              type=AttrTypeArrObj,
                                              parent_entity=self._entity,
                                              is_mandatory=False)
        attr_base.referral.add(self._entity)
        entity.attrs.add(attr_base)

        referral = Entry.objects.create(name='entry0', schema=self._entity, created_user=user)

        params = {
            'entry_name': 'entry-test',
            'attrs': [{
                'id': str(attr_base.id),
                'value': [
                    {'data': str(referral.id), 'index': 0},
                    {'data': str(referral.id), 'index': 1},
                ],
                'referral_key': [],
            }],
        }
        resp = self.client.post(reverse('entry:do_create', args=[entity.id]),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 200)

        self.assertEqual(AttributeValue.objects.count(), 3)

        entry = Entry.objects.last()
        self.assertEqual(entry.name, 'entry-test')
        self.assertEqual(entry.attrs.count(), 1)

        attr = entry.attrs.last()
        self.assertEqual(attr.name, 'attr-ref-test')
        self.assertEqual(attr.values.count(), 1)

        attr_value = attr.values.last()
        self.assertTrue(attr_value.get_status(AttributeValue.STATUS_DATA_ARRAY_PARENT))
        self.assertEqual(attr_value.value, '')
        self.assertIsNone(attr_value.referral)
        self.assertEqual(attr_value.data_array.count(), 2)
        self.assertTrue(all([x.referral.id == referral.id for x in attr_value.data_array.all()]))

    @patch('entry.views.create_entry_attrs.delay', Mock(side_effect=tasks.create_entry_attrs))
    def test_post_text_area_value(self):
        user = self.admin_login()

        textattr = EntityAttr.objects.create(name='attr-text',
                                             type=AttrTypeText,
                                             created_user=user,
                                             parent_entity=self._entity)
        self._entity.attrs.add(textattr)

        params = {
            'entry_name': 'entry',
            'attrs': [
                {
                    'id': str(self._entity_attr.id),
                    'value': [{'data': 'hoge', 'index': 0}],
                    'referral_key': [],
                },
                {
                    'id': str(textattr.id),
                    'value': [{'data': 'fuga', 'index': 0}],
                    'referral_key': [],
                },
            ],
        }
        resp = self.client.post(reverse('entry:do_create', args=[self._entity.id]),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Entry.objects.count(), 1)
        self.assertEqual(Attribute.objects.count(), 2)
        self.assertEqual(AttributeValue.objects.count(), 2)

        entry = Entry.objects.last()
        self.assertEqual(entry.attrs.count(), 2)
        self.assertTrue(any([
            (x.values.last().value == 'hoge' or x.values.last().value == 'fuga')
            for x in entry.attrs.all()
        ]))

    @patch('entry.views.create_entry_attrs.delay', Mock(side_effect=tasks.create_entry_attrs))
    def test_post_create_just_limit_of_value(self):
        user = self.admin_login()

        params = {
            'entry_name': 'entry',
            'attrs': [{
                'id': str(self._entity_attr.id),
                'value': [{'data': 'A' * AttributeValue.MAXIMUM_VALUE_SIZE, 'index': 0}],
                'referral_key': [],
            }],
        }
        resp = self.client.post(reverse('entry:do_create', args=[self._entity.id]),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Entry.objects.count(), 1)

        entry = Entry.objects.last()
        self.assertEqual(entry.attrs.count(), 1)
        self.assertEqual(entry.attrs.last().values.count(), 1)
        self.assertEqual(len(entry.attrs.last().values.last().value), AttributeValue.MAXIMUM_VALUE_SIZE)

    @patch('entry.views.edit_entry_attrs.delay', Mock(side_effect=tasks.edit_entry_attrs))
    def test_post_edit_just_limit_of_value(self):
        user = self.admin_login()

        entry = Entry.objects.create(name='entry', created_user=user, schema=self._entity)
        attr = entry.add_attribute_from_base(self._entity_attr, user)

        params = {
            'entry_name': 'entry',
            'attrs': [{
                'id': str(attr.id),
                'value': [{'data': 'A' * AttributeValue.MAXIMUM_VALUE_SIZE, 'index': 0}],
                'referral_key': [],
            }],
        }
        resp = self.client.post(reverse('entry:do_edit', args=[entry.id]),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(attr.values.count(), 1)
        self.assertEqual(len(attr.values.last().value), AttributeValue.MAXIMUM_VALUE_SIZE)

    @patch('entry.views.create_entry_attrs.delay', Mock(side_effect=tasks.create_entry_attrs))
    def test_post_create_exceeding_limit_of_value(self):
        user = self.admin_login()

        params = {
            'entry_name': 'entry',
            'attrs': [{
                'id': str(self._entity_attr.id),
                'value': {
                    'data': ['A' * AttributeValue.MAXIMUM_VALUE_SIZE + 'A'],
                    'index': 0,
                },
                'referral_key': [],
            }],
        }
        resp = self.client.post(reverse('entry:do_create', args=[self._entity.id]),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 400)
        self.assertEqual(Entry.objects.count(), 0)

    @patch('entry.views.edit_entry_attrs.delay', Mock(side_effect=tasks.edit_entry_attrs))
    def test_post_edit_exceeding_limit_of_value(self):
        user = self.admin_login()

        entry = Entry.objects.create(name='entry', created_user=user, schema=self._entity)
        attr = entry.add_attribute_from_base(self._entity_attr, user)

        params = {
            'entry_name': 'entry',
            'attrs': [{
                'id': str(attr.id),
                'value': [{'data': 'A' * AttributeValue.MAXIMUM_VALUE_SIZE + 'A', 'index': 0}],
                'referral_key': [],
            }],
        }
        resp = self.client.post(reverse('entry:do_edit', args=[entry.id]),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 400)
        self.assertEqual(attr.values.count(), 0)

    @patch('entry.views.create_entry_attrs.delay', Mock(side_effect=tasks.create_entry_attrs))
    def test_try_to_create_duplicate_name_of_entry(self):
        user = self.admin_login()

        entry = Entry.objects.create(name='entry', created_user=user, schema=self._entity)
        attr = entry.add_attribute_from_base(self._entity_attr, user)

        params = {
            'entry_name': 'entry',
            'attrs': [
                {
                    'id': str(self._entity_attr.id),
                    'value': [{'data': 'hoge', 'index': 0}],
                    'referral_key': [],
                },
            ],
        }
        resp = self.client.post(reverse('entry:do_create', args=[self._entity.id]),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 400)

    def test_try_to_edit_duplicate_name_of_entry(self):
        user = self.admin_login()

        entry = Entry.objects.create(name='entry', created_user=user, schema=self._entity)
        attr = entry.add_attribute_from_base(self._entity_attr, user)

        dup_entry = Entry.objects.create(name='dup_entry', created_user=user, schema=self._entity)
        dup_attr = entry.add_attribute_from_base(self._entity_attr, user)

        params = {
            'entry_name': 'entry',
            'attrs': [
                {'id': str(dup_attr.id), 'value': [{'data': 'hoge', 'index': 0}], 'referral_key': []},
            ],
        }
        resp = self.client.post(reverse('entry:do_edit', args=[dup_entry.id]),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 400)

    @patch('entry.views.create_entry_attrs.delay', Mock(side_effect=tasks.create_entry_attrs))
    def test_make_entry_with_unpermitted_params(self):
        user = self.admin_login()

        # update ACL of EntityAttr
        attr = EntityAttr.objects.create(name='newattr',
                                         type=AttrTypeStr,
                                         created_user=user,
                                         parent_entity=self._entity)
        self._entity.attrs.add(attr)

        self._entity_attr.is_mandatory = False
        self._entity_attr.is_public = False
        self._entity_attr.default_permission = ACLType.Nothing.id
        self._entity_attr.save()

        guest = self.guest_login()

        params = {
            'entry_name': 'entry',
            'attrs': [
                {'id': str(self._entity_attr.id), 'value': [{'data': 'hoge', 'index': 0}], 'referral_key': []},
                {'id': str(attr.id), 'value': [{'data': 'fuga', 'index': 0}], 'referral_key': []},
            ],
        }
        resp = self.client.post(reverse('entry:do_create', args=[self._entity.id]),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 200)

        # checks that Entry object is created with only permitted Attributes
        entry = Entry.objects.last()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.name, 'entry')
        self.assertEqual(entry.attrs.count(), 1)
        self.assertEqual(entry.attrs.last().schema, attr)

    @patch('entry.views.create_entry_attrs.delay', Mock(side_effect=tasks.create_entry_attrs))
    def test_get_available_attrs(self):
        admin = self.admin_login()

        entity = Entity.objects.create(name='entity', created_user=admin)

        attrs = []
        for index, permission in enumerate([ACLType.Readable, ACLType.Writable]):
            attr = EntityAttr.objects.create(name='attr%d' % index,
                                             type=AttrTypeStr,
                                             created_user=admin,
                                             parent_entity=entity,
                                             is_public=False,
                                             default_permission=permission.id)
            entity.attrs.add(attr)
            attrs.append(attr)

        params = {
            'entry_name': 'entry1',
            'attrs': [
                {'id': str(attrs[0].id), 'value': [{'data': 'hoge', 'index': 0}], 'referral_key': []},
                {'id': str(attrs[1].id), 'value': [{'data': 'fuga', 'index': 0}], 'referral_key': []},
            ],
        }

        resp = self.client.post(reverse('entry:do_create', args=[entity.id]),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 200)

        # switch to guest user
        user = self.guest_login()

        entry = Entry.objects.get(name='entry1')
        self.assertEqual(len(entry.get_available_attrs(admin)), 2)
        self.assertEqual(len(entry.get_available_attrs(user)), 2)
        self.assertEqual(len(entry.get_available_attrs(user, ACLType.Writable)), 1)
        self.assertEqual(entry.get_available_attrs(user, ACLType.Writable)[0]['name'], 'attr1')

    @patch('entry.views.create_entry_attrs.delay', Mock(side_effect=tasks.create_entry_attrs))
    @patch('entry.views.edit_entry_attrs.delay', Mock(side_effect=tasks.edit_entry_attrs))
    def test_create_and_edit_entry_that_has_boolean_attr(self):
        admin = self.admin_login()

        entity = Entity.objects.create(name='entity', created_user=admin)
        entity_attr = EntityAttr.objects.create(name='attr_bool',
                                                type=AttrTypeValue['boolean'],
                                                parent_entity=entity,
                                                created_user=admin)
        entity.attrs.add(entity_attr)

        # creates entry that has a parameter which is typed boolean
        params = {
            'entry_name': 'entry',
            'attrs': [
                {'id': str(entity_attr.id), 'value': [{'data': True, 'index': 0}], 'referral_key': []},
            ],
        }
        resp = self.client.post(reverse('entry:do_create', args=[entity.id]),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 200)

        # get entry which is created in here
        entry = Entry.objects.get(name='entry', schema=entity)

        self.assertEqual(entry.attrs.count(), 1)
        self.assertIsNotNone(entry.attrs.last().get_latest_value())
        self.assertTrue(entry.attrs.last().get_latest_value().boolean)

        # edit entry to update the value of attribute 'attr_bool'
        params = {
            'entry_name': 'entry',
            'attrs': [
                {'id': str(entry.attrs.get(name='attr_bool').id), 'value': [{'data': False, 'index': 0}], 'referral_key': []},
            ],
        }
        resp = self.client.post(reverse('entry:do_edit', args=[entry.id]),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 200)

        # checks AttributeValue which is specified to update
        self.assertEqual(entry.attrs.last().values.count(), 2)
        self.assertFalse(entry.attrs.last().get_latest_value().boolean)

    def test_post_create_entry_without_mandatory_param(self):
        user = self.admin_login()

        entity = Entity.objects.create(name='Entity', is_public=False, created_user=user)
        attr_base = EntityAttr.objects.create(name='attr',
                                              type=AttrTypeStr,
                                              is_mandatory=True,
                                              parent_entity=entity,
                                              created_user=user)
        entity.attrs.add(attr_base)

        params = {
            'entry_name': 'entry',
            'attrs': [
                {'id': str(attr_base.id), 'value': [], 'referral_key': []},
            ],
        }
        resp = self.client.post(reverse('entry:do_create', args=[entity.id]),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 400)
        self.assertEqual(Entry.objects.count(), 0)
        self.assertEqual(Attribute.objects.count(), 0)
        self.assertEqual(AttributeValue.objects.count(), 0)

    def test_post_edit_entry_without_mandatory_param(self):
        user = self.admin_login()

        entity = Entity.objects.create(name='Entity', is_public=False, created_user=user)
        attr_base = EntityAttr.objects.create(name='attr',
                                              type=AttrTypeStr,
                                              is_mandatory=True,
                                              parent_entity=entity,
                                              created_user=user)
        entity.attrs.add(attr_base)

        entry = Entry.objects.create(name='Entry', schema=entity, created_user=user)
        entry.complement_attrs(user)

        params = {
            'entry_name': 'Updated Entry',
            'attrs': [
                {'id': str(entry.attrs.get(name='attr').id), 'value': [], 'referral_key': []},
            ],
        }
        resp = self.client.post(reverse('entry:do_edit', args=[entry.id]),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 400)
        self.assertEqual(Entry.objects.get(id=entry.id).name, 'Entry')

    @patch('entry.views.create_entry_attrs.delay', Mock(side_effect=tasks.create_entry_attrs))
    @patch('entry.views.edit_entry_attrs.delay', Mock(side_effect=tasks.edit_entry_attrs))
    @patch('entry.views.delete_entry.delay', Mock(side_effect=tasks.delete_entry))
    def test_referred_entry_cache(self):
        user = self.admin_login()

        ref_entity = Entity.objects.create(name='referred_entity', created_user=user)

        ref_entry1 = Entry.objects.create(name='referred1', schema=ref_entity, created_user=user)
        ref_entry2 = Entry.objects.create(name='referred2', schema=ref_entity, created_user=user)
        ref_entry3 = Entry.objects.create(name='referred3', schema=ref_entity, created_user=user)

        entity = Entity.objects.create(name='entity', created_user=user)
        entity.attrs.add(EntityAttr.objects.create(name='ref',
                                                   type=AttrTypeValue['object'],
                                                   parent_entity=entity,
                                                   created_user=user))
        entity.attrs.add(EntityAttr.objects.create(name='arr_ref',
                                                   type=AttrTypeValue['array_object'],
                                                   parent_entity=entity,
                                                   created_user=user))

        # set entity that target each attributes refer to
        [x.referral.add(ref_entity) for x in entity.attrs.all()]

        params = {
            'entry_name': 'entry',
            'attrs': [
                {
                    'id': str(entity.attrs.get(name='ref').id),
                    'value': [
                        {'data': str(ref_entry1.id), 'index': 0},
                    ],
                    'referral_key': [],
                },
                {
                    'id': str(entity.attrs.get(name='arr_ref').id),
                    'value': [
                        {'data': str(ref_entry1.id), 'index': 0},
                        {'data': str(ref_entry2.id), 'index': 1},
                    ],
                    'referral_key': [],
                },
            ],
        }
        resp = self.client.post(reverse('entry:do_create', args=[entity.id]),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 200)

        # checks referred_object cache is set
        entry = Entry.objects.get(name='entry')
        self.assertEqual(ref_entry1.get_cache(Entry.CACHE_REFERRED_ENTRY), ([entry], 2))
        self.assertEqual(ref_entry2.get_cache(Entry.CACHE_REFERRED_ENTRY), ([entry], 1))
        self.assertIsNone(ref_entry3.get_cache(Entry.CACHE_REFERRED_ENTRY))

        # checks referred_object cache will be updated by unrefering
        params = {
            'entry_name': 'entry',
            'attrs': [
                {'id': str(entry.attrs.get(name='ref').id), 'value': [], 'referral_key': []},
                {'id': str(entry.attrs.get(name='arr_ref').id), 'value': [], 'referral_key': []},
            ],
        }
        resp = self.client.post(reverse('entry:do_edit', args=[entry.id]),
                                json.dumps(params), 'application/json')

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(ref_entry1.get_cache(Entry.CACHE_REFERRED_ENTRY), ([], 0))
        self.assertEqual(ref_entry2.get_cache(Entry.CACHE_REFERRED_ENTRY), ([], 0))
        self.assertIsNone(ref_entry3.get_cache(Entry.CACHE_REFERRED_ENTRY))

        # checks referred_object cache will be updated by the edit processing
        params = {
            'entry_name': 'entry',
            'attrs': [
                {
                    'id': str(entry.attrs.get(name='ref').id),
                    'value': [
                        {'data': str(ref_entry2.id), 'index': 0},
                    ],
                    'referral_key': [],
                },
                {
                    'id': str(entry.attrs.get(name='arr_ref').id),
                    'value': [
                        {'data': str(ref_entry2.id), 'index': 0},
                        {'data': str(ref_entry3.id), 'index': 1},
                    ],
                    'referral_key': [],
                },
            ],
        }
        resp = self.client.post(reverse('entry:do_edit', args=[entry.id]),
                                json.dumps(params), 'application/json')

        self.assertEqual(resp.status_code, 200)

        # checks referred_object cache is updated by chaning referring
        self.assertEqual(ref_entry1.get_cache(Entry.CACHE_REFERRED_ENTRY), ([], 0))
        self.assertEqual(ref_entry2.get_cache(Entry.CACHE_REFERRED_ENTRY), ([entry], 2))
        self.assertEqual(ref_entry3.get_cache(Entry.CACHE_REFERRED_ENTRY), ([entry], 1))

        # delete referring entry and make sure that
        # the cahce of referred_entry of ref_entry is reset
        resp = self.client.post(reverse('entry:do_delete', args=[entry.id]),
                                json.dumps(params), 'application/json')

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(ref_entry1.get_cache(Entry.CACHE_REFERRED_ENTRY), ([], 0))
        self.assertEqual(ref_entry2.get_cache(Entry.CACHE_REFERRED_ENTRY), ([], 0))
        self.assertEqual(ref_entry3.get_cache(Entry.CACHE_REFERRED_ENTRY), ([], 0))

    @patch('entry.views.create_entry_attrs.delay', Mock(side_effect=tasks.create_entry_attrs))
    def test_create_entry_with_named_ref(self):
        user = self.admin_login()

        ref_entity = Entity.objects.create(name='referred_entity', created_user=user)
        ref_entry = Entry.objects.create(name='referred_entry', created_user=user, schema=ref_entity)

        entity = Entity.objects.create(name='entity', created_user=user)
        new_attr_params = {
            'name': 'named_ref',
            'type': AttrTypeValue['named_object'],
            'created_user': user,
            'parent_entity': entity,
        }
        attr_base = EntityAttr.objects.create(**new_attr_params)
        attr_base.referral.add(ref_entity)

        entity.attrs.add(attr_base)

        # try to create with empty params
        params = {
            'entry_name': 'new_entry1',
            'attrs': [{
                'id': str(attr_base.id),
                'referral_key': [],
                'value': [],
            }],
        }
        resp = self.client.post(reverse('entry:do_create', args=[entity.id]), json.dumps(params), 'application/json')
        self.assertEqual(resp.status_code, 200)

        entry = Entry.objects.get(name='new_entry1')
        self.assertEqual(entry.attrs.get(name='named_ref').values.count(), 0)

        # try to create only with value which is a reference for other entry
        params = {
            'entry_name': 'new_entry2',
            'attrs': [{
                'id': str(attr_base.id),
                'value': [{'data': str(ref_entry.id), 'index': 0}],
                'referral_key': [],
            }],
        }
        resp = self.client.post(reverse('entry:do_create', args=[entity.id]), json.dumps(params), 'application/json')
        self.assertEqual(resp.status_code, 200)

        entry = Entry.objects.get(name='new_entry2')
        self.assertEqual(entry.attrs.get(name='named_ref').values.count(), 1)
        self.assertEqual(entry.attrs.get(name='named_ref').values.last().value, '')
        self.assertEqual(entry.attrs.get(name='named_ref').values.last().referral.id, ref_entry.id)

        # try to create only with referral_key
        params = {
            'entry_name': 'new_entry3',
            'attrs': [{
                'id': str(attr_base.id),
                'value': [],
                'referral_key': [{'data': 'hoge', 'index': 0}],
            }],
        }
        resp = self.client.post(reverse('entry:do_create', args=[entity.id]), json.dumps(params), 'application/json')
        self.assertEqual(resp.status_code, 200)

        entry = Entry.objects.get(name='new_entry3')
        self.assertEqual(entry.attrs.get(name='named_ref').values.count(), 1)
        self.assertEqual(entry.attrs.get(name='named_ref').values.last().value, 'hoge')
        self.assertEqual(entry.attrs.get(name='named_ref').values.last().referral, None)

    @patch('entry.views.create_entry_attrs.delay', Mock(side_effect=tasks.create_entry_attrs))
    def test_create_entry_with_array_named_ref(self):
        user = self.admin_login()

        ref_entity = Entity.objects.create(name='referred_entity', created_user=user)
        ref_entry = Entry.objects.create(name='referred_entry', created_user=user, schema=ref_entity)

        entity = Entity.objects.create(name='entity', created_user=user)
        new_attr_params = {
            'name': 'arr_named_ref',
            'type': AttrTypeValue['array_named_object'],
            'created_user': user,
            'parent_entity': entity,
        }
        attr_base = EntityAttr.objects.create(**new_attr_params)
        attr_base.referral.add(ref_entity)

        entity.attrs.add(attr_base)

        params = {
            'entry_name': 'new_entry',
            'attrs': [{
                'id': str(attr_base.id),
                'value': [
                    {'data': str(ref_entry.id), 'index': 0},
                    {'data': str(ref_entry.id), 'index': 1},
                ],
                'referral_key': [
                    {'data': 'hoge', 'index': 1},
                    {'data': 'fuga', 'index': 2},
                ],
            }],
        }

        resp = self.client.post(reverse('entry:do_create', args=[entity.id]), json.dumps(params), 'application/json')
        self.assertEqual(resp.status_code, 200)

        entry = Entry.objects.get(name='new_entry')
        self.assertEqual(entry.attrs.get(name='arr_named_ref').values.count(), 1)

        attrv = entry.attrs.get(name='arr_named_ref').values.last()
        self.assertTrue(attrv.get_status(AttributeValue.STATUS_DATA_ARRAY_PARENT))
        self.assertEqual(attrv.data_array.count(), 3)

        self.assertEqual(attrv.data_array.all()[0].value, '')
        self.assertEqual(attrv.data_array.all()[0].referral.id, ref_entry.id)

        self.assertEqual(attrv.data_array.all()[1].value, 'hoge')
        self.assertEqual(attrv.data_array.all()[1].referral.id, ref_entry.id)

        self.assertEqual(attrv.data_array.all()[2].value, 'fuga')
        self.assertEqual(attrv.data_array.all()[2].referral, None)

    @patch('entry.views.edit_entry_attrs.delay', Mock(side_effect=tasks.edit_entry_attrs))
    def test_edit_entry_with_named_ref(self):
        user = self.admin_login()

        ref_entity = Entity.objects.create(name='referred_entity', created_user=user)
        ref_entry = Entry.objects.create(name='referred_entry', created_user=user, schema=ref_entity)

        entity = Entity.objects.create(name='entity', created_user=user)

        attr_base = EntityAttr.objects.create(**{
            'name': 'named_ref',
            'type': AttrTypeValue['named_object'],
            'created_user': user,
            'parent_entity': entity,
        })
        attr_base.referral.add(ref_entity)

        entity.attrs.add(attr_base)

        entry = Entry.objects.create(name='entry', created_user=user, schema=entity)
        entry.complement_attrs(user)

        attr = entry.attrs.get(name='named_ref')
        attr.values.add(AttributeValue.objects.create(**{
            'created_user': user,
            'parent_attr': attr,
            'value': 'hoge',
            'referral': ref_entry,
            'status': AttributeValue.STATUS_LATEST
        }))

        # try to update with same data (expected not to be updated)
        params = {
            'entry_name': 'updated_entry',
            'attrs': [{
                'id': str(entry.attrs.get(name='named_ref').id),
                'value': [{'data': str(ref_entry.id), 'index': 0}],
                'referral_key': [{'data': 'hoge', 'index': 0}],
            }],
        }
        resp = self.client.post(reverse('entry:do_edit', args=[entry.id]), json.dumps(params), 'application/json')
        self.assertEqual(resp.status_code, 200)

        updated_entry = Entry.objects.get(id=entry.id)
        self.assertEqual(updated_entry.name, 'updated_entry')
        self.assertEqual(updated_entry.attrs.get(name='named_ref').values.count(), 1)

        # try to update with different data (expected to be updated)
        ref_entry2 = Entry.objects.create(name='referred_entry2', created_user=user, schema=ref_entity)
        params = {
            'entry_name': 'updated_entry',
            'attrs': [{
                'id': str(entry.attrs.get(name='named_ref').id),
                'value': [{'data': str(ref_entry2.id), 'index': 0}],
                'referral_key': [{'data': 'fuga', 'index': 0}],
            }],
        }
        resp = self.client.post(reverse('entry:do_edit', args=[entry.id]), json.dumps(params), 'application/json')
        self.assertEqual(resp.status_code, 200)

        updated_entry = Entry.objects.get(id=entry.id)
        self.assertEqual(updated_entry.attrs.get(name='named_ref').values.count(), 2)
        self.assertEqual(updated_entry.attrs.get(name='named_ref').values.last().value, 'fuga')
        self.assertEqual(updated_entry.attrs.get(name='named_ref').values.last().referral.id, ref_entry2.id)

    @patch('entry.views.edit_entry_attrs.delay', Mock(side_effect=tasks.edit_entry_attrs))
    def test_edit_entry_with_array_named_ref(self):
        user = self.admin_login()

        ref_entity = Entity.objects.create(name='referred_entity', created_user=user)
        ref_entry = Entry.objects.create(name='referred_entry', created_user=user, schema=ref_entity)

        entity = Entity.objects.create(name='entity', created_user=user)
        new_attr_params = {
            'name': 'arr_named_ref',
            'type': AttrTypeValue['array_named_object'],
            'created_user': user,
            'parent_entity': entity,
        }
        attr_base = EntityAttr.objects.create(**new_attr_params)
        attr_base.referral.add(ref_entity)

        entity.attrs.add(attr_base)

        # create an Entry associated to the 'entity'
        entry = Entry.objects.create(name='entry', created_user=user, schema=entity)
        entry.complement_attrs(user)

        attr = entry.attrs.get(name='arr_named_ref')
        self.assertTrue(attr.is_updated([ref_entry.id]))

        attrv = attr.get_latest_value()

        r_entries = []
        for i in range(0, 3):
            r_entry = Entry.objects.create(name='r_%d' % i, created_user=user, schema=ref_entity)
            r_entries.append(r_entry.id)

            attrv.data_array.add(AttributeValue.objects.create(**{
                'parent_attr': attr,
                'created_user': user,
                'status': AttributeValue.STATUS_LATEST,
                'value': 'key_%d' % i,
                'referral': r_entry,
            }))

        attr.values.add(attrv)

        # try to update with same data (expected not to be updated)
        params = {
            'entry_name': 'updated_entry',
            'attrs': [{
                'id': str(entry.attrs.get(name='arr_named_ref').id),
                'value': [{'data': str(r), 'index': i} for i, r in enumerate(r_entries)],
                'referral_key': [{'data': 'key_%d' % i, 'index': i} for i in range(0, 3)],
            }],
        }
        resp = self.client.post(reverse('entry:do_edit', args=[entry.id]), json.dumps(params), 'application/json')
        self.assertEqual(resp.status_code, 200)

        updated_entry = Entry.objects.get(id=entry.id)
        self.assertEqual(updated_entry.name, 'updated_entry')
        self.assertEqual(updated_entry.attrs.get(name='arr_named_ref').values.count(), 1)

        # try to update with different data (expected to be updated)
        params = {
            'entry_name': 'updated_entry',
            'attrs': [{
                'id': str(entry.attrs.get(name='arr_named_ref').id),
                'value': [
                    {'data': r_entries[1], 'index': 1},
                    {'data': r_entries[2], 'index': 2},
                ],
                'referral_key': [{'data': 'hoge_%d' % i, 'index': i} for i in range(0, 2)],
            }],
        }
        resp = self.client.post(reverse('entry:do_edit', args=[entry.id]), json.dumps(params), 'application/json')
        self.assertEqual(resp.status_code, 200)

        updated_entry = Entry.objects.get(id=entry.id)
        self.assertEqual(updated_entry.attrs.get(name='arr_named_ref').values.count(), 2)

        new_attrv = updated_entry.attrs.get(name='arr_named_ref').values.last()
        self.assertEqual(new_attrv.data_array.count(), 3)
        self.assertEqual(new_attrv.data_array.all()[0].value, 'hoge_0')
        self.assertIsNone(new_attrv.data_array.all()[0].referral)
        self.assertEqual(new_attrv.data_array.all()[1].value, 'hoge_1')
        self.assertEqual(new_attrv.data_array.all()[1].referral.id,
                         Entry.objects.get(id=r_entries[1]).id)
        self.assertEqual(new_attrv.data_array.all()[2].value, '')
        self.assertEqual(new_attrv.data_array.all()[2].referral.id,
                         Entry.objects.get(id=r_entries[2]).id)

        # try to update with same data but order is different (expected not to be updated)
        params = {
            'entry_name': 'updated_entry',
            'attrs': [{
                'id': str(entry.attrs.get(name='arr_named_ref').id),
                'value': [
                    {'data': r_entries[2], 'index': 2},
                    {'data': r_entries[1], 'index': 1},
                ],
                'referral_key': [
                    {'data': 'hoge_1', 'index': 1},
                    {'data': 'hoge_0', 'index': 0},
                ],
            }],
        }
        resp = self.client.post(reverse('entry:do_edit', args=[entry.id]), json.dumps(params), 'application/json')
        self.assertEqual(resp.status_code, 200)

        updated_entry = Entry.objects.get(id=entry.id)
        self.assertEqual(updated_entry.attrs.get(name='arr_named_ref').values.count(), 2)
