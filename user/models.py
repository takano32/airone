from django.db import models
from django.contrib.auth.models import User as DjangoUser
from airone.lib.acl import ACLType, ACLTypeBase


class User(DjangoUser):
    authorized_type = models.IntegerField(default=0)

    # to make a polymorphism between the Group model
    @property
    def permissions(self):
        return self.user_permissions

    def has_permission(self, target_obj, permission_level):
        # A bypass processing to rapidly return.
        # This condition is effective when the public objects are majority.
        if target_obj.is_public:
            return True

        # This try-catch syntax is needed because the 'issubclass' may occur a
        # TypeError exception when permission_level is not object.
        try:
            if not issubclass(permission_level, ACLTypeBase):
                return False
        except TypeError:
            return False

        # Checks that the default permission permits to access, or not
        if permission_level <= target_obj.default_permission:
            return True

        if not hasattr(target_obj, permission_level.name):
            return False

        perm = getattr(target_obj, permission_level.name)
        if (target_obj.is_public or
            # checks that current uesr is created this document
            target_obj.created_user == self or
            # checks user permission
            any([perm <= x for x in self.permissions.all() if target_obj.id == x.get_objid()]) or
            # checks group permission
            sum([[perm <= x for x in g.permissions.all() if target_obj.id == x.get_objid()]
                for g in self.groups.all()], [])):
            return True
        else:
            return False

    def get_acls(self, aclobj):
        return self.permissions.filter(codename__regex=(r'^%d\.' % aclobj.id))

    def set_active(self, is_active=True):
        self.is_active = is_active
