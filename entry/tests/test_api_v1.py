import json

from airone.lib.test import AironeViewTest
from airone.lib.types import AttrTypeValue

from django.urls import reverse

from entity.models import Entity, EntityAttr
from entry.models import Entry, Attribute, AttributeValue
from entry.settings import CONFIG
from group.models import Group


class ViewTest(AironeViewTest):
    def test_get_entries(self):
        admin = self.admin_login()

        # create Entity & Entries
        entity = Entity.objects.create(name='Entity', created_user=admin)
        for index in range(0, CONFIG.MAX_LIST_ENTRIES + 1):
            name = 'e-%s' % index
            Entry.objects.create(name=name, schema=entity, created_user=admin)

        # send request without keyword
        resp = self.client.get(reverse('entry:api_v1:get_entries', args=[entity.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'application/json')

        self.assertTrue('results' in resp.json())
        self.assertEqual(len(resp.json()['results']), CONFIG.MAX_LIST_ENTRIES)

        # send request with empty keyword
        resp = self.client.get(reverse('entry:api_v1:get_entries', args=[entity.id]), {'keyword': ''})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue('results' in resp.json())
        self.assertEqual(len(resp.json()['results']), CONFIG.MAX_LIST_ENTRIES)

        # send request with keyword parameter
        resp = self.client.get(reverse('entry:api_v1:get_entries', args=[entity.id]),
                               {'keyword': '10'})
        self.assertEqual(resp.status_code, 200)

        self.assertTrue('results' in resp.json())
        self.assertEqual(len(resp.json()['results']), 2)
        self.assertTrue(all([x['name'] == 'e-10' or x['name'] == 'e-100' for x in resp.json()['results']]))

        # send request with invalid keyword parameter
        resp = self.client.get(reverse('entry:api_v1:get_entries', args=[entity.id]),
                               {'keyword': 'invalid-keyword'})
        self.assertEqual(resp.status_code, 200)

        self.assertTrue('results' in resp.json())
        self.assertEqual(len(resp.json()['results']), 0)

        # send request to check keyword would be insensitive case
        resp = self.client.get(reverse('entry:api_v1:get_entries', args=[entity.id]),
                               {'keyword': 'E-0'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()['results']), 1)
        self.assertTrue(resp.json()['results'][0]['name'], 'e-0')

    def test_get_entries_with_multiple_ids(self):
        admin = self.admin_login()

        # create Entities & Entries
        for entity_name in ['Entity1', 'Entity2']:
            entity = Entity.objects.create(name='Entity', created_user=admin)
            for index in range(0, 10):
                name = 'e-%s' % index
                Entry.objects.create(name=name, schema=entity, created_user=admin)

        # specify multiple IDs of Entity
        entity_ids = '%s,%s' % (Entity.objects.first().id, Entity.objects.last().id)
        resp = self.client.get('/entry/api/v1/get_entries/%s/' % (entity_ids))
        self.assertEqual(resp.status_code, 200)

        self.assertTrue('results' in resp.json())
        self.assertEqual(len(resp.json()['results']), 20)

        # specify multiple IDs including invalid ones
        # this expects that the only entries of valid id will be returned.
        entity_ids = ',,,%s,,,,,9999' % Entity.objects.first().id
        resp = self.client.get('/entry/api/v1/get_entries/%s/' % entity_ids)
        self.assertEqual(resp.status_code, 200)

        self.assertTrue('results' in resp.json())
        self.assertEqual(len(resp.json()['results']), 10)

    def test_get_entries_with_multiple_entities(self):
        admin = self.admin_login()

        # create Entity&Entries
        for entity_name in ['Entity1', 'Entity2']:
            entity = Entity.objects.create(name=entity_name, created_user=admin)
            for index in range(0, 5):
                name = 'e-%s' % index
                Entry.objects.create(name=name, schema=entity, created_user=admin)

        entity_ids = ','.join([str(x.id) for x in Entity.objects.all()])
        resp = self.client.get(reverse('entry:api_v1:get_entries', args=[entity_ids]))

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'application/json')
        self.assertTrue('results' in resp.json())
        self.assertEqual(len(resp.json()['results']), 10)

    def test_get_referrals(self):
        admin = self.admin_login()

        # create Entity&Entries
        ref_entity = Entity.objects.create(name='Referred Entity', created_user=admin)
        ref_entry = Entry.objects.create(name='Referred Entry', schema=ref_entity, created_user=admin)

        entity = Entity.objects.create(name='Entity', created_user=admin)
        entity.attrs.add(EntityAttr.objects.create(**{
            'name': 'Refer',
            'type': AttrTypeValue['object'],
            'created_user': admin,
            'parent_entity': entity,
        }))

        for index in range(0, CONFIG.MAX_LIST_REFERRALS + 1):
            name = 'e-%s' % index
            e = Entry.objects.create(name=name, schema=entity, created_user=admin)
            e.complement_attrs(admin)

            ref_attr = e.attrs.get(name='Refer')
            ref_attr.add_value(admin, ref_entry)

        # send request without keyword
        resp = self.client.get(reverse('entry:api_v1:get_referrals', args=[ref_entry.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'application/json')

        self.assertEqual(resp.json()['total_count'], CONFIG.MAX_LIST_REFERRALS + 1)
        self.assertEqual(resp.json()['found_count'], CONFIG.MAX_LIST_REFERRALS)
        self.assertTrue(all(['id' in x and 'name' in x and 'entity' in x for x in resp.json()['entries']]))

        # send request with keyword parameter
        resp = self.client.get(reverse('entry:api_v1:get_referrals', args=[ref_entry.id]),
                                       {'keyword': 'e-10'})
        self.assertEqual(resp.status_code, 200)

        self.assertEqual(resp.json()['total_count'], CONFIG.MAX_LIST_REFERRALS + 1)
        self.assertEqual(resp.json()['found_count'], 1)

        # send request with invalid keyword parameter
        resp = self.client.get(reverse('entry:api_v1:get_referrals', args=[ref_entry.id]),
                                       {'keyword': 'invalid_keyword'})
        self.assertEqual(resp.status_code, 200)

        self.assertEqual(resp.json()['total_count'], CONFIG.MAX_LIST_REFERRALS + 1)
        self.assertEqual(resp.json()['found_count'], 0)

    def test_get_attr_referrals(self):
        admin = self.admin_login()

        # create Entity&Entries
        ref_entity = Entity.objects.create(name='Referred Entity', created_user=admin)

        entity = Entity.objects.create(name='Entity', created_user=admin)
        entity_attr = EntityAttr.objects.create(**{
            'name': 'Refer',
            'type': AttrTypeValue['object'],
            'created_user': admin,
            'parent_entity': entity,
        })

        entity_attr.referral.add(ref_entity)
        entity.attrs.add(entity_attr)

        for index in range(0, CONFIG.MAX_LIST_REFERRALS + 1):
            Entry.objects.create(name='e-%s' % index, schema=ref_entity, created_user=admin)

        entry = Entry.objects.create(name='entry', schema=entity, created_user=admin)

        # get Attribute object after complement them in the entry
        entry.complement_attrs(admin)
        attr = entry.attrs.get(name='Refer')

        # try to get entries without keyword
        resp = self.client.get(reverse('entry:api_v1:get_attr_referrals', args=[attr.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()['results']), CONFIG.MAX_LIST_REFERRALS)

        # specify invalid Attribute ID
        resp = self.client.get(reverse('entry:api_v1:get_attr_referrals', args=[9999]))
        self.assertEqual(resp.status_code, 400)

        # speify valid Attribute ID and a enalbed keyword
        resp = self.client.get(reverse('entry:api_v1:get_attr_referrals', args=[attr.id]),
                               {'keyword': 'e-1'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'application/json')
        self.assertTrue('results' in resp.json())

        # This means e-1 and 'e-10' to 'e-19' are returned
        self.assertEqual(len(resp.json()['results']), 11)

        # speify valid Attribute ID and a unabailabe keyword
        resp = self.client.get(reverse('entry:api_v1:get_attr_referrals', args=[attr.id]),
                               {'keyword': 'hoge'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()['results']), 0)

    def test_get_attr_referrals_with_entity_attr(self):
        """
        This test is needed because the get_attr_referrals API will receive an ID
        of Attribute from entry.edit view, but also receive an EntityAttr's one
        from entry.create view.
        """
        admin = self.admin_login()

        # create Entity&Entries
        ref_entity = Entity.objects.create(name='Referred Entity', created_user=admin)
        for index in range(0, CONFIG.MAX_LIST_REFERRALS + 1):
            Entry.objects.create(name='e-%s' % index, schema=ref_entity, created_user=admin)

        entity = Entity.objects.create(name='Entity', created_user=admin)
        entity_attr = EntityAttr.objects.create(**{
            'name': 'Refer',
            'type': AttrTypeValue['named_object'],
            'created_user': admin,
            'parent_entity': entity,
        })
        entity_attr.referral.add(ref_entity)
        entity.attrs.add(entity_attr)

        resp = self.client.get(reverse('entry:api_v1:get_attr_referrals', args=[entity_attr.id]),
                               {'keyword': 'e-1'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'application/json')
        self.assertTrue('results' in resp.json())

        # This means e-1 and 'e-10' to 'e-19' are returned
        self.assertEqual(len(resp.json()['results']), 11)

    def test_advanced_search(self):
        admin = self.admin_login()

        # create referred Entity and Entries
        ref_entity = Entity.objects.create(name='Referred Entity', created_user=admin)
        for index in range(0, 20):
            Entry.objects.create(name='r-%s' % index, schema=ref_entity, created_user=admin)

        attr_infos = [
            {'name': 'attr_ref', 'type': AttrTypeValue['object'], 'ref': ref_entity},
            {'name': 'attr_val', 'type': AttrTypeValue['string']},
        ]
        entity = Entity.objects.create(name='Entity', created_user=admin)

        for attr_info in attr_infos:
            entity_attr = EntityAttr.objects.create(**{
                'name': attr_info['name'],
                'type': attr_info['type'],
                'created_user': admin,
                'parent_entity': entity,
            })
            if 'ref' in attr_info:
                entity_attr.referral.add(attr_info['ref'])

            entity.attrs.add(entity_attr)

        for index in range(0, 20):
            ref_entry = Entry.objects.get(name='r-%d' % index)

            entry = Entry.objects.create(name='e-%d' % index, schema=entity, created_user=admin)
            entry.complement_attrs(admin)
            for attr_name in ['attr_ref', 'attr_val']:
                attr = entry.attrs.get(name=attr_name)

                base_params = {
                    'created_user': admin,
                    'parent_attr': attr,
                }
                if attr.schema.type & AttrTypeValue['string']:
                    attr.add_value(admin, str(index))

                elif attr.schema.type & AttrTypeValue['object']:
                    attr.add_value(admin, Entry.objects.get(name='r-%d' % index))

        # checks the the API request to get entries with 'or' cond_link parameter
        params = {
            'cond_link': 'or',
            'cond_params': [
                {'type': 'text', 'value': '5'},
                {'type': 'entry', 'value': str(Entry.objects.get(name='r-6').id)},
            ],
        }
        resp = self.client.post(reverse('entry:api_v1:search_entries', args=[entity.id]),
                                json.dumps(params), 'application/json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'application/json')
        self.assertEqual(len(resp.json()['results']), 3)
        self.assertTrue(any([x for x in resp.json()['results'] if x['name'] == 'e-5']))
        self.assertTrue(any([x for x in resp.json()['results'] if x['name'] == 'e-15']))
        self.assertTrue(any([x for x in resp.json()['results'] if x['name'] == 'e-6']))

        # checks the the API request to not get entries with 'or' cond_link parameter
        params = {
            'cond_link': 'or',
            'cond_params': [
                {'type': 'text', 'value': 'abcd'},
            ],
        }
        resp = self.client.post(reverse('entry:api_v1:search_entries', args=[entity.id]),
                                json.dumps(params), 'application/json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'application/json')
        self.assertEqual(len(resp.json()['results']), 0)

        # checks the the API request to get entries with 'and' cond_link parameter
        params = {
            'cond_link': 'and',
            'cond_params': [
                {'type': 'text', 'value': '5'},
                {'type': 'entry', 'value': str(Entry.objects.get(name='r-5').id)},
            ],
        }
        resp = self.client.post(reverse('entry:api_v1:search_entries', args=[entity.id]),
                                json.dumps(params), 'application/json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'application/json')
        self.assertEqual(len(resp.json()['results']), 1)
        self.assertTrue(any([x for x in resp.json()['results'] if x['name'] == 'e-5']))

        # checks the the API request to not get entries with 'and' cond_link parameter
        params = {
            'cond_link': 'and',
            'cond_params': [
                {'type': 'text', 'value': '5'},
                {'type': 'entry', 'value': str(Entry.objects.get(name='r-6').id)},
            ],
        }
        resp = self.client.post(reverse('entry:api_v1:search_entries', args=[entity.id]),
                                json.dumps(params), 'application/json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'application/json')
        self.assertEqual(len(resp.json()['results']), 0)

        # checks the the API request to get entries without cond_link parameter
        params = {
            'cond_params': [
                {'type': 'text', 'value': '5'},
                {'type': 'text', 'value': '6'},
            ],
        }
        resp = self.client.post(reverse('entry:api_v1:search_entries', args=[entity.id]),
                                json.dumps(params), 'application/json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'application/json')
        self.assertEqual(len(resp.json()['results']), 4)
        self.assertTrue(any([x for x in resp.json()['results'] if x['name'] == 'e-5']))
        self.assertTrue(any([x for x in resp.json()['results'] if x['name'] == 'e-15']))
        self.assertTrue(any([x for x in resp.json()['results'] if x['name'] == 'e-6']))
        self.assertTrue(any([x for x in resp.json()['results'] if x['name'] == 'e-16']))

        # checks the the API request to get entries with regex pattern and 'and' cond_link
        params = {
            'cond_link': 'and',
            'cond_params': [
                {'type': 'text', 'value': '1'},
                {'type': 'text', 'value': '2'},
            ],
        }
        resp = self.client.post(reverse('entry:api_v1:search_entries', args=[entity.id]),
                                json.dumps(params), 'application/json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'application/json')
        self.assertEqual(len(resp.json()['results']), 1)
        self.assertTrue(any([x for x in resp.json()['results'] if x['name'] == 'e-12']))

        # checks the the API request to get entries with regex pattern and 'or' cond_link
        params = {
            'cond_link': 'or',
            'cond_params': [
                {'type': 'text', 'value': '1'},
                {'type': 'text', 'value': '2'},
            ],
        }
        resp = self.client.post(reverse('entry:api_v1:search_entries', args=[entity.id]),
                                json.dumps(params), 'application/json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'application/json')
        self.assertEqual(len(resp.json()['results']), 12)

    def test_get_entry_history(self):
        user = self.guest_login()

        # initialize Entity and Entry
        entity = Entity.objects.create(name='Entity', created_user=user)
        entity.attrs.add(EntityAttr.objects.create(**{
            'name': 'attr',
            'type': AttrTypeValue['string'],
            'created_user': user,
            'parent_entity': entity,
        }))

        entry = Entry.objects.create(name='Entry', schema=entity, created_user=user)
        entry.complement_attrs(user)
        attr = entry.attrs.first()
        for index in range(5):
            attr.add_value(user, 'value-%d' % index)

        # check to get all history data
        resp = self.client.get(reverse('entry:api_v1:get_entry_history', args=[entry.id]), {'count': 10})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'application/json')

        resp_data = resp.json()['results']
        self.assertEqual(len(resp_data), 5)
        self.assertEqual([x['attr_value'] for x in resp_data],
                         ['value-%d' % x for x in range(4, -1, -1)])

        # check to get part of history data
        resp = self.client.get(reverse('entry:api_v1:get_entry_history', args=[entry.id]),
                               {'count': 2, 'index': 1})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'application/json')

        resp_data = resp.json()['results']
        self.assertEqual(len(resp_data), 2)
        self.assertEqual([x['attr_value'] for x in resp_data],
                         ['value-%d' % x for x in range(3, 1, -1)])

    def test_update_attr_with_attrv(self):
        user = self.guest_login()

        # initialize referred objects
        ref_entity = Entity.objects.create(name='RefEntity', created_user=user)
        ref_entries = [Entry.objects.create(name='r%d' % i, created_user=user, schema=ref_entity) for i in range(3)]
        groups = [Group.objects.create(name='g%d' % i) for i in range(2)]

        # initialize Entity and Entry
        entity = Entity.objects.create(name='Entity', created_user=user)

        # First of all, this test set values which is in 'values' of attr_info to each attributes
        # in order of first and second (e.g. in the case of 'str', this test sets 'foo' at first,
        # then sets 'bar') manually. After that, this test retrieve first value by calling the
        # 'update_attr_with_attrv' handler. So finnaly, this test expects first value is stored
        # in Database and Elasticsearch.
        attr_info = {
            'str': {
                'type': AttrTypeValue['string'],
                'values': ['foo', 'bar']
            },
            'obj': {
                'type': AttrTypeValue['object'],
                'values': [ref_entries[0], ref_entries[1]]
            },
            'grp': {
                'type': AttrTypeValue['group'],
                'values': [groups[0], groups[1]]
            },
            'name': {
                'type': AttrTypeValue['named_object'],
                'values': [
                    {'name': 'foo', 'id': ref_entries[0]},
                    {'name': 'bar', 'id': ref_entries[1]},
                ]
            },
            'bool': {
                'type': AttrTypeValue['boolean'],
                'values': [False, True]
            },
            'date': {
                'type': AttrTypeValue['date'],
                'values': ['2018-01-01', '2018-02-01']
            },
            'arr1': {
                'type': AttrTypeValue['array_string'],
                'values': [
                    ['foo', 'bar', 'baz'],
                    ['hoge', 'fuga', 'puyo']
                ]
            },
            'arr2': {
                'type': AttrTypeValue['array_object'],
                'values': [
                    [ref_entries[0], ref_entries[1]],
                    [ref_entries[2]]
                ]
            },
            'arr3': {
                'type': AttrTypeValue['array_named_object'],
                'values': [
                    [{'name': 'foo', 'id': ref_entries[0]}, {'name': 'bar', 'id': ref_entries[1]}],
                    [{'name': '', 'id': ref_entries[1]}, {'name': 'fuga', 'id': ref_entries[2]}]
                ]
            }
        }
        for attr_name, info in attr_info.items():
            attr = EntityAttr.objects.create(name=attr_name,
                                             type=info['type'],
                                             created_user=user,
                                             parent_entity=entity)

            if info['type'] & AttrTypeValue['object']:
                attr.referral.add(ref_entity)

            entity.attrs.add(attr)

        # initialize each AttributeValues
        entry = Entry.objects.create(name='Entry', schema=entity, created_user=user)
        entry.complement_attrs(user)
        for attr_name, info in attr_info.items():
            attr = entry.attrs.get(schema__name=attr_name)
            attrv1 = attr.add_value(user, info['values'][0])

            # store first value's attrv
            info['expected_value'] = attrv1.get_value()

            # update value to second value
            attrv2 = attr.add_value(user, info['values'][1])

            # check value is actually updated
            self.assertNotEqual(attrv1.get_value(), attrv2.get_value())

            # reset AttributeValue and latest_value equals with attrv1
            params = {'attr_id': str(attr.id), 'attrv_id': str(attrv1.id)}
            resp = self.client.post(reverse('entry:api_v1:update_attr_with_attrv'),
                                    json.dumps(params), 'application/json')
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(attrv1.get_value(), attr.get_latest_value().get_value())

        resp = Entry.search_entries(user, [entity.id])
        self.assertEqual(resp['ret_count'], 1)
        for attr_name, data in resp['ret_values'][0]['attrs'].items():
            self.assertEqual(data['type'], attr_info[attr_name]['type'])

            value = attr_info[attr_name]['values'][0]
            if data['type'] == AttrTypeValue['boolean']:
                self.assertEqual(data['value'], str(value))

            elif data['type'] == AttrTypeValue['group']:
                self.assertEqual(data['value'], {'name': value.name, 'id': value.id})

            elif data['type'] == AttrTypeValue['object']:
                self.assertEqual(data['value'], {'name': value.name, 'id': value.id})

            elif data['type'] == AttrTypeValue['array_object']:
                self.assertEqual(data['value'], [{'name': x.name, 'id': x.id} for x in value])

            elif data['type'] == AttrTypeValue['named_object']:
                self.assertEqual(data['value'],
                                 {value['name']: {'name': value['id'].name, 'id': value['id'].id}})

            elif data['type'] == AttrTypeValue['array_named_object']:
                self.assertEqual(data['value'],
                                 [{x['name']: {'name': x['id'].name, 'id': x['id'].id}} for x in value])

            else:
                self.assertEqual(data['value'], value)

    def test_update_attr_with_attrv_with_invalid_value(self):
        user = self.guest_login()

        # initialize Entity and Entry
        entity = Entity.objects.create(name='Entity', created_user=user)
        entity.attrs.add(EntityAttr.objects.create(**{
            'name': 'attr',
            'type': AttrTypeValue['string'],
            'created_user': user,
            'parent_entity': entity,
        }))

        entry = Entry.objects.create(name='Entry', schema=entity, created_user=user)
        entry.complement_attrs(user)
        attr = entry.attrs.first()

        # send request with invalid arguments
        params = {'attr_id': '0', 'attrv_id': '0'}
        resp = self.client.post(reverse('entry:api_v1:update_attr_with_attrv'),
                                json.dumps(params), 'application/json')
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.content, b'Specified Attribute-id is invalid')

        params = {'attr_id': str(attr.id), 'attrv_id': '0'}
        resp = self.client.post(reverse('entry:api_v1:update_attr_with_attrv'),
                                json.dumps(params), 'application/json')
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.content, b'Specified AttributeValue-id is invalid')

        attrvs = [attr.add_value(user, str(x)) for x in range(2)]
        self.assertEqual(attr.get_latest_value(), attrvs[-1])

        # change Attribute type of attr then get latest AttributeValue
        attr.schema.type = AttrTypeValue['object']
        attr.schema.save(update_fields=['type'])

        self.assertGreater(attr.get_latest_value().id, attrvs[-1].id)
