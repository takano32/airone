import json

from airone.lib.test import AironeViewTest
from airone.lib.types import AttrTypeValue

from user.models import User

from entity.models import Entity, EntityAttr
from entry.models import Entry


class APITest(AironeViewTest):
    def test_narrow_down_advanced_search_results(self):
        user = self.admin_login()

        for entity_index in range(0, 2):
            entity = Entity.objects.create(name='entity-%d' % entity_index, created_user=user)
            entity.attrs.add(EntityAttr.objects.create(**{
                'name': 'attr',
                'type': AttrTypeValue['string'],
                'created_user': user,
                'parent_entity': entity,
            }))

            for entry_index in range(0, 10):
                entry = Entry.objects.create(name='entry-%d' % (entry_index),
                                             schema=entity, created_user=user)
                entry.complement_attrs(user)

                # add an AttributeValue
                entry.attrs.first().add_value(user, 'data-%d' % entry_index)

                # register entry to the Elasticsearch
                entry.register_es()

        # send request without mandatory parameter
        resp = self.client.post('/api/v1/entry/search')
        self.assertEqual(resp.status_code, 400)

        # send search request and checks returned values are valid with several format of parameter,
        # This tests specifing informations of entity both id and name.
        hint_entities = [
            [x.id for x in Entity.objects.filter(name__regex='^entity-')],
            ['entity-%d' % i for i in range(0, 2)]
        ]
        for hint_entity in hint_entities:
            params = {
                'entities': hint_entity,
                'attrinfo': [{'name': 'attr', 'keyword': 'data-5'}]
            }
            resp = self.client.post('/api/v1/entry/search', json.dumps(params), 'application/json')

            self.assertEqual(resp.status_code, 200)

            result = resp.json()['result']
            self.assertEqual(result['ret_count'], 2)

    def test_api_referred_entry(self):
        user = self.guest_login()

        entity_ref = Entity.objects.create(name='ref', created_user=user)
        entity = Entity.objects.create(name='E', created_user=user)

        # set EntityAttr that refers entity_ref
        attr_info = [
                {'name': 'r0', 'type': AttrTypeValue['object']},
                {'name': 'r1', 'type': AttrTypeValue['named_object']},
                {'name': 'r2', 'type': AttrTypeValue['array_object']},
                {'name': 'r3', 'type': AttrTypeValue['array_named_object']},
        ]
        for info in attr_info:
            attr = EntityAttr.objects.create(**{
                'name': info['name'],
                'type': info['type'],
                'created_user': user,
                'parent_entity': entity,
            })
            attr.referral.add(entity_ref)
            entity.attrs.add(attr)

        # create referred entries
        refs = [Entry.objects.create(name='r%d' % i, schema=entity_ref, created_user=user) for i in range(0, 5)]

        # create referring entries and set values for each Attribute
        entry = Entry.objects.create(name='e', schema=entity, created_user=user)
        entry.complement_attrs(user)

        entry.attrs.get(name='r0').add_value(user, refs[0])
        entry.attrs.get(name='r1').add_value(user, {'name':'foo', 'id':refs[1]})
        entry.attrs.get(name='r2').add_value(user, [refs[2]])
        entry.attrs.get(name='r3').add_value(user, [{'name':'bar', 'id':refs[3]}])

        # send request without entry parameter
        resp = self.client.get('/api/v1/entry/referral')
        self.assertEqual(resp.status_code, 400)

        # send request with invalid entry parameter
        resp = self.client.get('/api/v1/entry/referral?entry=hoge')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {'result': []})

        # check to be able to get referred object no matter whether AttributeType
        for index in range(0, 4):
            resp = self.client.get('/api/v1/entry/referral?entry=%s' % refs[index].name)
            self.assertEqual(resp.status_code, 200)

            result = resp.json()['result']
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]['id'], refs[index].id)
            self.assertEqual(result[0]['entity'], {'id': entity_ref.id, 'name': entity_ref.name})
            self.assertEqual(result[0]['referral'], [{
                'id': entry.id,
                'name': entry.name,
                'entity': {'id': entity.id, 'name': entity.name}
            }])

        # check the case of no referred object
        resp = self.client.get('/api/v1/entry/referral?entry=%s' % refs[4].name)
        self.assertEqual(resp.status_code, 200)

        result = resp.json()['result']
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['id'], refs[4].id)
        self.assertEqual(result[0]['referral'], [])
