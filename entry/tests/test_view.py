import json

from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import Group

from entity.models import Entity, AttributeBase
from entry.models import Entry, Attribute, AttributeValue
from user.models import User

from airone.lib.types import AttrTypeStr, AttrTypeObj
from airone.lib.test import AironeViewTest
from xml.etree import ElementTree


class ViewTest(AironeViewTest):
    # override 'admin_login' method to create initial Entity/AttributeBase objects
    def admin_login(self):
        user = super(ViewTest, self).admin_login()

        # create test entity which is a base of creating entry
        self._entity = Entity(name='hoge', created_user=user)
        self._entity.save()

        # set AttributeBase for the test Entity object
        self._attr_base = AttributeBase(name='test',
                                        type=AttrTypeStr,
                                        is_mandatory=True,
                                        created_user=user)
        self._attr_base.save()
        self._entity.attr_bases.add(self._attr_base)

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
        group.permissions.add(entity.deletable)

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
                {'id': str(self._attr_base.id), 'value': 'hoge'},
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

    def test_post_with_optional_parameter(self):
        user = self.admin_login()

        # add an optional AttributeBase to the test Entity object
        self._attr_base_optional = AttributeBase(name='test-optional',
                                                 type=AttrTypeStr,
                                                 is_mandatory=False,
                                                 created_user=user)
        self._attr_base_optional.save()
        self._entity.attr_bases.add(self._attr_base_optional)

        params = {
            'entry_name': 'hoge',
            'attrs': [
                {'id': str(self._attr_base.id), 'value': 'hoge'},
                {'id': str(self._attr_base_optional.id), 'value': ''},
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
                {'id': str(self._attr_base.id), 'value': 'hoge'},
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

        attr_base = AttributeBase.objects.create(name='attr_with_referral',
                                                 created_user=user,
                                                 type=AttrTypeObj,
                                                 referral=self._entity,
                                                 is_mandatory=False)
        self._entity.attr_bases.add(attr_base)

        entry = Entry.objects.create(name='entry', schema=self._entity, created_user=user)

        params = {
            'entry_name': 'new_entry',
            'attrs': [
                {'id': str(self._attr_base.id), 'value': 'hoge'},
                {'id': str(attr_base.id), 'value': str(entry.id)},
            ],
        }
        resp = self.client.post(reverse('entry:do_create', args=[self._entity.id]),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Entry.objects.count(), 2)
        self.assertEqual(Entry.objects.last().name, 'new_entry')
        self.assertEqual(Entry.objects.last().attrs.last().values.count(), 1)
        self.assertEqual(Entry.objects.last().attrs.last().values.last().value, '')
        self.assertEqual(Entry.objects.last().attrs.last().values.last().referral.id, entry.id)

    def test_post_with_invalid_param(self):
        self.admin_login()

        params = {
            'entry_name': 'hoge',
            'attrs': [
                {'id': str(self._attr_base.id), 'value': 'hoge'},
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
                             created_user=user)
            attr.save()

            for value in ['hoge', 'fuga']:
                attr_value = AttributeValue(value=value, created_user=user)
                attr_value.save()

                attr.values.add(attr_value)

            entry.attrs.add(attr)

        # with invalid entry-id
        resp = self.client.get(reverse('entry:edit', args=[entry.id]))
        self.assertEqual(resp.status_code, 200)

        e_input = ElementTree.fromstring(resp.content.decode('utf-8')).find('.//table/tr/td/input')
        self.assertIsNotNone(e_input)
        self.assertEqual(Attribute.objects.get(id=e_input.attrib['attr_id']).values.last().value,
                         e_input.attrib['value'])
        self.assertEqual(Attribute.objects.get(id=e_input.attrib['attr_id']).values.last().referral,
                         None)

    def test_get_edit_with_optional_attr(self):
        user = self.admin_login()

        # making test Entry set
        entry = Entry(name='fuga', schema=self._entity, created_user=user)
        entry.save()

        attr = Attribute(name='foo',
                         created_user=user,
                         is_mandatory=False,
                         type=AttrTypeStr)
        attr.save()
        entry.attrs.add(attr)

        # with invalid entry-id
        resp = self.client.get(reverse('entry:edit', args=[entry.id]))
        self.assertEqual(resp.status_code, 200)

        e_input = ElementTree.fromstring(resp.content.decode('utf-8')).find('.//table/tr/td/input')
        self.assertIsNotNone(e_input)
        self.assertEqual(e_input.attrib['value'], '')

    def test_post_edit_without_login(self):
        params = {'attrs': [{'id': '0', 'value': 'hoge'}]}
        resp = self.client.post(reverse('entry:do_edit'),
                                json.dumps(params), 'application/json')

        self.assertEqual(resp.status_code, 401)
        self.assertEqual(AttributeValue.objects.count(), 0)

    def test_post_edit_with_invalid_param(self):
        self.admin_login()

        params = {'attrs': [{'id': '0', 'value': 'hoge'}]}
        resp = self.client.post(reverse('entry:do_edit'),
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
                             type=AttrTypeStr)
            attr.save()

            attr_value = AttributeValue(value='hoge', created_user=user)
            attr_value.save()

            attr.values.add(attr_value)
            entry.attrs.add(attr)

        params = {
            'entry_id': str(entry.id),
            'entry_name': 'hoge',
            'attrs': [
                {'id': str(Attribute.objects.get(name='foo').id), 'value': 'hoge'}, # same value
                {'id': str(Attribute.objects.get(name='bar').id), 'value': 'fuga'},
            ],
        }
        resp = self.client.post(reverse('entry:do_edit'), json.dumps(params), 'application/json')

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
                             type=AttrTypeStr)
            attr.save()
            entry.attrs.add(attr)

        params = {
            'entry_name': entry.name,
            'entry_id': str(entry.id),
            'attrs': [
                {'id': str(Attribute.objects.get(name='foo').id), 'value': ''}, # blank value
                {'id': str(Attribute.objects.get(name='bar').id), 'value': 'fuga'},
            ],
        }
        resp = self.client.post(reverse('entry:do_edit'), json.dumps(params), 'application/json')

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(AttributeValue.objects.count(), 1)
        self.assertEqual(Attribute.objects.get(name='foo').values.count(), 0)
        self.assertEqual(Attribute.objects.get(name='bar').values.count(), 1)
        self.assertEqual(Attribute.objects.get(name='bar').values.last().value, 'fuga')
        self.assertEqual(Entry.objects.get(id=entry.id).name, entry.name)

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
                             type=AttrTypeStr)
            attr.save()

            for value in ['hoge', 'fuga']:
                attr_value = AttributeValue(value=value, created_user=user)
                attr_value.save()

                attr.values.add(attr_value)

            entry.attrs.add(attr)

        resp = self.client.get(reverse('entry:show', args=[entry.id]))
        self.assertEqual(resp.status_code, 200)

    def test_post_edit_with_referral(self):
        user = self.admin_login()

        attr_base = AttributeBase.objects.create(name='attr_with_referral',
                                                 created_user=user,
                                                 type=AttrTypeObj,
                                                 referral=self._entity,
                                                 is_mandatory=False)
        self._entity.attr_bases.add(attr_base)

        entry = Entry.objects.create(name='old_entry', schema=self._entity, created_user=user)

        attr = entry.add_attribute_from_base(attr_base, user)
        attr_value = AttributeValue.objects.create(referral=entry, created_user=user)
        attr.values.add(attr_value)

        new_entry = Entry.objects.create(name='new_entry', schema=self._entity, created_user=user)

        params = {
            'entry_name': 'new_entry',
            'entry_id': str(entry.id),
            'attrs': [
                {'id': str(attr.id), 'value': str(new_entry.id)},
            ],
        }
        resp = self.client.post(reverse('entry:do_edit'), json.dumps(params), 'application/json')

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(entry.attrs.last().values.count(), 2)
        self.assertEqual(entry.attrs.last().values.first().value, '')
        self.assertEqual(entry.attrs.last().values.first().referral.id, entry.id)
        self.assertEqual(entry.attrs.last().values.last().value, '')
        self.assertEqual(entry.attrs.last().values.last().referral.id, new_entry.id)
