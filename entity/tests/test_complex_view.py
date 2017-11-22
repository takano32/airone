import json

from airone.lib.acl import ACLType
from airone.lib.test import AironeViewTest
from airone.lib.types import AttrTypeStr, AttrTypeObj, AttrTypeText
from airone.lib.types import AttrTypeArrStr, AttrTypeArrObj

from django.urls import reverse

from entity.models import Entity, EntityAttr
from entry.models import Entry, Attribute, AttributeValue


class ComplexViewTest(AironeViewTest):
    """
    This has complex tests that combine multiple requests across the inter-applicational
    """

    def test_add_attr_after_creating_entry(self):
        """
        This test executes followings
        - create a new Entity(entity) with an EntityAttr(attr)
        - create a new Entry for entity
        - update entity to append new EntityAttrs(arr-str, arr-obj)

        Then, this checks following
        - created additional Attributes which are corresponding to the added EntityAttrs
          automatically for accessing show page.
        - enable to edit entry correctly because #152 is fixed
        """
        user = self.admin_login()

        # create an Entity
        params = {
            'name': 'entity',
            'note': '',
            'is_toplevel': False,
            'attrs': [
                {'name': 'attr', 'type': str(AttrTypeStr), 'is_mandatory': False, 'row_index': '1'},
            ],
        }
        resp = self.client.post(reverse('entity:do_create'),
                                json.dumps(params),
                                'application/json')
        self.assertEqual(resp.status_code, 303)

        # get created objects
        entity = Entity.objects.get(name='entity')
        attr = entity.attrs.get(name='attr')

        # create an Entry for the created entity
        params = {
            'entry_name': 'entry',
            'attrs': [
                {'id': str(attr.id), 'value': 'attr-value'},
            ],
        }
        resp = self.client.post(reverse('entry:do_create', args=[entity.id]),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 200)

        # get created entry object
        entry = Entry.objects.get(name='entry')
        refer_entity = Entity.objects.create(name='E0', note='', created_user=user)

        # edit entity to append a new Array attributes
        params = {
            'name': 'entry',
            'note': '',
            'is_toplevel': False,
            'attrs': [{
                'id': str(attr.id),
                'name': attr.name,
                'type': str(attr.type),
                'is_mandatory': attr.is_mandatory,
                'row_index': '1',
            },
            {
                'name': 'arr-str',
                'type': str(AttrTypeArrStr),
                'is_mandatory': True,
                'row_index': '2',
            },
            {
                'name': 'arr-obj',
                'type': str(AttrTypeArrObj),
                'ref_ids': [refer_entity.id],
                'is_mandatory': True,
                'row_index': '3',
            }],
        }
        resp = self.client.post(reverse('entity:do_edit', args=[entity.id]),
                                json.dumps(params),
                                'application/json')
        self.assertEqual(resp.status_code, 303)

        # Checks that the Attributes associated to the added EntityAttrs are not created
        self.assertEqual(entity.attrs.count(), 3)
        self.assertEqual(entry.attrs.count(), 1)

        resp = self.client.get(reverse('entry:show', args=[entry.id]))
        self.assertEqual(resp.status_code, 200)

        # Checks that the new Attibutes is created in the show processing
        self.assertEqual(entity.attrs.count(), 3)
        self.assertEqual(entry.attrs.count(), entity.attrs.count())

        attr_str = entry.attrs.get(name=attr.name)
        attr_arr_str = entry.attrs.get(name='arr-str')
        attr_arr_obj = entry.attrs.get(name='arr-obj')
        refer_entry = Entry.objects.create(name='e0', schema=refer_entity, created_user=user)

        attr_str_value_count = attr_str.values.count()
        attr_arr_str_value_count = attr_arr_str.values.count()
        attr_arr_obj_value_count = attr_arr_obj.values.count()

        self.assertEqual(attr_str_value_count, 1)
        self.assertEqual(attr_arr_str_value_count, 1)
        self.assertEqual(attr_arr_obj_value_count, 1)

        # edit to add values to the new attributes
        params = {
            'entry_name': entry.name,
            'attrs': [
                {'id': str(attr_str.id), 'value': ['hoge']},
                {'id': str(attr_arr_str.id), 'value': ['foo', 'bar']},
                {'id': str(attr_arr_obj.id), 'value': [refer_entry.id]},
            ],
        }
        resp = self.client.post(reverse('entry:do_edit', args=[entry.id]),
                                json.dumps(params),
                                'application/json')
        self.assertEqual(resp.status_code, 200)

        # check updated values structure and count of AttributeValues
        self.assertEqual(attr_str.values.count(), attr_str_value_count + 1)
        self.assertEqual(attr_arr_str.values.count(), attr_arr_str_value_count + 1)
        self.assertEqual(attr_arr_obj.values.count(), attr_arr_obj_value_count + 1)

        value_arr_str = attr_arr_str.values.last()
        self.assertEqual(value_arr_str.data_array.count(), 2)

        value_arr_obj = attr_arr_obj.values.last()
        self.assertEqual(value_arr_obj.data_array.count(), 1)


    def test_inherite_attribute_acl(self):
        """
        This test executes followings
        - create a new Entity(entity) with an EntityAttr(attr)
        - change ACL of attr to be private by admin user
        - create a new Entry(entry1) from entity by admin user
        - switch the user to guest
        - create a new Entry(entry2) from entity by guest user

        Then, this checks following
        - The Entry(entry1) whcih is created by the admin user has one Attribute
        - The Entry(entry2) whcih is created by the guest user has no Attribute
        """
        user = self.admin_login()

        # create an Entity
        params = {
            'name': 'entity',
            'note': '',
            'is_toplevel': False,
            'attrs': [
                {'name': 'attr', 'type': str(AttrTypeStr), 'is_mandatory': False, 'row_index': '1'},
            ],
        }
        resp = self.client.post(reverse('entity:do_create'),
                                json.dumps(params),
                                'application/json')
        self.assertEqual(resp.status_code, 303)
        self.assertEqual(EntityAttr.objects.count(), 1)

        # set acl of attr
        entityattr = EntityAttr.objects.get(name='attr')
        params = {
            'object_id': str(entityattr.id),
            'object_type': str(entityattr.objtype),
            'acl': [
                {
                    'member_id': str(user.id),
                    'member_type': 'user',
                    'value': str(ACLType.Full.id)
                }
            ],
            'default_permission': str(ACLType.Nothing.id),
        }
        resp = self.client.post(reverse('acl:set'), json.dumps(params), 'application/json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Entity.objects.count(), 1)
        self.assertFalse(EntityAttr.objects.get(name='attr').is_public)

        # create Entity by admin
        entity = Entity.objects.get(name='entity')
        params = {
            'entry_name': 'entry1',
            'attrs': [
                {'id': str(entityattr.id), 'value': 'attr-value'},
            ],
        }
        resp = self.client.post(reverse('entry:do_create', args=[entity.id]),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Entry.objects.count(), 1)
        self.assertEqual(Entry.objects.get(name='entry1').attrs.count(), 1)

        # switch to guest user
        guest = self.guest_login()
        entity = Entity.objects.get(name='entity')
        params = {
            'entry_name': 'entry2',
            'attrs': [
                {'id': str(entityattr.id), 'value': 'attr-value'},
            ],
        }
        resp = self.client.post(reverse('entry:do_create', args=[entity.id]),
                                json.dumps(params),
                                'application/json')

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Entry.objects.count(), 2)
        self.assertEqual(Entry.objects.get(name='entry2').attrs.count(), 0)
