from django.db import models
from user.models import Member
from acl.models import ACLBase
from airone.lib import ACLObjType


class AttributeBase(ACLBase):
    type = models.IntegerField(default=0)
    is_mandatory = models.BooleanField(default=False)

    def __init__(self, *args, **kwargs):
        super(AttributeBase, self).__init__(*args, **kwargs)
        self.objtype = ACLObjType.AttrBase

class AttributeValue(models.Model):
    value = models.TextField()
    created_time = models.DateTimeField(auto_now=True)
    created_user = models.ForeignKey(Member)

class Attribute(AttributeBase):
    values = models.ManyToManyField(AttributeValue)
    status = models.IntegerField(default=0)

class Entity(ACLBase):
    note = models.CharField(max_length=200)
    attr_bases = models.ManyToManyField(AttributeBase)

    def __init__(self, *args, **kwargs):
        super(Entity, self).__init__(*args, **kwargs)
        self.objtype = ACLObjType.Entity
