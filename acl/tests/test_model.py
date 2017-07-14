from django.test import TestCase
from django.contrib.auth.models import Group, Permission
from acl.models import ACLBase
from user.models import User
from importlib import import_module


class ModelTest(TestCase):
    def test_acl_base(self):
        # chacks to enable embedded acl field
        ACLBase(name='hoge', created_user=User.objects.create(username='hoge')).save()
        
        acl = ACLBase.objects.first()
        self.assertIsNotNone(acl)
        self.assertIsInstance(acl.readable, Permission)
        self.assertIsInstance(acl.writable, Permission)
        self.assertIsInstance(acl.full, Permission)

    def test_pass_permission_check_with_public_obj(self):
        user = User.objects.create(username='foo', email='hoge@fuga.com', password='fuga')

        aclobj = ACLBase.objects.create(name='hoge', created_user=user, is_public=True)

        self.assertTrue(user.has_permission(aclobj, 'readable'))

    def test_pass_permission_check_with_created_user(self):
        user = User.objects.create(username='foo', email='foo@f.com', password='')

        aclobj = ACLBase.objects.create(name='hoge', created_user=user, is_public=False)

        self.assertTrue(user.has_permission(aclobj, 'invalid-permission-level'))

    def test_fail_permission_check_with_invalid_level(self):
        user = User.objects.create(username='foo', email='foo@f.com', password='')
        another_user = User.objects.create(username='bar', email='bar@f.com', password='')

        aclobj = ACLBase.objects.create(name='hoge', created_user=user, is_public=False)

        self.assertFalse(another_user.has_permission(aclobj, 'invalid-permission-level'))

    def test_pass_permission_check_with_user_permissoin(self):
        user = User.objects.create(username='foo', email='hoge@fuga.com', password='fuga')

        aclobj = ACLBase.objects.create(name='hoge', created_user=user, is_public=False)

        # set correct permission
        user.permissions.add(aclobj.readable)

        self.assertTrue(user.has_permission(aclobj, 'readable'))

    def test_pass_permission_check_with_surperior_permissoin(self):
        user = User.objects.create(username='foo', email='hoge@fuga.com', password='fuga')

        aclobj = ACLBase.objects.create(name='hoge', created_user=user, is_public=False)

        # set surperior permission
        user.permissions.add(aclobj.writable)

        self.assertTrue(user.has_permission(aclobj, 'readable'))

    def test_fail_permission_check_with_inferior_permissoin(self):
        user = User.objects.create(username='foo', email='hoge@fuga.com', password='fuga')
        another_user = User.objects.create(username='bar', email='bar@f.com', password='')

        aclobj = ACLBase.objects.create(name='hoge', created_user=user, is_public=False)

        # set inferior permission
        user.permissions.add(aclobj.readable)

        self.assertFalse(another_user.has_permission(aclobj, 'writable'))

    def test_pass_permission_check_with_group_permissoin(self):
        user = User.objects.create(username='foo', email='hoge@fuga.com', password='fuga')
        another_user = User.objects.create(username='bar', email='bar@f.com', password='')
        group = Group.objects.create(name='hoge')

        aclobj = ACLBase.objects.create(name='hoge', created_user=user, is_public=False)

        # set correct permission to the group that test user is belonged to
        group.permissions.add(aclobj.readable)
        another_user.groups.add(group)

        self.assertTrue(another_user.has_permission(aclobj, 'readable'))

    def test_get_registered_user_permissoins(self):
        user = User.objects.create(username='foo', email='hoge@fuga.com', password='fuga')

        aclobj = ACLBase.objects.create(name='hoge', created_user=user, is_public=False)
        user.permissions.add(aclobj.readable)

        self.assertEqual(user.get_acls(aclobj).count(), 1)
        self.assertEqual(user.get_acls(aclobj)[0], aclobj.readable)

    def test_get_registered_group_permissoins(self):
        user = User.objects.create(username='foo', email='hoge@fuga.com', password='fuga')
        group = Group.objects.create(name='hoge')

        aclobj = ACLBase.objects.create(name='hoge', created_user=user, is_public=False)
        group.permissions.add(aclobj.full)

        self.assertEqual(group.get_acls(aclobj).count(), 1)
        self.assertEqual(group.get_acls(aclobj)[0], aclobj.full)

    def test_get_subclass_object(self):
        user = User.objects.create(username='foo', email='hoge@fuga.com', password='fuga')

        # make objects to test
        model_entity = import_module('entity.models')
        model_entry = import_module('entry.models')
        kwargs = {
            'name': 'test-object',
            'created_user': user,
        }

        entity = model_entity.Entity.objects.create(**kwargs)
        attr_base = model_entity.AttributeBase.objects.create(parent_entity=entity,
                                                              **kwargs)
        entry = model_entry.Entry.objects.create(schema_id=entity.id, **kwargs)
        attr = model_entry.Attribute.objects.create(parent_entity=entity,
                                                    parent_entry=entry,
                                                    **kwargs)
        base = ACLBase.objects.create(**kwargs)

        self.assertEqual(ACLBase.objects.get(id=entity.id).get_subclass_object(), entity)
        self.assertEqual(ACLBase.objects.get(id=attr_base.id).get_subclass_object(), attr_base)
        self.assertEqual(ACLBase.objects.get(id=entry.id).get_subclass_object(), entry)
        self.assertEqual(ACLBase.objects.get(id=attr.id).get_subclass_object(), attr)
        self.assertEqual(ACLBase.objects.get(id=base.id).get_subclass_object(), base)
