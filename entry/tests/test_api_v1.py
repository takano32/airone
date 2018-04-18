import json

from airone.lib.test import AironeViewTest
from airone.lib.types import AttrTypeValue

from django.urls import reverse

from entity.models import Entity, EntityAttr
from entry.models import Entry, Attribute, AttributeValue
from entry.settings import CONFIG


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
            ref_attr.values.add(AttributeValue.objects.create(**{
                'referral': ref_entry,
                'parent_attr': ref_attr,
                'created_user': admin,
            }))

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
        self.assertEqual(resp.status_code, 400)

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
                    attr.values.add(AttributeValue.objects.create(**{
                        'value': '%d' % index,
                        **base_params,
                    }))
                elif attr.schema.type & AttrTypeValue['object']:
                    attr.values.add(AttributeValue.objects.create(**{
                        'referral': Entry.objects.get(name='r-%d' % index),
                        **base_params,
                    }))

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
