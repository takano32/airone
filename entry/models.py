import json
import re

from copy import deepcopy
from datetime import datetime, date, timedelta

from django.db import models
from django.db.models import Q
from django.core.cache import cache
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist

from entity.models import EntityAttr, Entity
from user.models import User
from group.models import Group

from acl.models import ACLBase
from airone.lib.acl import ACLObjType, ACLType
from airone.lib.types import AttrTypeStr, AttrTypeObj, AttrTypeText
from airone.lib.types import AttrTypeArrStr, AttrTypeArrObj
from airone.lib.types import AttrTypeValue
from airone.lib.elasticsearch import ESS
from airone.lib import auto_complement

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
            if attrv.referral and attrv.referral.is_active:
                if with_metainfo:
                    return {attrv.value: {'id': attrv.referral.id, 'name': attrv.referral.name}}
                else:
                    return {attrv.value: attrv.referral.name}
            else:
                return {attrv.value: None}

        def get_object_value(attrv):
            if attrv.referral and attrv.referral.is_active:
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

        elif self.parent_attr.schema.type == AttrTypeValue['group'] and self.value:
            group = Group.objects.filter(id=self.value)
            if not group:
                return None
            else:
                group = group.first()

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

    def format_for_history(self):
        if not self.data_type:
            # complement data_type as the current type of Attribute
            self.data_type = self.parent_attr.schema.type
            self.save()

        if self.data_type == AttrTypeValue['array_string']:
            return [x.value for x in self.data_array.all()]
        elif self.data_type == AttrTypeValue['array_object']:
            return [x.referral for x in self.data_array.all()]
        elif self.data_type == AttrTypeValue['object']:
            return self.referral
        elif self.data_type == AttrTypeValue['boolean']:
            return self.boolean
        elif self.data_type == AttrTypeValue['date']:
            return self.date
        elif self.data_type == AttrTypeValue['named_object']:
            return {
                'value': self.value,
                'referral': self.referral,
            }
        elif self.data_type == AttrTypeValue['array_named_object']:
            return sorted([{
                'value': x.value,
                'referral': x.referral,
            } for x in self.data_array.all()], key=lambda x: x['value'])

        elif self.data_type == AttrTypeValue['group'] and self.value:
            try:
                group = Group.objects.get(id=self.value)
                return {'id': group.id, 'name': group.name}
            except ObjectDoesNotExist:
                return {'id': '', 'name': ''}

        else:
            return self.value

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
        if not self.values.exists():
            # the result depends on the specified value
            if isinstance(recv_value, bool):
                # the case that first value is 'False' at the boolean typed parameter
                return True
            else:
                return recv_value

        last_value = self.values.last()
        if self.schema.type == AttrTypeStr or self.schema.type == AttrTypeText:
            # the case that specified value is empty or invalid
            if not recv_value:
                # Value would be changed as empty when there is valid value in the latest AttributeValue
                return last_value.value
            else:
                return last_value.value != recv_value

        elif self.schema.type == AttrTypeObj:
            # formalize recv_value type
            if isinstance(recv_value, Entry):
                recv_value = recv_value.id
            elif recv_value and isinstance(recv_value, str):
                recv_value = int(recv_value)

            if not last_value.referral and not recv_value:
                return False
            elif last_value.referral and not recv_value:
                return True
            elif not last_value.referral and recv_value:
                return True
            elif last_value.referral.id != recv_value:
                return True

        elif self.schema.type == AttrTypeArrStr:
            # the case that specified value is empty or invalid
            if not recv_value:
                # Value would be changed as empty when there are any values in the latest AttributeValue
                return last_value.data_array.count() > 0

            # the case of changing value
            if last_value.data_array.count() != len(recv_value):
                return True
            # the case of appending or deleting
            for value in recv_value:
                if not last_value.data_array.filter(value=value).exists():
                    return True

        elif self.schema.type == AttrTypeArrObj:
            # the case that specified value is empty or invalid
            if not recv_value:
                # Value would be changed as empty when there are any values in the latest AttributeValue
                return last_value.data_array.count() > 0

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
            return last_value.boolean != bool(recv_value)

        elif self.schema.type == AttrTypeValue['group']:
            return last_value.value != recv_value

        elif self.schema.type == AttrTypeValue['date']:
            return last_value.date != recv_value

        elif self.schema.type == AttrTypeValue['named_object']:
            # the case that specified value is empty or invalid
            if not recv_value:
                # Value would be changed as empty when there is valid value in the latest AttributeValue
                return last_value.value or (last_value.referral and last_value.referral.is_active)

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

            # the case that specified value is empty or invalid
            if not recv_value:
                # Value would be changed as empty when there are any values in the latest AttributeValue
                return last_value.data_array.count() > 0

            cmp_curr = []
            for co_attrv in last_value.data_array.all():
                if co_attrv.referral:
                    cmp_curr.append('%s-%s' % (co_attrv.referral.id, co_attrv.value))
                else:
                    cmp_curr.append('N-%s' % (co_attrv.value))

            cmp_recv = []
            for info in recv_value:
                name = info['name'] if 'name' in info and info['name'] else ''

                if 'id' in info and info['id']:
                    cmp_recv.append('%s-%s' % (get_entry_id(info['id']), name))
                else:
                    cmp_recv.append('N-%s' % (name))

            if sorted(cmp_curr) != sorted(cmp_recv):
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
        def _create_new_value():
            params = {
                'value': '',
                'created_user': self.created_user,
                'parent_attr': self,
                'data_type': self.schema.type,
                'status': 0,
            }
            if self.schema.type & AttrTypeValue['array']:
                params['status'] |= AttributeValue.STATUS_DATA_ARRAY_PARENT

            attrv = AttributeValue.objects.create(**params)
            self.values.add(attrv)

            return attrv

        attrv = self.values.filter(is_latest=True).last()
        if attrv:
            # When a type of attribute value is clear, a new Attribute value will be created
            if attrv.data_type != self.schema.type:
                return _create_new_value()
            else:
                return attrv

        elif self.values.count() > 0:
            # During the processing of updating attribute-value, a short period of time
            # that the latest attribute value is vanished might happen. This condition
            # prevents creating new blank AttributeValue when user get latest-value of
            # this Attribute at that time.
            attrv = self.values.last()

            # When a type of attribute value is clear, a new Attribute value will be created
            if attrv.data_type != self.schema.type:
                return _create_new_value()
            else:
                return attrv

        else:
            return _create_new_value()

    def get_last_value(self):
        attrv = self.values.last()
        if not attrv:
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
        if (not user.has_permission(self, ACLType.Readable) or
            not user.has_permission(self.schema, ACLType.Readable)):
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

    def _validate_value(self, value):
        if self.schema.type & AttrTypeValue['array']:
            if value is None:
                return True

            if(self.schema.type & AttrTypeValue['named']):
                return all([x for x in value if isinstance(x, dict) or isinstance(x, type({}.values()))])

            if(self.schema.type & AttrTypeValue['object']):
                return all([isinstance(x, str) or isinstance(x, int) or isinstance(x, Entry) or x is None for x in value])

            if self.schema.type & AttrTypeValue['string']:
                return True

        if(self.schema.type & AttrTypeValue['named']):
            return isinstance(value, dict)

        if(self.schema.type & AttrTypeValue['string'] or self.schema.type & AttrTypeValue['text']):
            return True

        if(self.schema.type & AttrTypeValue['object']):
            return isinstance(value, str) or isinstance(value, int) or isinstance(value, Entry) or value is None

        if(self.schema.type & AttrTypeValue['boolean']):
            return isinstance(value, bool)

        if(self.schema.type & AttrTypeValue['date']):
            try:
                return (isinstance(value, date) or
                        (isinstance(value, str) and isinstance(datetime.strptime(value, '%Y-%m-%d'), date)) or
                        value is None)
            except ValueError:
                return False

        if(self.schema.type & AttrTypeValue['group']):
            return isinstance(value, Group) or not value or Group.objects.filter(id=value)

        return False

    def add_value(self, user, value, boolean=False):
        """This method make AttributeValue and set it as the latest one"""

        # checks the type of specified value is acceptable for this Attribute object
        if not self._validate_value(value):
            raise TypeError('[%s] "%s" is not acceptable [attr_type:%d]' % (self.schema.name, str(value), self.schema.type))

        # Clear the flag that means target AttrValues are latet from the Values
        # that are already created.
        self.unset_latest_flag()

        # Initialize AttrValue as None, because this may not created
        # according to the specified parameters.
        attr_value = AttributeValue.create(user, self)

        # set attribute value according to the attribute-type
        if self.schema.type == AttrTypeValue['string'] or self.schema.type == AttrTypeValue['text']:
            attr_value.boolean = boolean
            attr_value.value = str(value)

        if self.schema.type == AttrTypeValue['group']:
            attr_value.boolean = boolean
            if isinstance(value, Group):
                attr_value.value = str(value.id)
            else:
                attr_value.value = value if value else ''

        elif self.schema.type == AttrTypeValue['object']:
            attr_value.boolean = boolean
            # set None if the referral entry is not specified
            attr_value.referral = None
            if not value:
                pass
            elif isinstance(value, str) and Entry.objects.filter(id=value).exists():
                attr_value.referral = Entry.objects.get(id=value)
            elif isinstance(value, Entry):
                attr_value.referral = value

        elif self.schema.type == AttrTypeValue['boolean']:
            attr_value.boolean = value

        elif self.schema.type == AttrTypeValue['date']:
            if isinstance(value, str):
                attr_value.date = datetime.strptime(value, '%Y-%m-%d').date()
            elif isinstance(value, date):
                attr_value.date = value

            attr_value.boolean = boolean

        elif (self.schema.type == AttrTypeValue['named_object'] and
              ('id' in value and value['id'] or 'name' in value and value['name'])):

            attr_value.value = value['name']
            attr_value.boolean = boolean

            attr_value.referral = None
            if not value['id']:
                pass
            elif isinstance(value['id'], str) and Entry.objects.filter(id=value['id']).exists():
                attr_value.referral = Entry.objects.get(id=value['id'])
            elif isinstance(value['id'], Entry):
                attr_value.referral = value['id']
            else:
                attr_value.referral = None

        elif self.schema.type & AttrTypeValue['array']:
            attr_value.boolean = boolean

            # set status of parent data_array
            attr_value.set_status(AttributeValue.STATUS_DATA_ARRAY_PARENT)

            if value:
                co_attrv_params = {
                    'created_user': user,
                    'parent_attr': self,
                    'data_type': self.schema.type,
                    'parent_attrv': attr_value,
                    'is_latest': False,
                    'boolean': boolean,
                }

                # create and append updated values
                attrv_bulk = []
                if self.schema.type == AttrTypeValue['array_string']:
                    attrv_bulk = [AttributeValue(value=v, **co_attrv_params) for v in value if v]

                elif self.schema.type == AttrTypeValue['array_object']:
                    for v in value:
                        if isinstance(v, Entry):
                            attrv_bulk.append(AttributeValue(referral=v, **co_attrv_params))
                        elif Entry.objects.filter(id=v).exists():
                            attrv_bulk.append(AttributeValue(referral=Entry.objects.get(id=v),
                                                             **co_attrv_params))

                elif self.schema.type == AttrTypeValue['array_named_object']:
                    for data in value:

                        referral = None
                        if 'id' not in data or not data['id']:
                            pass
                        elif isinstance(data['id'], Entry):
                            referral = data['id']
                        elif Entry.objects.filter(id=data['id']).exists():
                            referral = Entry.objects.get(id=data['id'])

                        if not referral and ('name' in data and not data['name']):
                            continue

                        # update boolean parameter if data has its value
                        if 'boolean' in data:
                            co_attrv_params['boolean'] = data['boolean']

                        attrv_bulk.append(AttributeValue(referral=referral,
                                                         value=data['name'] if 'name' in data else '',
                                                         **co_attrv_params))

                # Create each leaf AttributeValue in bulk. This processing send only one query to the DB
                # for making all AttributeValue objects.
                AttributeValue.objects.bulk_create(attrv_bulk)

                # set created leaf AttribueValues to the data_array parameter of parent AttributeValue
                attr_value.data_array.add(*AttributeValue.objects.filter(parent_attrv=attr_value))

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
            elif isinstance(value, str) and Group.objects.filter(name=value).exists():
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

    def remove_from_attrv(self, user, referral=None, value=''):
        """
        This method removes target entry from specified attribute
        """
        attrv = self.get_latest_value()
        if self.schema.type & AttrTypeValue['array']:

            if self.schema.type == AttrTypeValue['array_string']:
                if not value:
                    return

                updated_data = [x.value for x in attrv.data_array.all() if x.value != value]

            elif self.schema.type == AttrTypeValue['array_object']:
                if referral is None:
                    return

                updated_data = [x.referral.id for x in attrv.data_array.all()
                        if x.referral and  x.referral.id != referral.id]

            elif self.schema.type == AttrTypeValue['array_named_object']:
                if referral is None:
                    return

                updated_data = [{
                    'name': x.value,
                    'id': x.referral.id if x.referral else None,
                    'boolean': x.boolean,
                } for x in attrv.data_array.filter(~Q(referral__id=referral.id))]

            if self.is_updated(updated_data):
                self.add_value(user, updated_data, boolean=attrv.boolean)

    def add_to_attrv(self, user, referral=None, value='', boolean=False):
        """
        This method adds target entry to specified attribute with referral_key
        """
        attrv = self.get_latest_value()
        if self.schema.type & AttrTypeValue['array']:

            if self.schema.type == AttrTypeValue['array_string']:
                updated_data = [x.value for x in attrv.data_array.all()] + [value]

            elif self.schema.type == AttrTypeValue['array_object']:
                updated_data = [x.referral.id for x in attrv.data_array.all()] + [referral]

            elif self.schema.type == AttrTypeValue['array_named_object']:
                updated_data = [{
                    'name': x.value,
                    'boolean': x.boolean,
                    'id': x.referral.id if x.referral else None,
                } for x in attrv.data_array.all()] + [{
                    'name': str(value),
                    'boolean': boolean,
                    'id': referral
                }]

            if self.is_updated(updated_data):
                self.add_value(user, updated_data, boolean=attrv.boolean)

    def delete(self):
        super(Attribute, self).delete()

        def _may_remove_referral(referral):
            if not referral:
                # the case this refers no entry, do nothing
                return

            entry = Entry.objects.filter(id=referral.id, is_active=True).first()
            if not entry:
                # the case referred entry is already deleted, do nothing
                return

            if entry.get_referred_objects().count() > 0:
                # the case other entries also refer target referral, do nothing
                return

            entry.delete()

        # delete referral object that isn't referred from any objects if it's necessary
        if self.schema.is_delete_in_chain and self.schema.type & AttrTypeValue['object']:
            attrv = self.get_latest_value()

            if self.schema.type & AttrTypeValue['array']:
                [_may_remove_referral(x.referral) for x in attrv.data_array.all()]
            else:
                _may_remove_referral(attrv.referral)

    def restore(self):
        super(Attribute, self).restore()

        def _may_restore_referral(referral):
            if not referral:
                # the case this refers no entry, do nothing
                return

            entry = Entry.objects.filter(id=referral.id, is_active=False).first()
            if not entry:
                # the case referred entry is already restored, do nothing
                return

            entry.restore()

        # restore referral object that isn't referred from any objects if it's necessary
        if self.schema.is_delete_in_chain and self.schema.type & AttrTypeValue['object']:
            attrv = self.get_latest_value()

            if self.schema.type & AttrTypeValue['array']:
                [_may_restore_referral(x.referral) for x in attrv.data_array.all()]
            else:
                _may_restore_referral(attrv.referral)

class Entry(ACLBase):
    # This flag is set just after created or edited, then cleared at completion of the processing
    STATUS_CREATING = 1 << 0
    STATUS_EDITING = 1 << 1
    STATUS_COMPLEMENTING_ATTRS = 1 << 2

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

        # While an Attribute object which corresponding to base EntityAttr has been already
        # registered, a request to create same Attribute might be here when multiple request
        # invoked and make requests simultaneously. That request may call this method after
        # previous processing is finished.
        # In this case, we have to prevent to create new Attribute object.
        attr = Attribute.objects.filter(schema=base, parent_entry=self, is_active=True).first()
        if attr:
            self.may_append_attr(attr)
            return

        # This processing may avoid to run following more one time from mutiple request
        cache_key = 'add_%d' % base.id
        if self.get_cache(cache_key):
            return

        # set lock status
        self.set_cache(cache_key, 1)

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

        # release lock status
        self.clear_cache(cache_key)

        return attr

    def get_referred_objects(self):
        """
        This returns objects that refer current Entry in the AttributeValue
        """
        ids = AttributeValue.objects.filter(
                Q(referral=self, is_latest=True) |
                Q(referral=self, parent_attrv__is_latest=True)
                ).values_list('parent_attr__parent_entry', flat=True)

        return Entry.objects.filter(pk__in=ids, is_active=True)

    def may_append_attr(self, attr):
        """
        This appends Attribute object to attributes' array of entry when it's entitled to be there.
        """
        if (attr and attr.is_active and attr.parent_entry == self and
            attr.id not in [x.id for x in self.attrs.filter(is_active=True)]):
            self.attrs.add(attr)

    def may_remove_duplicate_attr(self, attr):
        """
        This removes speicified Attribute object if an Attribute object which refers same
        EntityAttr at schema parameter is registered to prevent saving duplicate one.
        """
        if self.attrs.filter(Q(schema=attr.schema, is_active=True), ~Q(id=attr.id)).exists():
            # remove attribute from Attribute list of this entry
            self.attrs.remove(attr)

            # update target attribute will be inactive
            attr.is_active = False
            attr.save(update_fields=['is_active'])

    def complement_attrs(self, user):
        """
        This method complements Attributes which are appended after creation of Entity
        """

        # Get auto complement user
        user = auto_complement.get_auto_complement_user(user)

        for attr_id in (set(self.schema.attrs.filter(is_active=True).values_list('id', flat=True)) -
                        set(self.attrs.filter(is_active=True).values_list('schema', flat=True))):

            entity_attr = self.schema.attrs.get(id=attr_id)
            if not user.has_permission(entity_attr, ACLType.Readable):
                continue

            newattr = self.add_attribute_from_base(entity_attr, user)
            if not newattr:
                continue

            if entity_attr.type & AttrTypeValue['array']:
                # Create a initial AttributeValue for editing processing
                attr_value = AttributeValue.objects.create(**{
                    'created_user': user,
                    'parent_attr': newattr,
                    'data_type': entity_attr.type,
                })

                # Set status of parent data_array
                attr_value.set_status(AttributeValue.STATUS_DATA_ARRAY_PARENT)

                newattr.values.add(attr_value)

            # When multiple requests to add new Attribute came here, multiple Attriutes
            # might be existed. If there were, this would delete new one.
            self.may_remove_duplicate_attr(newattr)

    def get_available_attrs(self, user, permission=ACLType.Readable, get_referral_entries=False, is_active=True):
        # To avoid unnecessary DB access for caching referral entries
        ref_entry_map = {}

        ret_attrs = []
        attrs = [x for x in self.attrs.filter(is_active=is_active, schema__is_active=True) if user.has_permission(x, permission)]
        for attr in sorted(attrs, key=lambda x:x.schema.index):
            attrinfo = {}

            attrinfo['id'] = attr.id
            attrinfo['name'] = attr.schema.name
            attrinfo['type'] = attr.schema.type
            attrinfo['is_mandatory'] = attr.schema.is_mandatory
            attrinfo['index'] = attr.schema.index
            attrinfo['referrals'] = []

            # set last-value of current attributes
            attrinfo['last_value'] = ''
            attrinfo['last_referral'] = None
            if attr.values.exists():
                last_value = attr.get_latest_value()
                if not last_value.data_type:
                    last_value.data_type = attr.schema.type
                    last_value.save()

                if last_value.data_type == AttrTypeStr or last_value.data_type == AttrTypeText:
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

                elif last_value.data_type == AttrTypeValue['array_named_object']:
                    values = [x.value for x in last_value.data_array.all()]
                    referrals = [x.referral for x in last_value.data_array.all()]

                    attrinfo['last_value'] = sorted([{
                        'value': v,
                        'referral': r if r and r.is_active else None,
                    } for (v, r) in zip(values, referrals)], key=lambda x: x['value'])

                elif last_value.data_type == AttrTypeValue['group'] and last_value.value:
                    group = Group.objects.filter(id=last_value.value)
                    if group:
                        attrinfo['last_referral'] = group.first()

            ret_attrs.append(attrinfo)

        return sorted(ret_attrs, key=lambda x: x['index'])

    def to_dict(self, user):
        # check permissions for each entry, entity and attrs
        if (not user.has_permission(self.schema, ACLType.Readable) or
            not user.has_permission(self, ACLType.Readable)):
            return None

        attrs = [x for x in self.attrs.filter(is_active=True, schema__is_active=True)
                 if (user.has_permission(x.schema, ACLType.Readable) and
                     user.has_permission(x, ACLType.Readable))]

        return {
            'id': self.id,
            'name': self.name,
            'entity': {
                'id': self.schema.id,
                'name': self.schema.name,
            },
            'attrs': [{
                'name': x.schema.name,
                'value': x.get_latest_value().get_value()
            } for x in attrs]
        }

    def delete(self):
        super(Entry, self).delete()

        # also delete each attributes
        for attr in self.attrs.filter(is_active=True):

            # delete Attribute object
            attr.delete()

        if settings.ES_CONFIG:
            self.unregister_es()

    def restore(self):
        super(Entry, self).restore()

        # also restore each attributes
        for attr in self.attrs.filter(is_active=False):

            # restore Attribute object
            attr.restore()

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
            cloned_attr = attr.clone(user, parent_entry=cloned_entry)

            if cloned_attr:
                cloned_entry.attrs.add(cloned_attr)

        cloned_entry.del_status(Entry.STATUS_CREATING)
        return cloned_entry

    def export(self, user):
        attrinfo = {}

        # This calling of complement_attrs is needed to take into account the case of the Attributes
        # that are added after creating this entry.
        self.complement_attrs(user)

        for attr in self.attrs.filter(is_active=True):
            if not user.has_permission(attr, ACLType.Readable):
                continue

            latest_value = attr.get_latest_value()
            if latest_value:
                attrinfo[attr.schema.name] = latest_value.get_value()
            else:
                attrinfo[attr.schema.name] = None

        return {'name': self.name, 'attrs': attrinfo}

    def get_es_document(self, es=None):
        """This processing registers entry information to Elasticsearch"""
        # This innner method truncates value in taking multi-byte in account
        def truncate(value):
            while len(value.encode('utf-8')) > ESS.MAX_TERM_SIZE:
                value = value[:-1]
            return value

        def _set_attrinfo(attr, attrv, container, is_recursive=False):
            attrinfo = {
                'name': attr.name,
                'type': attr.type,
                'key': '',
                'value': '',
                'referral_id': None,
            }

            # Basically register attribute information whatever value doesn't exist
            if not (attr.type & AttrTypeValue['array'] and not is_recursive):
                container.append(attrinfo)

            elif attr.type & AttrTypeValue['array'] and not is_recursive and attrv != None:
                # Here is the case of parent array, set each child values
                [_set_attrinfo(attr, x, container, True) for x in attrv.data_array.all()]

                # If there is no value in container, this set blank value for maching blank search request
                if not [x for x in container if x['name'] == attr.name]:
                    container.append(attrinfo)

                return

            # This is the processing to be safe even if the empty AttributeValue was passed.
            if attrv == None:
                return

            # Convert data format for mapping of Elasticsearch  according to the data type
            if (attr.type & AttrTypeValue['string'] or attr.type & AttrTypeValue['text']):
                # When the value was date format, Elasticsearch detect it date type
                # automatically. This processing explicitly set value to the date typed
                # parameter.
                ret = self._is_date_check(attrv.value)
                if ret and isinstance(ret[1], date):
                    attrinfo['date_value'] = ret[1]
                else:
                    attrinfo['value'] = truncate(attrv.value)

            elif attr.type & AttrTypeValue['boolean']:
                attrinfo['value'] = str(attrv.boolean)

            elif attr.type & AttrTypeValue['date']:
                attrinfo['date_value'] = attrv.date

            elif attr.type & AttrTypeValue['named']:
                attrinfo['key'] = attrv.value
                attrinfo['value'] = truncate(attrv.referral.name) if attrv.referral else ''
                attrinfo['referral_id'] = attrv.referral.id if attrv.referral else ''

            elif attr.type & AttrTypeValue['object']:
                attrinfo['value'] = truncate(attrv.referral.name) if attrv.referral else ''
                attrinfo['referral_id'] = attrv.referral.id if attrv.referral else ''

            elif attr.type & AttrTypeValue['group']:
                if attrv.value and Group.objects.filter(id=attrv.value).exists():
                    group = Group.objects.get(id=attrv.value)
                    attrinfo['value'] = truncate(group.name)
                    attrinfo['referral_id'] = group.id
                else:
                    attrinfo['value'] = attrinfo['referral_id'] = ''

        document = {
            'entity': {'id': self.schema.id, 'name': self.schema.name},
            'name': self.name,
            'attr': [],
        }

        # The reason why this is a beat around the bush processing is for the case that Attibutes
        # objects are not existed in attr parameter because of delay processing. If this entry
        # doesn't have an Attribute object associated with an EntityAttr, this registers blank
        # value to the Elasticsearch.
        for entity_attr in self.schema.attrs.filter(is_active=True):
            attrv = None

            attr = self.attrs.filter(schema=entity_attr)
            if attr:
                attrv = attr.first().get_latest_value()

            _set_attrinfo(entity_attr, attrv, document['attr'])

        return document

    def register_es(self, es=None, skip_refresh=False):
        if not es:
            es = ESS()

        resp = es.index(doc_type='entry', id=self.id, body=self.get_es_document(es))
        if not skip_refresh:
            es.refresh()

    def unregister_es(self, es=None):
        if not es:
            es = ESS()

        es.delete(doc_type='entry', id=self.id, ignore=[404])
        es.refresh(ignore=[404])

    def get_value_history(self, user, count=CONFIG.MAX_HISTORY_COUNT, index=0):
        def _get_values(attrv):
            return {
                'attrv_id': attrv.id,
                'value': attrv.format_for_history(),
                'created_time': attrv.created_time,
                'created_user': attrv.created_user.username,
            }

        ret_values = []
        all_attrv = AttributeValue.objects.filter(parent_attr__in=self.attrs.all(),
                                                  parent_attrv__isnull=True).order_by('-created_time')[index:]

        for (i, attrv) in enumerate(all_attrv):
            if (len(ret_values) >= count):
                break

            attr = attrv.parent_attr
            if (attr.is_active and
                attr.schema.is_active and
                user.has_permission(attr, ACLType.Readable) and
                user.has_permission(attr.schema, ACLType.Readable)):

                # try to get next attrv
                next_attrv = None
                for _attrv in all_attrv[(i+1):]:
                    if _attrv.parent_attr == attr:
                        next_attrv = _attrv
                        break

                ret_values.append({
                    'attr_id': attr.id,
                    'attr_name': attr.schema.name,
                    'attr_type': attr.schema.type,
                    'curr': _get_values(attrv),
                    'prev': _get_values(next_attrv) if next_attrv else None,
                })

        return ret_values

    @classmethod
    def search_entries(kls, user, hint_entity_ids, hint_attrs=[], limit=CONFIG.MAX_LIST_ENTRIES, entry_name=None, or_match=False, hint_referral=False):
        """Main method called from simple search and advanced search.

        Do the following:
        1. Create a query for Elasticsearch search. (_make_query)
        2. Execute the created query. (_execute_query)
        3. Search the reference entry,
           process the search results, and return. (_make_search_results)

        Args:
            user (:obj:`str`, optional): User who executed the process
            hint_entity_ids (list(str)): Entity ID specified in the search condition input
            hint_attrs (list(dict[str, str])): Defaults to Empty list.
                A list of search strings and attribute sets
            limit (int): Defaults to 100.
                Maximum number of search results to return
            entry_name (str): Search string for entry name
            or_match (bool): Defaults to False.
                Flag to determine whether the simple search or advanced search is called
            hint_referral (str): Defaults to False.
                Input value used to refine the reference entry.
                Use only for advanced searches.

        Returns:
            dict[str, str]: As a result of the search,
                the acquired entry and the attribute value of the entry are returned.

        """
        results = {
            'ret_count': 0,
            'ret_values': []
        }

        query = kls._make_query(kls, user, hint_entity_ids, hint_attrs, entry_name, or_match)

        res = kls._execute_query(query)

        if 'status' in res and res['status'] == 404:
            return results

        return kls._make_search_results(user, results, res, hint_attrs, limit, hint_referral)

    def _make_query(kls, user, hint_entity_ids, hint_attrs, entry_name, or_match):
        """Create a search query for Elasticsearch.

        Do the following:
        1. Initialize variables.
        2. Add the entity to the filtering condition.
        3. Add the entry name to the filtering condition.
        4. Add the attribute name to be searched.
        5. Analyzes the keyword entered for each attribute.
        6. Build queries along keywords.

        Args:
            user (:obj:`str`, optional): User who executed the process
            hint_entity_ids (list(str)): Entity ID specified in the search condition input
            hint_attrs (list(dict[str, str])): A list of search strings and attribute sets
            entry_name (str): Search string for entry name
            or_match (bool): Flag to determine whether the simple search or
                advanced search is called

        Returns:
            dict[str, str]: The created search query is returned.

        """

        # Making a query to send ElasticSearch by the specified parameters
        query = {
            "query": {
                "bool": {
                    'filter': [],
                    'should': [],
                }
            }
        }

        # set condition to get results that only have specified entity
        query['query']['bool']['filter'].append({
            'nested': {
                'path': 'entity',
                'query': {
                    'bool': {'should': [{'term': {'entity.id': int(x)}} for x in hint_entity_ids]}
                }
            }
        })

        # Included in query if refinement is entered for 'Name' in advanced search
        if entry_name:
            query['query']['bool']['filter'].append(kls._make_entry_name_query(kls, entry_name))

        # Set the attribute name so that all the attributes specified in the attribute,
        # to be searched can be used
        if hint_attrs:
            query['query']['bool']['filter'].append({
                'nested': {
                    'path': 'attr',
                    'query': {
                        'bool': {
                            'should': [{'term': {'attr.name': x['name']}} for x in hint_attrs if 'name' in x]
                        }
                    }
                }
            })

        attr_query = {}

        # filter attribute by keywords
        for hint in [x for x in hint_attrs if 'name' in x and 'keyword' in x and x['keyword']]:
            kls._parse_or_search(kls, hint, or_match, attr_query)

        # Build queries along keywords
        if attr_query:
            query['query']['bool']['filter'].append(
                kls._build_queries_along_keywords(kls, hint_attrs, attr_query, or_match))

        return query

    def _get_regex_pattern(keyword):
        """Create a regex pattern pattern.

        Create a regular expression pattern of the string received as an argument.
        If the following characters are included, an escape character is added.
            `(`,`)`,`<`,`"`,`{`,`[`

        Args:
            keyword (str): A string for which a regular expression pattern is created

        Returns:
            str: Regular expression pattern of argument

        """
        replace_list = ['(',')','<','"','{','[']
        keyword = ''.join(['\\' + x if x in replace_list else x for x in [*keyword]])
        return '.*%s.*' % ''.join(['[%s%s]' % (
                                  x.lower(), x.upper()) if x.isalpha() else x for x in keyword])

    def _get_hint_keyword_val(keyword):
        """Null character conversion processing.

        Args:
            keyword (str): String to search for

        Returns:
            str: If a character corresponding to the empty string specified by CONFIG is entered,
                the empty character is returned.
                Otherwise, the input value is returned.

        """
        if (CONFIG.EMPTY_SEARCH_CHARACTER == keyword
            or CONFIG.EMPTY_SEARCH_CHARACTER_CODE == keyword):
            return ''
        return keyword

    def _make_entry_name_query(kls, entry_name):
        """Create a search query for the entry name.

        Divides the search string with OR.
        Divide the divided character string with AND.
        Create a regular expression pattern query with the smallest unit string.
        If the string corresponds to a null character, specify the null character.

        Args:
            entry_name (str): Search string for entry name

        Returns:
            dict[str, str]: Entry name search query

        """
        entry_name_or_query = {
            'bool': {
                'should': []
            }
        }

        # Split and process keywords with 'or'
        for keyword_divided_or in entry_name.split(CONFIG.OR_SEARCH_CHARACTER):

            entry_name_and_query = {
                'bool': {
                    'filter': []
                }
            }

            # Keyword divided by 'or' is processed by dividing by 'and'
            for keyword in keyword_divided_or.split(CONFIG.AND_SEARCH_CHARACTER):
                name_val = kls._get_hint_keyword_val(keyword)
                if name_val:
                    # When normal conditions are specified
                    entry_name_and_query['bool']['filter'].append({
                        'regexp': {
                            'name': kls._get_regex_pattern(name_val)
                        }
                    })
                else :
                    # When blank is specified in the condition
                    entry_name_and_query['bool']['filter'].append({
                        'match': {
                            'name': ''
                        }
                    })
            entry_name_or_query['bool']['should'].append(entry_name_and_query)

        return entry_name_or_query

    def _parse_or_search(kls, hint, or_match, attr_query):
        """Performs keyword analysis processing.

        The search keyword is separated by OR and passed to the next process.

        Args:
            hint (dict[str, str]): Dictionary of attribute names and search keywords to be processed
            or_match (bool): Flag to determine whether the simple search or
                advanced search is called
            attr_query (dict[str, str]): Search query being created

        Returns:
            dict[str, str]: Add the analysis result to 'attr_query' for the keywords separated
                by 'OR' and return.

        """
        duplicate_keys = []

        # Split and process keywords with 'or'
        for keyword_divided_or in hint['keyword'].split(CONFIG.OR_SEARCH_CHARACTER):

            kls._parse_and_search(
                kls, hint, keyword_divided_or, or_match, attr_query, duplicate_keys)

        return attr_query

    def _parse_and_search(kls, hint, keyword_divided_or, or_match, attr_query, duplicate_keys):
        """Analyze the keywords separated by `OR`

        Keywords separated by OR are separated by AND.
        Create a block that summarizes all attribute filters for each smallest keyword.

        If the plan has already been processed, skip it.
        If not, add it to the list.

        If called from simple search, add to the query below.
        If called from advanced search, add it directly under keyword.
            {
                keyword: {
                    'bool': {
                        'should': []
                    }
                }
            }

        Args:
            hint (dict[str, str]): Dictionary of attribute names and search keywords to be processed
            keyword_divided_or (str): Character string with search keywords separated by OR
            or_match (bool): Flag to determine whether the simple search or
                advanced search is called
            attr_query (dict[str, str]): Search query being created
            duplicate_keys (list(str)): Holds a list of the smallest character strings
                that separate search keywords with AND and OR.
                If the target string is already included in the list, processing is skipped.

        Returns:
            dict[str, str]: The analysis result is added to 'attr_query' for the keywords separated
                by 'AND' and returned.

        """

        # Keyword divided by 'or' is processed by dividing by 'and'
        for keyword in keyword_divided_or.split(CONFIG.AND_SEARCH_CHARACTER):
            key = kls._make_key_for_each_block_of_keywords(hint, keyword, or_match)

            # Skip if keywords overlap
            if key in duplicate_keys:
                continue
            else:
                duplicate_keys.append(key)

            if or_match:
                if key not in attr_query:
                    # Add keyword if temporary variable doesn't contain keyword
                    attr_query[key] = {'bool': {'should': []}}

                attr_query[key]['bool']['should'].append(
                    kls._make_an_attribute_filter(kls, hint, keyword, or_match))
            else:
                attr_query[key] = kls._make_an_attribute_filter(
                    kls, hint, keyword, or_match)

        return attr_query

    def _make_key_for_each_block_of_keywords(hint, keyword, or_match):
        """Create a key for each block of minimal keywords.

        Create a key for each block of keywords.
        For simple search, the keyword is used as a key.
        In case of advanced search, attribute name is given to judge for each attribute.

        Args:
            hint (dict[str, str]): Dictionary of attribute names and search keywords to be processed
            keyword (str): String of the smallest unit in which search keyword is
                separated by AND and OR
            or_match (bool): Flag to determine whether the simple search or
                advanced search is called

        Returns:
            dict[str, str]: For simple search, the keyword of the argument is returned.
                In the case of advanced search,
                the attribute name is assigned to the argument keyword and returned.

        """
        return keyword if or_match else keyword + '_' + hint['name']

    def _build_queries_along_keywords(kls, hint_attrs, attr_query, or_match):
        """Build queries along search terms.

        Do the following:
        1. Get the keyword.
           In case of simple search, get the first search keyword.
           For advanced searches, retrieve multiple records for each attribute value.
        2. Process for each keyword acquired in 1.
        3. The search keyword is processed for each character string of the
           smallest unit separated by `AND` and `OR`.
        4. If `AND` is included in the string separated by `OR`, concatenate them with a filter.
           If it is not included, use it as is.
        5. If the search keyword contains OR, connect with should.
           If it is not included, use it as is.
        6. When conditions are specified with multiple attributes in advanced search,
           they are combined with filter.
        7. The query will be returned when the processing
           for the retrieved search keywords is completed.

        Args:
            hint_attrs (list(dict[str, str])): A list of search strings and attribute sets
            attr_query (dict[str, str]): A query that summarizes attributes
                by the smallest unit of a search keyword
            or_match (bool): Flag to determine whether the simple search or
                advanced search is called

        Returns:
            dict[str, str]: Assemble and return the attribute value part of the search query.

        """

        # Get the keyword.
        hints = [x for x in hint_attrs if x['keyword']] if not or_match else [hint_attrs[0]]
        res_query = {}

        for hint in hints:
            and_query = {}
            or_query = {}

            # Split keyword by 'or'
            for keyword_divided_or in hint['keyword'].split(CONFIG.OR_SEARCH_CHARACTER):
                if CONFIG.AND_SEARCH_CHARACTER in keyword_divided_or:

                    # If 'AND' is included in the keyword divided by 'OR', add it to 'filter'
                    for keyword in keyword_divided_or.split(CONFIG.AND_SEARCH_CHARACTER):
                        if keyword_divided_or not in and_query:
                            and_query[keyword_divided_or] = {'bool': {'filter': []}}

                        and_query[keyword_divided_or]['bool']['filter'].append(
                            attr_query[kls._make_key_for_each_block_of_keywords(
                                               hint, keyword, or_match)])

                else:
                    and_query[keyword_divided_or] = attr_query[kls.
                        _make_key_for_each_block_of_keywords(hint, keyword_divided_or, or_match)]

                if CONFIG.OR_SEARCH_CHARACTER in hint['keyword']:

                    # If the keyword contains 'or', concatenate with 'should'
                    if not or_query:
                        or_query = {'bool': {'should': []}}

                    or_query['bool']['should'].append(and_query[keyword_divided_or])

                else:
                    or_query = and_query[keyword_divided_or]

            if len(hints) > 1:
                # If conditions are specified for multiple attributes in advanced search,
                # connect with 'filter'
                if not res_query:
                    res_query = {'bool': {'filter': []}}

                res_query['bool']['filter'].append(or_query)

            else:
                res_query = or_query

        return res_query

    def _make_an_attribute_filter(kls, hint, keyword, or_match):
        """creates an attribute filter from keywords.

        For the attribute set in the name of hint, create a filter for filtering search keywords.
        If the search keyword is a date, the following processing is performed.
        1. Create a format for date fields.
        2. If the search keyword is a date, the following processing is performed.
           If `< date`, search below the specified date.
           If `> date`, search for dates after the specified date.
           If `<>` is not included,
               the search will be made before the specified date and after the specified date.
        3. If the search keyword is not a date, do the following:
           If a character corresponding to a null character is specified,
               it is converted to a null character.
           Create a 'match' query with the conversion results.
           If the conversion result is not empty, create a 'regexp' query.
           If the conversion result is an empty string, search for data
               with an empty attribute value
        4. After the above process, create a 'nested' query and return it.

        Args:
            hint (dict[str, str]): Dictionary of attribute names and search keywords to be processed
            keyword (str): String to search for
                String of the smallest unit in which search keyword is separated by `AND` and `OR`
            or_match (bool): Flag to determine whether the simple search or
                advanced search is called

        Returns:
            dict[str, str]: Created attribute filter

        """
        cond_attr = []
        cond_attr.append({
            'term': {'attr.name': hint['name']}
        })

        date_results = kls._is_date(keyword)
        if date_results:
            date_cond = {
                'range': {
                    'attr.date_value': {
                        'format': 'yyyy-MM-dd'
                    }
                },
            }
            for (range_check, date_obj) in date_results:
                timestr = date_obj.strftime('%Y-%m-%d')
                if range_check == '<':
                    # search of before date user specified
                    date_cond['range']['attr.date_value']['lt'] = timestr

                elif range_check == '>':
                    # search of after date user specified
                    date_cond['range']['attr.date_value']['gt'] = timestr

                else:
                    # search of exact day
                    date_cond['range']['attr.date_value']['gte'] = timestr
                    date_cond['range']['attr.date_value']['lte'] = timestr

            cond_attr.append(date_cond)

        else:
            hint_kyeword_val = kls._get_hint_keyword_val(keyword)
            cond_val = [{'match': {'attr.value': hint_kyeword_val}}]

            if hint_kyeword_val:
                if 'exact_match' not in hint:
                    cond_val.append({
                        'regexp': {
                            'attr.value': kls._get_regex_pattern(hint_kyeword_val)
                        }
                    })

                cond_attr.append({'bool' : {'should': cond_val}})

            else:
                cond_val_tmp = [{'bool': {'must_not': {'exists': {'field': 'attr.date_value'}}}}]
                cond_val_tmp.append({'bool' : {'should': cond_val}})
                cond_attr.append({'bool' : {'must': cond_val_tmp}})

        adding_cond = {
            'nested': {
                'path': 'attr',
                'query': {
                    'bool': {}
                }
            }
        }
        adding_cond['nested']['query']['bool']['filter'] = cond_attr

        return adding_cond

    def _execute_query(query):
        """Run a search query.

        Args:
            query (dict[str, str]): Search query

        Raises:
            Exception: If query execution fails, output error details.

        Returns:
            dict[str, str]: Search execution result

        """
        try:
            res = ESS().search(body=query, ignore=[404], sort=['name.keyword:asc'])
        except Exception as e:
            raise(e)

        return res

    def _make_search_results(user, results, res, hint_attrs, limit, hint_referral):
        """Acquires and returns the attribute values held by each search result

        When the condition of reference entry is specified, the entry to reference is acquired.
        Also, get the attribute name and attribute value that matched the condition.

        Do the following:
        1. Keep a list of IDs of all entries that have been found in Elasticsearch.
        2. If the reference entry filtering conditions have been entered,
           the following processing is performed.
           If not entered, get entry object from search result of Elasticsearch.

           2-1. If blank characters are entered in the filtering condition of the reference entry,
                only entries that are not referenced by other entries are filtered.
           2-2. In cases other than the above, only entries whose filtering condition is
                included in the entry name being referred to are acquired.
           2-3. Get the entry object from the entry ID obtained above.

        3. Get attributes for each entry for the maximum number of displayed items
           from the Elasticsearch search results.
        4. For the attribute of the acquired entry,
           the attribute value is acquired according to the attribute type.
        5. When all entries have been processed, the search results are returned.

        Args:
            user (:obj:`str`, optional): User who executed the process
            results (dict[str, str]): Variable for final search result storage
            res (`str`, optional): Search results for Elasticsearch
            hint_entity_ids (list(str)): Entity ID specified in the search condition input
            hint_attrs (list(dict[str, str])): A list of search strings and attribute sets
            limit (int): Maximum number of search results to return
            hint_referral (str): Input value used to refine the reference entry.
                Use only for advanced searches.

        Returns:
            dict[str, str]: A set of attributes and attribute values associated with the entry
                that was hit in the search

        """
        # set numbers of found entries
        results['ret_count'] = res['hits']['total']

        # get django objects from the hit information from Elasticsearch
        hit_entry_ids = [x['_id'] for x in res['hits']['hits']]
        if isinstance(hint_referral, str) and hint_referral:
            # If the hint_referral parameter is specified,
            # this filters results that only have specified referral entry.

            if (CONFIG.EMPTY_SEARCH_CHARACTER == hint_referral
                or CONFIG.EMPTY_SEARCH_CHARACTER_CODE == hint_referral):

                hit_entry_ids_num = [int(x) for x in hit_entry_ids]
                filtered_ids = set(hit_entry_ids_num) - set(AttributeValue.objects.filter(
                        Q(referral__id__in=hit_entry_ids,
                          parent_attr__is_active=True,
                          is_latest=True) |
                        Q(referral__id__in=hit_entry_ids,
                          parent_attr__is_active=True,
                          parent_attrv__is_latest=True)
                        ).values_list('referral_id', flat=True))

            else:

                filtered_ids = AttributeValue.objects.filter(
                        Q(parent_attr__parent_entry__name__iregex=hint_referral,
                          referral__id__in=hit_entry_ids,
                          is_latest=True) |
                        Q(parent_attr__parent_entry__name__iregex=hint_referral,
                          referral__id__in=hit_entry_ids,
                          parent_attrv__is_latest=True)
                        ).values_list('referral', flat=True)

            hit_entries = Entry.objects.filter(pk__in=filtered_ids, is_active=True)

            # reset matched count by filtered results by hint_referral parameter
            results['ret_count'] = len(hit_entries)
        else:
            hit_entries = Entry.objects.filter(id__in=hit_entry_ids, is_active=True)

        hit_infos = {}
        for entry in hit_entries:
            if len(hit_infos) >= limit:
                break

            hit_infos[entry] = [x['_source']['attr'] for x in res['hits']['hits'] if int(x['_id']) == entry.id][0]

        for (entry, hit_attrs) in sorted(hit_infos.items(), key=lambda x:x[0].name):
            # If 'keyword' parameter is specified and hited entry doesn't have value at the targt
            # attribute, that entry should be removed from result. This processing may be worth to
            # do before refering entry from DB for saving time of server-side processing.
            for hint in hint_attrs:
                if ('keyword' in hint and hint['keyword'] and
                    # This checks hitted entry has specified attribute
                    not [x for x in hit_attrs if x['name'] == hint['name']]):
                        continue

            ret_info = {
                'entity': {'id': entry.schema.id, 'name': entry.schema.name},
                'entry': {'id': entry.id, 'name': entry.name},
                'attrs': {},
            }

            # When 'hint_referral' parameter is specifed, return referred entries for each results
            if hint_referral != False:
                ret_info['referrals'] = [{
                    'id': x.id,
                    'name': x.name,
                    'schema': x.schema.name,
                } for x in entry.get_referred_objects()]

            # formalize attribute values according to the type
            for attrinfo in hit_attrs:
                if attrinfo['name'] in ret_info['attrs']:
                    ret_attrinfo = ret_info['attrs'][attrinfo['name']]
                else:
                    ret_attrinfo = ret_info['attrs'][attrinfo['name']] = {}

                # if target attribute is array type, then values would be stored in array
                if attrinfo['name'] not in ret_info['attrs']:
                    if attrinfo['type'] & AttrTypeValue['array']:
                        ret_info['attrs'][attrinfo['name']] = []
                    else:
                        ret_info['attrs'][attrinfo['name']] = ret_attrinfo

                ret_attrinfo['type'] = attrinfo['type']
                if (attrinfo['type'] == AttrTypeValue['string'] or
                    attrinfo['type'] == AttrTypeValue['text']):

                    if attrinfo['value']:
                        ret_attrinfo['value'] = attrinfo['value']
                    elif 'date_value' in attrinfo and attrinfo['date_value']:
                        ret_attrinfo['value'] = attrinfo['date_value'].split('T')[0]

                elif attrinfo['type'] == AttrTypeValue['boolean']:
                    ret_attrinfo['value'] = attrinfo['value']

                elif attrinfo['type'] == AttrTypeValue['date']:
                    ret_attrinfo['value'] = attrinfo['date_value']

                elif (attrinfo['type'] == AttrTypeValue['object'] or
                      attrinfo['type'] == AttrTypeValue['group']):
                    ret_attrinfo['value'] = {'id': attrinfo['referral_id'], 'name': attrinfo['value']}

                elif (attrinfo['type'] == AttrTypeValue['named_object']):
                    ret_attrinfo['value'] = {
                            attrinfo['key']: {'id': attrinfo['referral_id'], 'name': attrinfo['value']}
                    }

                elif attrinfo['type'] & AttrTypeValue['array']:
                    if 'value' not in ret_attrinfo:
                        ret_attrinfo['value'] = []

                    if attrinfo['type'] == AttrTypeValue['array_string']:
                        if 'date_value' in attrinfo:
                            ret_attrinfo['value'].append(attrinfo['date_value'].split('T')[0])
                        else:
                            ret_attrinfo['value'].append(attrinfo['value'])

                    elif attrinfo['type'] == AttrTypeValue['array_object']:
                        ret_attrinfo['value'].append({
                            'id': attrinfo['referral_id'],
                            'name': attrinfo['value']
                        })

                    elif attrinfo['type'] == AttrTypeValue['array_named_object']:
                        ret_attrinfo['value'].append({
                            attrinfo['key']: {'id': attrinfo['referral_id'], 'name': attrinfo['value']}
                        })

            results['ret_values'].append(ret_info)

        return results

    @classmethod
    def get_all_es_docs(kls):
        return ESS().search(body={'query': {'match_all': {}}}, ignore=[404])

    @classmethod
    def _is_date_check(kls, value):
        try:
            for delimiter in ['-', '/']:
                date_format = '%%Y%(del)s%%m%(del)s%%d' % {'del': delimiter}

                if re.match(r'^[<>]?[0-9]{4}%(del)s[0-9]+%(del)s[0-9]+' % {'del': delimiter}, value):

                    if value[0] in ['<', '>']:
                        return (value[0],
                                datetime.strptime(value[1:].split(' ')[0], date_format))
                    else:
                        return ('', datetime.strptime(value.split(' ')[0], date_format))

        except ValueError:
            # When datetime.strptie raised ValueError, it means value parameter maches date
            # format but they are not date value. In this case, we should deal it with a
            # string value.
            return None

        return None

    @classmethod
    def _is_date(kls, value):
        # checks all specified value is date format
        result = [kls._is_date_check(x) for x in value.split(' ') if x]

        # If result is not empty and all value is date, this returns the result
        return result if result and all(result) else None

    @classmethod
    def is_importable_data(kls, data):
        """This method confirms import data has following data structure
        Entity:
            - name: entry_name
            - attrs:
                attr_name1: attr_value
                attr_name2: attr_value
                ...
        """
        if not isinstance(data, dict):
            return False

        if not all([isinstance(x, list) for x in data.values()]):
            return False

        for entry_data in sum(data.values(), []):
            if not isinstance(entry_data, dict):
                return False

            if not ('attrs' in entry_data and 'name' in entry_data):
                return False

            if not isinstance(entry_data['name'], str):
                return False

            if not isinstance(entry_data['attrs'], dict):
                return False

        return True
