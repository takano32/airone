from django.db import models
from django.contrib.contenttypes.models import ContentType
from airone.lib.acl import ACLObjType
from acl.models import ACLBase


class AttributeBase(ACLBase):
    type = models.IntegerField(default=0)
    is_mandatory = models.BooleanField(default=False)
    referral = models.ForeignKey(ACLBase, null=True, related_name='referred_attr_base')

    def __init__(self, *args, **kwargs):
        super(AttributeBase, self).__init__(*args, **kwargs)
        self.objtype = ACLObjType.AttrBase

class Entity(ACLBase):
    note = models.CharField(max_length=200)
    attr_bases = models.ManyToManyField(AttributeBase)

    def __init__(self, *args, **kwargs):
        super(Entity, self).__init__(*args, **kwargs)
        self.objtype = ACLObjType.Entity
