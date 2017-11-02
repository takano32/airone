from django.db import models
from django.contrib.contenttypes.models import ContentType
from airone.lib.acl import ACLObjType
from acl.models import ACLBase


class EntityAttr(ACLBase):
    # This parameter is needed to make a relationship to the corresponding Entity at importing
    parent_entity = models.ForeignKey('Entity')

    type = models.IntegerField(default=0)
    is_mandatory = models.BooleanField(default=False)
    referral = models.ForeignKey(ACLBase, null=True, related_name='referred_attr_base')
    index = models.IntegerField(default=0)

    def __init__(self, *args, **kwargs):
        super(ACLBase, self).__init__(*args, **kwargs)
        self.objtype = ACLObjType.EntityAttr

class Entity(ACLBase):
    STATUS_TOP_LEVEL = 1 << 0

    note = models.CharField(max_length=200)
    attrs = models.ManyToManyField(EntityAttr)

    def __init__(self, *args, **kwargs):
        super(Entity, self).__init__(*args, **kwargs)
        self.objtype = ACLObjType.Entity
