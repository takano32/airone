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

    def test_delete_entry(self):
        entry = Entry(name='test',
                      schema=self._entity,
                      created_user=self._user)
        entry.save()

        attr = self.make_attr('attr', entry=entry)
        attr.save()

        entry.attrs.add(attr)

        entry_count = Entry.objects.count()

        entry.is_active = False
        entry.save()

        self.assertEqual(Entry.objects.count(), entry_count,
                         "number of entry should equal after delete")
        self.assertEqual(Entry.objects.last().created_user, self._user)
        self.assertEqual(Entry.objects.last().attrs.count(), 1)
        self.assertEqual(Entry.objects.last().attrs.last(), attr)
        self.assertEqual(Entry.objects.last().name, 'test')
        self.assertEqual(Entry.objects.last().is_active, False,
                         "Entry should be deleted")

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
        entry = Entry.objects.create(name='refered', created_user=self._user, schema=entity)

        attr = self.make_attr('attr_ref', attrtype=AttrTypeObj)
        attr.save()

        # make multiple value that refer 'entry' object
        [attr.values.add(AttributeValue.objects.create(created_user=self._user,
                                                       parent_attr=attr,
                                                       referral=entry)) for _ in range(0, 10)]
        # make a self reference value
        attr.values.add(AttributeValue.objects.create(created_user=self._user,
                                                      parent_attr=attr,
                                                      referral=self._entry))
        self._entry.attrs.add(attr)

        # This function checks that this get_referred_objects method only get
        # unique reference objects except for the self referred object.
        referred_entries = entry.get_referred_objects()
        self.assertEqual(referred_entries.count(), 10)
        self.assertEqual(set(referred_entries), set([self._entry]))

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

        # delete an entry that have an attribute which refers to the entry of ReferredEntity
        self._entry.delete()
        self.assertFalse(self._entry.is_active)
        self.assertEqual(self._entry.attrs.filter(is_active=True).count(), 0)

        # make sure that referral cache is updated by deleting referring entry
        self.assertEqual(list(entry.get_referred_objects()), [])

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

    def test_search_entries(self):
        user = User.objects.create(username='hoge')

        # create referred Entity and Entries
        ref_entity = Entity.objects.create(name='Referred Entity', created_user=user)
        ref_entry = Entry.objects.create(name='referred_entry', schema=ref_entity, created_user=user)
        ref_group = Group.objects.create(name='group')

        attr_info = {
            'str': {'type': AttrTypeValue['string'], 'value': 'foo-%d'},
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

        for index in range(0, 10):
            entry = Entry.objects.create(name='e-%d' % index, schema=entity, created_user=user)
            entry.complement_attrs(user)

            for attr_name, info in attr_info.items():
                attr = entry.attrs.get(name=attr_name)
                if attr_name == 'str':
                    attr.add_value(user, info['value'] % index)
                else:
                    attr.add_value(user, info['value'])

            entry.register_es()

        # search entries
        ret = Entry.search_entries(user, [entity.id], [
            {'name': 'str'},
            {'name': 'obj'},
            {'name': 'name'},
            {'name': 'bool'},
            {'name': 'group'},
            {'name': 'date'},
            {'name': 'arr_str'},
            {'name': 'arr_obj'},
            {'name': 'arr_name'},
        ])
        self.assertEqual(ret['ret_count'], 10)
        self.assertEqual(len(ret['ret_values']), 10)

        # check returned contents is corrected
        for v in ret['ret_values']:
            self.assertEqual(v['entity']['id'], entity.id)
            self.assertEqual(len(v['attrs']), 9)

            entry = Entry.objects.get(id=v['entry']['id'])

            for (attrname, attrinfo) in v['attrs'].items():
                attr = entry.attrs.get(schema__name=attrname)
                attrv = attr.get_latest_value()

                self.assertEqual(attrinfo['type'], attrv.data_type)
                if attrname == 'str':
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
                    self.assertEqual(attrinfo['value'], [x.value for x in attrv.data_array.all()])

                elif attrname == 'arr_obj':
                    self.assertEqual([x['id'] for x in  attrinfo['value']],
                                     [x.referral.id for x in attrv.data_array.all()])
                    self.assertEqual([x['name'] for x in  attrinfo['value']],
                                     [x.referral.name for x in attrv.data_array.all()])

                elif attrname == 'arr_name':
                    for co_attrv in attrv.data_array.all():
                        _co_v = [x[co_attrv.value] for x in attrinfo['value'] if co_attrv.value in x]
                        self.assertTrue(_co_v)
                        self.assertEqual(_co_v[0]['id'], co_attrv.referral.id)
                        self.assertEqual(_co_v[0]['name'], co_attrv.referral.name)

        # search entries with maximum entries to get
        ret = Entry.search_entries(user, [entity.id], [{'name': 'str'}], 5)
        self.assertEqual(ret['ret_count'], 10)
        self.assertEqual(len(ret['ret_values']), 5)

        # search entries with keyword
        ret = Entry.search_entries(user, [entity.id], [{'name': 'str', 'keyword': 'foo-5'}])
        self.assertEqual(ret['ret_count'], 1)
        self.assertEqual(ret['ret_values'][0]['entry']['name'], 'e-5')

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
                'checker': lambda v: self.assertEqual(v['value'], 'foo')},
            'obj': {
                'type': AttrTypeValue['object'],
                'value': str(ref_entry1.id),
                'checker': lambda v: self.assertEqual(v['value'], ref_entry1.name),
            },
            'name': {
                'type': AttrTypeValue['named_object'],
                'value': {'name': 'bar', 'id': str(ref_entry1.id)},
                'checker': lambda v: self.assertEqual(v['value'], ref_entry1.name),
            },
            'bool': {
                'type': AttrTypeValue['boolean'],
                'value': False,
                'checker': lambda v: self.assertEqual(v['value'], 'False'),
            },
            'group': {
                'type': AttrTypeValue['group'],
                'value': str(ref_group.id),
                'checker': lambda v: self.assertEqual(v['value'], ref_group.name),
            },
            'arr_str': {
                'type': AttrTypeValue['array_string'],
                'value': ['foo', 'bar', 'baz'],
                'checker': lambda v: self.assertTrue([x in v['values'] for x in ['foo', 'bar', 'baz']]),
            },
            'arr_obj': {
                'type': AttrTypeValue['array_object'],
                'value': [str(x.id) for x in Entry.objects.filter(schema=ref_entity)],
                'checker': lambda v: self.assertTrue(all([any([y for y in v['values'] if y['value'] == x.name])
                    for x in Entry.objects.filter(schema=ref_entity)])),
            },
            'arr_name': {
                'type': AttrTypeValue['array_named_object'],
                'value': [{'name': 'hoge', 'id' : str(x.id)} for x in Entry.objects.filter(schema=ref_entity)],
                'checker': lambda v: self.assertTrue(all([any([y for y in v['values'] if y['value'] == x.name])
                    for x in Entry.objects.filter(schema=ref_entity)])),
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
        self.assertEqual(res['_all']['primaries']['docs']['count'], ENTRY_COUNTS)

        # checks that all registered entries can be got from Elasticsearch
        for entry in Entry.objects.filter(schema=entity):
            res = self._es.get(index=settings.ES_CONFIG['INDEX'], doc_type='entry', id=entry.id)
            self.assertTrue(res['found'])

            for (k, v) in attr_info.items():
                value = [x for x in res['_source']['attr'] if x['name'] == k][0]

                self.assertEqual(value['name'], k)
                self.assertEqual(value['type'], v['type'])

                v['checker'](value)

        # checks delete entry and checks deleted entry will also be removed from Elasticsearch
        entry = Entry.objects.filter(schema=entity).last()
        entry.delete()

        res = self._es.indices.stats(index=settings.ES_CONFIG['INDEX'])
        self.assertEqual(res['_all']['primaries']['docs']['count'], ENTRY_COUNTS - 1)

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

        entity = Entity.objects.create(name='entity', created_user=user)
        for index in range(0, 2):
            entity.attrs.add(EntityAttr.objects.create(name='attr-%s' % index,
                                                       type=AttrTypeValue['string'],
                                                       created_user=user,
                                                       parent_entity=entity))

        entity.attrs.add(EntityAttr.objects.create(name='attr-arr',
                                                   type=AttrTypeValue['array_string'],
                                                   created_user=user,
                                                   parent_entity=entity))


        entry_info = {
            'entry1': {
                'attr-0': '2018/01/01',
                'attr-1': 'bar',
                'attr-arr': ['hoge', 'fuga']
            },
            'entry2': {
                'attr-0': 'hoge',
                'attr-1': 'bar',
                'attr-arr': []
            },
            'entry3': {
                'attr-0': '',
                'attr-1': 'hoge',
                'attr-arr': []
            }
        }
        for (name, attrinfo) in entry_info.items():
            entry = Entry.objects.create(name=name, schema=entity, created_user=user)
            entry.complement_attrs(user)

            for attr in entry.attrs.all():
                attr.add_value(user, attrinfo[attr.schema.name])

            entry.register_es()

        # search entries from Elasticsearch
        resp = Entry.search_entries(user, [entity.id], [{'name': 'attr-0'}])
        self.assertEqual(resp['ret_count'], 3)

        # search entries with keyword parameter from Elasticsearch
        resp = Entry.search_entries(user, [entity.id], [{'name': 'attr-0', 'keyword': '2018/01/01'}])
        self.assertEqual(resp['ret_count'], 1)
        self.assertEqual(resp['ret_values'][0]['entry']['name'], 'entry1')

        # search entries with keyword parameter that other entry has same value in untarget attr
        resp = Entry.search_entries(user, [entity.id], [{'name': 'attr-0', 'keyword': 'hoge'}])
        self.assertEqual(resp['ret_count'], 1)
        self.assertEqual(resp['ret_values'][0]['entry']['name'], 'entry2')

        # search entries with keyword parameter which is array type
        resp = Entry.search_entries(user, [entity.id], [{'name': 'attr-arr', 'keyword': 'hoge'}])
        self.assertEqual(resp['ret_count'], 1)
        self.assertEqual(resp['ret_values'][0]['entry']['name'], 'entry1')
