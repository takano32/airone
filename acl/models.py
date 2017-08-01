import importlib
import tablib

from django.db import models
from django.db.models.signals import post_save
from django.db.models.signals import pre_save
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth.models import Permission
from django.dispatch import receiver

from user.models import User

from airone.lib.acl import ACLType, ACLObjType


# Add comparison operations to the Permission model
def _get_acltype(permission):
    if not any([permission.name == x.name for x in ACLType.all()]):
        return 0
    return int(permission.codename.split('.')[-1])
def _get_objid(permission):
    if not any([permission.name == x.name for x in ACLType.all()]):
        return 0
    return int(permission.codename.split('.')[0])

Permission.get_aclid = lambda self: _get_acltype(self)
Permission.get_objid = lambda self: _get_objid(self)
Permission.__le__ = lambda self, comp: _get_acltype(self) <= _get_acltype(comp)
Permission.__ge__ = lambda self, comp: _get_acltype(self) >= _get_acltype(comp)

class ACLBase(models.Model):
    name = models.CharField(max_length=200)
    is_public = models.BooleanField(default=True)
    created_user = models.ForeignKey(User)
    is_active = models.BooleanField(default=True)

    # This fields describes the sub-class of this object
    objtype = models.IntegerField(default=0)

    def save(self, *args, **kwargs):
        super(ACLBase, self).save(*args, **kwargs)

        # create Permission sets for this object at once
        content_type = ContentType.objects.get_for_model(self)
        for acltype in ACLType.availables():
            codename = '%s.%s' % (self.id, acltype.id)
            if not Permission.objects.filter(codename=codename).count():
                Permission(name=acltype.name, codename=codename, content_type=content_type).save()

    def delete(self, *args, **kwargs):
        for acltype in ACLType.availables():
            Permission.objects.filter(codename__regex=r'%d\.' % self.id).delete()

        super(ACLBase, self).delete(*args, **kwargs)

    @property
    def readable(self):
        return self._get_permission(ACLType.Readable.id)

    @property
    def writable(self):
        return self._get_permission(ACLType.Writable.id)

    @property
    def full(self):
        return self._get_permission(ACLType.Full.id)

    def _get_permission(self, acltype):
        return Permission.objects.get(codename="%s.%s" % (self.id, acltype))

    def get_subclass_object(self):
        # Use importlib to prevent circular import
        if self.objtype == ACLObjType.Entity:
            model = importlib.import_module('entity.models').Entity
        elif self.objtype == ACLObjType.AttrBase:
            model = importlib.import_module('entity.models').AttributeBase
        elif self.objtype == ACLObjType.Entry:
            model = importlib.import_module('entry.models').Entry
        elif self.objtype == ACLObjType.Attr:
            model = importlib.import_module('entry.models').Attribute
        else:
            # set ACLBase model
            model = type(self)

        return model.objects.get(id=self.id)

    def is_same_object(self, comp):
        return all([self[x] == comp[x] for x in self._IMPORT_INFO['header']])
