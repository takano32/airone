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

        # send search request and checks returned values are valid
        params = {
            'entities': [x.id for x in Entity.objects.filter(name__regex='^entity-')],
            'attrinfo': [{'name': 'attr', 'keyword': 'data-5'}]
        }
        resp = self.client.post('/api/v1/entry/search', json.dumps(params), 'application/json')

        self.assertEqual(resp.status_code, 200)

        result = resp.json()['result']
        self.assertEqual(result['ret_count'], 2)
