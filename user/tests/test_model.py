from django.test import TestCase
from django.contrib.auth.models import User as DjangoUser

from entity.models import Entity, EntityAttr
from entry.models import Entry
from user.models import User, History


class ModelTest(TestCase):
    def setUp(self):
        self.user = User(username='ほげ', email='hoge@fuga.com', password='fuga')
        self.user.save()

    def test_make_user(self):
        self.assertTrue(isinstance(self.user, DjangoUser))
        self.assertEqual(self.user.username, 'ほげ')
        self.assertEqual(self.user.authorized_type, 0)
        self.assertIsNotNone(self.user.date_joined)
        self.assertTrue(self.user.is_active)

    def test_delete_user(self):
        self.user.set_active(False)
        self.user.save()

        user = User.objects.get(username='ほげ')
        self.assertTrue(isinstance(user, DjangoUser))
        self.assertEqual(user.username, 'ほげ')
        self.assertEqual(user.authorized_type, 0)
        self.assertIsNotNone(user.date_joined)
        self.assertFalse(user.is_active)

    def test_set_history_of_entity(self):
        entity = Entity.objects.create(name='test-entity', created_user=self.user)

        self.user.seth_entity_add(entity)
        self.user.seth_entity_mod(entity)
        self.user.seth_entity_del(entity)

        self.assertEqual(History.objects.count(), 3)
        self.assertEqual(History.objects.filter(operation=History.ADD_ENTITY).count(), 1)
        self.assertEqual(History.objects.filter(operation=History.MOD_ENTITY).count(), 1)
        self.assertEqual(History.objects.filter(operation=History.DEL_ENTITY).count(), 1)

    def test_set_history_of_attr(self):
        entity = Entity.objects.create(name='test-entity', created_user=self.user)
        attr = EntityAttr.objects.create(name='test-attr', created_user=self.user, parent_entity=entity)

        self.user.seth_attr_add(attr)
        self.user.seth_attr_mod(attr)
        self.user.seth_attr_del(attr)

        self.assertEqual(History.objects.count(), 3)
        self.assertEqual(History.objects.filter(operation=History.ADD_ATTR).count(), 1)
        self.assertEqual(History.objects.filter(operation=History.MOD_ATTR).count(), 1)
        self.assertEqual(History.objects.filter(operation=History.DEL_ATTR).count(), 1)

    def test_set_history_of_entry(self):
        entity = Entity.objects.create(name='test-entity', created_user=self.user)
        entry = Entry.objects.create(name='test-attr', created_user=self.user, schema=entity)

        self.user.seth_entry_del(entry)

    def test_set_history_of_invalid_type_entry(self):
        class InvalidType(object):
            pass

        entity = Entity.objects.create(name='test-entity', created_user=self.user)
        invalid_obj = InvalidType()

        with self.assertRaises(TypeError):
            self.user.seth_entity_add(invalid_obj)
            self.user.seth_entity_mod(invalid_obj)
            self.user.seth_entity_del(invalid_obj)

        self.assertEqual(History.objects.count(), 0)
