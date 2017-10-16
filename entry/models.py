from django.db import models
from entity.models import AttributeBase, Entity
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

class Attribute(AttributeBase):
    values = models.ManyToManyField(AttributeValue)

    # This parameter is needed to make a relationship with corresponding EntityAttr
    schema_id = models.IntegerField(default=0)
    parent_entry = models.ForeignKey('Entry')

    def __init__(self, *args, **kwargs):
        super(Attribute, self).__init__(*args, **kwargs)
        self.objtype = ACLObjType.EntryAttr

    def update_from_base(self, base):
        if not isinstance(base, AttributeBase):
            raise TypeError('Variable "base" is incorrect type')

        self.name = base.name
        self.type = base.type
        self.referral = base.referral
        self.is_mandatory = base.is_mandatory
        self.index = base.index

        self.save()

    # This checks whether each specified attribute needs to update
    def is_updated(self, recv_value):
        # the case new attribute-value is specified
        if self.values.count() == 0:
            # the result depends on the specified value
            return recv_value

        last_value = self.values.last()
        if ((self.type == AttrTypeStr or self.type == AttrTypeText) and
            last_value.value != recv_value):
            return True

        elif self.type == AttrTypeObj:
            if not last_value.referral and not recv_value:
                return False
            elif last_value.referral and not recv_value:
                return True
            elif not last_value.referral and int(recv_value):
                return True
            elif last_value.referral.id != int(recv_value):
                return True

        elif self.type == AttrTypeArrStr:
            # the case of changing value
            if last_value.data_array.count() != len(recv_value):
                return True
            # the case of appending or deleting
            for value in recv_value:
                if not last_value.data_array.filter(value=value).count():
                    return True

        elif self.type == AttrTypeArrObj:
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
        if not int(self.type) & AttrTypeValue['array']:
            return False
        return True

    def get_updated_values_of_array(self, values):
        if not self._validate_attr_values_of_array():
            return []

        last_value = self.values.last()
        if self.type == AttrTypeArrStr:
            return [x for x in values if not last_value.data_array.filter(value=x).count() and x]
        elif self.type == AttrTypeArrObj:
            return [x for x in values if not last_value.data_array.filter(referral=x).count() and x]

        return []

    def get_existed_values_of_array(self, values):
        if not self._validate_attr_values_of_array():
            return []

        last_value = self.values.last()
        if self.type == AttrTypeArrStr:
            return [x for x in last_value.data_array.all() if x.value in values]
        elif self.type == AttrTypeArrObj:
            return [x for x in last_value.data_array.all() if x.referral.id in
                    map(lambda y: int(y), values)]

        return []

    def get_latest_value(self):
        if self.type & AttrTypeValue['array']:
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
        if not isinstance(base, AttributeBase):
            raise TypeError('Variable "base" is incorrect type')

        if not isinstance(user, User):
            raise TypeError('Variable "user" is incorrect type')

        attr = Attribute.objects.create(name=base.name,
                                        type=base.type,
                                        is_mandatory=base.is_mandatory,
                                        referral=base.referral,
                                        schema_id=base.id,
                                        index=base.index,
                                        created_user=user,
                                        parent_entry=self)

        # inherites permissions of base object for user
        [[user.permissions.add(getattr(attr, acltype.name))
            for acltype in ACLType.availables() if permission.name == acltype.name]
            for permission in user.get_acls(base)]

        # inherites permissions of base object for each groups
        [[[group.permissions.add(getattr(attr, acltype.name))
            for acltype in ACLType.availables() if permission.name == acltype.name]
            for permission in group.get_acls(base)]
            for group in user.groups.all()]

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

            if attr.type == AttrTypeArrStr:
                return [x.value for x in attrv.data_array.all()]
            elif attr.type == AttrTypeArrObj:
                return [x.referral for x in attrv.data_array.all()]
            return []

        return sum([[{
            'id': self.id,
            'name': self.name,
            'schema': self.schema,
            'attr_name': attr.name,
            'attr_type': attr.type,
            'attr_value': attr_value.value,
            'attr_value_array': export_data_array(attr_value),
            'attr_referral': attr_value.referral,
            'created_time': attr_value.created_time,
            'created_user': attr_value.created_user.username,
        } for attr_value in attr.values.all()]
            for attr in self.attrs.order_by('index').all()
                if user.has_permission(attr, ACLType.Readable)], [])
