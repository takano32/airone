from django.test import TestCase
from user.models import User
from acl.models import ACL
from entity.models import Entity
from entity.models import Attribute
from entity.models import AttributeBase
from entity.models import AttributeValue


class ModelTest(TestCase):
    def setUp(self):
        self._test_user = User(name='test')
        self._test_user.save()

    def test_make_attrbase(self):
        attr_base = AttributeBase(name='hoge')
        attr_base.save()

        self.assertEqual(attr_base.name, 'hoge')
        self.assertTrue(isinstance(attr_base.type, int))

    def test_make_attr(self):
        attr = Attribute(name='name')
        attr.save()

        value1 = AttributeValue(created_user=self._test_user, value='foo')
        value1.save()
        value2 = AttributeValue(created_user=self._test_user, value='bar')
        value2.save()

        attr.values.add(*[value1, value2])

        self.assertEqual(attr.name, 'name')
        self.assertEqual(len(list(attr.values.all())), 2)
        self.assertEqual(attr.values.first().value, 'foo')
        self.assertEqual(attr.values.last().value, 'bar')

    def test_make_entity(self):
        entity = Entity(name='test01')
        entity.save()
        
        #self.assertIsNone(entity.acl)
        self.assertEqual(entity.name, 'test01')
        self.assertEqual(list(entity.attr_bases.all()), [])
