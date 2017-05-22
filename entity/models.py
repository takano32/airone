from django.db import models
from acl.models import ACLBaseModel
from user.models import Member


class AttributeBase(ACLBaseModel):
    name = models.CharField(max_length=200)
    type = models.IntegerField(default=0)

class AttributeValue(models.Model):
    value = models.TextField()
    created_time = models.DateTimeField(auto_now=True)
    created_user = models.ForeignKey(Member)

class Attribute(AttributeBase):
    values = models.ManyToManyField(AttributeValue)
    status = models.IntegerField(default=0)

class Entity(ACLBaseModel):
    name = models.CharField(max_length=200)
    attribute_bases = models.ManyToManyField(AttributeBase)
