from group.models import Group
from django.test import TestCase
from entity.models import Entity, EntityAttr
from entry.models import Entry, Attribute, AttributeValue
from user.models import User
from airone.lib.acl import ACLObjType, ACLType
from airone.lib.types import AttrTypeStr, AttrTypeObj, AttrTypeArrStr, AttrTypeArrObj
from airone.lib.types import AttrTypeValue


class ModelTest(TestCase):
    def setUp(self):
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

        self.assertEqual(attr.get_updated_values_of_array(['hoge', 'puyo', '']), ['puyo'])
        self.assertEqual(attr.get_existed_values_of_array(['hoge', 'puyo']),
                         [AttributeValue.objects.get(value='hoge')])

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

        self.assertEqual(attr.get_updated_values_of_array([e1.id, e3.id, 0]), [e3.id])
        self.assertEqual(attr.get_existed_values_of_array([e1.id, e3.id]),
                         [AttributeValue.objects.get(referral=e1)])

    def test_for_boolean_attr_and_value(self):
        attr = self.make_attr('attr_bool', AttrTypeValue['boolean'])
        attr.save()

        attr.values.add(AttributeValue.objects.create(**{
            'created_user': self._user,
            'parent_attr': attr,
            'status': AttributeValue.STATUS_LATEST
        }))

        # Checks default value
        self.assertIsNotNone(attr.get_latest_value())
        self.assertFalse(attr.get_latest_value().boolean)

        # Checks attitude of is_update
        self.assertFalse(attr.is_updated(False))
        self.assertTrue(attr.is_updated(True))

    def test_get_referred_objects(self):
        entity = Entity.objects.create(name='Entity2', created_user=self._user)
        entry = Entry.objects.create(name='refered', created_user=self._user, schema=entity)

        attr = self.make_attr('attr_ref', attrtype=AttrTypeObj)
        attr.save()

        # make multiple value that refer 'entry' object
        [attr.values.add(AttributeValue.objects.create(created_user=self._user,
                                                       parent_attr=attr,
                                                       status=AttributeValue.STATUS_LATEST,
                                                       referral=entry)) for _ in range(0, 10)]
        # make a self reference value
        attr.values.add(AttributeValue.objects.create(created_user=self._user,
                                                      parent_attr=attr,
                                                      status=AttributeValue.STATUS_LATEST,
                                                      referral=self._entry))
        self._entry.attrs.add(attr)

        # This function checks that this get_referred_objects method only get
        # unique reference objects except for the self referred object.
        self.assertEqual(entry.get_referred_objects(), [self._entry])

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
                                                      parent_attr=attr,
                                                      status=AttributeValue.STATUS_LATEST))

        self.assertEqual(len(attr.get_value_history(self._user)), 3)
