from django.db import models
from django.db.models.signals import post_save
from django.db.models.signals import pre_save
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth.models import Permission
from django.dispatch import receiver

from user.models import User

from airone.lib import ACLType


# Add comparison operations to the Permission model
def _get_acltype(permission):
    return int(permission.codename.split('.')[-1])

Permission.__le__ = lambda self, comp: _get_acltype(self) <= _get_acltype(comp)
Permission.__ge__ = lambda self, comp: _get_acltype(self) >= _get_acltype(comp)

class ACLBase(models.Model):
    name = models.CharField(max_length=200)
    is_public = models.BooleanField(default=True)
    created_user = models.ForeignKey(User)

    # This fields describes the sub-class of this object
    objtype = models.IntegerField(default=0)

    def save(self, *args, **kwargs):
        super(ACLBase, self).save(*args, **kwargs)

        # create Permission sets for this object at once
        content_type = ContentType.objects.get_for_model(self)
        for acltype in ACLType():
            codename = '%s.%s.%s' % (content_type.model, self.id, acltype.id)
            if not Permission.objects.filter(codename=codename).count():
                Permission(name=acltype.name, codename=codename, content_type=content_type).save()

    @property
    def readable(self):
        return self._get_permission(ACLType.Readable.id)

    @property
    def writable(self):
        return self._get_permission(ACLType.Writable.id)

    @property
    def deletable(self):
        return self._get_permission(ACLType.Deletable.id)

    def _get_permission(self, acltype):
        content_type = ContentType.objects.get_for_model(self)
        return Permission.objects.get(codename="%s.%s.%s" % (content_type.model, self.id, acltype))
