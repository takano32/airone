from django.test import TestCase
from django.contrib.auth.models import Group, Permission
from acl.models import ACLBase
from user.models import User
from importlib import import_module
from airone.lib.acl import ACLType


class ModelTest(TestCase):
    def setUp(self):
        self.user =  User.objects.create(username='foo', email='hoge@fuga.com', password='fuga')

    def test_acl_base(self):
        # chacks to enable embedded acl field
        ACLBase(name='hoge', created_user=User.objects.create(username='hoge')).save()
        
        acl = ACLBase.objects.first()
        self.assertIsNotNone(acl)
        self.assertIsInstance(acl.readable, Permission)
        self.assertIsInstance(acl.writable, Permission)
        self.assertIsInstance(acl.full, Permission)

    def test_pass_permission_check_with_public_obj(self):
        aclobj = ACLBase.objects.create(name='hoge', created_user=self.user, is_public=True)

        self.assertTrue(self.user.has_permission(aclobj, ACLType.Readable))

    def test_pass_permission_check_with_created_user(self):
        aclobj = ACLBase.objects.create(name='hoge', created_user=self.user, is_public=False)

        self.assertFalse(self.user.has_permission(aclobj, 'invalid-permission-level'))

    def test_fail_permission_check_with_invalid_level(self):
        another_user = User.objects.create(username='bar', email='bar@f.com', password='')

        aclobj = ACLBase.objects.create(name='hoge', created_user=self.user, is_public=False)

        self.assertFalse(another_user.has_permission(aclobj, 'invalid-permission-level'))

    def test_pass_permission_check_with_user_permissoin(self):
        aclobj = ACLBase.objects.create(name='hoge', created_user=self.user, is_public=False)

        # set correct permission
        self.user.permissions.add(aclobj.readable)

        self.assertTrue(self.user.has_permission(aclobj, ACLType.Readable))

    def test_pass_permission_check_with_surperior_permissoin(self):
        aclobj = ACLBase.objects.create(name='hoge', created_user=self.user, is_public=False)

        # set surperior permission
        self.user.permissions.add(aclobj.writable)

        self.assertTrue(self.user.has_permission(aclobj, ACLType.Readable))

    def test_fail_permission_check_with_inferior_permissoin(self):
        another_user = User.objects.create(username='bar', email='bar@f.com', password='')

        aclobj = ACLBase.objects.create(name='hoge', created_user=self.user, is_public=False)

        # set inferior permission
        self.user.permissions.add(aclobj.readable)

        self.assertFalse(another_user.has_permission(aclobj, ACLType.Writable))

    def test_pass_permission_check_with_group_permissoin(self):
        another_user = User.objects.create(username='bar', email='bar@f.com', password='')
        group = Group.objects.create(name='hoge')

        aclobj = ACLBase.objects.create(name='hoge', created_user=self.user, is_public=False)

        # set correct permission to the group that test user is belonged to
        group.permissions.add(aclobj.readable)
        another_user.groups.add(group)

        self.assertTrue(another_user.has_permission(aclobj, ACLType.Readable))

    def test_get_registered_user_permissoins(self):
        aclobj = ACLBase.objects.create(name='hoge', created_user=self.user, is_public=False)
        self.user.permissions.add(aclobj.readable)

        self.assertEqual(self.user.get_acls(aclobj).count(), 1)
        self.assertEqual(self.user.get_acls(aclobj)[0], aclobj.readable)

    def test_get_registered_group_permissoins(self):
        group = Group.objects.create(name='hoge')

        aclobj = ACLBase.objects.create(name='hoge', created_user=self.user, is_public=False)
        group.permissions.add(aclobj.full)

        self.assertEqual(group.get_acls(aclobj).count(), 1)
        self.assertEqual(group.get_acls(aclobj)[0], aclobj.full)

    def test_get_subclass_object(self):
        # make objects to test
        model_entity = import_module('entity.models')
        model_entry = import_module('entry.models')
        kwargs = {
            'name': 'test-object',
            'created_user': self.user,
        }

        entity = model_entity.Entity.objects.create(**kwargs)
        attr_base = model_entity.EntityAttr.objects.create(parent_entity=entity, **kwargs)
        entry = model_entry.Entry.objects.create(schema=entity, **kwargs)
        attr = model_entry.Attribute.objects.create(parent_entry=entry, schema=attr_base, **kwargs)
        base = ACLBase.objects.create(**kwargs)

        self.assertEqual(ACLBase.objects.get(id=entity.id).get_subclass_object(), entity)
        self.assertEqual(ACLBase.objects.get(id=attr_base.id).get_subclass_object(), attr_base)
        self.assertEqual(ACLBase.objects.get(id=entry.id).get_subclass_object(), entry)
        self.assertEqual(ACLBase.objects.get(id=attr.id).get_subclass_object(), attr)
        self.assertEqual(ACLBase.objects.get(id=base.id).get_subclass_object(), base)

    def test_manipurate_status_param(self):
        TEST_FLAG_0 = (1 << 0)
        TEST_FLAG_1 = (1 << 1)
        TEST_FLAG_2 = (1 << 2)

        entity = import_module('entity.models').Entity.objects.create(name='entity1',
                                                                      created_user=self.user)

        entity.set_status(TEST_FLAG_0 | TEST_FLAG_2)
        self.assertTrue(entity.get_status(TEST_FLAG_0))
        self.assertFalse(entity.get_status(TEST_FLAG_1))
        self.assertTrue(entity.get_status(TEST_FLAG_2))

        entity.del_status(TEST_FLAG_2)
        self.assertTrue(entity.get_status(TEST_FLAG_0))
        self.assertFalse(entity.get_status(TEST_FLAG_1))
        self.assertFalse(entity.get_status(TEST_FLAG_2))

    def test_operation_for_acltype(self):
        type_readable = ACLType.Readable

        self.assertTrue(type_readable == ACLType.Readable)
        self.assertTrue(type_readable == ACLType.Readable.id)
        self.assertTrue(type_readable == ACLType.Readable.name)

        self.assertFalse(type_readable != ACLType.Readable)
        self.assertFalse(type_readable != ACLType.Readable.id)
        self.assertFalse(type_readable != ACLType.Readable.name)
        self.assertTrue(type_readable != ACLType.Writable)

        self.assertTrue(type_readable <= ACLType.Writable)
        self.assertFalse(type_readable <= ACLType.Nothing)

    def test_default_permission(self):
        another_user = User.objects.create(username='bar', email='bar@f.com', password='')
        aclobj = ACLBase.objects.create(name='hoge',
                                        created_user=another_user,
                                        is_public=False,
                                        default_permission=ACLType.Readable.id)

        self.assertTrue(self.user.has_permission(aclobj, ACLType.Nothing))
        self.assertTrue(self.user.has_permission(aclobj, ACLType.Readable))
        self.assertFalse(self.user.has_permission(aclobj, ACLType.Writable))
        self.assertFalse(self.user.has_permission(aclobj, ACLType.Full))

        self.assertTrue(another_user.has_permission(aclobj, ACLType.Nothing))
        self.assertTrue(another_user.has_permission(aclobj, ACLType.Readable))
        self.assertTrue(another_user.has_permission(aclobj, ACLType.Writable))
        self.assertTrue(another_user.has_permission(aclobj, ACLType.Full))
