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

    def test_make_attribute_value(self):
        AttributeValue(value='hoge', created_user=self._user).save()

        self.assertEqual(AttributeValue.objects.count(), 1)
        self.assertEqual(AttributeValue.objects.last().value, 'hoge')
        self.assertEqual(AttributeValue.objects.last().created_user, self._user)
        self.assertIsNotNone(AttributeValue.objects.last().created_time)

    def test_make_attribute(self):
        attr = Attribute(name='attr', created_user=self._user)
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

        attr = Attribute(name='attr', created_user=self._user)
        attr.save()

        entry.attrs.add(attr)

        self.assertEqual(Entry.objects.count(), 1)
        self.assertEqual(Entry.objects.last().created_user, self._user)
        self.assertEqual(Entry.objects.last().attrs.count(), 1)
        self.assertEqual(Entry.objects.last().attrs.last(), attr)

    def test_inherite_attribute_permission_of_user(self):
        user = User.objects.create(username='hoge')

        entity = Entity.objects.create(name='entity', created_user=user)
        attrbase = AttributeBase.objects.create(name='attr', created_user=user)

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
        attrbase = AttributeBase.objects.create(name='attr', created_user=user)

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
                                                created_user=user)
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
