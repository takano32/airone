from django.db import models
from entity.models import AttributeBase, Entity
from user.models import User
from acl.models import ACLBase
from airone.lib import ACLObjType


class AttributeValue(models.Model):
    value = models.TextField()
    created_time = models.DateTimeField(auto_now=True)
    created_user = models.ForeignKey(User)

class Attribute(AttributeBase):
    values = models.ManyToManyField(AttributeValue)
    status = models.IntegerField(default=0)

    def __init__(self, *args, **kwargs):
        super(Attribute, self).__init__(*args, **kwargs)
        self.objtype = ACLObjType.Attr

class Entry(ACLBase):
    attrs = models.ManyToManyField(Attribute)
    schema = models.ForeignKey(Entity)
    created_user = models.ForeignKey(User)
