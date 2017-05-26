from django.db import models
from django.core import exceptions
from user.models import Member


class ACL(models.Model):
    readable = models.ManyToManyField(Member, related_name='acl_readable', blank=True)
    writable = models.ManyToManyField(Member, related_name='acl_writable', blank=True)
    deletable = models.ManyToManyField(Member, related_name='acl_deletable', blank=True)

    def unset_member(self, member):
        self.readable.remove(member)
        self.writable.remove(member)
        self.deletable.remove(member)

class ACLBase(models.Model):
    name = models.CharField(max_length=200)
    acl = models.OneToOneField(ACL, related_name='object', null=True)

    # This fields describes the sub-class of this object
    objtype = models.IntegerField(default=0)

    def save(self, *args, **kwargs):
        # create a default ACL object if it doens't exist
        if not self.acl:
            self.acl = ACL.objects.create()

        super(ACLBase, self).save(*args, **kwargs)
