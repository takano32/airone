from django.db import models
from django.contrib.contenttypes.models import ContentType
from airone.lib.acl import ACLObjType
from acl.models import ACLBase


class AttributeBase(ACLBase):
    type = models.IntegerField(default=0)
    is_mandatory = models.BooleanField(default=False)
    referral = models.ForeignKey(ACLBase, null=True, related_name='referred_attr_base')
    index = models.IntegerField(default=0)

class EntityAttr(AttributeBase):
    # This parameter is needed to make a relationship to the corresponding Entity at importing
    parent_entity = models.ForeignKey('Entity')

    def __init__(self, *args, **kwargs):
        super(AttributeBase, self).__init__(*args, **kwargs)
        self.objtype = ACLObjType.EntityAttr

class Entity(ACLBase):
    note = models.CharField(max_length=200)
    attrs = models.ManyToManyField(EntityAttr)

    def __init__(self, *args, **kwargs):
        super(Entity, self).__init__(*args, **kwargs)
        self.objtype = ACLObjType.Entity
