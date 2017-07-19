from django.db import models
from django.contrib.auth.models import User as DjangoUser


class User(DjangoUser):
    authorized_type = models.IntegerField(default=0)

    # to make a polymorphism between the Group model
    @property
    def permissions(self):
        return self.user_permissions

    def has_permission(self, aclobj, permission_level):
        if aclobj.is_public:
            return True

        if aclobj.created_user.id == self.id:
            return True

        if not hasattr(aclobj, permission_level):
            return False

        # get permission object of required level
        permission = getattr(aclobj, permission_level)

        acl_checker = (lambda m:
            [permission <= x for x in m.permissions.filter(codename__regex=(r'^%d\.' % aclobj.id))])

        if any(acl_checker(self)):
            return True

        if any([acl_checker(g) for g in self.groups.all()]):
            return True

        return False

    def get_acls(self, aclobj):
        return self.permissions.filter(codename__regex=(r'^%d\.' % aclobj.id))

    def set_active(self, is_active=True):
        self.is_active = is_active
