from django.db import models
from django.db.models import Q
from django.core.cache import cache

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
    boolean = models.BooleanField(default=False)

    def set_status(self, val):
        self.status |= val
        self.save()

    def del_status(self, val):
        self.status &= ~val
        self.save()

    def get_status(self, val):
        return self.status & val

    def reconstruct_referral_cache(self):
        """
        This method reconstruct the referral cache for each entries that this object refers to.
        The 'get_referred_objects' method of Entry caches the result, so this calls it in advance
        to be fast the next view showing.
        """
        if int(self.parent_attr.schema.type) & AttrTypeValue['object']:
            referrals = [Entry.objects.get(id=self.referral.id)] if self.referral else []
            if int(self.parent_attr.schema.type) & AttrTypeValue['array']:
                referrals = [Entry.objects.get(id=x.referral.id) for x in self.data_array.all()]

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

    def get_value_history(self, user):
        # At the first time, checks the ermission to read
        if not user.has_permission(self, ACLType.Readable):
            return []

        # This helper function returns value in response to the type
        def get_attr_value(attrv):
            attr = attrv.parent_attr

            if attr.schema.type == AttrTypeValue['array_string']:
                return [x.value for x in attrv.data_array.all()]
            elif attr.schema.type == AttrTypeValue['array_object']:
                return [x.referral for x in attrv.data_array.all()]
            elif attr.schema.type == AttrTypeValue['object']:
                return attrv.referral
            elif attr.schema.type == AttrTypeValue['boolean']:
                return attrv.boolean
            else:
                return attrv.value

        return [{
            'attr_name': self.schema.name,
            'attr_type': self.schema.type,
            'attr_value': get_attr_value(attrv),
            'created_time': attrv.created_time,
            'created_user': attrv.created_user.username,
        } for attrv in self.values.all()]

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
            'where': ['status & %d > 0' % AttributeValue.STATUS_LATEST],
        }

        cached_value = self.get_cache(self.CACHE_REFERRED_ENTRY)
        if use_cache and cached_value:
            return cached_value

        for attrvalue in AttributeValue.objects.filter(referral=self).extra(**cond):
            if not attrvalue.get_status(AttributeValue.STATUS_LATEST):
                continue

            if (not attrvalue.parent_attr.is_active or
                not attrvalue.parent_attr.parent_entry.is_active):
                continue

            # update total count of referred values
            if attrvalue.get_status(AttributeValue.STATUS_DATA_ARRAY_PARENT):
                total_count += attrvalue.data_array.count()
            else:
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
                last_value = attr.values.last()

                if attr.schema.type == AttrTypeStr or attr.schema.type == AttrTypeText:
                    attrinfo['last_value'] = last_value.value
                elif attr.schema.type == AttrTypeObj and last_value.referral:
                    attrinfo['last_referral'] = last_value.referral
                elif attr.schema.type == AttrTypeArrStr:
                    attrinfo['last_value'] = [x.value for x in last_value.data_array.all()]
                elif attr.schema.type == AttrTypeArrObj:
                    attrinfo['last_value'] = [x.referral for x in last_value.data_array.all()]
                elif attr.schema.type == AttrTypeValue['boolean']:
                    attrinfo['last_value'] = last_value.boolean

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
