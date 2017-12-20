from airone.lib.test import AironeViewTest
from airone.lib.types import AttrTypeValue

from django.urls import reverse

from entity.models import Entity, EntityAttr
from entry.models import Entry, Attribute, AttributeValue
from entry.settings import CONFIG


class ViewTest(AironeViewTest):
    def test_get_entries(self):
        admin = self.admin_login()

        # create Entity&Entries
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
                'status': AttributeValue.STATUS_LATEST,
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
