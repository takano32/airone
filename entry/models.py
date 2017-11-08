from django.db import models
from entity.models import EntityAttr, Entity
from user.models import User
from acl.models import ACLBase
from airone.lib.acl import ACLObjType, ACLType
from airone.lib.types import AttrTypeStr, AttrTypeObj, AttrTypeText
from airone.lib.types import AttrTypeArrStr, AttrTypeArrObj
from airone.lib.types import AttrTypeValue


class AttributeValue(models.Model):
    # This is a constant that indicates target object binds multiple AttributeValue objects.
    STATUS_DATA_ARRAY_PARENT = 1 << 0
    STATUS_LATEST = 1 << 1
    MAXIMUM_VALUE_SIZE = (1 << 16)

    value = models.TextField()
    referral = models.ForeignKey(ACLBase, null=True, related_name='referred_attr_value')
    data_array = models.ManyToManyField('AttributeValue')
    created_time = models.DateTimeField(auto_now_add=True)
    created_user = models.ForeignKey(User)
    parent_attr = models.ForeignKey('Attribute')
    status = models.IntegerField(default=0)

    def set_status(self, val):
        self.status |= val
        self.save()

    def del_status(self, val):
        self.status &= ~val
        self.save()

    def get_status(self, val):
        return self.status & val

    @classmethod
    def search(kls, query):
        results = []
        for obj in kls.objects.filter(value__icontains=query):
            attr = obj.parent_attr
            entry = attr.parent_entry

            results.append({
                'type': entry.__class__.__name__,
                'object': entry,
                'hint': "attribute '%s' has '%s'" % (attr.name, obj.value)
            })

        return results

class Attribute(ACLBase):
    values = models.ManyToManyField(AttributeValue)

    # This parameter is needed to make a relationship with corresponding EntityAttr
    schema = models.ForeignKey(EntityAttr)
    parent_entry = models.ForeignKey('Entry')

    def __init__(self, *args, **kwargs):
        super(Attribute, self).__init__(*args, **kwargs)
        self.objtype = ACLObjType.EntryAttr

    # This checks whether each specified attribute needs to update
    def is_updated(self, recv_value):
        # the case new attribute-value is specified
        if self.values.count() == 0:
            # the result depends on the specified value
            return recv_value

        last_value = self.values.last()
        if ((self.schema.type == AttrTypeStr or self.schema.type == AttrTypeText) and
            last_value.value != recv_value):
            return True

        elif self.schema.type == AttrTypeObj:
            if not last_value.referral and not recv_value:
                return False
            elif last_value.referral and not recv_value:
                return True
            elif not last_value.referral and int(recv_value):
                return True
            elif last_value.referral.id != int(recv_value):
                return True

        elif self.schema.type == AttrTypeArrStr:
            # the case of changing value
            if last_value.data_array.count() != len(recv_value):
                return True
            # the case of appending or deleting
            for value in recv_value:
                if not last_value.data_array.filter(value=value).count():
                    return True

        elif self.schema.type == AttrTypeArrObj:
            # the case of changing value
            if last_value.data_array.count() != len(recv_value):
                return True
            # the case of appending or deleting
            for id in recv_value:
                if not last_value.data_array.filter(referral=id).count():
                    return True

        return False

    # These are helper funcitons to get differental AttributeValue(s) by an update request.
    def _validate_attr_values_of_array(self):
        if not int(self.schema.type) & AttrTypeValue['array']:
            return False
        return True

    def get_updated_values_of_array(self, values):
        if not self._validate_attr_values_of_array():
            return []

        last_value = self.values.last()
        if self.schema.type == AttrTypeArrStr:
            return [x for x in values if not last_value.data_array.filter(value=x).count() and x]
        elif self.schema.type == AttrTypeArrObj:
            return [x for x in values if not last_value.data_array.filter(referral=x).count() and x]

        return []

    def get_existed_values_of_array(self, values):
        if not self._validate_attr_values_of_array():
            return []

        last_value = self.values.last()
        if self.schema.type == AttrTypeArrStr:
            return [x for x in last_value.data_array.all() if x.value in values]
        elif self.schema.type == AttrTypeArrObj:
            return [x for x in last_value.data_array.all() if x.referral.id in
                    map(lambda y: int(y), values)]

        return []

    def get_latest_value(self):
        if self.schema.type & AttrTypeValue['array']:
            return self.values.extra(where=['status & 1 = 1']).order_by('created_time').last()
        else:
            return self.values.extra(where=['status & 1 = 0']).order_by('created_time').last()

class Entry(ACLBase):
    attrs = models.ManyToManyField(Attribute)
    schema = models.ForeignKey(Entity)

    def __init__(self, *args, **kwargs):
        super(Entry, self).__init__(*args, **kwargs)
        self.objtype = ACLObjType.Entry

    def add_attribute_from_base(self, base, user):
        if not isinstance(base, EntityAttr):
            raise TypeError('Variable "base" is incorrect type')

        if not isinstance(user, User):
            raise TypeError('Variable "user" is incorrect type')

        attr = Attribute.objects.create(name=base.name,
                                        schema=base,
                                        created_user=user,
                                        parent_entry=self,
                                        is_public=base.is_public,
                                        default_permission=base.default_permission)

        # inherites permissions of base object for user
        [[user.permissions.add(getattr(attr, acltype.name))
            for acltype in ACLType.availables() if permission.name == acltype.name]
            for permission in user.get_acls(base)]

        # inherites permissions of base object for each groups
        [[[group.permissions.add(getattr(attr, acltype.name))
            for acltype in ACLType.availables() if permission.name == acltype.name]
            for permission in group.get_acls(base)]
            for group in user.groups.all()]

        # inherits acl parameters
        attr.inherit_acl(base)

        self.attrs.add(attr)
        return attr

    def get_referred_objects(self):
        """
        This returns objects that refer current Entry in the AttributeValue
        """
        ret = []
        for attrvalue in AttributeValue.objects.filter(referral=self):
            if not attrvalue.get_status(AttributeValue.STATUS_LATEST):
                continue

            referred_obj = attrvalue.parent_attr.parent_entry
            if referred_obj not in ret and referred_obj != self:
                ret.append(referred_obj)

        return ret

    def get_value_history(self, user):
        def export_data_array(attrv):
            attr = attrv.parent_attr

            if attr.schema.type == AttrTypeArrStr:
                return [x.value for x in attrv.data_array.all()]
            elif attr.schema.type == AttrTypeArrObj:
                return [x.referral for x in attrv.data_array.all()]
            return []

        return sum([[{
            'id': self.id,
            'name': self.schema.name,
            'schema': self.schema,
            'attr_name': attr.schema.name,
            'attr_type': attr.schema.type,
            'attr_value': attr_value.value,
            'attr_value_array': export_data_array(attr_value),
            'attr_referral': attr_value.referral,
            'created_time': attr_value.created_time,
            'created_user': attr_value.created_user.username,
        } for attr_value in attr.values.all()]
            for attr in self.attrs.all()
                if user.has_permission(attr, ACLType.Readable)], [])

    def complement_attrs(self, user):
        """
        This method complements Attributes which are appended after creation of Entity
        """

        for attr_id in (set(self.schema.attrs.values_list('id', flat=True)) -
                        set([x.schema.id for x in self.attrs.all()])):

            entity_attr = self.schema.attrs.get(id=attr_id)
            if (not entity_attr.is_active or
                not user.has_permission(entity_attr, ACLType.Readable)):
                continue

            newattr = self.add_attribute_from_base(entity_attr, user)
            if entity_attr.type & AttrTypeValue['array']:
                # Create a initial AttributeValue for editing processing
                attr_value = AttributeValue.objects.create(created_user=user, parent_attr=newattr)

                # Set a flag that means this is the latest value
                attr_value.set_status(AttributeValue.STATUS_LATEST)

                # Set status of parent data_array
                attr_value.set_status(AttributeValue.STATUS_DATA_ARRAY_PARENT)

                newattr.values.add(attr_value)
