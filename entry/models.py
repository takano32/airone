import json
import re

from copy import deepcopy
from datetime import datetime, date, timedelta

from django.db import models
from django.db.models import Q
from django.core.cache import cache
from django.conf import settings

from entity.models import EntityAttr, Entity
from user.models import User
from group.models import Group

from acl.models import ACLBase
from airone.lib.acl import ACLObjType, ACLType
from airone.lib.types import AttrTypeStr, AttrTypeObj, AttrTypeText
from airone.lib.types import AttrTypeArrStr, AttrTypeArrObj
from airone.lib.types import AttrTypeValue
from airone.lib.elasticsearch import ESS

from .settings import CONFIG


class AttributeValue(models.Model):
    # This is a constant that indicates target object binds multiple AttributeValue objects.
    STATUS_DATA_ARRAY_PARENT = 1 << 0

    MAXIMUM_VALUE_SIZE = (1 << 16)

    value = models.TextField()
    referral = models.ForeignKey(ACLBase, null=True, related_name='referred_attr_value')
    data_array = models.ManyToManyField('AttributeValue')
    created_time = models.DateTimeField(auto_now_add=True)
    created_user = models.ForeignKey(User)
    parent_attr = models.ForeignKey('Attribute')
    status = models.IntegerField(default=0)
    boolean = models.BooleanField(default=False)
    date = models.DateField(null=True)

    # This parameter means that target AttributeValue is the latest one. This is usefull to
    # find out enabled AttributeValues by Attribute or EntityAttr object. And separating this
    # parameter from status is very meaningful to reduce query at clearing this flag (If this
    # flag is a value of status paramete, you have to send at least two query to set it down,
    # because you have to check current value by SELECT, after that you calculate new value
    # then update it).
    is_latest = models.BooleanField(default=True)

    # The reason why the 'data_type' parameter is also needed in addition to the Attribute is that
    # the value of 'type' in Attribute may be changed dynamically.
    #
    # If that value is changed after making AttributeValue, we can't know the old type of Attribute.
    # So it's necessary to save the value of AttrTypeVelue for each AttributeValue instance.
    # And this value is constract, this parameter will never be changed after creating.
    data_type = models.IntegerField(default=0)

    # This indicates the parent AttributeValue object, this parameter is usefull to identify
    # leaf AttriuteValue objects.
    parent_attrv = models.ForeignKey('AttributeValue', null=True, related_name='child')

    def set_status(self, val):
        self.status |= val
        self.save()

    def del_status(self, val):
        self.status &= ~val
        self.save()

    def get_status(self, val):
        return self.status & val

    def clone(self, user, **extra_params):
        cloned_value = AttributeValue.objects.get(id=self.id)

        # By removing the primary key, we can clone a django model instance
        cloned_value.pk = None

        # set extra configure
        for (k, v) in extra_params.items():
            setattr(cloned_value, k, v)

        # update basic parameters to new one
        cloned_value.created_user = user
        cloned_value.created_time = datetime.now()
        cloned_value.save()

        cloned_value.data_array.clear()

        return cloned_value

    def get_value(self, with_metainfo=False):
        """
        This returns registered value according to the type of Attribute
        """
        def get_named_value(attrv):
            if attrv.referral:
                if with_metainfo:
                    return {attrv.value: {'id': attrv.referral.id, 'name': attrv.referral.name}}
                else:
                    return {attrv.value: attrv.referral.name}
            else:
                return {attrv.value: None}

        def get_object_value(attrv):
            if attrv.referral:
                if with_metainfo:
                    return {'id': attrv.referral.id, 'name': attrv.referral.name}
                else:
                    return attrv.referral.name

        value = None
        if (self.parent_attr.schema.type == AttrTypeValue['string'] or
            self.parent_attr.schema.type == AttrTypeValue['text']):
            value = self.value

        elif self.parent_attr.schema.type == AttrTypeValue['boolean']:
            value = self.boolean

        elif self.parent_attr.schema.type == AttrTypeValue['date']:
            value = self.date

        elif self.parent_attr.schema.type == AttrTypeValue['object']:
            value = get_object_value(self)

        elif self.parent_attr.schema.type == AttrTypeValue['named_object']:
            value = get_named_value(self)

        elif self.parent_attr.schema.type == AttrTypeValue['group'] and Group.objects.filter(id=int(self.value)):
            group = Group.objects.get(id=int(self.value))
            if with_metainfo:
                value = {'id': group.id, 'name': group.name}
            else:
                value = group.name

        elif self.parent_attr.schema.type & AttrTypeValue['array']:
            if self.parent_attr.schema.type == AttrTypeValue['array_string']:
                value = [x.value for x in self.data_array.all()]

            elif self.parent_attr.schema.type == AttrTypeValue['array_object']:
                value = [get_object_value(x) for x in self.data_array.all() if x.referral]

            elif self.parent_attr.schema.type == AttrTypeValue['array_named_object']:
                value = [get_named_value(x) for x in self.data_array.all()]

        if with_metainfo:
            value = {'type': self.parent_attr.schema.type, 'value': value}

        return value

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

    @classmethod
    def create(kls, user, attr, **params):
        return kls.objects.create(created_user=user,
                                  parent_attr=attr,
                                  data_type=attr.schema.type,
                                  **params)

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
            if isinstance(recv_value, bool):
                # the case that first value is 'False' at the boolean typed parameter
                return True
            else:
                return recv_value

        last_value = self.values.last()
        if ((self.schema.type == AttrTypeStr or self.schema.type == AttrTypeText) and
            last_value.value != recv_value):
            return True

        elif self.schema.type == AttrTypeObj:
            # formalize recv_value type
            if isinstance(recv_value, Entry):
                recv_value = recv_value.id

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
                if not last_value.data_array.filter(value=value).exists():
                    return True

        elif self.schema.type == AttrTypeArrObj:
            # the case of changing value
            if last_value.data_array.count() != len(recv_value):
                return True

            # the case of appending or deleting
            for value in recv_value:
                # formalize value type
                if isinstance(value, Entry):
                    value = value.id

                if not last_value.data_array.filter(referral__id=value).exists():
                    return True

        elif self.schema.type == AttrTypeValue['boolean']:
            return last_value.boolean != recv_value

        elif self.schema.type == AttrTypeValue['group']:
            return last_value.value != recv_value

        elif self.schema.type == AttrTypeValue['date']:
            return last_value.date != recv_value

        elif self.schema.type == AttrTypeValue['named_object']:
            if last_value.value != recv_value['name']:
                return True

            # formalize recv_value['id'] type
            if isinstance(recv_value['id'], Entry):
                recv_value['id'] = recv_value['id'].id

            if not last_value.referral and recv_value['id']:
                return True

            if (last_value.referral and recv_value['id'] and
                last_value.referral.id != int(recv_value['id'])):
                return True

        elif self.schema.type == AttrTypeValue['array_named_object']:
            def get_entry_id(value):
                if isinstance(value, Entry):
                    return value.id
                elif isinstance(value, str):
                    return int(value)
                else:
                    return value

            current_refs = [x.referral.id for x in last_value.data_array.all() if x.referral]
            if sorted(current_refs) != sorted([get_entry_id(x['id']) for x in recv_value if 'id' in x and x['id']]):
                return True

            current_keys = [x.value for x in last_value.data_array.all() if x.value]
            if sorted(current_keys) != sorted([x['name'] for x in recv_value if 'name' in x and x['name']]):
                return True

        return False

    # These are helper funcitons to get differental AttributeValue(s) by an update request.
    def _validate_attr_values_of_array(self):
        if not int(self.schema.type) & AttrTypeValue['array']:
            return False
        return True

    def get_values(self, where_extra=[]):
        where_cond = [] + where_extra

        if self.schema.type & AttrTypeValue['array']:
            where_cond.append('status & %d > 0' % AttributeValue.STATUS_DATA_ARRAY_PARENT)
        else:
            where_cond.append('status & %d = 0' % AttributeValue.STATUS_DATA_ARRAY_PARENT)

        return self.values.extra(where=where_cond).order_by('created_time')

    def get_latest_values(self):
        params = {
            'where_extra': ['is_latest > 0'],
        }
        return self.get_values(**params)

    def get_latest_value(self):
        attrv = self.values.filter(is_latest=True)
        if attrv:
            return attrv.last()
        else:
            attrv = AttributeValue.objects.create(**{
                'value': '',
                'created_user': self.created_user,
                'parent_attr': self,
                'status': 1 if self.schema.type & AttrTypeValue['group'] else 0,
                'data_type': self.schema.type,
            })
            self.values.add(attrv)

            return attrv

    def clone(self, user, **extra_params):
        if not user.has_permission(self, ACLType.Readable):
            return None

        # We can't clone an instance by the way (.pk=None and save) like AttributeValue,
        # since the subclass instance refers to the parent_link's primary key during save.
        params = {
            'name': self.name,
            'created_user': user,
            'schema': self.schema,
            'parent_entry': self.parent_entry,
            **extra_params,
        }
        cloned_attr = Attribute.objects.create(**params)

        attrv = self.get_latest_value()
        if attrv:
            new_attrv = attrv.clone(user, parent_attr=cloned_attr)

            # When the Attribute is array, this method also clone co-AttributeValues
            if self.schema.type & AttrTypeValue['array']:
                for co_attrv in attrv.data_array.all():
                    new_attrv.data_array.add(co_attrv.clone(user))

            cloned_attr.values.add(new_attrv)

        return cloned_attr

    def unset_latest_flag(self):
        AttributeValue.objects.filter(parent_attr=self,
                                      is_latest=True).update(is_latest=False)

    def get_value_history(self, user):
        # At the first time, checks the ermission to read
        if not user.has_permission(self, ACLType.Readable):
            return []

        # This helper function returns value in response to the type
        def get_attr_value(attrv):
            if not attrv.data_type:
                # complement data_type as the current type of Attribute
                attrv.data_type = attrv.parent_attr.schema.type
                attrv.save()

            if attrv.data_type == AttrTypeValue['array_string']:
                return [x.value for x in attrv.data_array.all()]
            elif attrv.data_type == AttrTypeValue['array_object']:
                return [x.referral for x in attrv.data_array.all()]
            elif attrv.data_type == AttrTypeValue['object']:
                return attrv.referral
            elif attrv.data_type == AttrTypeValue['boolean']:
                return attrv.boolean
            elif attrv.data_type == AttrTypeValue['date']:
                return attrv.date
            elif attrv.data_type == AttrTypeValue['named_object']:
                return {
                    'value': attrv.value,
                    'referral': attrv.referral,
                }
            elif attrv.data_type == AttrTypeValue['array_named_object']:
                return sorted([{
                    'value': x.value,
                    'referral': x.referral,
                } for x in attrv.data_array.all()], key=lambda x: x['value'])

            elif attrv.data_type == AttrTypeValue['group']:
                if Group.objects.filter(id=int(attrv.value)).count():
                    group = Group.objects.get(id=int(attrv.value))
                    return {'id': group.id, 'name': group.name}
                else:
                    return {'id': '', 'name': ''}

            else:
                return attrv.value

        return [{
            'attr_name': self.schema.name,
            'attr_type': self.schema.type,
            'attr_value': get_attr_value(attrv),
            'created_time': attrv.created_time,
            'created_user': attrv.created_user.username,
        } for attrv in self.values.all()]

    def _validate_value(self, value):
        if self.schema.type & AttrTypeValue['array']:
            if(self.schema.type & AttrTypeValue['named']):
                return all([x for x in value if isinstance(x, dict) or isinstance(x, type({}.values()))])

            if(self.schema.type & AttrTypeValue['object']):
                return all([x for x in value if (isinstance(x, str) or
                                                 isinstance(x, Entry) or
                                                 x is None)])

            if self.schema.type & AttrTypeValue['string']:
                return True

        if(self.schema.type & AttrTypeValue['named']):
            return isinstance(value, dict)

        if(self.schema.type & AttrTypeValue['string'] or self.schema.type & AttrTypeValue['text']):
            return True

        if(self.schema.type & AttrTypeValue['object']):
            return isinstance(value, str) or isinstance(value, Entry) or value is None

        if(self.schema.type & AttrTypeValue['boolean']):
            return isinstance(value, bool)

        if(self.schema.type & AttrTypeValue['date']):
            return isinstance(value, date) or value is None

        if(self.schema.type & AttrTypeValue['group']):
            if isinstance(value, Group):
                return True
            elif isinstance(value, str):
                return Group.objects.filter(id=int(value))
            elif isinstance(value, int):
                return Group.objects.filter(id=value)

        return False

    def add_value(self, user, value):
        """This method make AttributeValue and set it as the latest one"""

        # checks the type of specified value is acceptable for this Attribute object
        if not self._validate_value(value):
            raise TypeError('"%s" is not acceptable [attr_type:%d]' % (str(value), self.schema.type))

        # Clear the flag that means target AttrValues are latet from the Values
        # that are already created.
        self.unset_latest_flag()

        # Initialize AttrValue as None, because this may not created
        # according to the specified parameters.
        attr_value = None

        # set attribute value according to the attribute-type
        if self.schema.type == AttrTypeValue['string'] or self.schema.type == AttrTypeValue['text']:
            attr_value = AttributeValue.create(user, self)
            attr_value.value = str(value)

        if self.schema.type == AttrTypeValue['group']:
            attr_value = AttributeValue.create(user, self)
            if isinstance(value, Group):
                attr_value.value = str(value.id)
            else:
                attr_value.value = str(value)

        elif self.schema.type == AttrTypeValue['object']:
            attr_value = AttributeValue.create(user, self)
            # set None if the referral entry is not specified
            attr_value.referral = None
            if not value:
                pass
            elif isinstance(value, str) and Entry.objects.filter(id=value):
                attr_value.referral = Entry.objects.get(id=value)
            elif isinstance(value, Entry):
                attr_value.referral = value

        elif self.schema.type == AttrTypeValue['boolean']:
            attr_value = AttributeValue.create(user, self)
            attr_value.boolean = value

        elif self.schema.type == AttrTypeValue['date']:
            attr_value = AttributeValue.create(user, self)
            attr_value.date = value

        elif (self.schema.type == AttrTypeValue['named_object'] and
              ('id' in value and value['id'] or 'name' in value and value['name'])):

            attr_value = AttributeValue.create(user, self)
            attr_value.value = value['name']

            attr_value.referral = None
            if not value['id']:
                pass
            elif isinstance(value['id'], str) and Entry.objects.filter(id=value['id']):
                attr_value.referral = Entry.objects.get(id=value['id'])
            elif isinstance(value['id'], Entry):
                attr_value.referral = value['id']
            else:
                attr_value.referral = None

        elif self.schema.type & AttrTypeValue['array']:
            attr_value = AttributeValue.create(user, self)
            # set status of parent data_array
            attr_value.set_status(AttributeValue.STATUS_DATA_ARRAY_PARENT)
            co_attrv_params = {
                'created_user': user,
                'parent_attr': self,
                'data_type': self.schema.type,
                'parent_attrv': attr_value,
                'is_latest': False,
            }

            # create and append updated values
            attrv_bulk = []
            if self.schema.type == AttrTypeValue['array_string']:
                attrv_bulk = [AttributeValue(value=v, **co_attrv_params) for v in value]

            elif self.schema.type == AttrTypeValue['array_object']:
                for v in value:
                    ref = None
                    if isinstance(v, str):
                        ref = Entry.objects.get(id=int(v))
                    if isinstance(v, int):
                        ref = Entry.objects.get(id=v)
                    elif isinstance(v, Entry):
                        ref = v

                    attrv_bulk.append(AttributeValue(referral=ref, **co_attrv_params))

            elif self.schema.type == AttrTypeValue['array_named_object']:
                for data in value:

                    referral = None
                    if 'id' not in data or not data['id']:
                        pass
                    elif isinstance(data['id'], str) and Entry.objects.filter(id=int(data['id'])):
                        referral = Entry.objects.get(id=int(data['id']))
                    elif isinstance(data['id'], int) and Entry.objects.filter(id=data['id']):
                        referral = Entry.objects.get(id=data['id'])
                    elif isinstance(data['id'], Entry):
                        referral = data['id']

                    attrv_bulk.append(AttributeValue(referral=referral,
                                                     value=data['name'] if 'name' in data else '',
                                                     **co_attrv_params))

            # Create each leaf AttributeValue in bulk. This processing send only one query to the DB
            # for making all AttributeValue objects.
            AttributeValue.objects.bulk_create(attrv_bulk)

            # set created leaf AttribueValues to the data_array parameter of parent AttributeValue
            attr_value.data_array.add(*AttributeValue.objects.filter(parent_attrv=attr_value))

        if attr_value:
            attr_value.save()

            # append new AttributeValue
            self.values.add(attr_value)

        return attr_value

    def convert_value_to_register(self, value):
        """
        This absorbs difference values according to the type of Attributes
        """

        def get_entry(schema, name):
            return Entry.objects.get(is_active=True, schema=schema, name=name)

        def is_entry(schema, name):
            return Entry.objects.filter(is_active=True, schema=schema, name=name)

        def get_named_object(data):
            (key, value) = list(data.items())[0]

            ret_value = {'name': key, 'id': None}
            if isinstance(value, ACLBase):
                ret_value['id'] = value

            elif isinstance(value, str):
                entryset = [get_entry(r, value)
                    for r in self.schema.referral.all() if is_entry(r, value)]

                if any(entryset):
                    ret_value['id'] = entryset[0]
                else:
                    ret_value['id'] = None

            return ret_value

        if (self.schema.type == AttrTypeValue['string'] or
            self.schema.type == AttrTypeValue['text']):
            return value

        elif self.schema.type == AttrTypeValue['object']:
            if isinstance(value, ACLBase):
                return value
            elif isinstance(value, str):
                entryset = [get_entry(r, value)
                    for r in self.schema.referral.all() if is_entry(r, value)]

                if any(entryset):
                    return entryset[0]

        elif self.schema.type == AttrTypeValue['group']:
            if isinstance(value, Group):
                return value.id
            elif isinstance(value, str) and Group.objects.filter(name=value):
                return Group.objects.get(name=value).id

        elif self.schema.type == AttrTypeValue['boolean']:
            return value

        elif self.schema.type == AttrTypeValue['date']:
            return value

        elif self.schema.type == AttrTypeValue['named_object']:
            if not isinstance(value, dict):
                return None

            return get_named_object(value)

        elif self.schema.type & AttrTypeValue['array']:
            if not isinstance(value, list):
                return None

            if self.schema.type == AttrTypeValue['array_string']:
                return value

            elif self.schema.type == AttrTypeValue['array_object']:
                return sum([[get_entry(r, v)
                    for r in self.schema.referral.all() if is_entry(r, v)]
                    for v in value], [])

            elif self.schema.type == AttrTypeValue['array_named_object']:
                if not all([isinstance(x, dict) for x in value]):
                    return None

                return [get_named_object(x) for x in value]

        return None

class Entry(ACLBase):
    # This flag is set just after created or edited, then cleared at completion of the processing
    STATUS_CREATING = 1 << 0
    STATUS_EDITING = 1 << 1

    attrs = models.ManyToManyField(Attribute)
    schema = models.ForeignKey(Entity)

    def __init__(self, *args, **kwargs):
        super(Entry, self).__init__(*args, **kwargs)
        self.objtype = ACLObjType.Entry

    def get_cache(self, cache_key):
        return cache.get("%s_%s" % (self.id, cache_key))

    def set_cache(self, cache_key, value):
        cache.set("%s_%s" % (self.id, cache_key), value)

    def clear_cache(self, cache_key):
        cache.delete("%s_%s" % (self.id, cache_key))

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

        self.attrs.add(attr)
        return attr

    def get_referred_objects(self):
        """
        This returns objects that refer current Entry in the AttributeValue
        """
        return Entry.objects.filter(
                Q(attrs__is_active=True, attrs__values__is_latest=True,
                  attrs__values__referral=self) |
                Q(attrs__is_active=True, attrs__values__is_latest=True,
                  attrs__values__data_array__referral=self))

    def complement_attrs(self, user):
        """
        This method complements Attributes which are appended after creation of Entity
        """

        for attr_id in (set(self.schema.attrs.values_list('id', flat=True)) -
                        set(self.attrs.values_list('schema', flat=True))):

            entity_attr = self.schema.attrs.get(id=attr_id)
            if (not entity_attr.is_active or
                not user.has_permission(entity_attr, ACLType.Readable)):
                continue

            newattr = self.add_attribute_from_base(entity_attr, user)
            if entity_attr.type & AttrTypeValue['array']:
                # Create a initial AttributeValue for editing processing
                attr_value = AttributeValue.objects.create(created_user=user, parent_attr=newattr)

                # Set status of parent data_array
                attr_value.set_status(AttributeValue.STATUS_DATA_ARRAY_PARENT)

                newattr.values.add(attr_value)

    def get_available_attrs(self, user, permission=ACLType.Readable, get_referral_entries=False):
        # To avoid unnecessary DB access for caching referral entries
        ref_entry_map = {}

        ret_attrs = []
        attrs = [x for x in self.attrs.filter(is_active=True) if user.has_permission(x, permission)]
        for attr in sorted(attrs, key=lambda x:x.schema.index):
            attrinfo = {}

            attrinfo['id'] = attr.id
            attrinfo['name'] = attr.schema.name
            attrinfo['type'] = attr.schema.type
            attrinfo['is_mandatory'] = attr.schema.is_mandatory
            attrinfo['index'] = attr.schema.index

            # set last-value of current attributes
            attrinfo['last_value'] = ''
            attrinfo['last_referral'] = None
            if attr.values.count() > 0:
                last_value = attr.get_latest_value()
                if not last_value.data_type:
                    last_value.data_type = attr.schema.type
                    last_value.save()

                if last_value.data_type == AttrTypeStr or attr.schema.type == AttrTypeText:
                    attrinfo['last_value'] = last_value.value

                elif (last_value.data_type == AttrTypeObj and last_value.referral and last_value.referral.is_active):
                    attrinfo['last_referral'] = last_value.referral

                elif last_value.data_type == AttrTypeArrStr:
                    # this dict-key 'last_value' is uniformed with all array types
                    attrinfo['last_value'] = [x.value for x in last_value.data_array.all()]

                elif last_value.data_type == AttrTypeArrObj:
                    attrinfo['last_value'] = [x.referral for x
                            in last_value.data_array.all() if x.referral and x.referral.is_active]

                elif last_value.data_type == AttrTypeValue['boolean']:
                    attrinfo['last_value'] = last_value.boolean

                elif last_value.data_type == AttrTypeValue['date']:
                    attrinfo['last_value'] = last_value.date

                elif last_value.data_type == AttrTypeValue['named_object']:
                    attrinfo['last_value'] = last_value.value

                    if last_value.referral and last_value.referral.is_active:
                        attrinfo['last_referral'] = last_value.referral
                    else:
                        attrinfo['last_referral'] = None

                elif last_value.data_type == AttrTypeValue['array_named_object']:
                    values = [x.value for x in last_value.data_array.all()]
                    referrals = [x.referral for x in last_value.data_array.all()]

                    attrinfo['last_value'] = sorted([{
                        'value': v,
                        'referral': r if r and r.is_active else None,
                    } for (v, r) in zip(values, referrals)], key=lambda x: x['value'])

                elif last_value.data_type == AttrTypeValue['group']:
                    attrinfo['last_referral'] = Group.objects.get(id=int(last_value.value))

            # set Entries which are specified in the referral parameter
            attrinfo['referrals'] = []

            if get_referral_entries:
                for referral in attr.schema.referral.all():
                    if not user.has_permission(referral, permission):
                        continue

                    # when an entry in referral attribute is deleted,
                    # user should be able to select new referral or keep it unchanged.
                    # so candidate entries of referral attribute are:
                    # - active(not deleted) entries (new referral)
                    # - last value even if the entry has been deleted (keep it unchanged)
                    if referral.id not in ref_entry_map:
                        # cache referral Entries
                        entries = ref_entry_map[referral.id] = Entry.objects.filter(schema=referral, is_active=True)
                    else:
                        entries = ref_entry_map[referral.id]

                    attrinfo['referrals'] += entries

            ret_attrs.append(attrinfo)

        return sorted(ret_attrs, key=lambda x: x['index'])

    def delete(self):
        super(Entry, self).delete()

        # also delete each attributes
        for attr in self.attrs.filter(is_active=True):

            # delete Attribute object
            attr.delete()

        if settings.ES_CONFIG:
            es = ESS()
            res = es.delete(doc_type='entry', id=self.id, ignore=[404])
            es.refresh(ignore=[404])

    def clone(self, user, **extra_params):
        if (not user.has_permission(self, ACLType.Readable) or
            not user.has_permission(self.schema, ACLType.Readable)):
            return None

        # set STATUS_CREATING flag until all related parameters are set
        status = Entry.STATUS_CREATING
        if 'status' in extra_params:
            status |= extra_params.pop('status')

        # We can't clone an instance by the way (.pk=None and save) like AttributeValue,
        # since the subclass instance refers to the parent_link's primary key during save.
        params = {
            'name': self.name,
            'created_user': user,
            'schema': self.schema,
            'status': status,
            **extra_params,
        }
        cloned_entry = Entry.objects.create(**params)

        for attr in self.attrs.filter(is_active=True):
            cloned_entry.attrs.add(attr.clone(user, parent_entry=cloned_entry))

        cloned_entry.del_status(Entry.STATUS_CREATING)
        return cloned_entry

    def export(self, user):
        attrinfo = {}
        for attr in self.attrs.filter(is_active=True):
            if not user.has_permission(attr, ACLType.Readable):
                continue

            latest_value = attr.get_latest_value()
            if latest_value:
                attrinfo[attr.schema.name] = latest_value.get_value()
            else:
                attrinfo[attr.schema.name] = None

        return {'name': self.name, 'attrs': attrinfo}

    def register_es(self, es=None, skip_refresh=False):
        """This processing registers entry information to Elasticsearch"""

        if not es:
            es = ESS()

        document = {
            'entity': {'id': self.schema.id, 'name': self.schema.name},
            'name': self.name,
            'attr': [],
        }

        for attr in self.attrs.filter(is_active=True):
            attrinfo = {
                'name': attr.schema.name,
                'type': attr.schema.type,
                'value': None,
                'values': [],
            }

            latest_value = attr.get_latest_value()
            if latest_value:

                _value = latest_value.get_value(with_metainfo=True)
                try:
                    if _value['type'] & AttrTypeValue['array']:

                        if _value['type'] & AttrTypeValue['string']:
                            attrinfo['values'] = []
                            for v in _value['value']:
                                timeobj = self._is_date(v)
                                if timeobj:
                                    attrinfo['values'].append({'date_value': timeobj})
                                else:
                                    attrinfo['values'].append({'value': v})

                        elif _value['type'] & AttrTypeValue['named']:
                            _arrinfo = []
                            for v in _value['value']:
                                [k] = v.keys()

                                _vinfo = {'key': k}
                                if k in v and v[k]:
                                    _vinfo['value'] = v[k]['name']
                                    _vinfo['referral_id'] = v[k]['id']

                                _arrinfo.append(_vinfo)

                            attrinfo['values'] = _arrinfo

                        elif _value['type'] & AttrTypeValue['object']:
                            attrinfo['values'] = [{'value': v['name'], 'referral_id': v['id']} for v in _value['value']]

                    else:
                        if (_value['type'] & AttrTypeValue['string'] or
                            _value['type'] & AttrTypeValue['text']):
                            # When the value was date format, Elasticsearch detect it date type
                            # automatically. This processing explicitly set value to the date typed
                            # parameter.
                            timeobj = self._is_date(_value['value'])
                            if timeobj:
                                attrinfo['date_value'] = timeobj
                            else:
                                attrinfo['value'] = str(_value['value'])

                        elif _value['type'] & AttrTypeValue['boolean']:
                            attrinfo['value'] = str(_value['value'])

                        elif _value['type'] & AttrTypeValue['date']:
                            attrinfo['date_value'] = _value['value']

                        elif _value['type'] & AttrTypeValue['named']:
                            [k] = _value['value'].keys()
                            if k in _value['value'] and _value['value'][k]:
                                attrinfo['key'] = k
                                attrinfo['value'] = _value['value'][k]['name']
                                attrinfo['referral_id'] = _value['value'][k]['id']

                        elif (_value['type'] & AttrTypeValue['object'] or
                              _value['type'] & AttrTypeValue['group']):
                            attrinfo['value'] = _value['value']['name']
                            attrinfo['referral_id'] = _value['value']['id']

                except TypeError:
                    # The attribute that has no value returns None at get_value method
                    pass

            document['attr'].append(attrinfo)

        resp = es.index(doc_type='entry', id=self.id, body=document)
        if not skip_refresh:
            es.refresh()

    @classmethod
    def search_entries(kls, user, hint_entity_ids, hint_attrs=[], limit=CONFIG.MAX_LIST_ENTRIES):
        results = {
            'ret_count': 0,
            'ret_values': []
        }

        # Making a query to send ElasticSearch by the specified parameters
        query = {
            "query": {
                "bool": {
                    'filter': [],
                    'should': []
                }
            }
        }
        for entity_id in hint_entity_ids:
            query['query']['bool']['should'].append({
                'term': {'entity.id': int(entity_id)}
            })

        for hint in hint_attrs:
            if 'name' in hint:
                query['query']['bool']['filter'].append({
                    'match': {'attr.name': hint['name']}
                })

            if 'keyword' in hint and hint['keyword']:

                timeobj = kls._is_date(hint['keyword'])
                if timeobj:
                    timestr = timeobj.strftime('%Y/%m/%d')
                    query['query']['bool']['filter'].append({
                        'bool' : {
                            'should': [
                                {'range': {
                                    'attr.date_value': {
                                        'gte': timestr,
                                        'lte': timestr,
                                        'format': 'yyyy/MM/dd'
                                    }
                                }},
                                {'range': {
                                    'attr.values.date_value': {
                                        'gte': timestr,
                                        'lte': timestr,
                                        'format': 'yyyy/MM/dd'
                                    }
                                }},
                            ]
                        }
                    })
                else:
                    query['query']['bool']['filter'].append({
                        'bool' : {
                            'should': [
                                {'regexp': {'attr.values.value': '.*%s.*' % hint['keyword']}},
                                {'match': {'attr.values.value': hint['keyword']}},
                                {'regexp': {'attr.value': '.*%s.*' % hint['keyword']}},
                                {'match': {'attr.value': hint['keyword']}},
                            ]
                        }
                    })

        try:
            res = ESS().search(body=query, ignore=[404])
        except Exception as e:
            raise(e)

        if 'status' in res and res['status'] == 404:
            return results

        # set numbers of found entries
        results['ret_count'] = res['hits']['total']

        for hit in res['hits']['hits']:
            if len(results['ret_values']) >= limit:
                break

            # If 'keyword' parameter is specified and hited entry doesn't have value at the targt
            # attribute, that entry should be removed from result. This processing may be worth to
            # do before refering entry from DB for saving time of server-side processing.
            for hint in hint_attrs:
                if ('keyword' in hint and hint['keyword'] and
                    # This checks hitted entry has specified attribute
                    not [x for x in hit['_source']['attr'] if x['name'] == hint['name']]):
                        continue

            will_append_entry = True
            entry = Entry.objects.get(id=hit['_id'])

            ret_info = {
                'entity': {'id': entry.schema.id, 'name': entry.schema.name},
                'entry': {'id': entry.id, 'name': entry.name},
                'attrs': {},
            }

            # Gathering attribute informations
            for hint in hint_attrs:
                ret_info['attrs'][hint['name']] = ret_attrinfo = {}

                try:
                    attrinfo = [x for x in hit['_source']['attr'] if x['name'] == hint['name']][0]
                except IndexError:
                    if 'keyword' in hint and hint['keyword']:
                        will_append_entry = False
                        break
                    else:
                        continue

                if attrinfo:
                    ret_attrinfo['type'] = attrinfo['type']

                    # Checks that target values contain 'keyward' pattern if it's specified
                    if 'keyword' in hint and hint['keyword']:
                        timeobj = kls._is_date(hint['keyword'])

                        # the case target array attribute has no value that matches keyward parameter
                        if ((attrinfo['type'] & AttrTypeValue['array'] and
                             not any(['date_value' in x for x in attrinfo['values']]) and
                             not any([re.match(hint['keyword'], x['value']) for x in attrinfo['values']])) or

                            # the case target attry attribute has no matched date_value associated with keyword
                            (attrinfo['type'] & AttrTypeValue['array'] and
                             (any(['date_value' in x for x in attrinfo['values']]) or timeobj) and
                             not any([x['date_value'].split('T')[0] == timeobj.strftime('%Y-%m-%d')
                                 for x in attrinfo['values'] if 'date_value' in x and timeobj])) or

                            # the case target has no value in array value
                            (attrinfo['type'] & AttrTypeValue['array'] and
                             not any(['date_value' in x or x['value'] for x in attrinfo['values']])) or

                            # the case target has no value
                            (not (attrinfo['type'] & AttrTypeValue['array']) and
                             ('date_value' not in attrinfo or not attrinfo['date_value']) and
                             not attrinfo['value']) or

                            # the case target attribute has no value
                            (not (attrinfo['type'] & AttrTypeValue['array']) and
                             not timeobj and 'date_value' not in attrinfo and not attrinfo['value']) or

                            # the case target attribute doesn't have have that matches keyword parameter
                            (not (attrinfo['type'] & AttrTypeValue['array']) and
                             attrinfo['value'] and not re.match(hint['keyword'], attrinfo['value'])) or

                            # the case target hint parameter is date, but keyword is not date parameter
                            (not (attrinfo['type'] & AttrTypeValue['array']) and
                             'date_value' in attrinfo and attrinfo['date_value'] and not timeobj) or

                            # the case target date parameter doesn't match with specified keyword date
                            (not (attrinfo['type'] & AttrTypeValue['array']) and
                             'date_value' in attrinfo and attrinfo['date_value'] and timeobj and
                             str(attrinfo['date_value']).split('T')[0] != timeobj.strftime('%Y-%m-%d'))):

                            will_append_entry = False
                            break

                    # Set AttributeValue parameter to be returned
                    try:
                        if (attrinfo['type'] == AttrTypeValue['string'] or
                            attrinfo['type'] == AttrTypeValue['text']):

                            if attrinfo['value']:
                                ret_attrinfo['value'] = attrinfo['value']
                            elif attrinfo['date_value']:
                                ret_attrinfo['value'] = attrinfo['date_value'].split('T')[0]

                        elif attrinfo['type'] == AttrTypeValue['boolean']:
                            ret_attrinfo['value'] = attrinfo['value']

                        elif attrinfo['type'] == AttrTypeValue['date']:
                            ret_attrinfo['value'] = attrinfo['date_value']

                        elif (attrinfo['type'] == AttrTypeValue['object'] or
                              attrinfo['type'] == AttrTypeValue['group']):
                            ret_attrinfo['value'] = {'id': attrinfo['referral_id'], 'name': attrinfo['value']}

                        elif attrinfo['type'] == AttrTypeValue['named_object']:
                            ret_attrinfo['value'] = {
                                    attrinfo['key']: {'id': attrinfo['referral_id'], 'name': attrinfo['value']}
                            }

                        elif attrinfo['type'] == AttrTypeValue['array_string']:
                            ret_attrinfo['value'] = []
                            for v in attrinfo['values']:
                                if 'date_value' in v:
                                    ret_attrinfo['value'].append(v['date_value'].split('T')[0])
                                else:
                                    ret_attrinfo['value'].append(v['value'])

                        elif attrinfo['type'] == AttrTypeValue['array_object']:
                            ret_attrinfo['value'] = [{'id': x['referral_id'], 'name': x['value']} for x in attrinfo['values']]

                        elif attrinfo['type'] == AttrTypeValue['array_named_object']:
                            ret_attrinfo['value'] = [
                                    {x['key']: {'id': x['referral_id'], 'name': x['value']}} for x in attrinfo['values']
                            ]

                    except KeyError as e:
                        # When an entry doesn't have any value, elasticsearch doesn't have any value of
                        # 'value', 'values', 'key' and 'referral_id'. And if 'keyward' parameter is
                        # specified, ignore the candidate that doesn't have any values.
                        if 'keyword' in hint and hint['keyword']:
                            will_append_entry = False
                            break

            if will_append_entry:
                results['ret_values'].append(ret_info)
            else:
                results['ret_count'] -= 1

        return results

    @classmethod
    def _is_date(kls, value):
        ret = None
        if re.match(r'^[0-9]{4}/[0-9]+/[0-9]+', value):
            # ignore unconvert characters if exists by splitting
            ret = datetime.strptime(value.split(' ')[0], '%Y/%m/%d')

        elif re.match(r'^[0-9]{4}-[0-9]+-[0-9]+', value):
            ret = datetime.strptime(value.split(' ')[0], '%Y-%m-%d')

        return ret
