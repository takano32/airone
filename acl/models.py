from django.db import models
from django.db.models.signals import post_save
from django.db.models.signals import pre_save
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth.models import Permission
from django.dispatch import receiver
from airone.lib import ACLType


class ACLBase(models.Model):
    name = models.CharField(max_length=200)
    is_public = models.BooleanField(default=True)

    # This fields describes the sub-class of this object
    objtype = models.IntegerField(default=0)

    def save(self, *args, **kwargs):
        super(ACLBase, self).save(*args, **kwargs)
        content_type = ContentType.objects.get_for_model(self)
        for acltype in ACLType():
            Permission(name=acltype.name,
                       content_type=content_type,
                       codename='%s.%s.%s' % (content_type.model, self.id, acltype.id)).save()

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
