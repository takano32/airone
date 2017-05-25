from django.db import models
from user.models import Member


class ACL(models.Model):
    readable = models.ManyToManyField(Member, related_name='acl_readable', blank=True)
    writable = models.ManyToManyField(Member, related_name='acl_writable', blank=True)
    deletable = models.ManyToManyField(Member, related_name='acl_deletable', blank=True)

class ACLBase(models.Model):
    name = models.CharField(max_length=200)
    acl = models.ForeignKey(ACL, default=lambda: ACL.objects.create())

    # This fields describes the sub-class of this object
    objtype = models.IntegerField(default=0)

    def __init__(self, *args, **kwargs):
        super(ACLBase, self).__init__(*args, **kwargs)

class ACLTest(models.Model):
    test = models.ManyToManyField(Member, related_name='acl_test')
