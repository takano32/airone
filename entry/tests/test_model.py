from group.models import Group
from datetime import date
from django.test import TestCase
from django.core.cache import cache
from django.conf import settings
from entity.models import Entity, EntityAttr
from entry.models import Entry, Attribute, AttributeValue
from user.models import User
from airone.lib.acl import ACLObjType, ACLType
from airone.lib.types import AttrTypeStr, AttrTypeObj, AttrTypeArrStr, AttrTypeArrObj
from airone.lib.types import AttrTypeValue
from airone.lib.test import AironeTestCase


class ModelTest(AironeTestCase):
    def setUp(self):
        super(ModelTest, self).setUp()

        self._user = User(username='test')
        self._user.save()

        self._entity = Entity(name='entity', created_user=self._user)
        self._entity.save()

        self._entry = Entry(name='entry', created_user=self._user, schema=self._entity)
        self._entry.save()

        self._attr = self.make_attr('attr')
        self._attr.save()

    def make_attr(self, name, attrtype=AttrTypeStr, user=None, entity=None, entry=None):
        entity_attr = EntityAttr(name=name,
                                 type=attrtype,
                                 created_user=(user and user or self._user),
                                 parent_entity=(entity and entity or self._entity))
        entity_attr.save()

        return Attribute(name=name,
                         schema=entity_attr,
                         created_user=(user and user or self._user),
                         parent_entry=(entry and entry or self._entry))

    def test_make_attribute_value(self):
        AttributeValue(value='hoge', created_user=self._user, parent_attr=self._attr).save()

        self.assertEqual(AttributeValue.objects.count(), 1)
        self.assertEqual(AttributeValue.objects.last().value, 'hoge')
        self.assertEqual(AttributeValue.objects.last().created_user, self._user)
        self.assertIsNotNone(AttributeValue.objects.last().created_time)

    def test_make_attribute(self):
        value = AttributeValue(value='hoge', created_user=self._user, parent_attr=self._attr)
        value.save()

        self._attr.values.add(value)

        self.assertEqual(Attribute.objects.count(), 1)
        self.assertEqual(Attribute.objects.last().objtype, ACLObjType.EntryAttr)
        self.assertEqual(Attribute.objects.last().values.count(), 1)
        self.assertEqual(Attribute.objects.last().values.last(), value)

    def test_make_entry(self):
        entry = Entry(name='test',
                      schema=self._entity,
                      created_user=self._user)
        entry.save()

        attr = self.make_attr('attr', entry=entry)
        attr.save()

        entry.attrs.add(attr)

        self.assertEqual(Entry.objects.count(), 2)
        self.assertEqual(Entry.objects.last().created_user, self._user)
        self.assertEqual(Entry.objects.last().attrs.count(), 1)
        self.assertEqual(Entry.objects.last().attrs.last(), attr)
        self.assertEqual(Entry.objects.last().name, 'test')
        self.assertEqual(Entry.objects.last().is_active, True,
                         "Entry should not be deleted after created")

    def test_inherite_attribute_permission_of_user(self):
        user = User.objects.create(username='hoge')

        entity = Entity.objects.create(name='entity', created_user=user)
        attrbase = EntityAttr.objects.create(name='attr',
                                             created_user=user,
                                             parent_entity=entity)

        # update acl metadata
        attrbase.is_public = False
        attrbase.default_permission = ACLType.Readable.id

        # set a permission to the user
        user.permissions.add(attrbase.writable)

        entry = Entry.objects.create(name='entry', schema=entity, created_user=user)
        attr = entry.add_attribute_from_base(attrbase, user)

        self.assertEqual(user.permissions.filter(name='writable').count(), 2)
        self.assertEqual(user.permissions.filter(name='writable').first(), attrbase.writable)
        self.assertEqual(user.permissions.filter(name='writable').last(), attr.writable)

        # checks that acl metadata is inherited
        self.assertFalse(attr.is_public)
        self.assertEqual(attr.default_permission, attrbase.default_permission)

    def test_inherite_attribute_permission_of_group(self):
        user = User.objects.create(username='hoge')
        group = Group.objects.create(name='group')
        user.groups.add(group)

        entity = Entity.objects.create(name='entity', created_user=user)
        attrbase = EntityAttr.objects.create(name='attr',
                                             created_user=user,
                                             parent_entity=entity)

        # set a permission to the user
        group.permissions.add(attrbase.writable)

        entry = Entry.objects.create(name='entry', schema=entity, created_user=user)
        attr = entry.add_attribute_from_base(attrbase, user)

        self.assertEqual(group.permissions.filter(name='writable').count(), 2)
        self.assertEqual(group.permissions.filter(name='writable').first(), attrbase.writable)
        self.assertEqual(group.permissions.filter(name='writable').last(), attr.writable)

    def test_update_attribute_from_base(self):
        user = User.objects.create(username='hoge')

        # test objects to be handled as referral
        entity = Entity.objects.create(name='entity', created_user=user)

        attrbase = EntityAttr.objects.create(name='attrbase',
                                                type=AttrTypeStr.TYPE,
                                                created_user=user,
                                                parent_entity=entity)
        entry = Entry.objects.create(name='entry', schema=entity, created_user=user)
        attr = entry.add_attribute_from_base(attrbase, user)

        # update attrbase
        attrbase.name = 'hoge'
        attrbase.type = AttrTypeObj.TYPE
        attrbase.referral.add(entity)
        attrbase.is_mandatory = True

        self.assertEqual(Attribute.objects.get(id=attr.id).schema, attrbase)

    def test_status_update_methods_of_attribute_value(self):
        value = AttributeValue(value='hoge', created_user=self._user, parent_attr=self._attr)
        value.save()

        self.assertFalse(value.get_status(AttributeValue.STATUS_DATA_ARRAY_PARENT))

        value.set_status(AttributeValue.STATUS_DATA_ARRAY_PARENT)

        self.assertTrue(value.get_status(AttributeValue.STATUS_DATA_ARRAY_PARENT))

        value.del_status(AttributeValue.STATUS_DATA_ARRAY_PARENT)

        self.assertFalse(value.get_status(AttributeValue.STATUS_DATA_ARRAY_PARENT))

    def test_attr_helper_of_attribute_with_string_values(self):
        self.assertTrue(self._attr.is_updated('hoge'))

        self._attr.values.add(AttributeValue.objects.create(value='hoge',
                                                            created_user=self._user,
                                                            parent_attr=self._attr))
        self._attr.values.add(AttributeValue.objects.create(value='fuga',
                                                            created_user=self._user,
                                                            parent_attr=self._attr))

        self.assertFalse(self._attr.is_updated('fuga'))
        self.assertTrue(self._attr.is_updated('hgoe'))
        self.assertTrue(self._attr.is_updated('puyo'))

    def test_attr_helper_of_attribute_with_object_values(self):
        e1 = Entry.objects.create(name='E1', created_user=self._user, schema=self._entity)
        e2 = Entry.objects.create(name='E2', created_user=self._user, schema=self._entity)

        entity = Entity.objects.create(name='e2', created_user=self._user)
        entry = Entry.objects.create(name='_E', created_user=self._user, schema=entity)

        attr = self.make_attr('attr2', attrtype=AttrTypeObj, entity=entity, entry=entry)
        attr.save()

        attr.values.add(AttributeValue.objects.create(referral=e1, created_user=self._user,
                                                      parent_attr=attr))

        self.assertFalse(attr.is_updated(e1.id))
        self.assertTrue(attr.is_updated(e2.id))

        # checks that this method accepts Entry
        self.assertFalse(attr.is_updated(e1))
        self.assertTrue(attr.is_updated(e2))

    def test_attr_helper_of_attribute_with_array_string_vlaues(self):
        entity = Entity.objects.create(name='e2', created_user=self._user)
        entry = Entry.objects.create(name='_E', created_user=self._user, schema=entity)

        attr = self.make_attr('attr2', attrtype=AttrTypeArrStr, entity=entity, entry=entry)
        attr.save()

        attr_value = AttributeValue.objects.create(created_user=self._user, parent_attr=attr)
        attr_value.set_status(AttributeValue.STATUS_DATA_ARRAY_PARENT)

        attr_value.data_array.add(AttributeValue.objects.create(value='hoge',
                                                     created_user=self._user,
                                                     parent_attr=attr))

        attr_value.data_array.add(AttributeValue.objects.create(value='fuga',
                                                     created_user=self._user,
                                                     parent_attr=attr))

        attr.values.add(attr_value)

        self.assertFalse(attr.is_updated(['hoge', 'fuga']))
        self.assertFalse(attr.is_updated(['fuga', 'hoge']))
        self.assertTrue(attr.is_updated(['hoge', 'puyo']))          # update
        self.assertTrue(attr.is_updated(['hoge']))                  # delete
        self.assertTrue(attr.is_updated(['puyo']))                  # delete & update
        self.assertTrue(attr.is_updated(['hoge', 'fuga', 'puyo']))  # add
        self.assertTrue(attr.is_updated(['hoge', 'fuga', 'abcd']))  # add & update

    def test_attr_helper_of_attribute_with_array_object_values(self):
        e1 = Entry.objects.create(name='E1', created_user=self._user, schema=self._entity)
        e2 = Entry.objects.create(name='E2', created_user=self._user, schema=self._entity)
        e3 = Entry.objects.create(name='E3', created_user=self._user, schema=self._entity)
        e4 = Entry.objects.create(name='E4', created_user=self._user, schema=self._entity)

        entity = Entity.objects.create(name='e2', created_user=self._user)
        entry = Entry.objects.create(name='_E', created_user=self._user, schema=entity)

        attr = self.make_attr('attr2', attrtype=AttrTypeArrObj, entity=entity, entry=entry)
        attr.save()

        attr_value = AttributeValue.objects.create(created_user=self._user, parent_attr=attr)
        attr_value.set_status(AttributeValue.STATUS_DATA_ARRAY_PARENT)

        attr_value.data_array.add(AttributeValue.objects.create(referral=e1,
                                                     created_user=self._user,
                                                     parent_attr=attr))

        attr_value.data_array.add(AttributeValue.objects.create(referral=e2,
                                                     created_user=self._user,
                                                     parent_attr=attr))

        attr.values.add(attr_value)

        self.assertFalse(attr.is_updated([e1.id, e2.id]))
        self.assertFalse(attr.is_updated([e2.id, e1.id]))
        self.assertTrue(attr.is_updated([e1.id, e3.id]))        # update
        self.assertTrue(attr.is_updated([e1.id]))               # delete
        self.assertTrue(attr.is_updated([e3.id]))               # delete & update
        self.assertTrue(attr.is_updated([e1.id, e2.id, e3.id])) # create
        self.assertTrue(attr.is_updated([e1.id, e3.id, e4.id])) # create & update

        # checks that this method also accepts Entry
        self.assertFalse(attr.is_updated([e2, e1]))
        self.assertTrue(attr.is_updated([e1, e3]))

    def test_attr_helper_of_attribute_with_named_ref(self):
        ref_entity = Entity.objects.create(name='referred_entity', created_user=self._user)
        ref_entry1 = Entry.objects.create(name='referred_entry1', created_user=self._user, schema=ref_entity)
        ref_entry2 = Entry.objects.create(name='referred_entry2', created_user=self._user, schema=ref_entity)

        entity = Entity.objects.create(name='entity', created_user=self._user)
        new_attr_params = {
            'name': 'named_ref',
            'type': AttrTypeValue['named_object'],
            'created_user': self._user,
            'parent_entity': entity,
        }
        attr_base = EntityAttr.objects.create(**new_attr_params)
        attr_base.referral.add(ref_entity)

        entity.attrs.add(attr_base)

        entry = Entry.objects.create(name='entry', created_user=self._user, schema=entity)
        entry.complement_attrs(self._user)

        attr = entry.attrs.get(name='named_ref')
        self.assertTrue(attr.is_updated(ref_entry1.id))

        attr.values.add(AttributeValue.objects.create(created_user=self._user,
                                                      parent_attr=attr,
                                                      value='hoge',
                                                      referral=ref_entry1))

        self.assertFalse(attr.is_updated({'id': ref_entry1.id, 'name': 'hoge'}))
        self.assertTrue(attr.is_updated({'id': ref_entry2.id, 'name': 'hoge'}))
        self.assertTrue(attr.is_updated({'id': ref_entry1.id, 'name': 'fuga'}))
        self.assertTrue(attr.is_updated({'id': ref_entry1.id, 'name': ''}))

    def test_attr_helper_of_attribute_with_array_named_ref(self):
        ref_entity = Entity.objects.create(name='referred_entity', created_user=self._user)
        ref_entry = Entry.objects.create(name='referred_entry', created_user=self._user, schema=ref_entity)

        entity = Entity.objects.create(name='entity', created_user=self._user)
        new_attr_params = {
            'name': 'arr_named_ref',
            'type': AttrTypeValue['array_named_object'],
            'created_user': self._user,
            'parent_entity': entity,
        }
        attr_base = EntityAttr.objects.create(**new_attr_params)
        attr_base.referral.add(ref_entity)

        entity.attrs.add(attr_base)

        # create an Entry associated to the 'entity'
        entry = Entry.objects.create(name='entry', created_user=self._user, schema=entity)
        entry.complement_attrs(self._user)

        attr = entry.attrs.get(name='arr_named_ref')
        self.assertTrue(attr.is_updated([{'id': ref_entry.id}]))

        # checks that this method also accepts Entry
        self.assertTrue(attr.is_updated([{'id': ref_entry}]))

        attrv = AttributeValue.objects.create(**{
            'parent_attr': attr,
            'created_user': self._user,
            'status': AttributeValue.STATUS_DATA_ARRAY_PARENT,
        })

        r_entries = []
        for i in range(0, 3):
            r_entry = Entry.objects.create(name='r_%d' % i, created_user=self._user, schema=ref_entity)
            r_entries.append({'id': r_entry.id})

            attrv.data_array.add(AttributeValue.objects.create(**{
                'parent_attr': attr,
                'created_user': self._user,
                'value': 'key_%d' % i,
                'referral': r_entry,
            }))

        attr.values.add(attrv)

        # this processing doesn't care the order of contet
        self.assertFalse(attr.is_updated([{**x, 'name': y} for x, y in zip(r_entries, ['key_0', 'key_2', 'key_1'])]))

        self.assertTrue(attr.is_updated([{'name': x} for x in ['key_0', 'key_1', 'key_2']]))
        self.assertTrue(attr.is_updated([{**x, 'name': y} for x, y in zip(r_entries, ['key_0', 'key_1'])]))
        self.assertTrue(attr.is_updated(r_entries))

    def test_for_boolean_attr_and_value(self):
        attr = self.make_attr('attr_bool', AttrTypeValue['boolean'])
        attr.save()

        # Checks get_latest_value returns empty AttributeValue
        # even if target attribute doesn't have any value
        attrv = attr.get_latest_value()
        self.assertIsNotNone(attrv)
        self.assertIsNone(attrv.referral)
        self.assertIsNone(attrv.date)

        attr.values.add(AttributeValue.objects.create(**{
            'created_user': self._user,
            'parent_attr': attr,
        }))

        # Checks default value
        self.assertIsNotNone(attr.get_latest_value())
        self.assertFalse(attr.get_latest_value().boolean)

        # Checks attitude of is_update
        self.assertFalse(attr.is_updated(False))
        self.assertTrue(attr.is_updated(True))

    def test_for_date_attr_and_value(self):
        attr = self.make_attr('attr_date', AttrTypeValue['date'])
        attr.save()

        attr.values.add(AttributeValue.objects.create(**{
            'created_user': self._user,
            'parent_attr': attr,
        }))

        # Checks default value
        self.assertIsNotNone(attr.get_latest_value())
        self.assertIsNone(attr.get_latest_value().date)

        # Checks attitude of is_update
        self.assertTrue(attr.is_updated(date(9999, 12, 31)))

    def test_get_referred_objects(self):
        entity = Entity.objects.create(name='Entity2', created_user=self._user)
        entry1 = Entry.objects.create(name='r1', created_user=self._user, schema=entity)
        entry2 = Entry.objects.create(name='r2', created_user=self._user, schema=entity)

        attr = self.make_attr('attr_ref', attrtype=AttrTypeValue['object'])
        attr.save()

        # this attribute is needed to check not only get referral from normal object attribute,
        # but also from an attribute that refers array referral objects
        arr_attr = self.make_attr('attr_arr_ref', attrtype=AttrTypeValue['array_object'])
        arr_attr.save()

        # make multiple value that refer 'entry' object
        [attr.values.add(AttributeValue.objects.create(created_user=self._user,
                                                       parent_attr=attr,
                                                       referral=entry1)) for _ in range(0, 10)]
        # make a self reference value
        attr.values.add(AttributeValue.objects.create(created_user=self._user,
                                                      parent_attr=attr,
                                                      referral=self._entry))

        # set another referral value to the 'attr_arr_ref' attr
        arr_attr.add_value(self._user, [entry1, entry2])

        self._entry.attrs.add(attr)
        self._entry.attrs.add(arr_attr)

        # This function checks that this get_referred_objects method only get
        # unique reference objects except for the self referred object.
        for entry in [entry1, entry2]:
            referred_entries = entry.get_referred_objects()
            self.assertEqual(referred_entries.count(), 1)
            self.assertEqual(list(referred_entries), [self._entry])

    def test_coordinating_attribute_with_dynamically_added_one(self):
        newattr = EntityAttr.objects.create(name='newattr',
                                            type=AttrTypeStr,
                                            created_user=self._user,
                                            parent_entity=self._entity)
        self._entity.attrs.add(newattr)

        # create new attributes which are appended after creation of Entity
        self._entry.complement_attrs(self._user)

        self.assertEqual(self._entry.attrs.count(), 1)
        self.assertEqual(self._entry.attrs.last().schema, newattr)

    def test_get_value_history(self):
        attr = self.make_attr('attr')
        attr.save()

        attr.values.add(AttributeValue.objects.create(value='foo',
                                                      created_user=self._user,
                                                      parent_attr=attr))
        attr.values.add(AttributeValue.objects.create(value='bar',
                                                      created_user=self._user,
                                                      parent_attr=attr))
        attr.values.add(AttributeValue.objects.create(value='baz',
                                                      created_user=self._user,
                                                      parent_attr=attr))

        self.assertEqual(len(attr.get_value_history(self._user)), 3)

        # checks data_type is set as the current type of Attribute if it's not set
        self.assertTrue(all([v.data_type == AttrTypeValue['string'] for v in attr.values.all()]))

    def test_delete_entry(self):
        entity = Entity.objects.create(name='ReferredEntity', created_user=self._user)
        entry = Entry.objects.create(name='entry', created_user=self._user, schema=entity)

        attr = self.make_attr('attr_ref', attrtype=AttrTypeObj)
        attr.save()

        self._entry.attrs.add(attr)

        # make a self reference value
        attr.values.add(AttributeValue.objects.create(created_user=self._user,
                                                      parent_attr=attr,
                                                      referral=entry))

        # set referral cache
        self.assertEqual(list(entry.get_referred_objects()), [self._entry])

        # register entry to the Elasticsearch to check that will be deleted
        deleting_entry_id = self._entry.id
        self._entry.register_es()
        res = self._es.get(index=settings.ES_CONFIG['INDEX'], doc_type='entry', id=deleting_entry_id)
        self.assertTrue(res['found'])

        # delete an entry that have an attribute which refers to the entry of ReferredEntity
        self._entry.delete()
        self.assertFalse(self._entry.is_active)
        self.assertEqual(self._entry.attrs.filter(is_active=True).count(), 0)

        # make sure that referral cache is updated by deleting referring entry
        self.assertEqual(list(entry.get_referred_objects()), [])

        # checks that the document in the Elasticsearch associated with the entry was also deleted
        res = self._es.get(index=settings.ES_CONFIG['INDEX'], doc_type='entry', id=deleting_entry_id, ignore=[404])
        self.assertFalse(res['found'])

    def test_order_of_array_named_ref_entries(self):
        ref_entity = Entity.objects.create(name='referred_entity', created_user=self._user)
        ref_entry = Entry.objects.create(name='referred_entry', created_user=self._user, schema=ref_entity)

        entity = Entity.objects.create(name='entity', created_user=self._user)
        new_attr_params = {
            'name': 'arr_named_ref',
            'type': AttrTypeValue['array_named_object'],
            'created_user': self._user,
            'parent_entity': entity,
        }
        attr_base = EntityAttr.objects.create(**new_attr_params)
        attr_base.referral.add(ref_entity)

        entity.attrs.add(attr_base)

        # create an Entry associated to the 'entity'
        entry = Entry.objects.create(name='entry', created_user=self._user, schema=entity)
        entry.complement_attrs(self._user)

        attr = entry.attrs.get(name='arr_named_ref')
        self.assertTrue(attr.is_updated([{'id': ref_entry.id}]))

        attrv = AttributeValue.objects.create(**{
            'parent_attr': attr,
            'created_user': self._user,
            'status': AttributeValue.STATUS_DATA_ARRAY_PARENT,
        })

        r_entries = []
        for i in range(3, 0, -1):
            r_entry = Entry.objects.create(name='r_%d' % i, created_user=self._user, schema=ref_entity)
            r_entries.append(r_entry.id)

            attrv.data_array.add(AttributeValue.objects.create(**{
                'parent_attr': attr,
                'created_user': self._user,
                'value': 'key_%d' % i,
                'referral': r_entry,
            }))

        attr.values.add(attrv)

        # checks the order of entries for array_named_ref that are shown in the views of
        # list/show/edit
        results = entry.get_available_attrs(self._user)
        self.assertEqual(len(results), 1)
        self.assertEqual(len(results[0]['last_value']), 3)
        self.assertEqual(results[0]['last_value'][0]['value'], 'key_1')
        self.assertEqual(results[0]['last_value'][1]['value'], 'key_2')
        self.assertEqual(results[0]['last_value'][2]['value'], 'key_3')

        # checks the order of entries for array_named_ref that are shown in the history of
        # show page
        results = entry.attrs.get(name='arr_named_ref').get_value_history(self._user)
        self.assertEqual(len(results), 2)
        self.assertEqual(len(results[1]['attr_value']), 3)
        self.assertEqual(results[1]['attr_value'][0]['value'], 'key_1')
        self.assertEqual(results[1]['attr_value'][1]['value'], 'key_2')
        self.assertEqual(results[1]['attr_value'][2]['value'], 'key_3')

    def test_clone_attribute_value(self):
        basic_params = {
            'created_user': self._user,
            'parent_attr': self._attr,
        }
        attrv = AttributeValue.objects.create(value='hoge', **basic_params)

        for i in range(0, 10):
            attrv.data_array.add(AttributeValue.objects.create(value=str(i), **basic_params))

        clone = attrv.clone(self._user)

        self.assertIsNotNone(clone)
        self.assertNotEqual(clone.id, attrv.id)
        self.assertNotEqual(clone.created_time, attrv.created_time)

        # check that data_array is cleared after cloning
        self.assertEqual(attrv.data_array.count(), 10)
        self.assertEqual(clone.data_array.count(), 0)

        # check that value and permission will be inherited from original one
        self.assertEqual(clone.value, attrv.value)

    def test_clone_attribute_without_permission(self):
        unknown_user = User.objects.create(username='unknown')

        attr = self.make_attr(name='attr', attrtype=AttrTypeValue['array_string'])
        attr.is_public = False
        attr.save()
        self.assertIsNone(attr.clone(unknown_user))

    def test_clone_attribute_typed_string(self):
        attr = self.make_attr(name='attr', attrtype=AttrTypeValue['string'])
        attr.save()

        params = {
            'parent_attr': attr,
            'created_user': self._user,
            'value': 'hoge',
        }
        attr.values.add(AttributeValue.objects.create(**params))

        cloned_attr = attr.clone(self._user)
        self.assertIsNotNone(cloned_attr)
        self.assertNotEqual(cloned_attr.id, attr.id)
        self.assertEqual(cloned_attr.name, attr.name)
        self.assertEqual(cloned_attr.values.count(), attr.values.count())
        self.assertNotEqual(cloned_attr.values.last(), attr.values.last())

    def test_clone_attribute_typed_array_string(self):
        attr = self.make_attr(name='attr', attrtype=AttrTypeValue['array_string'])
        attr.save()

        params = {
            'parent_attr': attr,
            'created_user': self._user,
            'status': AttributeValue.STATUS_DATA_ARRAY_PARENT,
        }
        parent_attrv = AttributeValue.objects.create(**params)
        for i in range(0, 10):
            params['value'] = str(i)
            parent_attrv.data_array.add(AttributeValue.objects.create(**params))

        attr.values.add(parent_attrv)

        cloned_attr = attr.clone(self._user)
        self.assertIsNotNone(cloned_attr)
        self.assertNotEqual(cloned_attr.id, attr.id)
        self.assertEqual(cloned_attr.name, attr.name)
        self.assertEqual(cloned_attr.values.count(), attr.values.count())
        self.assertNotEqual(cloned_attr.values.last(), attr.values.last())

        # checks that AttributeValues that parent_attr has also be cloned
        parent_attrv = attr.values.last()
        cloned_attrv = cloned_attr.values.last()

        self.assertEqual(parent_attrv.data_array.count(), cloned_attrv.data_array.count())
        for v1, v2 in zip(parent_attrv.data_array.all(), cloned_attrv.data_array.all()):
            self.assertNotEqual(v1, v2)
            self.assertEqual(v1.value, v2.value)

    def test_clone_entry(self):
        self._entity.attrs.add(EntityAttr.objects.create(**{
            'name': 'attr',
            'type': AttrTypeValue['string'],
            'created_user': self._user,
            'parent_entity': self._entity,
        }))

        entry = Entry.objects.create(name='entry', schema=self._entity, created_user=self._user)
        entry.complement_attrs(self._user)

        entry_attr = entry.attrs.last()
        for i in range(0, 10):
            entry_attr.values.add(AttributeValue.objects.create(**{
                'parent_attr': entry_attr,
                'created_user': self._user,
                'value': str(i),
            }))

        clone = entry.clone(self._user)

        self.assertIsNotNone(clone)
        self.assertNotEqual(clone.id, entry.id)
        self.assertEqual(clone.name, entry.name)
        self.assertEqual(clone.attrs.count(), entry.attrs.count())
        self.assertNotEqual(clone.attrs.last(), entry_attr)

        # checks parent_entry in the cloned Attribute object is updated
        clone_attr = clone.attrs.last()
        self.assertEqual(entry_attr.parent_entry, entry)
        self.assertEqual(clone_attr.parent_entry, clone)

        # checks parent_entry in the cloned AttributeValue object is updated
        self.assertEqual(entry_attr.values.last().parent_attr, entry_attr)
        self.assertEqual(clone_attr.values.last().parent_attr, clone_attr)

    def test_clone_entry_with_extra_params(self):
        entry = Entry.objects.create(name='entry', schema=self._entity, created_user=self._user)
        entry.complement_attrs(self._user)

        clone = entry.clone(self._user, name='cloned_entry')

        self.assertIsNotNone(clone)
        self.assertNotEqual(clone.id, entry.id)
        self.assertEqual(clone.name, 'cloned_entry')

    def test_clone_entry_without_permission(self):
        unknown_user = User.objects.create(username='unknown_user')

        entry = Entry.objects.create(name='entry',
                                     schema=self._entity,
                                     created_user=self._user,
                                     is_public=False)

        entry.complement_attrs(self._user)
        self.assertIsNone(entry.clone(unknown_user))

        # set permission to access, then it can be cloned
        unknown_user.permissions.add(entry.readable)
        self.assertIsNotNone(entry.clone(unknown_user))

    def test_set_value_method(self):
        user = User.objects.create(username='hoge')

        # create referred Entity and Entries
        ref_entity = Entity.objects.create(name='Referred Entity', created_user=user)
        for index in range(0, 10):
            last_ref = Entry.objects.create(name='r-%s' % index, schema=ref_entity, created_user=user)

        attr_info = {
            'str': {'type': AttrTypeValue['string'], 'value': 'foo',
                    'invalid_values': [123, last_ref, True]},
            'obj': {'type': AttrTypeValue['object'], 'value': str(last_ref.id)},
            'name': {'type': AttrTypeValue['named_object'],
                     'value': {'name': 'bar', 'id': str(last_ref.id)}},
            'bool': {'type': AttrTypeValue['boolean'], 'value': False},
            'arr_str': {'type': AttrTypeValue['array_string'], 'value': ['foo', 'bar', 'baz']},
            'arr_obj': {'type': AttrTypeValue['array_object'],
                        'value': [str(x.id) for x in Entry.objects.filter(schema=ref_entity)]},
            'arr_name': {'type': AttrTypeValue['array_named_object'],
                         'value': [{'name': 'hoge', 'id': str(last_ref.id)}]},
            'group': {'type': AttrTypeValue['group'], 'value':
                      str(Group.objects.create(name='group').id)},
            'date': {'type': AttrTypeValue['date'], 'value': date(2018, 12, 31)}
        }

        entity = Entity.objects.create(name='entity', created_user=user)
        for attr_name, info in attr_info.items():
            attr = EntityAttr.objects.create(name=attr_name,
                                             type=info['type'],
                                             created_user=user,
                                             parent_entity=entity)

            if info['type'] & AttrTypeValue['object']:
                attr.referral.add(ref_entity)

            entity.attrs.add(attr)

        entry = Entry.objects.create(name='entry', schema=entity, created_user=user)
        entry.complement_attrs(user)

        for attr_name, info in attr_info.items():
            attr = entry.attrs.get(name=attr_name)
            attrv = attr.add_value(user, info['value'])

            self.assertEqual(attrv, attr.get_latest_value())
            self.assertEqual(attr.values.last().data_type, info['type'])

            # checks that validation processing works well
            if 'invalid_values' in info:
                [self.assertEqual(attr.add_value(user, x).value, str(x)) for x in info['invalid_values']]

        # check update attr-value with specifying entry directly
        new_ref = Entry.objects.get(schema=ref_entity, name='r-1')
        entry.attrs.get(name='obj').add_value(user, new_ref)
        entry.attrs.get(name='name').add_value(user, {'name': 'new_value', 'id': new_ref})
        entry.attrs.get(name='arr_obj').add_value(user, [new_ref])
        entry.attrs.get(name='arr_name').add_value(user, [{'name': 'new_value', 'id': new_ref}])

        latest_value = entry.attrs.get(name='obj').get_latest_value()
        self.assertEqual(latest_value.referral.id, new_ref.id)

        latest_value = entry.attrs.get(name='name').get_latest_value()
        self.assertEqual(latest_value.value, 'new_value')
        self.assertEqual(latest_value.referral.id, new_ref.id)

        latest_value = entry.attrs.get(name='arr_obj').get_latest_value()
        self.assertEqual(latest_value.data_array.count(), 1)
        self.assertEqual(latest_value.data_array.last().referral.id, new_ref.id)

        latest_value = entry.attrs.get(name='arr_name').get_latest_value()
        self.assertEqual(latest_value.data_array.count(), 1)
        self.assertEqual(latest_value.data_array.last().value, 'new_value')
        self.assertEqual(latest_value.data_array.last().referral.id, new_ref.id)

        # test to get attribute values of empty entry
        entry1 = Entry.objects.create(name='entry1', schema=entity, created_user=user)
        entry1.complement_attrs(user)

        results = entry1.get_available_attrs(user)
        self.assertIsNone([x for x in results if x['name'] == 'group'][0]['last_referral'])
        self.assertEqual([x for x in results if x['name'] == 'group'][0]['last_value'], '')

    def test_set_attrvalue_to_entry_attr_without_availabe_value(self):
        user = User.objects.create(username='hoge')

        entity = Entity.objects.create(name='entity', created_user=user)
        entity.attrs.add(EntityAttr.objects.create(**{
            'name': 'attr',
            'type': AttrTypeValue['object'],
            'created_user': user,
            'parent_entity': entity,
        }))

        entry = Entry.objects.create(name='entry', schema=entity, created_user=user)
        entry.complement_attrs(user)

        attr  = entry.attrs.first()
        attrv = attr.add_value(user, None)

        self.assertIsNotNone(attrv)
        self.assertEqual(attr.values.count(), 1)
        self.assertIsNone(attr.values.first().referral)

    def test_update_data_type_of_attrvalue(self):
        """
        This test checks that data_type parameter of AttributeValue will be changed after
        calling 'get_available_attrs' method if that parameter is not set.

        Basically, the data_type of AttributeValue is same with the type of Attribute. But,
        some AttributeValues which are registered before adding this parameter do not have
        available value. So this processing is needed to set. This assumes unknown typed
        AttributeValue as the current type of Attribute.
        """
        user = User.objects.create(username='hoge')

        entity = Entity.objects.create(name='entity', created_user=user)
        entity.attrs.add(EntityAttr.objects.create(**{
            'name': 'attr',
            'type': AttrTypeValue['string'],
            'created_user': user,
            'parent_entity': entity,
        }))

        entry = Entry.objects.create(name='entry', schema=entity, created_user=user)
        entry.complement_attrs(user)

        attrv = entry.attrs.first().add_value(user, 'hoge')

        # vanish data_type of initial AttributeValue instance
        attrv.data_type = 0
        attrv.save()

        # this processing complements data_type parameter of latest AttributeValue
        # as the current type of Attribute instance
        results = entry.get_available_attrs(self._user)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['last_value'], 'hoge')
        self.assertEqual(AttributeValue.objects.get(id=attrv.id).data_type, AttrTypeValue['string'])

    def test_get_deleted_referred_attrs(self):
        user = User.objects.create(username='hoge')

        # create referred Entity and Entries
        ref_entity = Entity.objects.create(name='ReferredEntity', created_user=user)
        ref_entry = Entry.objects.create(name='ReferredEntry', schema=ref_entity, created_user=user)

        attr_info = {
            'obj': {'type': AttrTypeValue['object'], 'value': ref_entry},
            'name': {'type': AttrTypeValue['named_object'], 'value': {'name': 'hoge', 'id': ref_entry}},
            'arr_obj': {'type': AttrTypeValue['array_object'], 'value': [ref_entry]},
            'arr_name': {'type': AttrTypeValue['array_named_object'], 'value': [{'name': 'hoge', 'id': ref_entry}]},
        }

        entity = Entity.objects.create(name='entity', created_user=user)
        for attr_name, info in attr_info.items():
            attr = EntityAttr.objects.create(name=attr_name,
                                             type=info['type'],
                                             created_user=user,
                                             parent_entity=entity)

            attr.referral.add(ref_entity)
            entity.attrs.add(attr)

        entry = Entry.objects.create(name='entry', schema=entity, created_user=user)
        entry.complement_attrs(user)
        for attr_name, info in attr_info.items():
            entry.attrs.get(name=attr_name).add_value(user, info['value'])

        # checks all set vaialbles can be got correctly
        available_attrs = entry.get_available_attrs(user)
        self.assertEqual(len(available_attrs), len(attr_info))
        for attr in available_attrs:
            if attr['name'] == 'obj':
                self.assertEqual(attr['last_referral'].id, ref_entry.id)
            elif attr['name'] == 'name':
                self.assertEqual(attr['last_referral'].id, ref_entry.id)
            elif attr['name'] == 'arr_obj':
                self.assertEqual([x.id for x in attr['last_value']], [ref_entry.id])
            elif attr['name'] == 'arr_name':
                self.assertEqual([x['value'] for x in attr['last_value']], ['hoge'])
                self.assertEqual([x['referral'].id for x in attr['last_value']], [ref_entry.id])

        # delete referral entry, then get available attrs
        ref_entry.delete()
        available_attrs = entry.get_available_attrs(user)
        self.assertEqual(len(available_attrs), len(attr_info))
        for attr in available_attrs:
            if attr['name'] == 'obj':
                self.assertEqual(attr['last_referral'], None)
            elif attr['name'] == 'name':
                self.assertEqual(attr['last_referral'], None)
            elif attr['name'] == 'arr_obj':
                self.assertEqual(attr['last_value'], [])
            elif attr['name'] == 'arr_name':
                self.assertEqual([x['value'] for x in attr['last_value']], ['hoge'])
                self.assertEqual([x['referral'] for x in attr['last_value']], [None])

    def test_get_available_attrs_with_empty_referral(self):
        user = User.objects.create(username='hoge')

        ref_entity = Entity.objects.create(name='ReferredEntity', created_user=user)
        entity = Entity.objects.create(name='entity', created_user=user)
        attr_info = {
            'obj': {'type': AttrTypeValue['object'], 'value': None},
            'name': {'type': AttrTypeValue['named_object'], 'value': {'name': 'hoge', 'id': None}},
            'arr_obj': {'type': AttrTypeValue['array_object'], 'value': []},
            'arr_name': {'type': AttrTypeValue['array_named_object'], 'value': [{'name': 'hoge', 'id': None}]},
        }

        entity = Entity.objects.create(name='entity', created_user=user)
        for attr_name, info in attr_info.items():
            attr = EntityAttr.objects.create(name=attr_name,
                                             type=info['type'],
                                             created_user=user,
                                             parent_entity=entity)

            attr.referral.add(ref_entity)
            entity.attrs.add(attr)

        entry = Entry.objects.create(name='entry', schema=entity, created_user=user)
        entry.complement_attrs(user)
        for attr_name, info in attr_info.items():
            entry.attrs.get(name=attr_name).add_value(user, info['value'])

        # get empty values for each attributes
        available_attrs = entry.get_available_attrs(user)
        self.assertEqual(len(available_attrs), len(attr_info))
        for attr in available_attrs:
            if attr['name'] == 'obj':
                self.assertEqual(attr['last_referral'], None)
            elif attr['name'] == 'name':
                self.assertEqual(attr['last_referral'], None)
            elif attr['name'] == 'arr_obj':
                self.assertEqual(attr['last_value'], [])
            elif attr['name'] == 'arr_name':
                self.assertEqual([x['value'] for x in attr['last_value']], ['hoge'])
                self.assertEqual([x['referral'] for x in attr['last_value']], [None])

    def test_get_value_of_attrv(self):
        user = User.objects.create(username='hoge')

        # create referred Entity and Entries
        ref_entity = Entity.objects.create(name='Referred Entity', created_user=user)
        for index in range(0, 10):
            last_ref = Entry.objects.create(name='r-%s' % index, schema=ref_entity, created_user=user)

        attr_info = {
            'str': {'type': AttrTypeValue['string'], 'value': 'foo'},
            'obj': {'type': AttrTypeValue['object'], 'value': str(last_ref.id)},
            'name': {'type': AttrTypeValue['named_object'], 'value': {'name': 'bar', 'id': str(last_ref.id)}},
            'bool': {'type': AttrTypeValue['boolean'], 'value': False},
            'arr_str': {'type': AttrTypeValue['array_string'], 'value': ['foo', 'bar', 'baz']},
            'arr_obj': {'type': AttrTypeValue['array_object'],
                        'value': [str(x.id) for x in Entry.objects.filter(schema=ref_entity)]},
            'arr_name': {'type': AttrTypeValue['array_named_object'],
                         'value': [{'name': 'hoge', 'id': str(last_ref.id)}]},
            'group': {'type': AttrTypeValue['group'], 'value': str(Group.objects.create(name='group').id)},
            'date': {'type': AttrTypeValue['date'], 'value': date(2018, 12, 31)}
        }

        entity = Entity.objects.create(name='entity', created_user=user)
        for attr_name, info in attr_info.items():
            attr = EntityAttr.objects.create(name=attr_name,
                                             type=info['type'],
                                             created_user=user,
                                             parent_entity=entity)

            if info['type'] & AttrTypeValue['object']:
                attr.referral.add(ref_entity)

            entity.attrs.add(attr)

        entry = Entry.objects.create(name='entry', schema=entity, created_user=user)
        entry.complement_attrs(user)

        for attr_name, info in attr_info.items():
            attr = entry.attrs.get(name=attr_name)
            attrv = attr.add_value(user, info['value'])

        # test get_value method for each AttributeValue of Attribute types
        expected_values = {
            'str': str(attr_info['str']['value']),
            'obj': Entry.objects.get(id=attr_info['obj']['value']).name,
            'name': {attr_info['name']['value']['name']: Entry.objects.get(id=attr_info['name']['value']['id']).name},
            'bool': attr_info['bool']['value'],
            'arr_str': attr_info['arr_str']['value'],
            'arr_obj': [Entry.objects.get(id=x).name for x in attr_info['arr_obj']['value']],
            'arr_name': [{x['name']: Entry.objects.get(id=x['id']).name} for x in attr_info['arr_name']['value']],
        }

        for attr_name, value in expected_values.items():
            attr = entry.attrs.get(name=attr_name)
            if attr_name == 'arr_str':
                self.assertEqual(set(attr.get_latest_value().get_value()), set(value))
            else:
                self.assertEqual(attr.get_latest_value().get_value(), value)

        # test get_value method with 'with_metainfo' parameter
        expected_values = {
            'str': {'type': AttrTypeValue['string'], 'value': str(attr_info['str']['value'])},
            'obj': {
                'type': AttrTypeValue['object'],
                'value': {
                    'id': Entry.objects.get(id=attr_info['obj']['value']).id,
                    'name': Entry.objects.get(id=attr_info['obj']['value']).name,
                }
            },
            'name': {
                'type': AttrTypeValue['named_object'],
                'value': {
                    attr_info['name']['value']['name']: {
                        'id': Entry.objects.get(id=attr_info['name']['value']['id']).id,
                        'name': Entry.objects.get(id=attr_info['name']['value']['id']).name,
                    }
                },
            },
            'bool': {'type': AttrTypeValue['boolean'], 'value': attr_info['bool']['value']},
            'arr_str': {'type': AttrTypeValue['array_string'], 'value': attr_info['arr_str']['value']},
            'arr_obj': {
                'type': AttrTypeValue['array_object'],
                'value': [{
                    'id': Entry.objects.get(id=x).id,
                    'name': Entry.objects.get(id=x).name
                } for x in attr_info['arr_obj']['value']]
            },
            'arr_name': {
                'type': AttrTypeValue['array_named_object'],
                'value': [{x['name']: {
                    'id': Entry.objects.get(id=x['id']).id,
                    'name': Entry.objects.get(id=x['id']).name,
                }} for x in attr_info['arr_name']['value']]
            },
        }

        for attr_name, value in expected_values.items():
            attr = entry.attrs.get(name=attr_name)
            if attr_name == 'arr_str':
                self.assertEqual(set(attr.get_latest_value().get_value(with_metainfo=True)), set(value))
            else:
                self.assertEqual(attr.get_latest_value().get_value(with_metainfo=True), value)

    def test_convert_value_to_register(self):
        user = User.objects.create(username='hoge')

        ref_entity = Entity.objects.create(name='Referred Entity', created_user=user)
        ref_entry = Entry.objects.create(name='Ref Entry', schema=ref_entity, created_user=user)
        attr_info = {
            'str': {'type': AttrTypeValue['string']},
            'obj': {'type': AttrTypeValue['object']},
            'name': {'type': AttrTypeValue['named_object']},
            'bool': {'type': AttrTypeValue['boolean']},
            'arr1': {'type': AttrTypeValue['array_string']},
            'arr2': {'type': AttrTypeValue['array_object']},
            'arr3': {'type': AttrTypeValue['array_named_object']},
            'group': {'type': AttrTypeValue['group']},
            'date': {'type': AttrTypeValue['date']}
        }

        entity = Entity.objects.create(name='entity', created_user=user)
        for attr_name, info in attr_info.items():
            attr = EntityAttr.objects.create(name=attr_name,
                                             type=info['type'],
                                             created_user=user,
                                             parent_entity=entity)

            if info['type'] & AttrTypeValue['object']:
                attr.referral.add(ref_entity)

            entity.attrs.add(attr)

        entry = Entry.objects.create(name='entry', schema=entity, created_user=user)
        entry.complement_attrs(user)

        group = Group.objects.create(name='Group')
        checklist = [
            {'attr': 'str', 'input': 'foo', 'checker': lambda x: x == 'foo'},
            {'attr': 'obj', 'input': 'Ref Entry', 'checker': lambda x: x.id == ref_entry.id},
            {'attr': 'obj', 'input': 'Invalid Entry', 'checker': lambda x: x == None},
            {'attr': 'name', 'input': {'foo': ref_entry},
             'checker': lambda x: x['name'] == 'foo' and x['id'].id == ref_entry.id},
            {'attr': 'bool', 'input': False, 'checker': lambda x: x == False},
            {'attr': 'arr1', 'input': ['foo', 'bar'], 'checker': lambda x: x == ['foo', 'bar']},
            {'attr': 'arr2', 'input': ['Ref Entry'], 'checker': lambda x: len(x) == 1 and x[0].id == ref_entry.id},
            {'attr': 'arr2', 'input': ['Ref Entry', 'Invalid Entry'],
             'checker': lambda x: len(x) == 1 and x[0].id == ref_entry.id},
            {'attr': 'arr3', 'input': [{'foo': 'Ref Entry'}],
             'checker': lambda x: len(x) == 1 and x[0]['name'] == 'foo' and x[0]['id'].id == ref_entry.id},
            {'attr': 'arr3', 'input': [{'foo': 'Ref Entry'}, {'bar': 'Invalid Entry'}],
             'checker': lambda x: (len(x) == 2 and x[0]['name'] == 'foo' and x[0]['id'].id == ref_entry.id and
                                  x[1]['name'] == 'bar' and x[1]['id'] == None)},
            {'attr': 'group', 'input': 'Group', 'checker': lambda x: x == group.id},
            {'attr': 'date', 'input': date(2018, 12, 31), 'checker': lambda x: x == date(2018, 12, 31)}
        ]
        for info in checklist:
            attr = entry.attrs.get(name=info['attr'])

            converted_data = attr.convert_value_to_register(info['input'])
            self.assertTrue(info['checker'](converted_data))

            # create AttributeValue using converted value
            attr.add_value(user, converted_data)

            self.assertIsNotNone(attr.get_latest_value())

    def test_export_entry(self):
        user = User.objects.create(username='hoge')

        ref_entity = Entity.objects.create(name='Referred Entity', created_user=user)
        attr_info = {
            'str1': {'type': AttrTypeValue['string'], 'is_public': True},
            'str2': {'type': AttrTypeValue['string'], 'is_public': True},
            'obj': {'type': AttrTypeValue['object'], 'is_public': True},
            'invisible': {'type': AttrTypeValue['string'], 'is_public': False},
        }

        entity = Entity.objects.create(name='entity', created_user=user)
        for attr_name, info in attr_info.items():
            attr = EntityAttr.objects.create(name=attr_name,
                                             type=info['type'],
                                             created_user=user,
                                             parent_entity=entity,
                                             is_public=info['is_public'])

            if info['type'] & AttrTypeValue['object']:
                attr.referral.add(ref_entity)

            entity.attrs.add(attr)

        entry = Entry.objects.create(name='entry', schema=entity, created_user=user)
        entry.complement_attrs(user)
        entry.attrs.get(name='str1').add_value(user, 'hoge')

        entry.attrs.get(name='str2').add_value(user, 'foo')
        entry.attrs.get(name='str2').add_value(user, 'bar') # update AttributeValue of Attribute 'str2'

        exported_data = entry.export(user)
        self.assertEqual(exported_data['name'], entry.name)
        self.assertEqual(len(exported_data['attrs']), len([x for x in attr_info.values() if x['is_public']]))

        self.assertEqual(exported_data['attrs']['str1'], 'hoge')
        self.assertEqual(exported_data['attrs']['str2'], 'bar')
        self.assertIsNone(exported_data['attrs']['obj'])

        # change the name of EntityAttr then export entry
        NEW_ATTR_NAME = 'str1 (changed)'
        entity_attr = entry.schema.attrs.get(name='str1')
        entity_attr.name = NEW_ATTR_NAME
        entity_attr.save()

        exported_data = entry.export(user)
        self.assertTrue(NEW_ATTR_NAME in exported_data['attrs'])
        self.assertEqual(exported_data['attrs'][NEW_ATTR_NAME], 'hoge')

        # Add an Attribute after creating entry
        entity.attrs.add(EntityAttr.objects.create(**{
            'name': 'new_attr',
            'type': AttrTypeValue['string'],
            'created_user': user,
            'parent_entity': entity,
        }))
        exported_data = entry.export(user)
        self.assertTrue('new_attr' in exported_data['attrs'])

    def test_search_entries(self):
        user = User.objects.create(username='hoge')

        # create referred Entity and Entries
        ref_entity = Entity.objects.create(name='Referred Entity', created_user=user)
        ref_entry = Entry.objects.create(name='referred_entry', schema=ref_entity, created_user=user)
        ref_group = Group.objects.create(name='group')

        attr_info = {
            'str': {'type': AttrTypeValue['string'], 'value': 'foo-%d'},
            'str2': {'type': AttrTypeValue['string'], 'value': 'foo-%d'},
            'obj': {'type': AttrTypeValue['object'], 'value': str(ref_entry.id)},
            'name': {'type': AttrTypeValue['named_object'], 'value': {'name': 'bar', 'id': str(ref_entry.id)}},
            'bool': {'type': AttrTypeValue['boolean'], 'value': False},
            'group': {'type': AttrTypeValue['group'], 'value': str(ref_group.id)},
            'date': {'type': AttrTypeValue['date'], 'value': date(2018, 12, 31)},
            'arr_str': {'type': AttrTypeValue['array_string'], 'value': ['foo', 'bar', 'baz']},
            'arr_obj': {'type': AttrTypeValue['array_object'],
                        'value': [str(x.id) for x in Entry.objects.filter(schema=ref_entity)]},
            'arr_name': {'type': AttrTypeValue['array_named_object'],
                         'value': [{'name': 'hoge', 'id': str(ref_entry.id)}]},
        }

        entity = Entity.objects.create(name='entity', created_user=user)
        for attr_name, info in attr_info.items():
            attr = EntityAttr.objects.create(name=attr_name,
                                             type=info['type'],
                                             created_user=user,
                                             parent_entity=entity)

            if info['type'] & AttrTypeValue['object']:
                attr.referral.add(ref_entity)

            entity.attrs.add(attr)

        for index in range(0, 11):
            entry = Entry.objects.create(name='e-%d' % index, schema=entity, created_user=user)
            entry.complement_attrs(user)

            for attr_name, info in attr_info.items():
                attr = entry.attrs.get(name=attr_name)
                if attr_name == 'str':
                    attr.add_value(user, info['value'] % index)
                elif attr_name == 'str2':
                    attr.add_value(user, info['value'] % (index + 100))
                else:
                    attr.add_value(user, info['value'])

            entry.register_es()

        # search entries
        ret = Entry.search_entries(user, [entity.id], [
            {'name': 'str'},
            {'name': 'str2'},
            {'name': 'obj'},
            {'name': 'name'},
            {'name': 'bool'},
            {'name': 'group'},
            {'name': 'date'},
            {'name': 'arr_str'},
            {'name': 'arr_obj'},
            {'name': 'arr_name'},
        ])
        self.assertEqual(ret['ret_count'], 11)
        self.assertEqual(len(ret['ret_values']), 11)

        # check returned contents is corrected
        for v in ret['ret_values']:
            self.assertEqual(v['entity']['id'], entity.id)
            self.assertEqual(len(v['attrs']), len(attr_info))

            entry = Entry.objects.get(id=v['entry']['id'])

            for (attrname, attrinfo) in v['attrs'].items():
                attr = entry.attrs.get(schema__name=attrname)
                attrv = attr.get_latest_value()

                # checks accurate type parameters are stored
                self.assertEqual(attrinfo['type'], attrv.data_type)

                # checks accurate values are stored
                if attrname == 'str' or attrname == 'str2':
                    self.assertEqual(attrinfo['value'], attrv.value)

                elif attrname == 'obj':
                    self.assertEqual(attrinfo['value']['id'], attrv.referral.id)
                    self.assertEqual(attrinfo['value']['name'], attrv.referral.name)

                elif attrname == 'name':
                    key = attrv.value
                    self.assertEqual(attrinfo['value'][key]['id'], attrv.referral.id)
                    self.assertEqual(attrinfo['value'][key]['name'], attrv.referral.name)

                if attrname == 'bool':
                    self.assertEqual(attrinfo['value'], str(attrv.boolean))

                if attrname == 'date':
                    self.assertEqual(attrinfo['value'], str(attrv.date))

                elif attrname == 'group':
                    group = Group.objects.get(id=int(attrv.value))
                    self.assertEqual(attrinfo['value']['id'], group.id)
                    self.assertEqual(attrinfo['value']['name'], group.name)

                elif attrname == 'arr_str':
                    self.assertEqual(sorted([x for x in attrinfo['value']]),
                                     sorted([x.value for x in attrv.data_array.all()]))

                elif attrname == 'arr_obj':
                    self.assertEqual([x['id'] for x in attrinfo['value']],
                                     [x.referral.id for x in attrv.data_array.all()])
                    self.assertEqual([x['name'] for x in  attrinfo['value']],
                                     [x.referral.name for x in attrv.data_array.all()])

                elif attrname == 'arr_name':
                    for co_attrv in attrv.data_array.all():
                        _co_v = [x[co_attrv.value] for x in attrinfo['value']]
                        self.assertTrue(_co_v)
                        self.assertEqual(_co_v[0]['id'], co_attrv.referral.id)
                        self.assertEqual(_co_v[0]['name'], co_attrv.referral.name)

        # search entries with maximum entries to get
        ret = Entry.search_entries(user, [entity.id], [{'name': 'str'}], 5)
        self.assertEqual(ret['ret_count'], 11)
        self.assertEqual(len(ret['ret_values']), 5)

        # search entries with keyword
        ret = Entry.search_entries(user, [entity.id], [{'name': 'str', 'keyword': 'foo-5'}])
        self.assertEqual(ret['ret_count'], 1)
        self.assertEqual(ret['ret_values'][0]['entry']['name'], 'e-5')

        # search entries with blank values
        entry = Entry.objects.create(name='entry-blank', schema=entity, created_user=user)
        entry.complement_attrs(user)
        entry.register_es()

        for attrname in attr_info.keys():
            ret = Entry.search_entries(user, [entity.id], [{'name': attrname}])
            self.assertEqual(len([x for x in ret['ret_values'] if x['entry']['id'] == entry.id]), 1)

        # check functionallity of the 'exact_match' parameter
        ret = Entry.search_entries(user, [entity.id], [{'name': 'str', 'keyword': 'foo-1'}])
        self.assertEqual(ret['ret_count'], 2)
        ret = Entry.search_entries(user, [entity.id], [{'name': 'str', 'keyword': 'foo-1', 'exact_match': True}])
        self.assertEqual(ret['ret_count'], 1)
        self.assertEqual(ret['ret_values'][0]['entry']['name'], 'e-1')

        # check functionallity of the 'entry_name' parameter
        ret = Entry.search_entries(user, [], entry_name='e-1')
        self.assertEqual(ret['ret_count'], 2)

        # check combination of 'entry_name' and 'hint_attrs' parameter
        ret = Entry.search_entries(user, [entity.id], [{'name': 'str', 'keyword': 'foo-10'}], entry_name='e-1')
        self.assertEqual(ret['ret_count'], 1)

    def test_search_entries_with_or_match(self):
        user = User.objects.create(username='hoge')
        entity_info = {
            'E1': [
                {'type': AttrTypeValue['string'], 'name': 'foo'}
            ],
            'E2': [
                {'type': AttrTypeValue['string'], 'name': 'bar'}
            ]
        }

        for (name, attrinfos) in entity_info.items():
            entity = Entity.objects.create(name=name, created_user=user)

            for attrinfo in attrinfos:
                entity.attrs.add(EntityAttr.objects.create(**{
                    'name': attrinfo['name'],
                    'type': attrinfo['type'],
                    'created_user': user,
                    'parent_entity': entity,
                }))

            for i in [x for x in range(0, 5)]:
                entry = Entry.objects.create(name='%s-%d' % (entity.name, i), schema=entity, created_user=user)
                entry.complement_attrs(user)

                for attrinfo in attrinfos:
                    attr = entry.attrs.get(schema__name=attrinfo['name'])
                    attr.add_value(user, str(i))

                entry.register_es()

        # search entries by only attribute name and keyword without entity
        hints = [{'name': x.name, 'keyword': '3'} for x in EntityAttr.objects.filter(is_active=True)]
        ret = Entry.search_entries(user, [], hints, or_match=True)

        self.assertEqual(ret['ret_count'], 2)
        self.assertEqual(sorted([x['entry']['name'] for x in ret['ret_values']]), sorted(['E1-3', 'E2-3']))

    def test_register_entry_to_elasticsearch(self):
        ENTRY_COUNTS = 10
        user = User.objects.create(username='hoge')

        # create referred Entity and Entries
        ref_entity = Entity.objects.create(name='Referred Entity', created_user=user)

        ref_entry1 = Entry.objects.create(name='referred_entry1', schema=ref_entity, created_user=user)
        ref_entry2 = Entry.objects.create(name='referred_entry2', schema=ref_entity, created_user=user)

        ref_group = Group.objects.create(name='group')

        attr_info = {
            'str': {
                'type': AttrTypeValue['string'],
                'value': 'foo',
            },
            'obj': {
                'type': AttrTypeValue['object'],
                'value': str(ref_entry1.id),
            },
            'name': {
                'type': AttrTypeValue['named_object'],
                'value': {'name': 'bar', 'id': str(ref_entry1.id)},
            },
            'bool': {
                'type': AttrTypeValue['boolean'],
                'value': False,
            },
            'date': {
                'type': AttrTypeValue['date'],
                'value': date(2018, 1, 1),
            },
            'group': {
                'type': AttrTypeValue['group'],
                'value': str(ref_group.id),
            },
            'arr_str': {
                'type': AttrTypeValue['array_string'],
                'value': ['foo', 'bar', 'baz'],
            },
            'arr_obj': {
                'type': AttrTypeValue['array_object'],
                'value': [str(x.id) for x in Entry.objects.filter(schema=ref_entity)],
            },
            'arr_name': {
                'type': AttrTypeValue['array_named_object'],
                'value': [{'name': 'hoge', 'id' : str(x.id)} for x in Entry.objects.filter(schema=ref_entity)],
            }
        }

        entity = Entity.objects.create(name='entity', created_user=user)
        for attr_name, info in attr_info.items():
            attr = EntityAttr.objects.create(name=attr_name,
                                             type=info['type'],
                                             created_user=user,
                                             parent_entity=entity)

            if info['type'] & AttrTypeValue['object']:
                attr.referral.add(ref_entity)

            entity.attrs.add(attr)

        for index in range(0, ENTRY_COUNTS):
            entry = Entry.objects.create(name='e-%d' % index, schema=entity, created_user=user)
            entry.complement_attrs(user)

            for attr_name, info in attr_info.items():
                attr = entry.attrs.get(name=attr_name)
                attr.add_value(user, info['value'])

            entry.register_es()

        # checks that all entries are registered to the ElasticSearch.
        res = self._es.indices.stats(index=settings.ES_CONFIG['INDEX'])
        self.assertEqual(res['_all']['total']['segments']['count'], ENTRY_COUNTS)

        # checks that all registered entries can be got from Elasticsearch
        for entry in Entry.objects.filter(schema=entity):
            res = self._es.get(index=settings.ES_CONFIG['INDEX'], doc_type='entry', id=entry.id)
            self.assertTrue(res['found'])

            # This checks whether returned results have all values of attributes
            self.assertEqual(set([x['name'] for x in res['_source']['attr']]),
                             set(k for k in attr_info.keys()))

            for (k, v) in attr_info.items():
                value = [x for x in res['_source']['attr'] if x['name'] == k]

                self.assertTrue(all([x['type'] == v['type'] for x in value]))
                if k == 'str':
                    self.assertEqual(len(value), 1)
                    self.assertEqual(value[0]['value'], 'foo')

                elif k == 'obj':
                    self.assertEqual(len(value), 1)
                    self.assertEqual(value[0]['value'], ref_entry1.name)
                    self.assertEqual(value[0]['referral_id'], ref_entry1.id)

                elif k == 'name':
                    self.assertEqual(len(value), 1)
                    self.assertEqual(value[0]['key'], 'bar')
                    self.assertEqual(value[0]['value'], ref_entry1.name)
                    self.assertEqual(value[0]['referral_id'], ref_entry1.id)

                elif k == 'bool':
                    self.assertEqual(len(value), 1)
                    self.assertEqual(value[0]['value'], 'False')

                elif k == 'date':
                    self.assertEqual(len(value), 1)
                    self.assertEqual(value[0]['date_value'], '2018-01-01')

                elif k == 'group':
                    self.assertEqual(len(value), 1)
                    self.assertEqual(value[0]['value'], ref_group.name)
                    self.assertEqual(value[0]['referral_id'], ref_group.id)

                elif k == 'arr_str':
                    self.assertEqual(len(value), 3)
                    self.assertEqual(sorted([x['value'] for x in value]),
                                     sorted(['foo', 'bar', 'baz']))

                elif k == 'arr_obj':
                    self.assertEqual(len(value), Entry.objects.filter(schema=ref_entity).count())
                    self.assertEqual(sorted([x['value'] for x in value]),
                                     sorted([x.name for x in Entry.objects.filter(schema=ref_entity)]))
                    self.assertEqual(sorted([x['referral_id'] for x in value]),
                                     sorted([x.id for x in Entry.objects.filter(schema=ref_entity)]))

                elif k == 'arr_name':
                    self.assertEqual(len(value), Entry.objects.filter(schema=ref_entity).count())
                    self.assertEqual(sorted([x['value'] for x in value]),
                                     sorted([x.name for x in Entry.objects.filter(schema=ref_entity)]))
                    self.assertEqual(sorted([x['referral_id'] for x in value]),
                                     sorted([x.id for x in Entry.objects.filter(schema=ref_entity)]))
                    self.assertTrue(all([x['key'] == 'hoge' for x in value]))

        # checks delete entry and checks deleted entry will also be removed from Elasticsearch
        entry = Entry.objects.filter(schema=entity).last()
        entry.delete()

        res = self._es.indices.stats(index=settings.ES_CONFIG['INDEX'])
        self.assertEqual(res['_all']['total']['segments']['count'], ENTRY_COUNTS - 1)

        res = self._es.get(index=settings.ES_CONFIG['INDEX'], doc_type='entry', id=entry.id, ignore=[404])
        self.assertFalse(res['found'])

    def test_update_elasticsearch_field(self):
        user = User.objects.create(username='hoge')

        entity = Entity.objects.create(name='entity', created_user=user)
        entity_attr = EntityAttr.objects.create(name='attr',
                                                type=AttrTypeValue['string'],
                                                created_user=user,
                                                parent_entity=entity)
        entity.attrs.add(entity_attr)

        entry = Entry.objects.create(name='entry', schema=entity, created_user=user)
        entry.complement_attrs(user)

        attr = entry.attrs.get(schema=entity_attr)
        attr.add_value(user, 'hoge')

        # register entry to the Elasticsearch
        entry.register_es()

        # checks registered value is corrected
        res = self._es.get(index=settings.ES_CONFIG['INDEX'], doc_type='entry', id=entry.id)
        self.assertEqual(res['_source']['attr'][0]['name'], entity_attr.name)
        self.assertEqual(res['_source']['attr'][0]['type'], entity_attr.type)
        self.assertEqual(res['_source']['attr'][0]['value'], 'hoge')


        # update latest value of Attribute 'attr'
        attr.add_value(user, 'fuga')
        entry.register_es()

        # checks registered value was also updated
        res = self._es.get(index=settings.ES_CONFIG['INDEX'], doc_type='entry', id=entry.id)
        self.assertEqual(res['_source']['attr'][0]['value'], 'fuga')

    def test_search_entries_from_elasticsearch(self):
        user = User.objects.create(username='hoge')

        entities = []
        for ename in ['eitnty1', 'entity2']:
            entity = Entity.objects.create(name=ename, created_user=user)

            entities.append(entity)
            for index in range(0, 2):
                entity.attrs.add(EntityAttr.objects.create(name='attr-%s' % index,
                                                           type=AttrTypeValue['string'],
                                                           created_user=user,
                                                           parent_entity=entity))

            entity.attrs.add(EntityAttr.objects.create(name='ほげ',
                                                       type=AttrTypeValue['string'],
                                                       created_user=user,
                                                       parent_entity=entity))

            entity.attrs.add(EntityAttr.objects.create(name='attr-arr',
                                                       type=AttrTypeValue['array_string'],
                                                       created_user=user,
                                                       parent_entity=entity))

            entity.attrs.add(EntityAttr.objects.create(name='attr-date',
                                                       type=AttrTypeValue['date'],
                                                       created_user=user,
                                                       parent_entity=entity))

        entry_info = {
            'entry1': {
                'attr-0': '2018/01/01',
                'attr-1': 'bar',
                'ほげ': 'ふが',
                'attr-date': date(2018, 1, 2),
                'attr-arr': ['hoge', 'fuga']
            },
            'entry2': {
                'attr-0': 'hoge',
                'attr-1': 'bar',
                'ほげ': 'ふが',
                'attr-date': None,
                'attr-arr': ['2018/01/01']
            },
            'entry3': {
                'attr-0': '0123-45-6789', # This is date format but not date value
                'attr-1': 'hoge',
                'ほげ': 'fuga',
                'attr-date': None,
                'attr-arr': []
            }
        }

        for entity in entities:
            for (name, attrinfo) in entry_info.items():
                entry = Entry.objects.create(name=name, schema=entity, created_user=user)
                entry.complement_attrs(user)

                for attr in entry.attrs.all():
                    attr.add_value(user, attrinfo[attr.schema.name])

                entry.register_es()

        # search entries of entity1 from Elasticsearch and checks that the entreis of non entity1
        # are not returned.
        resp = Entry.search_entries(user, [entities[0].id], [{'name': 'attr-0'}])
        self.assertEqual(resp['ret_count'], 3)
        self.assertTrue(all([x['entity']['id'] == entities[0].id for x in resp['ret_values']]))

        # checks the value which is non date but date format was registered correctly
        self.assertEqual([entry_info['entry3']['attr-0']],
                         [x['attrs']['attr-0']['value'] for x in resp['ret_values']
                             if x['entry']['name'] == 'entry3'])

        # checks ret_count counts number of entries whatever attribute contidion was changed
        resp = Entry.search_entries(user, [entities[0].id], [{'name': 'attr-0'}, {'name': 'attr-1'}])
        self.assertEqual(resp['ret_count'], 3)
        resp = Entry.search_entries(user, [entities[0].id, entities[1].id], [{'name': 'attr-0'}])
        self.assertEqual(resp['ret_count'], 6)

        # checks results that contain multi-byte values could be got
        resp = Entry.search_entries(user, [entities[0].id], [{'name': 'ほげ', 'keyword': 'ふが'}])
        self.assertEqual(resp['ret_count'], 2)
        self.assertEqual(sorted([x['entry']['name'] for x in resp['ret_values']]),
                         sorted(['entry1', 'entry2']))

        # search entries with date keyword parameter in string type from Elasticsearch
        resp = Entry.search_entries(user, [entities[0].id], [{'name': 'attr-0', 'keyword': '2018/01/01'}])
        self.assertEqual(resp['ret_count'], 1)
        self.assertEqual(resp['ret_values'][0]['entry']['name'], 'entry1')
        self.assertEqual(resp['ret_values'][0]['attrs']['attr-0']['value'], '2018-01-01')

        # search entries with date keyword parameter in date type from Elasticsearch
        for x in ['2018-01-02', '2018/01/02', '2018-1-2', '2018-01-2', '2018-1-02']:
            resp = Entry.search_entries(user, [entities[0].id], [{'name': 'attr-date', 'keyword': x}])
            self.assertEqual(resp['ret_count'], 1)
            self.assertEqual(resp['ret_values'][0]['entry']['name'], 'entry1')
            self.assertEqual(resp['ret_values'][0]['attrs']['attr-date']['value'], '2018-01-02')

        # search entries with date keyword parameter in string array type from Elasticsearch
        resp = Entry.search_entries(user, [entities[0].id], [{'name': 'attr-arr', 'keyword': '2018-01-01'}])
        self.assertEqual(resp['ret_count'], 1)
        self.assertEqual(resp['ret_values'][0]['entry']['name'], 'entry2')
        self.assertEqual(resp['ret_values'][0]['attrs']['attr-arr']['value'], ['2018-01-01'])

        # search entries with keyword parameter that other entry has same value in untarget attr
        resp = Entry.search_entries(user, [entities[0].id], [{'name': 'attr-0', 'keyword': 'hoge'}])
        self.assertEqual(resp['ret_count'], 1)
        self.assertEqual(resp['ret_values'][0]['entry']['name'], 'entry2')

        # search entries with keyword parameter which is array type
        resp = Entry.search_entries(user, [entities[0].id], [{'name': 'attr-arr', 'keyword': 'hoge'}])
        self.assertEqual(resp['ret_count'], 1)
        self.assertEqual(resp['ret_values'][0]['entry']['name'], 'entry1')
        self.assertEqual(sorted(resp['ret_values'][0]['attrs']['attr-arr']['value']),
                         sorted(['hoge', 'fuga']))

        # search entries with an invalid or unmatch date keyword parameter in date type from Elasticsearch
        for x in ['2018/02/01', 'hoge']:
            resp = Entry.search_entries(user, [entities[0].id], [{'name': 'attr-date', 'keyword': x}])
            self.assertEqual(resp['ret_count'], 0)

    def test_search_result_count(self):
        """
        This tests that ret_count of search_entries will be equal with actual count of entries.
        """
        user = User.objects.create(username='hoge')

        ref_entity = Entity.objects.create(name='ref_entity', created_user=user)
        ref_entry = Entry.objects.create(name='ref', schema=ref_entity, created_user=user)

        entity = Entity.objects.create(name='entity', created_user=user)
        for name in ['foo', 'bar']:
            attr = EntityAttr.objects.create(name=name,
                                             type=AttrTypeValue['object'],
                                             created_user=user,
                                             parent_entity=entity)
            attr.referral.add(ref_entity)
            entity.attrs.add(attr)

        for i in range(0, 20):
            entry = Entry.objects.create(name='e%3d' % i, schema=entity, created_user=user)
            entry.complement_attrs(user)

            if i < 10:
                entry.attrs.get(schema__name='foo').add_value(user, ref_entry)
            else:
                entry.attrs.get(schema__name='bar').add_value(user, ref_entry)

            entry.register_es()

        resp = Entry.search_entries(user, [entity.id], [{'name': 'foo', 'keyword': 'ref'}], limit=5)
        self.assertEqual(resp['ret_count'], 10)

    def test_search_entities_have_individual_attrs(self):
        user = User.objects.create(username='hoge')

        entity_info = {
            'entity1': ['foo', 'bar'],
            'entity2': ['bar', 'hoge']
        }

        entities = []
        for (entity_name, attrnames) in entity_info.items():
            entity = Entity.objects.create(name=entity_name, created_user=user)
            entities.append(entity.id)

            for attrname in attrnames:
                entity.attrs.add(EntityAttr.objects.create(name=attrname,
                                                           type=AttrTypeValue['string'],
                                                           created_user=user,
                                                           parent_entity=entity))

            # create entries for this entity
            for i in range(0, 5):
                e = Entry.objects.create(name='entry-%d' % i, created_user=user, schema=entity)
                e.register_es()

        # This request expects 'no match' because attribute 'foo' and 'hoge' are not had by both two entities
        resp = Entry.search_entries(user, entities, [{'name': x} for x in ['foo', 'hoge']])
        self.assertEqual(resp['ret_count'], 0)

        resp = Entry.search_entries(user, entities, [{'name': x} for x in ['bar']])
        self.assertEqual(resp['ret_count'], 10)
        for name in entity_info.keys():
            self.assertEqual(len([x for x in resp['ret_values'] if x['entity']['name'] == name]), 5)

    def test_search_entries_sorted_result(self):
        user = User.objects.create(username='hoge')

        entity = Entity.objects.create(name='EntityA', created_user=user)
        entity.save()

        # register AAA5, AAA0, AAA4, AAA1, AAA3, AAA2 in this order 
        for i in range(3):
            e1 = Entry.objects.create(name="AAA%d" % (5- i), schema=entity, created_user=user)
            e1.save()
            e1.register_es()

            e2 = Entry.objects.create(name="AAA%d" % i, schema=entity, created_user=user)
            e2.save()
            e2.register_es()
            
        # search
        resp = Entry.search_entries(user, [], entry_name="AAA")

        # 6 results should be returned
        self.assertEqual(resp['ret_count'], 6)
        # 6 results should be sorted
        for i in range(6):
            self.assertEqual(resp['ret_values'][i]['entry']['name'], "AAA%d" % i)
        
        
    def test_get_last_value(self):
        user = User.objects.create(username='hoge')

        entity = Entity.objects.create(name='entity', created_user=user)
        for name in ['foo', 'bar']:
            entity.attrs.add(EntityAttr.objects.create(name=name,
                                                       type=AttrTypeValue['string'],
                                                       created_user=user,
                                                       parent_entity=entity))

        entry = Entry.objects.create(name='entry', schema=entity, created_user=user)
        entry.complement_attrs(user)

        # the case of creating default empty AttributeValue
        attr = entry.attrs.get(schema__name='foo')
        self.assertEqual(attr.values.count(), 0)

        attrv = attr.get_last_value()
        self.assertIsNotNone(attrv)
        self.assertEqual(attrv.value, '')
        self.assertEqual(attrv, attr.get_latest_value())
        self.assertEqual(attr.values.count(), 1)

        # the case of creating specified AttributeValue
        attr = entry.attrs.get(schema__name='bar')
        self.assertEqual(attr.values.count(), 0)

        attr.add_value(user, 'hoge')
        attrv = attr.get_last_value()
        self.assertIsNotNone(attrv)
        self.assertEqual(attrv.value, 'hoge')
        self.assertEqual(attrv, attr.get_latest_value())
        self.assertEqual(attr.values.count(), 1)

    def test_utility_for_updating_attributes(self):
        user = User.objects.create(username='hoge')
        entity_ref = Entity.objects.create(name='Ref', created_user=user)
        entry_refs = [Entry.objects.create(name='ref-%d' % i, schema=entity_ref, created_user=user) for i in range(3)]
        entity = Entity.objects.create(name='Entity', created_user=user)

        attrinfos = [
            {'name': 'arr_str', 'type': AttrTypeValue['array_string'],
             'value': ['foo']},
            {'name': 'arr_obj', 'type': AttrTypeValue['array_object'], 'referral': entity_ref,
             'value': [entry_refs[0]]},
            {'name': 'arr_name', 'type': AttrTypeValue['array_named_object'], 'referral': entity_ref,
             'value': [{'id': entry_refs[0], 'name': 'foo'}]},
        ]
        for info in attrinfos:
            attr = EntityAttr.objects.create(name=info['name'],
                                             type=info['type'],
                                             created_user=user,
                                             parent_entity=entity)
            if 'referral' in info:
                attr.referral.add(info['referral'])

            entity.attrs.add(attr)

        # initialize test entry
        entry = Entry.objects.create(name='entry', schema=entity, created_user=user)
        entry.complement_attrs(user)

        attrs = {}
        for info in attrinfos:
            attr = attrs[info['name']] = entry.attrs.get(schema__name=info['name'])
            attr.add_value(user, info['value'])

        # test append attrv
        attrs['arr_str'].add_to_attrv(user, value='bar')
        attrv = attrs['arr_str'].get_latest_value()
        self.assertEqual(attrv.data_array.count(), 2)
        self.assertEqual(sorted([x.value for x in attrv.data_array.all()]),
                         sorted(['foo', 'bar']))

        attrs['arr_obj'].add_to_attrv(user, referral=entry_refs[1])
        attrv = attrs['arr_obj'].get_latest_value()
        self.assertEqual(attrv.data_array.count(), 2)
        self.assertEqual(sorted([x.referral.name for x in attrv.data_array.all()]),
                         sorted(['ref-0', 'ref-1']))

        attrs['arr_name'].add_to_attrv(user, referral=entry_refs[1], value='baz')
        attrv = attrs['arr_name'].get_latest_value()
        self.assertEqual(attrv.data_array.count(), 2)
        self.assertEqual(sorted([x.value for x in attrv.data_array.all()]),
                         sorted(['foo', 'baz']))
        self.assertEqual(sorted([x.referral.name for x in attrv.data_array.all()]),
                         sorted(['ref-0', 'ref-1']))

        # test remove attrv
        attrs['arr_str'].remove_from_attrv(user, value='foo')
        attrv = attrs['arr_str'].get_latest_value()
        self.assertEqual(attrv.data_array.count(), 1)
        self.assertEqual(sorted([x.value for x in attrv.data_array.all()]),
                         sorted(['bar']))

        attrs['arr_obj'].remove_from_attrv(user, referral=entry_refs[0])
        attrv = attrs['arr_obj'].get_latest_value()
        self.assertEqual(attrv.data_array.count(), 1)
        self.assertEqual(sorted([x.referral.name for x in attrv.data_array.all()]),
                         sorted(['ref-1']))

        attrs['arr_name'].remove_from_attrv(user, referral=entry_refs[0])
        attrv = attrs['arr_name'].get_latest_value()
        self.assertEqual(attrv.data_array.count(), 1)
        self.assertEqual(sorted([x.value for x in attrv.data_array.all()]),
                         sorted(['baz']))
        self.assertEqual(sorted([x.referral.name for x in attrv.data_array.all()]),
                         sorted(['ref-1']))

        # test try to remove attrv with invalid value
        attrs['arr_str'].remove_from_attrv(user, value=None)
        attrv = attrs['arr_str'].get_latest_value()
        self.assertEqual(attrv.data_array.count(), 1)
        self.assertEqual(sorted([x.value for x in attrv.data_array.all()]),
                         sorted(['bar']))

        attrs['arr_obj'].remove_from_attrv(user, referral=None)
        attrv = attrs['arr_obj'].get_latest_value()
        self.assertEqual(attrv.data_array.count(), 1)
        self.assertEqual(sorted([x.referral.name for x in attrv.data_array.all()]),
                         sorted(['ref-1']))

        attrs['arr_name'].remove_from_attrv(user, referral=None)
        attrv = attrs['arr_name'].get_latest_value()
        self.assertEqual(attrv.data_array.count(), 1)
        self.assertEqual(sorted([x.value for x in attrv.data_array.all()]),
                         sorted(['baz']))
        self.assertEqual(sorted([x.referral.name for x in attrv.data_array.all()]),
                         sorted(['ref-1']))
