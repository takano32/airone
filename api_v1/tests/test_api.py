import re
import json
import yaml

from django.test import Client

from airone.lib.test import AironeViewTest
from airone.lib.types import AttrTypeValue

from entity.models import Entity, EntityAttr
from entry.models import Entry
from group.models import Group


class APITest(AironeViewTest):
    def test_post_entry(self):
        admin = self.admin_login()

        # create referred Entity and Entries
        ref_entity = Entity.objects.create(name='Referred Entity', created_user=admin)
        ref_e = []
        for index in range(0, 10):
            ref_e.append(Entry.objects.create(name='r-%d' % index, schema=ref_entity, created_user=admin))

        entity = Entity.objects.create(name='Entity', created_user=admin)
        attr_params = [
            {'name': 'val', 'type': AttrTypeValue['string']},
            {'name': 'ref', 'type': AttrTypeValue['object'], 'ref': ref_entity},
            {'name': 'name', 'type': AttrTypeValue['named_object'], 'ref': ref_entity},
            {'name': 'bool', 'type': AttrTypeValue['boolean']},
            {'name': 'group', 'type': AttrTypeValue['group']},
            {'name': 'text', 'type': AttrTypeValue['text']},
            {'name': 'vals', 'type': AttrTypeValue['array_string']},
            {'name': 'refs', 'type': AttrTypeValue['array_object'], 'ref': ref_entity},
            {'name': 'names', 'type': AttrTypeValue['array_named_object'], 'ref': ref_entity},
        ]
        for attr_info in attr_params:
            entity_attr = EntityAttr.objects.create(**{
                'name': attr_info['name'],
                'type': attr_info['type'],
                'created_user': admin,
                'parent_entity': entity,
            })
            if 'ref' in attr_info:
                entity_attr.referral.add(attr_info['ref'])

            entity.attrs.add(entity_attr)

        params = {
            'name': 'entry1',
            'entity': entity.name,
            'attrs': {
                'val': 'hoge',
                'ref': 'r-5',
                'name': {'name': 'hoge', 'id': 'r-1'},
                'bool': False,
                'group': Group.objects.create(name='new_group').name,
                'text': 'fuga',
                'vals': ['foo', 'bar'],
                'refs': ['r-2', 'r-3'],
                'names': [{'name': 'foo', 'id': 'r-4'}, {'name': 'bar', 'id': 'r-5'}],
            }
        }
        resp = self.client.post('/api/v1/entry', json.dumps(params), 'application/json')
        self.assertEqual(resp.status_code, 200)

        ret_data = resp.json()
        new_entry = Entry.objects.get(id=ret_data['result'])
        self.assertEqual(new_entry.name, 'entry1')
        self.assertEqual(new_entry.attrs.count(), 9)

        # checking for attr_val
        checklist = [
            {'name': 'val', 'check': lambda v: self.assertEqual(v.value, 'hoge')},
            {'name': 'ref', 'check': lambda v: self.assertEqual(v.referral.id, ref_e[5].id)},
            {'name': 'name', 'check': lambda v: self.assertEqual(v.value, 'hoge')},
            {'name': 'name', 'check': lambda v: self.assertEqual(v.referral.id, ref_e[1].id)},
            {'name': 'bool', 'check': lambda v: self.assertEqual(v.boolean, False)},
            {'name': 'group', 'check': lambda v: self.assertEqual(v.value,
                str(Group.objects.get(name='new_group').id))},
            {'name': 'text', 'check': lambda v: self.assertEqual(v.value, 'fuga')},
            {'name': 'vals', 'check': lambda v: self.assertEqual(v.data_array.count(), 2)},
            {'name': 'vals', 'check': lambda v: self.assertEqual(v.data_array.first().value, 'foo')},
            {'name': 'vals', 'check': lambda v: self.assertEqual(v.data_array.last().value, 'bar')},
            {'name': 'refs', 'check': lambda v: self.assertEqual(v.data_array.count(), 2)},
            {'name': 'refs', 'check': lambda v: self.assertEqual(v.data_array.first().referral.id,
                                                                 ref_e[2].id)},
            {'name': 'refs', 'check': lambda v: self.assertEqual(v.data_array.last().referral.id,
                                                                 ref_e[3].id)},
            {'name': 'names', 'check': lambda v: self.assertEqual(v.data_array.count(), 2)},
            {'name': 'names', 'check': lambda v: self.assertEqual(v.data_array.first().referral.id,
                                                                 ref_e[4].id)},
            {'name': 'names', 'check': lambda v: self.assertEqual(v.data_array.first().value, 'foo')},
            {'name': 'names', 'check': lambda v: self.assertEqual(v.data_array.last().referral.id,
                                                                 ref_e[5].id)},
            {'name': 'names', 'check': lambda v: self.assertEqual(v.data_array.last().value, 'bar')},
        ]
        for info in checklist:
            attr = new_entry.attrs.get(name=info['name'])
            info['check'](attr.get_latest_value())

    def test_post_entry_with_invalid_params(self):
        admin = self.admin_login()

        # create referred Entity and Entries
        ref_entity = Entity.objects.create(name='Referred Entity', created_user=admin)
        ref_e = []
        for index in range(0, 10):
            ref_e.append(Entry.objects.create(name='r-%d' % index, schema=ref_entity, created_user=admin))

        entity = Entity.objects.create(name='Entity', created_user=admin)
        attr_params = [
            {'name': 'val', 'type': AttrTypeValue['string'], 'required': True},
            {'name': 'ref', 'type': AttrTypeValue['object'], 'ref': ref_entity},
        ]
        for attr_info in attr_params:
            entity_attr = EntityAttr.objects.create(**{
                'name': attr_info['name'],
                'type': attr_info['type'],
                'created_user': admin,
                'parent_entity': entity,
                'is_mandatory': True if 'required' in attr_info else False,
            })
            if 'ref' in attr_info:
                entity_attr.referral.add(attr_info['ref'])

            entity.attrs.add(entity_attr)

        # send request without essential params
        params = {
            'name': 'invalid-entry',
            'entity': entity.name,
            'attrs': {}
        }
        resp = self.client.post('/api/v1/entry', json.dumps(params), 'application/json')
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(Entry.objects.filter(schema=entity, name='invalid-entry').count(), 0)

        # send request without all attrs
        params = {
            'name': 'invalid-entry',
            'entity': entity.name,
            'attrs': {}
        }
        resp = self.client.post('/api/v1/entry', json.dumps(params), 'application/json')
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(Entry.objects.filter(schema=entity, name='invalid-entry').count(), 0)

        # send request only with mandatory attrs
        params = {
            'name': 'valid-entry',
            'entity': entity.name,
            'attrs': {'val': 'hoge'}
        }
        resp = self.client.post('/api/v1/entry', json.dumps(params), 'application/json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Entry.objects.filter(schema=entity, name='valid-entry').count(), 1)

        # send request with invalid attr param
        params = {
            'name': 'invalid-entry',
            'entity': entity.name,
            'attrs': {
                'val': 'hoge',
                'invalid-attr': 'hoge',
            }
        }
        resp = self.client.post('/api/v1/entry', json.dumps(params), 'application/json')
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(Entry.objects.filter(schema=entity, name='invalid-entry').count(), 0)

        # send request with invalid attr param
        params = {
            'name': 'invalid-entry',
            'entity': entity.name,
            'attrs': {
                'val': 'hoge',
                'invalid-attr': 'hoge',
            }
        }
        resp = self.client.post('/api/v1/entry', json.dumps(params), 'application/json')
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(Entry.objects.filter(schema=entity, name='invalid-entry').count(), 0)

        # send request with invalid value (the value 'fuga' is invalid)
        params = {
            'name': 'invalid-entry',
            'entity': entity.name,
            'attrs': {
                'val': 'hoge',
                'ref': 'fuga',
            }
        }
        resp = self.client.post('/api/v1/entry', json.dumps(params), 'application/json')
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(Entry.objects.filter(schema=entity, name='invalid-entry').count(), 0)

        # send request with invalid format value ('ref' required only str type parameter)
        params = {
            'name': 'invalid-entry',
            'entity': entity.name,
            'attrs': {
                'val': 'hoge',
                'ref': ['r-3'],
            }
        }
        resp = self.client.post('/api/v1/entry', json.dumps(params), 'application/json')
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(Entry.objects.filter(schema=entity, name='invalid-entry').count(), 0)

    def test_get_entry(self):
        admin = self.admin_login()

        # create referred Entity and Entries
        ref_entity = Entity.objects.create(name='Referred Entity', created_user=admin)
        ref_e = []
        for index in range(0, 10):
            ref_e.append(Entry.objects.create(name='r-%d' % index, schema=ref_entity, created_user=admin))

        entity = Entity.objects.create(name='Entity', created_user=admin)
        attr_params = [
            {'name': 'val', 'type': AttrTypeValue['string'],
             'setter': lambda attr, i: attr.add_value(admin, str(i))},
            {'name': 'ref', 'type': AttrTypeValue['object'], 'ref': ref_entity,
             'setter': lambda attr, i: attr.add_value(admin, ref_e[i])},
            {'name': 'name', 'type': AttrTypeValue['named_object'], 'ref': ref_entity,
             'setter': lambda attr, i: attr.add_value(admin, {'name': 'name-%d' % i, 'id': ref_e[i]})},
            {'name': 'bool', 'type': AttrTypeValue['boolean'],
             'setter': lambda attr, i: attr.add_value(admin, True if i % 2 == 0 else False)},
            {'name': 'group', 'type': AttrTypeValue['group'],
             'setter': lambda attr, i: attr.add_value(admin, str(Group.objects.create(name='group-%d' % i).id))},
            {'name': 'text', 'type': AttrTypeValue['text'],
             'setter': lambda attr, i: attr.add_value(admin, 'text-%d' % i)},
            {'name': 'vals', 'type': AttrTypeValue['array_string'],
             'setter': lambda attr, i: attr.add_value(admin, [str(x) for x in range(0, i)])},
            {'name': 'refs', 'type': AttrTypeValue['array_object'], 'ref': ref_entity,
             'setter': lambda attr, i: attr.add_value(admin, [ref_e[x] for x  in range(0, i)])},
            {'name': 'names', 'type': AttrTypeValue['array_named_object'], 'ref': ref_entity,
             'setter': lambda attr, i: attr.add_value(admin, [{'name': 'name-%d' % x, 'id': ref_e[x]}
                 for x in range(0, i)])},
        ]
        for attr_info in attr_params:
            entity_attr = EntityAttr.objects.create(**{
                'name': attr_info['name'],
                'type': attr_info['type'],
                'created_user': admin,
                'parent_entity': entity,
            })
            if 'ref' in attr_info:
                entity_attr.referral.add(attr_info['ref'])

            entity.attrs.add(entity_attr)

        for i in range(0, 3):
            entry = Entry.objects.create(name='e-%d' % i, schema=entity, created_user=admin)
            entry.complement_attrs(admin)

            for attrinfo in attr_params:
                attr = entry.attrs.get(name=attrinfo['name'])
                attrinfo['setter'](attr, i)

        resp = self.client.get('/api/v1/entry')
        self.assertEqual(resp.status_code, 200)

        results = resp.json()
        self.assertEqual(len(results), 13)
        self.assertEqual(len([x for x in results if re.match(r'^r-*', x['name'])]), 10)
        self.assertEqual(len([x for x in results if re.match(r'^e-*', x['name'])]), 3)

        entry2 = Entry.objects.get(name='e-2')
        e2 = [x for x in results if x['name'] == entry2.name][0]
        self.assertEqual(e2['id'], entry2.id)
        self.assertEqual(len(e2['attrs']), 9)
        self.assertTrue(all([entry2.attrs.filter(name=x['name']).count() for x in e2['attrs']]))

        # check all returned attr values
        for attrinfo in e2['attrs']:
            if attrinfo['name'] == 'val':
                self.assertEqual(attrinfo['value'], '2')

            if attrinfo['name'] == 'ref':
                self.assertEqual(attrinfo['value']['id'], ref_e[2].id)
                self.assertEqual(attrinfo['value']['name'], ref_e[2].name)

            if attrinfo['name'] == 'name':
                self.assertEqual(attrinfo['value']['name'], 'name-2')
                self.assertEqual(attrinfo['value']['ref_id'], ref_e[2].id)
                self.assertEqual(attrinfo['value']['ref_name'], ref_e[2].name)

            if attrinfo['name'] == 'bool':
                self.assertEqual(attrinfo['value'], True)

            if attrinfo['name'] == 'group':
                group = Group.objects.get(name='group-2')
                self.assertEqual(attrinfo['value']['id'], group.id)
                self.assertEqual(attrinfo['value']['name'], group.name)

            if attrinfo['name'] == 'text':
                self.assertEqual(attrinfo['value'], 'text-2')

            if attrinfo['name'] == 'vals':
                self.assertEqual(len(attrinfo['value']), 2)
                self.assertEqual(attrinfo['value'][0], '0')
                self.assertEqual(attrinfo['value'][1], '1')

            if attrinfo['name'] == 'refs':
                self.assertEqual(len(attrinfo['value']), 2)
                self.assertEqual(attrinfo['value'][0]['id'], ref_e[0].id)
                self.assertEqual(attrinfo['value'][0]['name'], ref_e[0].name)
                self.assertEqual(attrinfo['value'][1]['id'], ref_e[1].id)
                self.assertEqual(attrinfo['value'][1]['name'], ref_e[1].name)

            if attrinfo['name'] == 'names':
                self.assertEqual(len(attrinfo['value']), 2)
                self.assertEqual(attrinfo['value'][0]['name'], 'name-0')
                self.assertEqual(attrinfo['value'][0]['ref_id'], ref_e[0].id)
                self.assertEqual(attrinfo['value'][0]['ref_name'], ref_e[0].name)
