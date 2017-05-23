from django.db import models
from user.models import Member
from acl.models import ACL


class AttributeBase(models.Model):
    name = models.CharField(max_length=200)
    type = models.IntegerField(default=0)
    is_mandatory = models.BooleanField(default=False)
    acl = models.ForeignKey(ACL, blank=True, null=True)

class AttributeValue(models.Model):
    value = models.TextField()
    created_time = models.DateTimeField(auto_now=True)
    created_user = models.ForeignKey(Member)

class Attribute(AttributeBase):
    values = models.ManyToManyField(AttributeValue)
    status = models.IntegerField(default=0)

class Entity(models.Model):
    name = models.CharField(max_length=200)
    note = models.CharField(max_length=200)
    attr_bases = models.ManyToManyField(AttributeBase)
    acl = models.ForeignKey(ACL, blank=True, null=True)
