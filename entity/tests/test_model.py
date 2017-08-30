from django.test import TestCase
from user.models import User
from entity.models import Entity
from entity.models import EntityAttr
from entity.admin import EntityResource


class ModelTest(TestCase):
    def setUp(self):
        self._test_user = User(username='test')
        self._test_user.save()

    def test_make_attrbase(self):
        entity = Entity(name='test01', created_user=self._test_user)
        entity.save()

        attr_base = EntityAttr(name='hoge', created_user=self._test_user, parent_entity=entity)
        attr_base.save()

        self.assertEqual(attr_base.name, 'hoge')
        self.assertTrue(isinstance(attr_base.type, int))

    def test_make_entity(self):
        entity = Entity(name='test01', created_user=self._test_user)
        entity.save()
        
        self.assertEqual(entity.name, 'test01')
        self.assertEqual(list(entity.attrs.all()), [])
        self.assertTrue(entity.is_active)

    def test_set_parent(self):
        entity = Entity(name='test01', created_user=self._test_user)
        entity.save()

        attr_base = EntityAttr(name='hoge', created_user=self._test_user, parent_entity=entity)
        attr_base.save()

        self.assertEqual(attr_base.parent_entity, entity)

    def test_import_with_existed_object(self):
        entity = Entity(name='test01', note='note1', created_user=self._test_user)
        entity.save()

        EntityResource.import_data_from_request({
            'id': entity.id,
            'name': entity.name,
            'note': entity.note,
            'created_user': entity.created_user.username
        }, self._test_user)

        self.assertEqual(Entity.objects.count(), 1)
        self.assertEqual(Entity.objects.last().name, entity.name)
        self.assertEqual(Entity.objects.last().note, entity.note)
        self.assertEqual(Entity.objects.last().created_user, self._test_user)

    def test_import_with_new_object(self):
        EntityResource.import_data_from_request({
            'name': 'foo',
            'note': 'bar',
            'created_user': self._test_user,
        }, self._test_user)
        self.assertEqual(Entity.objects.count(), 1)
        self.assertEqual(Entity.objects.last().name, 'foo')
        self.assertEqual(Entity.objects.last().note, 'bar')
        self.assertEqual(Entity.objects.last().created_user, self._test_user)

    def test_import_with_updating_object(self):
        entity = Entity(name='test01', note='note1', created_user=self._test_user)
        entity.save()

        EntityResource.import_data_from_request({
            'id': entity.id,
            'name': 'changed_name',
            'note': 'changed_note',
            'created_user': entity.created_user.username
        }, self._test_user)

        self.assertEqual(Entity.objects.count(), 1)
        self.assertEqual(Entity.objects.last().name, 'changed_name')
        self.assertEqual(Entity.objects.last().note, 'changed_note')
        self.assertEqual(Entity.objects.last().created_user, self._test_user)

    def test_import_with_invalid_parameter(self):
        with self.assertRaises(RuntimeError):
            EntityResource.import_data_from_request({
                'name': 'hoge',
                'note': 'fuga',
                'invalid_key': 'invalid_value',
                'created_user': self._test_user.username,
            }, self._test_user)

        self.assertEqual(Entity.objects.count(), 0)

    def test_import_without_mandatory_parameter(self):
        with self.assertRaises(RuntimeError):
            EntityResource.import_data_from_request({
                'note': 'fuga',
                'created_user': self._test_user.username,
            }, self._test_user)

        self.assertEqual(Entity.objects.count(), 0)

    def test_import_with_spoofing_parameter(self):
        user = User.objects.create(username='another_user')

        EntityResource.import_data_from_request({
            'name': 'entity',
            'note': 'note',
            'created_user': user
        }, self._test_user)

        self.assertEqual(Entity.objects.count(), 0)

    def test_import_without_permission_parameter(self):
        user = User.objects.create(username='another_user')

        entity = Entity(name='origin_name', created_user=user, is_public=False)
        entity.save()

        EntityResource.import_data_from_request({
            'id': entity.id,
            'name': 'changed_name',
            'note': 'changed_note',
            'created_user': entity.created_user.username
        }, self._test_user)

        self.assertEqual(Entity.objects.count(), 1)
        self.assertEqual(Entity.objects.last().name, 'origin_name')
