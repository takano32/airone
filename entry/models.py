from copy import deepcopy
from datetime import datetime

from django.db import models
from django.db.models import Q
from django.core.cache import cache

from entity.models import EntityAttr, Entity
from user.models import User
from group.models import Group

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
    boolean = models.BooleanField(default=False)

    # The reason why the 'data_type' parameter is also needed in addition to the Attribute is that
    # the value of 'type' in Attribute may be changed dynamically.
    #
    # If that value is changed after making AttributeValue, we can't know the old type of Attribute.
    # So it's necessary to save the value of AttrTypeVelue for each AttributeValue instance.
    # And this value is constract, this parameter will never be changed after creating.
    data_type = models.IntegerField(default=0)

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

    def reconstruct_referral_cache(self):
        """
        This method reconstruct the referral cache for each entries that this object refers to.
        The 'get_referred_objects' method of Entry caches the result, so this calls it in advance
        to be fast the next view showing.
        """
        if int(self.parent_attr.schema.type) & AttrTypeValue['object']:
            referrals = [Entry.objects.get(id=self.referral.id)] if self.referral else []
            if int(self.parent_attr.schema.type) & AttrTypeValue['array']:
                # Wrapping with 'set' is needed to avoid unnecessary processing
                # when mulitple attrvs which refer to same entries are existed
                referrals = set([Entry.objects.get(id=x.referral.id) for x in self.data_array.all() if x.referral])

            for referral in referrals:
                referral.get_referred_objects(use_cache=False)

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
                                  status=kls.STATUS_LATEST,
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

        elif self.schema.type == AttrTypeValue['boolean']:
            return last_value.boolean != recv_value

        elif self.schema.type == AttrTypeValue['group']:
            return last_value.value != recv_value

        elif self.schema.type == AttrTypeValue['named_object']:
            if last_value.value != recv_value['name']:
                return True

            if not last_value.referral and recv_value['id']:
                return True

            if (last_value.referral and recv_value['id'] and
                last_value.referral.id != int(recv_value['id'])):
                return True

        elif self.schema.type == AttrTypeValue['array_named_object']:
            current_refs = [x.referral.id for x in last_value.data_array.all() if x.referral]
            if sorted(current_refs) != sorted([int(x['id']) for x in recv_value if 'id' in x]):
                return True

            current_keys = [x.value for x in last_value.data_array.all() if x.value]
            if sorted(current_keys) != sorted([x['name'] for x in recv_value if 'name' in x]):
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
            'where_extra': ['status & %s > 0' % AttributeValue.STATUS_LATEST],
        }
        return self.get_values(**params)

    def get_latest_value(self):
        return self.get_values().last()

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
                return all([x for x in value if isinstance(x, str) or x is None])

            if(self.schema.type & AttrTypeValue['string'] or self.schema.type & AttrTypeValue['text']):
                return all([x for x in value if isinstance(x, str)])

        if(self.schema.type & AttrTypeValue['named']):
            return isinstance(value, dict)

        if(self.schema.type & AttrTypeValue['string'] or self.schema.type & AttrTypeValue['text']):
            return isinstance(value, str)

        if(self.schema.type & AttrTypeValue['object']):
            return isinstance(value, str) or value is None

        if(self.schema.type & AttrTypeValue['boolean']):
            return isinstance(value, bool)

        if(self.schema.type & AttrTypeValue['group']):
            return isinstance(value, str) and Group.objects.filter(id=int(value)).count()

        return False

    def add_value(self, user, value):
        """This method make AttributeValue and set it as the latest one"""

        # checks the type of specified value is acceptable for this Attribute object
        if not self._validate_value(value):
            raise TypeError('"%s" is not acceptable [attr_type:%d]' % (str(value), self.schema.type))

        # Clear the flag that means target AttrValues are latet from the Values
        # that are already created.
        cond_latest = {
            'where': ['status & %d > 0' % AttributeValue.STATUS_LATEST],
        }
        for old_value in self.values.extra(**cond_latest):
            old_value.del_status(AttributeValue.STATUS_LATEST)

            # Sync db to update status value of AttributeValue,
            # because the referred cache reconstruct processing checks this status value.
            old_value.save()

            if self.schema.type & AttrTypeValue['array']:
                # also clear the latest flags on the values in data_array
                [x.del_status(AttributeValue.STATUS_LATEST) for x in old_value.data_array.all()]

        # Initialize AttrValue as None, because this may not created
        # according to the specified parameters.
        attr_value = None

        # set attribute value according to the attribute-type
        if (self.schema.type == AttrTypeValue['string'] or
            self.schema.type == AttrTypeValue['text'] or
            self.schema.type == AttrTypeValue['group']):

            attr_value = AttributeValue.create(user, self)
            attr_value.value = value

        elif self.schema.type == AttrTypeValue['object']:
            attr_value = AttributeValue.create(user, self)
            # set None if the referral entry is not specified
            if value and Entry.objects.filter(id=value).count():
                attr_value.referral = Entry.objects.get(id=value)
            else:
                attr_value.referral = None

        elif self.schema.type == AttrTypeValue['boolean']:
            attr_value = AttributeValue.create(user, self)
            attr_value.boolean = value

        elif (self.schema.type == AttrTypeValue['named_object'] and
              ('id' in value and value['id'] or 'name' in value and value['name'])):

            attr_value = AttributeValue.create(user, self)
            attr_value.value = value['name']

            if value['id'] and Entry.objects.filter(id=value['id']).count():
                attr_value.referral = Entry.objects.get(id=value['id'])
            else:
                attr_value.referral = None

        elif self.schema.type & AttrTypeValue['array']:
            attr_value = AttributeValue.create(user, self)
            # set status of parent data_array
            attr_value.set_status(AttributeValue.STATUS_DATA_ARRAY_PARENT)

            # create and append updated values
            if self.schema.type == AttrTypeValue['array_string']:
                [attr_value.data_array.add(AttributeValue.create(user, self, value=v)) for v in value]

            elif self.schema.type == AttrTypeValue['array_object']:
                [attr_value.data_array.add(AttributeValue.create(user, self, referral=Entry.objects.get(id=v)))
                        for v in value]

            elif self.schema.type == AttrTypeValue['array_named_object']:
                for data in value:
                    referral = None
                    if 'id' in data and Entry.objects.filter(id=data['id']).count():
                        referral = Entry.objects.get(id=data['id'])

                    attr_value.data_array.add(AttributeValue.create(**{
                        'user': user,
                        'attr': self,
                        'value': data['name'] if 'name' in data else '',
                        'referral': referral,
                    }))

        if attr_value:
            attr_value.save()

            # append new AttributeValue
            self.values.add(attr_value)

        return attr_value

class Entry(ACLBase):
    # This flag is set just after created or edited, then cleared at completion of the processing
    STATUS_CREATING = 1 << 0
    STATUS_EDITING = 1 << 1

    # constract of cache key for referred entry
    CACHE_REFERRED_ENTRY = 'cache_referred_entry'

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

        # inherits acl parameters
        attr.inherit_acl(base)

        self.attrs.add(attr)
        return attr

    def get_referred_objects(self, max_count=None, use_cache=False):
        """
        This returns objects that refer current Entry in the AttributeValue
        """
        referred_entries = []
        total_count = 0
        cond = {
            'where': [
                'status & %d > 0' % AttributeValue.STATUS_LATEST,
                'status & %d = 0' % AttributeValue.STATUS_DATA_ARRAY_PARENT,
            ],
        }

        cached_value = self.get_cache(self.CACHE_REFERRED_ENTRY)
        if use_cache and cached_value:
            return cached_value

        for attrvalue in AttributeValue.objects.filter(referral=self).extra(**cond):
            if (not attrvalue.parent_attr.is_active or
                not attrvalue.parent_attr.parent_entry.is_active):
                continue

            # update total count of referred values
            total_count += 1

            referred_obj = attrvalue.parent_attr.parent_entry
            if not (referred_obj not in referred_entries and referred_obj != self):
                continue

            if not max_count or len(referred_entries) < max_count:
                referred_entries.append(referred_obj)

        # set to cache
        self.set_cache(self.CACHE_REFERRED_ENTRY, (referred_entries, total_count))

        return (referred_entries, total_count)

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

                elif last_value.data_type == AttrTypeObj and last_value.referral:
                    attrinfo['last_referral'] = last_value.referral

                elif last_value.data_type == AttrTypeArrStr:
                    # this dict-key 'last_value' is uniformed with all array types
                    attrinfo['last_value'] = [x.value for x in last_value.data_array.all()]

                elif last_value.data_type == AttrTypeArrObj:
                    attrinfo['last_value'] = [x.referral for x in last_value.data_array.all()]

                elif last_value.data_type == AttrTypeValue['boolean']:
                    attrinfo['last_value'] = last_value.boolean

                elif last_value.data_type == AttrTypeValue['named_object']:
                    attrinfo['last_value'] = last_value.value
                    attrinfo['last_referral'] = last_value.referral

                elif last_value.data_type == AttrTypeValue['array_named_object']:
                    values = [x.value for x in last_value.data_array.all()]
                    referrals = [x.referral for x in last_value.data_array.all()]

                    attrinfo['last_value'] = sorted([{
                        'value': v,
                        'referral': r
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
            referred_ids = set()

            # before deleting attirubte, pick up referred entries to reconstruct referred cache
            if attr.schema.type & AttrTypeValue['object']:

                attrs = Attribute.objects.filter(schema=attr.schema.id, is_active=True)
                for attrv in sum([list(a.get_latest_values()) for a in attrs], []):
                    if attr.schema.type & AttrTypeValue['array']:
                        [referred_ids.add(x.referral.id) for x in attrv.data_array.all()]
                    else:
                        referred_ids.add(attrv.referral.id)

            # delete Attribute object
            attr.delete()

            # reset referred_entries cache
            for entry in [Entry.objects.get(id=x) for x in referred_ids]:
                entry.get_referred_objects(use_cache=False)

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
            **extra_params,
        }
        cloned_entry = Entry.objects.create(**params)

        for attr in self.attrs.filter(is_active=True):
            cloned_entry.attrs.add(attr.clone(user, parent_entry=cloned_entry))

        return cloned_entry
