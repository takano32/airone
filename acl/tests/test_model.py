from django.test import TestCase
from acl.models import ACL


class ModelTest(TestCase):
    def test_acl_base(self):
        # chacks to enable embedded acl field
        ACL().save()
        
        acl = ACL.objects.first()
        self.assertIsNotNone(acl)
        self.assertEqual(list(acl.readable.all()), [])
