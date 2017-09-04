import json
import yaml

from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import Group

from entity.models import Entity, EntityAttr
from entry.models import Entry, Attribute, AttributeValue
from user.models import User

from airone.lib.types import AttrTypeStr, AttrTypeObj, AttrTypeArrStr, AttrTypeArrObj
from airone.lib.test import AironeViewTest
from xml.etree import ElementTree


class ViewTest(AironeViewTest):
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

    def test_get_index_without_login(self):
        resp = self.client.get(reverse('entry:index', args=[0]))
        self.assertEqual(resp.status_code, 303)

    def test_get_index_with_login(self):
        self.admin_login()

        resp = self.client.get(reverse('entry:index', args=[self._entity.id]))
        self.assertEqual(resp.status_code, 200)

        root = ElementTree.fromstring(resp.content.decode('utf-8'))
        self.assertIsNone(root.find('.//tbody/tr/td'))

    def test_get_index_with_entries(self):
        user = self.admin_login()

        Entry(name='fuga', schema=self._entity, created_user=user).save()

        resp = self.client.get(reverse('entry:index', args=[self._entity.id]))
        self.assertEqual(resp.status_code, 200)

        root = ElementTree.fromstring(resp.content.decode('utf-8'))
        self.assertIsNotNone(root.find('.//tbody/tr/td'))

    def test_get_permitted_entries(self):
        user = self.admin_login()

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
        user = self.admin_login()

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
                {'id': '0', 'value': 'fuga'},
            ],
        }
        resp = self.client.post(reverse('entry:do_create', args=[0]),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 401)
        self.assertEqual(Entry.objects.count(), 0)
        self.assertEqual(Attribute.objects.count(), 0)
        self.assertEqual(AttributeValue.objects.count(), 0)

    def test_post_with_login(self):
        self.admin_login()

        params = {
            'entry_name': 'hoge',
            'attrs': [
                {'id': str(self._entity_attr.id), 'value': 'hoge'},
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
        self.assertEqual(entry.attrs.last().values.last(), AttributeValue.objects.last())

    def test_post_create_entry_without_permission(self):
        self.admin_login()

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
                {'id': str(attr_base.id), 'value': 'hoge'},
            ],
        }
        resp = self.client.post(reverse('entry:do_create', args=[entity.id]),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 400)
        self.assertEqual(Entry.objects.count(), 0)
        self.assertEqual(Attribute.objects.count(), 0)
        self.assertEqual(AttributeValue.objects.count(), 0)

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
                {'id': str(self._entity_attr.id), 'value': 'hoge'},
                {'id': str(self._entity_attr_optional.id), 'value': ''},
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

    def test_post_with_lack_of_params(self):
        self.admin_login()

        params = {
            'entry_name': '',
            'attrs': [
                {'id': str(self._entity_attr.id), 'value': 'hoge'},
            ],
        }
        resp = self.client.post(reverse('entry:do_create', args=[self._entity.id]),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 400)
        self.assertEqual(Entry.objects.count(), 0)
        self.assertEqual(Attribute.objects.count(), 0)
        self.assertEqual(AttributeValue.objects.count(), 0)

    def test_post_create_with_referral(self):
        user = self.admin_login()

        attr_base = EntityAttr.objects.create(name='attr_with_referral',
                                                 created_user=user,
                                                 type=AttrTypeObj,
                                                 referral=self._entity,
                                                 parent_entity=self._entity,
                                                 is_mandatory=False)
        self._entity.attrs.add(attr_base)

        entry = Entry.objects.create(name='entry', schema=self._entity, created_user=user)

        params = {
            'entry_name': 'new_entry',
            'attrs': [
                {'id': str(self._entity_attr.id), 'value': 'hoge'},
                {'id': str(attr_base.id), 'value': str(entry.id)},
            ],
        }
        resp = self.client.post(reverse('entry:do_create', args=[self._entity.id]),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Entry.objects.count(), 2)
        self.assertEqual(Entry.objects.last().name, 'new_entry')
        self.assertEqual(Entry.objects.last().attrs.last().type, AttrTypeObj)
        self.assertEqual(Entry.objects.last().attrs.last().values.count(), 1)
        self.assertEqual(Entry.objects.last().attrs.last().values.last().value, '')
        self.assertEqual(Entry.objects.last().attrs.last().values.last().referral.id, entry.id)

    def test_post_with_invalid_param(self):
        self.admin_login()

        params = {
            'entry_name': 'hoge',
            'attrs': [
                {'id': str(self._entity_attr.id), 'value': 'hoge'},
                {'id': '9999', 'value': 'invalid value'},
            ],
        }
        resp = self.client.post(reverse('entry:do_create', args=[self._entity.id]),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 400)
        self.assertEqual(Entry.objects.count(), 0)
        self.assertEqual(Attribute.objects.count(), 0)
        self.assertEqual(AttributeValue.objects.count(), 0)

    def test_post_without_entry(self):
        user = self.admin_login()

        attr_base = EntityAttr.objects.create(name='ref_attr',
                                                 created_user=user,
                                                 type=AttrTypeObj,
                                                 referral=self._entity,
                                                 parent_entity=self._entity,
                                                 is_mandatory=False)
        self._entity.attrs.add(attr_base)

        params = {
            'entry_name': 'new_entry',
            'attrs': [
                {'id': str(self._entity_attr.id), 'value': 'hoge'},
                {'id': str(attr_base.id), 'value': '0'},
            ],
        }
        resp = self.client.post(reverse('entry:do_create', args=[self._entity.id]),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Entry.objects.last().attrs.get(name='ref_attr').values.last().value, '')

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
            attr = Attribute(name=attr_name,
                             type=AttrTypeStr,
                             is_mandatory=True,
                             parent_entry=entry,
                             created_user=user)
            attr.save()

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

        attr = Attribute(name='foo',
                         created_user=user,
                         is_mandatory=False,
                         parent_entry=entry,
                         type=AttrTypeStr)
        attr.save()
        entry.attrs.add(attr)

        # with invalid entry-id
        resp = self.client.get(reverse('entry:edit', args=[entry.id]))
        self.assertEqual(resp.status_code, 200)

    def test_post_edit_without_login(self):
        params = {'attrs': [{'id': '0', 'value': ['hoge']}]}
        resp = self.client.post(reverse('entry:do_edit', args=[0]),
                                json.dumps(params), 'application/json')

        self.assertEqual(resp.status_code, 401)
        self.assertEqual(AttributeValue.objects.count(), 0)

    def test_post_edit_with_invalid_param(self):
        self.admin_login()

        params = {'attrs': [{'id': '0', 'value': ['hoge']}]}
        resp = self.client.post(reverse('entry:do_edit', args=[0]),
                                json.dumps(params), 'application/json')

        self.assertEqual(resp.status_code, 400)
        self.assertEqual(AttributeValue.objects.count(), 0)

    def test_post_edit_with_valid_param(self):
        user = self.admin_login()

        # making test Entry set
        entry = Entry(name='fuga', schema=self._entity, created_user=user)
        entry.save()

        for attr_name in ['foo', 'bar']:
            attr = Attribute(name=attr_name,
                             created_user=user,
                             is_mandatory=True,
                             parent_entry=entry,
                             type=AttrTypeStr)
            attr.save()

            attr_value = AttributeValue(value='hoge', created_user=user, parent_attr=attr)
            attr_value.save()

            attr.values.add(attr_value)
            entry.attrs.add(attr)

        params = {
            'entry_name': 'hoge',
            'attrs': [
                {'id': str(Attribute.objects.get(name='foo').id), 'value': ['hoge']},
                {'id': str(Attribute.objects.get(name='bar').id), 'value': ['fuga']},
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

    def test_post_edit_with_optional_params(self):
        user = self.admin_login()

        # making test Entry set
        entry = Entry(name='fuga', schema=self._entity, created_user=user)
        entry.save()

        for attr_name in ['foo', 'bar']:
            attr = Attribute(name=attr_name,
                             created_user=user,
                             is_mandatory=False,
                             parent_entry=entry,
                             type=AttrTypeStr)
            attr.save()
            entry.attrs.add(attr)

        params = {
            'entry_name': entry.name,
            'attrs': [
                # include blank value
                {'id': str(Attribute.objects.get(name='foo').id), 'value': ['']},
                {'id': str(Attribute.objects.get(name='bar').id), 'value': ['fuga']},
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

    def test_post_edit_with_array_string_value(self):
        user = self.admin_login()

        entity = Entity.objects.create(name='entity', created_user=user)
        entry = Entry.objects.create(name='entry', created_user=user, schema=entity)

        attr = Attribute.objects.create(name='attr',
                                        type=AttrTypeArrStr,
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
            'attrs': [
                # include blank value
                {'id': str(attr.id), 'value': ['hoge', 'puyo']},
            ],
        }
        resp = self.client.post(reverse('entry:do_edit', args=[entry.id]),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 200)
        # status=0 means leaf value
        self.assertEqual(AttributeValue.objects.filter(status=0).count(), 3)
        # status=1 means parent value
        self.assertEqual(AttributeValue.objects.filter(status=1).count(), 2)
        self.assertEqual(attr.values.count(), 2)
        self.assertTrue(attr.values.last().status & AttributeValue.STATUS_DATA_ARRAY_PARENT)

        self.assertEqual(attr.values.last().data_array.count(), 2)
        self.assertTrue(all([x.value in ['hoge', 'puyo'] for x in attr.values.last().data_array.all()]))

    def test_post_edit_with_array_object_value(self):
        user = self.admin_login()

        entity = Entity.objects.create(name='entity', created_user=user)
        entry = Entry.objects.create(name='entry', created_user=user, schema=entity)

        e1 = Entry.objects.create(name='E1', created_user=user, schema=entity)
        e2 = Entry.objects.create(name='E2', created_user=user, schema=entity)
        e3 = Entry.objects.create(name='E3', created_user=user, schema=entity)

        attr = Attribute.objects.create(name='attr',
                                        type=AttrTypeArrObj,
                                        created_user=user,
                                        parent_entry=entry,
                                        referral=entity)

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
            'attrs': [
                # include blank value
                {'id': str(attr.id), 'value': [e2.id, e3.id]},
            ],
        }
        resp = self.client.post(reverse('entry:do_edit', args=[entry.id]),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 200)
        # status=0 means leaf value
        self.assertEqual(AttributeValue.objects.filter(status=0).count(), 3)
        # status=1 means parent value
        self.assertEqual(AttributeValue.objects.filter(status=1).count(), 2)
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
            attr = Attribute(name=attr_name,
                             created_user=user,
                             is_mandatory=True,
                             parent_entry=entry,
                             type=AttrTypeStr)
            attr.save()

            for value in ['hoge', 'fuga']:
                attr_value = AttributeValue(value=value, created_user=user, parent_attr=attr)
                attr_value.save()

                attr.values.add(attr_value)

            entry.attrs.add(attr)

        resp = self.client.get(reverse('entry:show', args=[entry.id]))
        self.assertEqual(resp.status_code, 200)

    def test_post_edit_with_referral(self):
        user = self.admin_login()

        attr_base = EntityAttr.objects.create(name='attr_with_referral',
                                                 created_user=user,
                                                 type=AttrTypeObj,
                                                 referral=self._entity,
                                                 parent_entity=self._entity,
                                                 is_mandatory=False)
        self._entity.attrs.add(attr_base)

        entry = Entry.objects.create(name='old_entry', schema=self._entity, created_user=user)

        attr = entry.add_attribute_from_base(attr_base, user)
        attr_value = AttributeValue.objects.create(referral=entry,
                                                   created_user=user,
                                                   parent_attr=attr)
        attr.values.add(attr_value)

        new_entry = Entry.objects.create(name='new_entry', schema=self._entity, created_user=user)

        params = {
            'entry_name': 'new_entry',
            'attrs': [
                {'id': str(attr.id), 'value': [str(new_entry.id)]},
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

    def test_post_edit_without_referral_value(self):
        user = self.admin_login()

        attr_base = EntityAttr.objects.create(name='attr_with_referral',
                                                 created_user=user,
                                                 type=AttrTypeObj,
                                                 referral=self._entity,
                                                 parent_entity=self._entity,
                                                 is_mandatory=False)
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
                {'id': str(attr.id), 'value': ['0']},
            ],
        }
        resp = self.client.post(reverse('entry:do_edit', args=[entry.id]),
                                json.dumps(params), 'application/json')

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(attr.values.count(), 2)
        self.assertEqual(attr.values.last().value, '')

    def test_get_export(self):
        user = self.admin_login()

        entry = Entry(name='fuga', schema=self._entity, created_user=user)
        entry.save()

        for attr_name in ['foo', 'bar']:
            attr = Attribute(name=attr_name,
                             type=AttrTypeStr,
                             is_mandatory=True,
                             parent_entry=entry,
                             created_user=user)
            attr.save()

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

    def test_post_delete_entry(self):
        user = self.admin_login()

        entry = Entry(name='fuga', schema=self._entity, created_user=user)
        entry.save()

        entry.attrs.add(Attribute.objects.create(name='attr-test',
                                                 type=AttrTypeStr,
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
        self.assertFalse(Attribute.objects.get(name='attr-test').is_active)

    def test_post_delete_entry_without_permission(self):
        user1 = self.admin_login()
        user2 = User(username='nyaa')
        user2.save()

        entry = Entry(name='fuga', schema=self._entity, created_user=user2, is_public=False)
        entry.save()

        entry_count = Entry.objects.count()

        params = {}

        resp = self.client.post(reverse('entry:do_delete', args=[entry.id]),
                                json.dumps(params), 'application/json')

        self.assertEqual(resp.status_code, 400)

        self.assertEqual(Entry.objects.count(), entry_count)

        entry = Entry.objects.last()
        self.assertTrue(entry.is_active)

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
            'attrs': [
                {'id': str(attr_base.id), 'value': 'hoge'},
                {'id': str(attr_base.id), 'value': 'fuga'},
                {'id': str(attr_base.id), 'value': 'puyo'},
            ],
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

    def test_post_create_array_object_attribute(self):
        user = self.admin_login()

        # create a test data set
        entity = Entity.objects.create(name='entity-test',
                                       created_user=user)

        attr_base = EntityAttr.objects.create(name='attr-ref-test',
                                                 created_user=user,
                                                 type=AttrTypeArrObj,
                                                 referral=self._entity,
                                                 parent_entity=self._entity,
                                                 is_mandatory=False)
        entity.attrs.add(attr_base)

        referral = Entry.objects.create(name='entry0', schema=self._entity, created_user=user)

        params = {
            'entry_name': 'entry-test',
            'attrs': [
                {'id': str(attr_base.id), 'value': str(referral.id)},
                {'id': str(attr_base.id), 'value': str(referral.id)},
            ],
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
