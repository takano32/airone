from django.db import models
from entity.models import AttributeBase, Entity
from user.models import User
from acl.models import ACLBase
from airone.lib.acl import ACLObjType, ACLType
from airone.lib.types import AttrTypeStr, AttrTypeObj
from airone.lib.resources import Importable


class AttributeValue(models.Model, Importable):
    _IMPORT_INFO = {
        'header': ['id', 'refer', 'value', 'attribute_id', 'created_time', 'created_user'],
        'mandatory_keys': ['attribute_id', 'created_user'],
        'resource_module': 'entry.admin',
        'resource_model_name': 'AttrValueResource',
    }

    value = models.TextField()
    referral = models.ForeignKey(ACLBase, null=True, related_name='referred_attr_value')
    created_time = models.DateTimeField(auto_now=True)
    created_user = models.ForeignKey(User)
    parent_attr = models.ForeignKey('Attribute')

class Attribute(AttributeBase, Importable):
    _IMPORT_INFO = {
        'header': ['id', 'name', 'entity', 'schema_id', 'entry_id', 'created_user'],
        'mandatory_keys': ['name', 'entity', 'schema_id', 'entry_id', 'created_user'],
        'resource_module': 'entry.admin',
        'resource_model_name': 'AttrResource',
    }

    values = models.ManyToManyField(AttributeValue)
    schema_id = models.IntegerField(default=0)
    parent_entry = models.ForeignKey('Entry')

    def __init__(self, *args, **kwargs):
        super(Attribute, self).__init__(*args, **kwargs)
        self.objtype = ACLObjType.Attr

    def update_from_base(self, base):
        if not isinstance(base, AttributeBase):
            raise TypeError('Variable "base" is incorrect type')

        self.name = base.name
        self.type = base.type
        self.referral = base.referral
        self.is_mandatory = base.is_mandatory

        self.save()

class Entry(ACLBase, Importable):
    _IMPORT_INFO = {
        'header': ['id', 'name', 'entity', 'created_user'],
        'mandatory_keys': ['name', 'entity', 'created_user'],
        'resource_module': 'entry.admin',
        'resource_model_name': 'EntryResource',
    }

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
                                        created_user=user,
                                        parent_entity=base.parent_entity,
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
