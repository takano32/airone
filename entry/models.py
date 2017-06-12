from django.db import models
from entity.models import AttributeBase, Entity
from user.models import User
from acl.models import ACLBase
from airone.lib.acl import ACLObjType


class AttributeValue(models.Model):
    value = models.TextField()
    referral = models.ForeignKey(ACLBase, null=True, related_name='referred_attr_value')
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

    def add_attribute_from_base(self, base, user):
        attr = Attribute.objects.create(name=base.name,
                                        type=base.type,
                                        is_mandatory=base.is_mandatory,
                                        created_user=user)
        self.attrs.add(attr)
        return attr
