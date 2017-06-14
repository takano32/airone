from django.db import models
from entity.models import AttributeBase, Entity
from user.models import User
from acl.models import ACLBase
from airone.lib.acl import ACLObjType
from airone.lib.types import AttrTypeStr, AttrTypeObj


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
                                        referral=base.referral,
                                        created_user=user)
        self.attrs.add(attr)
        return attr

    def get_latest_attributes(self):
        ret_attrs = []
        for attr in self.attrs.all():
            attrinfo = {}

            attrinfo['id'] = attr.id
            attrinfo['name'] = attr.name

            # set Entries which are specified in the referral parameter
            attrinfo['referrals'] = []
            if attr.referral:
                attrinfo['referrals'] = Entry.objects.filter(schema=attr.referral)

            # set last-value of current attributes
            attrinfo['last_value'] = ''
            if attr.values.count() > 0:
                last_value = attr.values.last()

                if attr.type == AttrTypeStr:
                    attrinfo['last_value'] = last_value.value
                elif attr.type == AttrTypeObj and last_value.referral:
                    attrinfo['referral'] = last_value.referral

            ret_attrs.append(attrinfo)

        return ret_attrs
