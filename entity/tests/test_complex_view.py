import json

from airone.lib.test import AironeViewTest
from airone.lib.types import AttrTypeStr, AttrTypeObj, AttrTypeText
from airone.lib.types import AttrTypeArrStr, AttrTypeArrObj

from django.urls import reverse

from entity.models import Entity
from entry.models import Entry, Attribute, AttributeValue


class ComplexViewTest(AironeViewTest):
    """
    This has complex tests that combine multiple requests across the inter-applicational
    """

    # This is the test to confirm the fix of the problem of #152.
    def test_add_attr_after_creating_entry(self):
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
                'ref_id': refer_entity.id,
                'is_mandatory': True,
                'row_index': '3',
            }],
        }
        resp = self.client.post(reverse('entity:do_edit', args=[entity.id]),
                                json.dumps(params),
                                'application/json')
        self.assertEqual(resp.status_code, 303)

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
