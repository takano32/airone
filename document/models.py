from django.db import models
from user.models import Member


class ACL(models.Model):
    readable = models.ManyToManyField(Member, related_name='acl_readable')
    writable = models.ManyToManyField(Member, related_name='acl_writable')
    deletable = models.ManyToManyField(Member, related_name='acl_deletable')

class AttributeType(models.Model):
    name = models.CharField(max_length=200)
    type = models.IntegerField(default=0)

class AttributeBase(models.Model):
    name = models.CharField(max_length=200)
    type = models.ForeignKey(AttributeType)
    acl = models.ForeignKey(ACL)

class AttributeValue(models.Model):
    value = models.TextField()
    created_time = models.DateTimeField(auto_now=True)
    created_user = models.ForeignKey(Member)

class Attribute(AttributeBase):
    values = models.ManyToManyField(AttributeValue)
    last_value = models.OneToOneField(AttributeValue, related_name='attr')
    status = models.IntegerField(default=0)

class Entity(models.Model):
    acl = models.ForeignKey(ACL)
    attribute_bases = models.ManyToManyField(AttributeBase)

class Entry(models.Model):
    acl = models.ForeignKey(ACL)
    entity = models.ForeignKey(Entity)
    attributes = models.ManyToManyField(Attribute)
    created_user = models.ForeignKey(Member)
    created_time = models.DateTimeField(auto_now=True)
    updated_time = models.DateTimeField(auto_now=True)
