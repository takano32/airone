import re
import json
import yaml
import pytz

from django.test import Client
from django.conf import settings

from airone.lib.test import AironeViewTest
from airone.lib.types import AttrTypeValue

from entity.models import Entity, EntityAttr
from entry.models import Entry, Attribute, AttributeValue
from group.models import Group
from user.models import User

from unittest import skip, mock
from datetime import date, datetime, timedelta

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
            {'name': 'date', 'type': AttrTypeValue['date']},
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
                'date': '2018-12-31',
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
        self.assertEqual(new_entry.attrs.count(), 10)

        # checking new_entry is registered to the Elasticsearch
        res = self._es.get(index=settings.ES_CONFIG['INDEX'], doc_type='entry', id=new_entry.id)
        self.assertTrue(res['found'])

        # checking for attr_val
        checklist = [
            {'name': 'val', 'check': lambda v: self.assertEqual(v.value, 'hoge')},
            {'name': 'ref', 'check': lambda v: self.assertEqual(v.referral.id, ref_e[5].id)},
            {'name': 'name', 'check': lambda v: self.assertEqual(v.value, 'hoge')},
            {'name': 'name', 'check': lambda v: self.assertEqual(v.referral.id, ref_e[1].id)},
            {'name': 'bool', 'check': lambda v: self.assertEqual(v.boolean, False)},
            {'name': 'date', 'check': lambda v: self.assertEqual(v.date, date(2018,12,31))},
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

    def test_post_entry_with_token(self):
        admin = User.objects.create(username='admin', is_superuser='True')

        entity = Entity.objects.create(name='Entity', created_user=admin)
        params = {
            'name': 'Entry',
            'entity': entity.name,
            'attrs': {},
        }

        resp = self.client.post('/api/v1/entry', json.dumps(params), 'application/json', **{
            'HTTP_AUTHORIZATION': 'Token %s' % str(admin.token),
        })
        self.assertEqual(Entry.objects.filter(schema=entity).count(), 1)
        self.assertEqual(Entry.objects.filter(schema=entity).first().name, 'Entry')

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

        # update entry which has been already created.
        #
        # This lacks mandatory parameter 'val', but this will be successful. Because that
        # is created at the last request to create 'valid-entry'.
        params = {
            'name': 'valid-entry',
            'entity': entity.name,
            'attrs': {'ref': 'r-1'}
        }
        resp = self.client.post('/api/v1/entry', json.dumps(params), 'application/json')
        self.assertEqual(resp.status_code, 200)

        entry = Entry.objects.get(schema=entity, name='valid-entry')
        self.assertEqual(entry.attrs.get(name='val').get_latest_value().value, 'hoge')
        self.assertIsNotNone(entry.attrs.get(name='ref').get_latest_value().referral)
        self.assertEqual(entry.attrs.get(name='ref').get_latest_value().referral.id,
                         Entry.objects.get(name='r-1', schema=ref_entity).id)

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

    def test_post_entry_without_permissoin(self):
        admin = self.admin_login()

        entity = Entity.objects.create(name='Entity', created_user=admin, is_public=False)
        attr_params = [
            {'name': 'attr1', 'type': AttrTypeValue['string'], 'is_public': True},
            {'name': 'attr2', 'type': AttrTypeValue['string'], 'is_public': False},
        ]
        for attr_info in attr_params:
            entity.attrs.add(EntityAttr.objects.create(**{
                'name': attr_info['name'],
                'type': attr_info['type'],
                'is_public': attr_info['is_public'],
                'created_user': admin,
                'parent_entity': entity,
            }))

        # re-login as guest
        guest = self.guest_login()

        # checks that we can't create a new entry because of lack of permission
        params = {
            'name': 'entry',
            'entity': entity.name,
            'attrs': {'attr1': 'hoge', 'attr2': 'fuga'},
        }
        resp = self.client.post('/api/v1/entry', json.dumps(params), 'application/json')
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()['result'], 'Permission denied to create(or update) entry')

        # Set permisson to create new entry
        guest.permissions.add(entity.writable)

        # checks that we can create an entry but attr2 doesn't set because
        # guest doesn't have permission of writable for attr2
        params = {
            'name': 'entry',
            'entity': entity.name,
            'attrs': {'attr1': 'hoge', 'attr2': 'fuga'},
        }
        resp = self.client.post('/api/v1/entry', json.dumps(params), 'application/json')
        self.assertEqual(resp.status_code, 200)

        entry = Entry.objects.get(name='entry', schema=entity)
        self.assertEqual(entry.attrs.count(), 1)
        self.assertEqual(entry.attrs.last().name, 'attr1')

    def test_update_entry(self):
        admin = self.admin_login()

        entity = Entity.objects.create(name='Entity', created_user=admin, is_public=False)
        entity.attrs.add(EntityAttr.objects.create(**{
            'name': 'attr',
            'type': AttrTypeValue['string'],
            'created_user': admin,
            'parent_entity': entity,
        }))

        entry = Entry.objects.create(name='entry', schema=entity, created_user=admin)
        entry.complement_attrs(admin)

        # update entry by sending request to /api/v1/entry
        params = {
            'name': entry.name,
            'entity': entity.name,
            'attrs': {'attr': 'hoge'},
        }
        resp = self.client.post('/api/v1/entry', json.dumps(params), 'application/json')
        self.assertEqual(resp.status_code, 200)

        self.assertEqual(resp.json()['result'], entry.id)

        attrv = entry.attrs.last().get_latest_value()
        self.assertIsNotNone(attrv)
        self.assertEqual(attrv.value, 'hoge')

        # update entry by specifying entry ID
        params = {
            'id': entry.id,
            'name': 'updated_entry',
            'entity': entity.name,
            'attrs': {'attr': 'fuga'},
        }
        resp = self.client.post('/api/v1/entry', json.dumps(params), 'application/json')
        self.assertEqual(resp.status_code, 200)

        self.assertEqual(resp.json()['result'], entry.id)

        entry = Entry.objects.get(id=resp.json()['result'])
        self.assertEqual(entry.name, 'updated_entry')
        self.assertEqual(entry.attrs.last().get_latest_value().value, 'fuga')

        # update with same value of current one, this expects that no attributes are updated
        attr_value_count = AttributeValue.objects.count()
        # update entry by specifying entry ID
        params = {
            'id': entry.id,
            'name': 'updated_entry',
            'entity': entity.name,
            'attrs': {'attr': 'fuga'},
        }
        resp = self.client.post('/api/v1/entry', json.dumps(params), 'application/json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(AttributeValue.objects.count(), attr_value_count)

    def test_refresh_token(self):
        admin = self.admin_login()

        resp = self.client.post('/api/v1/user/refresh_token', json.dumps({}), 'application/json')

    def test_failed_to_get_entry(self):
        # send request without login
        resp = self.client.get('/api/v1/entry')
        self.assertEqual(resp.status_code, 400)

        user = self.guest_login()

        # send request without mandatory parameters
        resp = self.client.get('/api/v1/entry')
        self.assertEqual(resp.status_code, 400)

        # send request with invalid name of Entity
        resp = self.client.get('/api/v1/entry', {'entity': 'foo', 'entry': 'bar'})
        self.assertEqual(resp.status_code, 404)

        # send request with invalid name of Entry
        entity = Entity.objects.create(name='foo', created_user=user)
        resp = self.client.get('/api/v1/entry', {'entity': 'foo', 'entry': 'bar'})
        self.assertEqual(resp.status_code, 404)

    def test_get_entry(self):
        user = self.admin_login()

        ref_entity = Entity.objects.create(name='RefEntity', created_user=user)
        ref_entry = Entry.objects.create(name='RefEntry', created_user=user, schema=ref_entity)

        for entity_name in ['hoge', 'fuga']:
            entity = Entity.objects.create(name=entity_name, created_user=user)
            attr_info = {
                'str': {'type': AttrTypeValue['string'], 'value': 'foo'},
                'ref': {'type': AttrTypeValue['object'], 'value': ref_entry, 'referral': ref_entity},
                'no_str': {'type': AttrTypeValue['string']},
            }
            for (name, info) in attr_info.items():
                attr = EntityAttr.objects.create(name=name,
                                                 type=info['type'],
                                                 parent_entity=entity,
                                                 created_user=user)
                if 'referral' in info:
                    attr.referral.add(info['referral'])

                entity.attrs.add(attr)

            for i in range(0, 10):
                entry = Entry.objects.create(name='entry-%d' % i, schema=entity, created_user=user)
                entry.complement_attrs(user)

                for (name, info) in attr_info.items():
                    if 'value' in info:
                        attr = entry.attrs.get(schema__name=name)
                        attr.add_value(user, info['value'])

        # set private to Entity 'fuga'
        Entity.objects.filter(name='fuga').update(is_public=False)

        # set private to Entry 'entry-0'
        Entry.objects.filter(name='entry-0').update(is_public=False)

        # set private to EntityAttr 'str'
        EntityAttr.objects.filter(name='str').update(is_public=False)

        # set private to Attribute 'ref' in Entry 'entry-1'
        Attribute.objects.filter(name='ref', parent_entry__name='entry-1').update(is_public=False)

        # the case to specify 'eitnty' and 'entry' parameters
        resp = self.client.get('/api/v1/entry', {'entity': 'hoge', 'entry': 'entry-0'})
        self.assertEqual(resp.status_code, 200)

        results = resp.json()
        self.assertTrue(isinstance(results, list))
        self.assertEqual(len(results), 1)

        entry = Entry.objects.get(name='entry-0', schema__name='hoge')
        self.assertEqual(results[0]['id'], entry.id)
        self.assertEqual(len(results[0]['attrs']), entry.attrs.count())

        # the case to specify only 'entry' parameter
        resp = self.client.get('/api/v1/entry', {'entry': 'entry-0'})
        self.assertEqual(resp.status_code, 200)

        results = resp.json()
        self.assertEqual(len(results), 2)
        self.assertEqual([x['id'] for x in results], [x.id for x in Entry.objects.filter(name='entry-0')])
        self.assertEqual([x['entity']['name'] for x in results], ['hoge', 'fuga'])

        # switch to the guest user to verify permission checking processing will work
        self.guest_login()

        # the case to specify only 'entry' parameter
        resp = self.client.get('/api/v1/entry', {'entry': 'entry-0'})
        self.assertEqual(resp.status_code, 404)

        resp = self.client.get('/api/v1/entry', {'entry': 'entry-1'})
        self.assertEqual(resp.status_code, 200)

        results = resp.json()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['id'], Entry.objects.get(name='entry-1', schema__name='hoge').id)
        self.assertEqual([x['name'] for x in results[0]['attrs']], ['no_str'])

        resp = self.client.get('/api/v1/entry', {'entry': 'entry-2'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(sorted([x['name'] for x in resp.json()[0]['attrs']]), sorted(['ref', 'no_str']))

    def test_delete_entry(self):
        # wrapper to send delete request in this test
        def send_request(param):
            return self.client.delete('/api/v1/entry', json.dumps(param), 'application/json')

        admin = self.admin_login()

        entity1 = Entity.objects.create(name='Entity1', created_user=admin)
        entity2 = Entity.objects.create(name='Entity2', created_user=admin, is_public=False)

        # The 'entry1' will be deleted from API request for testing. And 'entry2' is also used for this test,
        # but this is not public one so it couldn't be deleted by the user who doesn't have priviledged level.
        entry11 = Entry.objects.create(name='entry11', schema=entity1, created_user=admin)
        entry12 = Entry.objects.create(name='entry12', schema=entity1, created_user=admin, is_public=False)
        entry21 = Entry.objects.create(name='entry21', schema=entity2, created_user=admin)

        # re-login for checking entries permission
        user = self.guest_login()

        # The case of no specifying mandatory parameter
        resp = send_request({})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.content.decode('utf-8'),
                         '"Parameter \\"entity\\" and \\"entry\\" are mandatory"')

        # The case of specifying invalid entity parameter
        resp = send_request({'entity': 'hoge', 'entry': 'fuga'})
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.content.decode('utf-8'),
                         '"Failed to find specified Entity (hoge)"')

        # The case of specifying invalid etnry parameter
        resp = send_request({'entity': 'Entity1', 'entry': 'fuga'})
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.content.decode('utf-8'),
                         '"Failed to find specified Entry (fuga)"')

        # The case of specifying entry of entity which user doesn't have read permission
        resp = send_request({'entity': 'Entity2', 'entry': 'entry21'})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.content.decode('utf-8'),
                         '"Permission denied to operate"')

        # The case of specifying entry which user doen't have delete permission
        resp = send_request({'entity': 'Entity1', 'entry': 'entry12'})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.content.decode('utf-8'),
                         '"Permission denied to operate"')

        # The case of success to delete
        resp = send_request({'entity': 'Entity1', 'entry': 'entry11'})
        self.assertEqual(resp.status_code, 200)

        # checks specified entry would be deleted
        entry11.refresh_from_db()
        self.assertFalse(entry11.is_active)

    @mock.patch('api_v1.auth.datetime')
    def test_expiring_token_lifetime(self, dt_mock):
        user = User.objects.create(username='testuser')

        entity = Entity.objects.create(name='E1', created_user=user)
        entry = Entry.objects.create(name='e1', schema=entity, created_user=user,)

        # Fixed value of datetime.now() for 100-seconds future
        dt_mock.now = mock.Mock(return_value=datetime.now(tz=pytz.UTC) + timedelta(seconds=100))

        # By default, token_lifetime is set of User.TOKEN_LIFETIME which is more than 100 seconds
        resp = self.client.get('/api/v1/entry', {'entity': 'E1', 'entry': 'e1'}, **{
            'HTTP_AUTHORIZATION': 'Token %s' % str(user.token),
        })
        self.assertEqual(resp.status_code, 200)

        # Set token_lifetime shortest one, it means current token has been expired already.
        user.token_lifetime = 1
        user.save()
        resp = self.client.get('/api/v1/entry', {'entity': 'E1', 'entry': 'e1'}, **{
            'HTTP_AUTHORIZATION': 'Token %s' % str(user.token),
        })
        self.assertEqual(resp.status_code, 401)

        # Once setting 0 at token_lifetime, access token will never be expired
        user.token_lifetime = 0
        user.save()
        resp = self.client.get('/api/v1/entry', {'entity': 'E1', 'entry': 'e1'}, **{
            'HTTP_AUTHORIZATION': 'Token %s' % str(user.token),
        })
        self.assertEqual(resp.status_code, 200)
