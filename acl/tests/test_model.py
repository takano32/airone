from django.test import TestCase
from django.contrib.auth.models import Permission
from acl.models import ACLBase


class ModelTest(TestCase):
    def test_acl_base(self):
        # chacks to enable embedded acl field
        ACLBase(name='hoge').save()
        
        acl = ACLBase.objects.first()
        self.assertIsNotNone(acl)
        self.assertIsInstance(acl.readable, Permission)
        self.assertIsInstance(acl.writable, Permission)
        self.assertIsInstance(acl.deletable, Permission)
