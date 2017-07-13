from django.test import TestCase
from user.models import User
from entity.models import Entity
from entity.models import AttributeBase


class ModelTest(TestCase):
    def setUp(self):
        self._test_user = User(username='test')
        self._test_user.save()

    def test_make_attrbase(self):
        entity = Entity(name='test01', created_user=self._test_user)
        entity.save()

        attr_base = AttributeBase(name='hoge', created_user=self._test_user, parent_entity=entity)
        attr_base.save()

        self.assertEqual(attr_base.name, 'hoge')
        self.assertTrue(isinstance(attr_base.type, int))

    def test_make_entity(self):
        entity = Entity(name='test01', created_user=self._test_user)
        entity.save()
        
        self.assertEqual(entity.name, 'test01')
        self.assertEqual(list(entity.attr_bases.all()), [])

    def test_set_parent(self):
        entity = Entity(name='test01', created_user=self._test_user)
        entity.save()

        attr_base = AttributeBase(name='hoge', created_user=self._test_user, parent_entity=entity)
        attr_base.save()

        self.assertEqual(attr_base.parent_entity, entity)
