from django.db import models
from django.contrib.contenttypes.models import ContentType
from airone.lib.acl import ACLObjType
from acl.models import ACLBase


class AttributeBase(ACLBase):
    _IMPORT_INFO = {
        'header':               ['id', 'name', 'type', 'refer', 'entity', 'created_user', 'is_mandatory'],
        'mandatory_keys':       ['name', 'type', 'entity', 'created_user'],
        'resource_module':      'entity.admin',
        'resource_model_name':  'AttrBaseResource',
    }

    type = models.IntegerField(default=0)
    is_mandatory = models.BooleanField(default=False)
    referral = models.ForeignKey(ACLBase, null=True, related_name='referred_attr_base')
    parent_entity = models.ForeignKey('Entity')

    def __init__(self, *args, **kwargs):
        super(AttributeBase, self).__init__(*args, **kwargs)
        self.objtype = ACLObjType.AttrBase

class Entity(ACLBase):
    _IMPORT_INFO = {
        'header':               ['id', 'name', 'note', 'created_user'],
        'mandatory_keys':       ['name', 'created_user'],
        'resource_module':      'entity.admin',
        'resource_model_name':  'EntityResource',
    }

    note = models.CharField(max_length=200)
    attr_bases = models.ManyToManyField(AttributeBase)

    def __init__(self, *args, **kwargs):
        super(Entity, self).__init__(*args, **kwargs)
        self.objtype = ACLObjType.Entity
