import mock
import re
import sys
import json
import yaml

from airone.lib.test import AironeViewTest
from airone.lib.types import AttrTypeStr, AttrTypeObj, AttrTypeText
from airone.lib.types import AttrTypeArrStr, AttrTypeArrObj
from airone.lib.types import AttrTypeNamedObj, AttrTypeArrNamedObj
from airone.lib.types import AttrTypeValue
from django.conf import settings
from django.urls import reverse
from django.contrib.auth.models import User as DjangoUser
from group.models import Group
from io import StringIO
from datetime import date

from entity.models import Entity, EntityAttr
from entry.models import Entry, Attribute, AttributeValue

from xml.etree import ElementTree

class ViewTest(AironeViewTest):
    def setUp(self):
        super(ViewTest, self).setUp()

        self.admin = self.admin_login()

        # preparing test Entity/Entry objects
        fp = self.open_fixture_file('entry.yaml')
        resp = self.client.post(reverse('dashboard:do_import'), {'file': fp})

    def test_search_without_query(self):
        resp = self.client.get(reverse('dashboard:search'))
        self.assertEqual(resp.status_code, 400)

    def test_search_entity_and_entry(self):
        query = 'ent'

        resp = self.client.get(reverse('dashboard:search'), {'query': query})
        self.assertEqual(resp.status_code, 200)

        self.assertEqual(len(resp.context['results']), Entry.objects.filter(name__icontains=query).count())


    def test_search_entry_deduped_result(self):
        query = 'srv001'

        # In fixture, Entry 'srv001' has Attribute 'attr-str' and AttributeValue 'I am srv001'.
        # Search result should be displayed as single row.

        resp = self.client.get(reverse('dashboard:search'), {'query': query})
        self.assertEqual(resp.status_code, 200)

        self.assertEqual(len(resp.context['results']), 1)


    def test_search_entry_from_value(self):
        resp = self.client.get(reverse('dashboard:search'), {'query': 'hoge'})
        self.assertEqual(resp.status_code, 200)

        self.assertEqual(len(resp.context['results']), 1)

    def test_search_invalid_objects(self):
        resp = self.client.get(reverse('dashboard:search'), {'query': 'hogefuga'})
        self.assertEqual(resp.status_code, 200)

        self.assertEqual(len(resp.context['results']), 0)

    def test_show_dashboard_with_airone_user(self):
        resp = self.client.get(reverse('dashboard:index'))
        self.assertEqual(resp.status_code, 200)
        self.assertIsNotNone(resp.context["version"])

    def test_show_dashboard_with_django_user(self):
        # create test user which is authenticated by Django, not AirOne
        user = DjangoUser(username='django-user')
        user.set_password('passwd')
        user.save()

        # login as the django-user
        self.client.login(username='django-user', password='passwd')

        resp = self.client.get(reverse('dashboard:index'))
        self.assertEqual(resp.status_code, 200)

    def test_show_dashboard_with_anonymous(self):
        # logout test-user, this means current user is Anonymous
        self.client.logout()

        resp = self.client.get(reverse('dashboard:index'))
        self.assertEqual(resp.status_code, 200)

    def test_enable_profiler(self):
        self.client.logout()

        # set StringIO to capteure stdout context
        sys.stdout = StringIO()
        with mock.patch('airone.lib.profile.settings') as st_mock:
            # set to enable AirOne Profiler
            st_mock.AIRONE = {'ENABLE_PROFILE': True}

            resp = self.client.get(reverse('dashboard:index'))
            self.assertEqual(resp.status_code, 200)
            self.assertTrue(re.match("^\[Profiling result\] \(([0-9\.]*)\) .*$",
                                     sys.stdout.getvalue()))

        # reset stdout setting
        sys.stdout = sys.__stdout__

    def test_show_advanced_search(self):
        # create entity which has attr
        entity1 = Entity.objects.create(name="entity-1", created_user=self.admin)
        entity1.attrs.add(EntityAttr.objects.create(**{
            'name': 'attr-1-1',
            'type': AttrTypeValue['string'],
            'created_user': self.admin,
            'parent_entity': entity1,
        }))
        entity1.save()

        # create entity which doesn't have attr
        entity2 = Entity.objects.create(name="entity-2", created_user=self.admin)
        entity2.save()

        resp = self.client.get(reverse('dashboard:advanced_search'))
        self.assertEqual(resp.status_code, 200)

        entity_names = map(lambda e: e.name, resp.context['entities'])

        # entity-1 should be displayed
        self.assertEquals(1, len(list(filter(lambda n: n=="entity-1", entity_names))))
        # entity-2 should not be displayed
        self.assertEquals(0, len(list(filter(lambda n: n=="entity-2", entity_names))))

    def test_show_advanced_search_results(self):
        for entity_index in range(0, 2):
            entity = Entity.objects.create(name='entity-%d' % entity_index, created_user=self.admin)
            entity.attrs.add(EntityAttr.objects.create(**{
                'name': 'attr',
                'type': AttrTypeValue['string'],
                'created_user': self.admin,
                'parent_entity': entity,
            }))

            for entry_index in range(0, 10):
                entry = Entry.objects.create(name='entry-%d' % (entry_index),
                                             schema=entity, created_user=self.admin)
                entry.complement_attrs(self.admin)

                # add an AttributeValue
                entry.attrs.first().add_value(self.admin, 'data-%d' % entry_index)

                # register entry to the Elasticsearch
                entry.register_es()

        # test to show advanced_search_result page
        resp = self.client.get(reverse('dashboard:advanced_search_result'), {
            'entity[]': [x.id for x in Entity.objects.filter(name__regex='^entity-')],
            'attr[]': ['attr'],
        })
        self.assertEqual(resp.status_code, 200)

        # test to export results of advanced_search
        resp = self.client.post(reverse('dashboard:export_search_result'), {
            'entities': json.dumps([x.id for x in Entity.objects.filter(name__regex='^entity-')]),
            'attrinfo': json.dumps([{'name': 'attr', 'keyword': 'data-5'}]),
            'export_style': '"csv"',
        })
        self.assertEqual(resp.status_code, 200)

        csv_contents = [x for x in resp.content.decode('utf-8').splitlines() if x]
        self.assertEqual(len(csv_contents), 3)
        self.assertEqual(csv_contents[0], 'Name,attr')
        self.assertEqual(csv_contents[1], 'entry-5,data-5')
        self.assertEqual(csv_contents[2], 'entry-5,data-5')

        # test to show advanced_search_result page without mandatory params
        resp = self.client.get(reverse('dashboard:advanced_search_result'), {
            'attr[]': ['attr'],
        })
        self.assertEqual(resp.status_code, 400)

        # test to show advanced_search_result page with is_all_entries param
        resp = self.client.get(reverse('dashboard:advanced_search_result'), {
            'attr[]': ['attr'],
            'is_all_entities': 'true',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(sorted(resp.context['entities'].split(',')),
                         sorted([str(Entity.objects.get(name='entity-%d' % i).id) for i in range(2)]))
        self.assertEqual(resp.context['results']['ret_count'], 20)

    def test_export_advanced_search_result_with_referral(self):
        user = self.admin

        # initialize Entities
        ref_entity = Entity.objects.create(name='Referred Entity', created_user=user)
        entity = Entity.objects.create(name='entity', created_user=user)
        entity_attr = EntityAttr.objects.create(name='attr_ref',
                                                type=AttrTypeValue['object'],
                                                created_user=user,
                                                parent_entity=entity)
        entity_attr.referral.add(ref_entity)
        entity.attrs.add(entity_attr)

        # initialize Entries
        ref_entry = Entry.objects.create(name='ref', schema=ref_entity, created_user=user)
        ref_entry.register_es()

        entry = Entry.objects.create(name='entry', schema=entity, created_user=user)
        entry.complement_attrs(user)
        entry.attrs.first().add_value(user, ref_entry)

        # export with 'has_referral' parameter which has blank value
        resp = self.client.post(reverse('dashboard:export_search_result'), {
            'entities': json.dumps([ref_entity.id]),
            'attrinfo': json.dumps([]),
            'has_referral': json.dumps(''),
            'export_style': '"csv"',
        })
        self.assertEqual(resp.status_code, 200)

        # verifying result has referral entry's infomations
        csv_contents = [x for x in resp.content.decode('utf-8').splitlines() if x]
        self.assertEqual(len(csv_contents), 2)
        self.assertEqual(csv_contents[0], 'Name,Referral')
        self.assertEqual(csv_contents[1], "ref,['entry / entity']")

        # export with 'has_referral' parameter which has invalid value
        resp = self.client.post(reverse('dashboard:export_search_result'), {
            'entities': json.dumps([ref_entity.id]),
            'attrinfo': json.dumps([]),
            'has_referral': json.dumps('hogefuga'),
            'export_style': '"csv"',
        })
        self.assertEqual(resp.status_code, 200)

        csv_contents = [x for x in resp.content.decode('utf-8').splitlines() if x]
        self.assertEqual(len(csv_contents), 1)

    def test_show_advanced_search_results_csv_escape(self):
        user = self.admin

        dummy_entity = Entity.objects.create(name='Dummy', created_user=user)
        dummy_entry = Entry(name='D,U"MM"Y', schema=dummy_entity, created_user=user)
        dummy_entry.save()

        CASES = [
            [AttrTypeStr, 'raison,de"tre', '"raison,de""tre"'],
            [AttrTypeObj,  dummy_entry, '"D,U""MM""Y"'],
            [AttrTypeText, "1st line\r\n2nd line", '"1st line' + "\r\n" + '2nd line"'],
            [AttrTypeNamedObj, {"key": dummy_entry}, "\"{'key': 'D,U\"\"MM\"\"Y'}\""],
            [AttrTypeArrStr, ["one", "two", "three"], "\"['one', 'two', 'three']\""],
            [AttrTypeArrObj, [dummy_entry], "\"['D,U\"\"MM\"\"Y']\""],
            [AttrTypeArrNamedObj, [{"key1": dummy_entry}], "\"[{'key1': 'D,U\"\"MM\"\"Y'}]\""]
        ]

        for case in CASES:
            # setup data
            type_name = case[0].__name__ # AttrTypeStr -> 'AttrTypeStr'
            attr_name = type_name + ',"ATTR"'

            test_entity = Entity.objects.create(name="TestEntity_" + type_name, created_user=user)

            test_entity_attr = EntityAttr.objects.create(
                name=attr_name, type=case[0], created_user=user, parent_entity=test_entity)

            test_entity.attrs.add(test_entity_attr)
            test_entity.save()

            test_entry = Entry.objects.create(name=type_name + ',"ENTRY"', schema=test_entity, created_user=user)
            test_entry.save()

            test_attr = Attribute.objects.create(
                name=attr_name, schema=test_entity_attr, created_user=user, parent_entry=test_entry)

            test_attr.save()
            test_entry.attrs.add(test_attr)
            test_entry.save()

            test_val = None

            if case[0].TYPE & AttrTypeValue['array'] ==0:
                if case[0] == AttrTypeStr:
                    test_val = AttributeValue.create(user=user, attr=test_attr, value=case[1])
                elif case[0] == AttrTypeObj:
                    test_val = AttributeValue.create(user=user, attr=test_attr, referral=case[1])
                elif case[0] == AttrTypeText:
                    test_val = AttributeValue.create(user=user, attr=test_attr, value=case[1])
                elif case[0] == AttrTypeNamedObj:
                    [(k, v)] = case[1].items()
                    test_val = AttributeValue.create(user=user, attr=test_attr, value=k, referral=v)
            else:
                test_val = AttributeValue.create(user=user, attr=test_attr)
                test_val.set_status(AttributeValue.STATUS_DATA_ARRAY_PARENT)
                for child in case[1]:
                    test_val_child = None
                    if case[0] == AttrTypeArrStr:
                        test_val_child = AttributeValue.create(user=user, attr=test_attr, value=child)
                    elif case[0] == AttrTypeArrObj:
                        test_val_child = AttributeValue.create(user=user, attr=test_attr, referral=child)
                    elif case[0] == AttrTypeArrNamedObj:
                        [(k, v)] = child.items()
                        test_val_child = AttributeValue.create(user=user, attr=test_attr, value=k, referral=v)
                    test_val.data_array.add(test_val_child)

            test_val.save()
            test_attr.values.add(test_val)
            test_attr.save()

            test_entry.register_es()

            resp = self.client.post(reverse('dashboard:export_search_result'), {
                'entities': json.dumps([test_entity.id]),
                'attrinfo': json.dumps([{'name': test_attr.name, 'keyword': ''}]),
                'export_style': '"csv"',
            })
            self.assertEqual(resp.status_code, 200)

            content = resp.content.decode('utf-8')
            header = content.splitlines()[0]
            self.assertEqual(header, 'Name,"%s,""ATTR"""' % type_name)

            data = content.replace(header, '', 1).strip()
            self.assertEqual(data, '"%s,""ENTRY""",' % type_name + case[2] )

    def test_yaml_export(self):
        user = self.admin

        # create entity
        entity_ref = Entity.objects.create(name='RefEntity', created_user=user)
        entry_ref = Entry.objects.create(name='ref', schema=entity_ref, created_user=user)

        attr_info = {
            'str': {'type': AttrTypeValue['string'], 'value': 'foo',
                    'invalid_values': [123, entry_ref, True]},
            'obj': {'type': AttrTypeValue['object'], 'value': str(entry_ref.id)},
            'name': {'type': AttrTypeValue['named_object'],
                     'value': {'name': 'bar', 'id': str(entry_ref.id)}},
            'bool': {'type': AttrTypeValue['boolean'], 'value': False},
            'arr_str': {'type': AttrTypeValue['array_string'], 'value': ['foo', 'bar', 'baz']},
            'arr_obj': {'type': AttrTypeValue['array_object'],
                        'value': [str(entry_ref.id)]},
            'arr_name': {'type': AttrTypeValue['array_named_object'],
                         'value': [
                             {'name': 'hoge', 'id': str(entry_ref.id)},
                             {'name': 'fuga', 'boolean': False}, # specify boolean parameter
                          ]},
            'group': {'type': AttrTypeValue['group'], 'value': str(Group.objects.create(name='group').id)},
            'date': {'type': AttrTypeValue['date'], 'value': date(2020, 1, 1)}
        }
        entities = []
        for index in range(2):
            entity = Entity.objects.create(name='Entity-%d' % index, created_user=user)
            for attr_name, info in attr_info.items():
                attr = EntityAttr.objects.create(name=attr_name,
                                                 type=info['type'],
                                                 created_user=user,
                                                 parent_entity=entity)

                if info['type'] & AttrTypeValue['object']:
                    attr.referral.add(entity_ref)

                entity.attrs.add(attr)

            # create an entry of Entity
            for e_index in range(2):
                entry = Entry.objects.create(name='e-%d' % e_index, schema=entity, created_user=user)
                entry.complement_attrs(user)

                for attr_name, info in attr_info.items():
                    attr = entry.attrs.get(name=attr_name)
                    attrv = attr.add_value(user, info['value'])

                entry.register_es()

            entities.append(entity)

        resp = self.client.post(reverse('dashboard:export_search_result'), {
            'entities': json.dumps([x.id for x in Entity.objects.filter(name__regex='^Entity-')]),
            'attrinfo': json.dumps([{'name': x, 'keyword': ''} for x in attr_info.keys()]),
            'export_style': '"yaml"',
        })

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Disposition'], 'attachment; filename="search_results.yaml"')

        resp_data = yaml.load(resp.content)
        for index in range(2):
            entity = Entity.objects.get(name='Entity-%d' % index)
            e_data = resp_data[entity.name]

            self.assertEqual(len(resp_data[entity.name]), Entry.objects.filter(schema=entity).count())
            for e_data in resp_data[entity.name]:
                self.assertTrue(e_data['name'] in ['e-0', 'e-1'])
                self.assertTrue(all([x in attr_info.keys() for x in e_data['attrs']]))

        # Checked to be able to import exported data
        entry_another_ref = Entry.objects.create(name='another_ref', schema=entity_ref, created_user=user)
        new_group = Group.objects.create(name='new_group')
        new_attr_values = {
            'str': 'bar',
            'obj': 'another_ref',
            'name': {'hoge': 'another_ref'},
            'bool': True,
            'arr_str': ['hoge', 'fuga'],
            'arr_obj': ['another_ref'],
            'arr_name': [{'foo': 'another_ref'}, {'bar': 'ref'}],
            'group': 'new_group',
            'date': '1999-01-01',
        }
        resp_data['Entity-1'][0]['attrs'] = new_attr_values

        mockio = mock.mock_open(read_data=yaml.dump(resp_data))
        with mock.patch('builtins.open', mockio):
            with open('hogefuga.yaml') as fp:
                resp = self.client.post(reverse('entry:do_import', args=[entities[1].id]), {'file': fp})
                self.assertEqual(resp.status_code, 303)

        self.assertEqual(entry_another_ref.get_referred_objects().count(), 1)

        updated_entry = entry_another_ref.get_referred_objects().first()
        self.assertEqual(updated_entry.name, resp_data['Entity-1'][0]['name'])

        for (attr_name, value_info) in new_attr_values.items():
            attrv = updated_entry.attrs.get(name=attr_name).get_latest_value()

            if attr_name == 'str':
                self.assertEqual(attrv.value, value_info)
            elif attr_name == 'obj':
                self.assertEqual(attrv.referral.id, entry_another_ref.id)
            elif attr_name == 'name':
                self.assertEqual(attrv.value, list(value_info.keys())[0])
                self.assertEqual(attrv.referral.id, entry_another_ref.id)
            elif attr_name == 'bool':
                self.assertTrue(attrv.boolean)
            elif attr_name == 'arr_str':
                self.assertEqual(sorted([x.value for x in attrv.data_array.all()]),
                                 sorted(value_info))
            elif attr_name == 'arr_obj':
                self.assertEqual([x.referral.id for x in attrv.data_array.all()],
                                 [entry_another_ref.id])
            elif attr_name == 'arr_name':
                self.assertEqual(sorted([x.value for x in attrv.data_array.all()]),
                                 sorted([list(x.keys())[0] for x in value_info]))
                self.assertEqual(sorted([x.referral.name for x in attrv.data_array.all()]),
                                 sorted([list(x.values())[0] for x in value_info]))
            elif attr_name == 'group':
                self.assertEqual(int(attrv.value), new_group.id)
            elif attr_name == 'date':
                self.assertEqual(attrv.date, date(1999, 1, 1))
