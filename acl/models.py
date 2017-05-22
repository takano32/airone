from django.db import models
from user.models import Member


class ACL(models.Model):
    readable = models.ManyToManyField(Member, related_name='acl_readable', blank=True)
    writable = models.ManyToManyField(Member, related_name='acl_writable', blank=True)
    deletable = models.ManyToManyField(Member, related_name='acl_deletable', blank=True)
