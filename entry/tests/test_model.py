from django.test import TestCase
from entity.models import Entity
from entry.models import Entry, Attribute, AttributeValue
from user.models import User
from airone.lib import ACLObjType


class ModelTest(TestCase):
    def setUp(self):
        self._user = User(username='test')
        self._user.save()

        self._entity = Entity(name='entity')
        self._entity.save()

    def test_make_attribute_value(self):
        AttributeValue(value='hoge', created_user=self._user).save()

        self.assertEqual(AttributeValue.objects.count(), 1)
        self.assertEqual(AttributeValue.objects.last().value, 'hoge')
        self.assertEqual(AttributeValue.objects.last().created_user, self._user)
        self.assertIsNotNone(AttributeValue.objects.last().created_time)

    def test_make_attribute(self):
        attr = Attribute(name='attr')
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

        attr = Attribute(name='attr')
        attr.save()

        entry.attrs.add(attr)

        self.assertEqual(Entry.objects.count(), 1)
        self.assertEqual(Entry.objects.last().created_user, self._user)
        self.assertEqual(Entry.objects.last().attrs.count(), 1)
        self.assertEqual(Entry.objects.last().attrs.last(), attr)
