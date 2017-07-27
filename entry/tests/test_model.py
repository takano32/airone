from django.contrib.auth.models import Group
from django.test import TestCase
from entity.models import Entity, AttributeBase
from entry.models import Entry, Attribute, AttributeValue
from user.models import User
from airone.lib.acl import ACLObjType
from airone.lib.types import AttrTypeStr, AttrTypeObj


class ModelTest(TestCase):
    def setUp(self):
        self._user = User(username='test')
        self._user.save()

        self._entity = Entity(name='entity', created_user=self._user)
        self._entity.save()

        self._entry = Entry(name='entry', created_user=self._user, schema=self._entity)
        self._entry.save()

    def make_attr(self, name, user=None, entity=None, entry=None):
        return Attribute(name=name,
                         created_user=(user and user or self._user),
                         parent_entity=(entity and entity or self._entity),
                         parent_entry=(entry and entry or self._entry))

    def test_make_attribute_value(self):
        AttributeValue(value='hoge', created_user=self._user).save()

        self.assertEqual(AttributeValue.objects.count(), 1)
        self.assertEqual(AttributeValue.objects.last().value, 'hoge')
        self.assertEqual(AttributeValue.objects.last().created_user, self._user)
        self.assertIsNotNone(AttributeValue.objects.last().created_time)

    def test_make_attribute(self):
        attr = self.make_attr('attr')
        attr.save()

        value = AttributeValue(value='hoge', created_user=self._user)
        value.save()

        attr.values.add(value)

        self.assertEqual(Attribute.objects.count(), 1)
        self.assertEqual(Attribute.objects.last().objtype, ACLObjType.Attr)
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
        self.assertEqual(Entry.objects.last().get_screen_name(), 'test')
        self.assertEqual(Entry.objects.last().is_deleted(), False,
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

        entry.delete()
        entry.save()
        
        self.assertEqual(Entry.objects.count(), entry_count,
                         "number of entry should equal after delete")
        self.assertEqual(Entry.objects.last().created_user, self._user)
        self.assertEqual(Entry.objects.last().attrs.count(), 1)
        self.assertEqual(Entry.objects.last().attrs.last(), attr)
        self.assertEqual(Entry.objects.last().name, 'test')
        self.assertEqual(Entry.objects.last().get_screen_name(), 'test(deleted)')
        self.assertEqual(Entry.objects.last().is_deleted(), True,
                         "Entry should be deleted")
        
    def test_inherite_attribute_permission_of_user(self):
        user = User.objects.create(username='hoge')

        entity = Entity.objects.create(name='entity', created_user=user)
        attrbase = AttributeBase.objects.create(name='attr',
                                                created_user=user,
                                                parent_entity=entity)

        # set a permission to the user
        user.permissions.add(attrbase.writable)

        entry = Entry.objects.create(name='entry', schema=entity, created_user=user)
        attr = entry.add_attribute_from_base(attrbase, user)

        self.assertEqual(user.permissions.filter(name='writable').count(), 2)
        self.assertEqual(user.permissions.filter(name='writable').first(), attrbase.writable)
        self.assertEqual(user.permissions.filter(name='writable').last(), attr.writable)

    def test_inherite_attribute_permission_of_group(self):
        user = User.objects.create(username='hoge')
        group = Group.objects.create(name='group')
        user.groups.add(group)

        entity = Entity.objects.create(name='entity', created_user=user)
        attrbase = AttributeBase.objects.create(name='attr',
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

        attrbase = AttributeBase.objects.create(name='attrbase',
                                                type=AttrTypeStr.TYPE,
                                                created_user=user,
                                                parent_entity=entity)
        entry = Entry.objects.create(name='entry', schema=entity, created_user=user)
        attr = entry.add_attribute_from_base(attrbase, user)

        # update attrbase
        attrbase.name = 'hoge'
        attrbase.type = AttrTypeObj.TYPE
        attrbase.referral = entity
        attrbase.is_mandatory = True

        attr.update_from_base(attrbase)

        self.assertEqual(Attribute.objects.get(id=attr.id).name, attrbase.name)
        self.assertEqual(Attribute.objects.get(id=attr.id).type, attrbase.type)
        self.assertEqual(Attribute.objects.get(id=attr.id).referral.id, attrbase.referral.id)
        self.assertEqual(Attribute.objects.get(id=attr.id).is_mandatory, attrbase.is_mandatory)
