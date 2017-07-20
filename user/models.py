from django.db import models
from django.contrib.auth.models import User as DjangoUser


class User(DjangoUser):
    authorized_type = models.IntegerField(default=0)

    # to make a polymorphism between the Group model
    @property
    def permissions(self):
        return self.user_permissions

    def has_permission(self, target_obj, permission_level):
        if not hasattr(target_obj, permission_level):
            return False

        perm = getattr(target_obj, permission_level)
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
