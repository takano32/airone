from importlib import import_module

from django.db import models
from django.contrib.auth.models import User as DjangoUser
from airone.lib.acl import ACLType, ACLTypeBase

from rest_framework.authtoken.models import Token

from datetime import datetime


class User(DjangoUser):
    MAXIMUM_TOKEN_LIFETIME = 10 ** 8
    TOKEN_LIFETIME = 86400

    authorized_type = models.IntegerField(default=0)
    token_lifetime = models.IntegerField(default=TOKEN_LIFETIME)

    # to make a polymorphism between the Group model
    @property
    def permissions(self):
        return self.user_permissions

    @property
    def token(self):
        return Token.objects.get_or_create(user=self)[0]

    def has_permission(self, target_obj, permission_level):
        # A bypass processing to rapidly return.
        # This condition is effective when the public objects are majority.
        if target_obj.is_public or self.is_superuser:
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

        # check user permission
        if any([permission_level.id <= x.get_aclid() for x in self.permissions.all() if target_obj.id == x.get_objid()]):
            return True

        # check group permission
        if any(sum([[permission_level.id <= x.get_aclid() for x in g.permissions.all() if target_obj.id == x.get_objid()] for g in self.groups.all()], [])):
            return True

        # This means user has no permission to access target object
        return False

    def get_acls(self, aclobj):
        return self.permissions.filter(codename__regex=(r'^%d\.' % aclobj.id))

    def delete(self):
        """
        Override Model.delete method of Django
        """
        self.is_active = False
        self.username = "%s_deleted_%s" % (self.username, datetime.now().strftime("%Y%m%d_%H%M%S"))
        self.email = "deleted__%s" % (self.email)
        self.save()

    # operations for registering History
    def seth_entity_add(self, target):
        return History.register(self, target, History.ADD_ENTITY)
    def seth_entity_mod(self, target):
        return History.register(self, target, History.MOD_ENTITY)
    def seth_entity_del(self, target):
        return History.register(self, target, History.DEL_ENTITY)
    def seth_entry_del(self, target):
        return History.register(self, target, History.DEL_ENTRY)

class History(models.Model):
    """
    These constants describe operations of History and bit-map construct following
    * The last 3-bits (0000xxx)[2]: describe operation flag
      - 001 : ADD
      - 010 : MOD
      - 100 : DEL
    * The last 4-bit or later (xxxx000)[2] describe operation target
      - 001 : Entity
      - 010 : EntityAttr
      - 100 : Entry
    """
    OP_ADD = 1 << 0
    OP_MOD = 1 << 1
    OP_DEL = 1 << 2

    TARGET_ENTITY = 1 << 3
    TARGET_ATTR = 1 << 4
    TARGET_ENTRY = 1 << 5

    ADD_ENTITY  = OP_ADD + TARGET_ENTITY
    ADD_ATTR    = OP_ADD + TARGET_ATTR
    MOD_ENTITY  = OP_MOD + TARGET_ENTITY
    MOD_ATTR    = OP_MOD + TARGET_ATTR
    DEL_ENTITY  = OP_DEL + TARGET_ENTITY
    DEL_ATTR    = OP_DEL + TARGET_ATTR
    DEL_ENTRY   = OP_DEL + TARGET_ENTRY

    target_obj = models.ForeignKey(import_module('acl.models').ACLBase,
                                   related_name='referred_target_obj')
    time = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(User)
    operation = models.IntegerField(default=0)
    text = models.CharField(max_length=512)
    is_detail = models.BooleanField(default=False)

    # This parameter is needed to record related operation histories
    details = models.ManyToManyField('History')

    def add_attr(self, target, text=''):
        detail = History.register(target=target,
                                  operation=History.ADD_ATTR,
                                  user=self.user,
                                  text=text,
                                  is_detail=True)
        self.details.add(detail)

    def mod_attr(self, target, text=''):
        detail = History.register(target=target,
                                  operation=History.MOD_ATTR,
                                  user=self.user,
                                  text=text,
                                  is_detail=True)
        self.details.add(detail)

    def del_attr(self, target, text=''):
        detail = History.register(target=target,
                                  operation=History.DEL_ATTR,
                                  user=self.user,
                                  text=text,
                                  is_detail=True)
        self.details.add(detail)

    def mod_entity(self, target, text=''):
        detail = History.register(target=target,
                                  operation=History.MOD_ENTITY,
                                  user=self.user,
                                  text=text,
                                  is_detail=True)
        self.details.add(detail)

    @classmethod
    def register(kls, user, target, operation, is_detail=False, text=''):
        if kls._type_check(target, operation):
            return kls.objects.create(target_obj=target,
                                      user=user,
                                      operation=operation,
                                      text=text,
                                      is_detail=is_detail)
        else:
            raise TypeError("Couldn't register history '%s' because of invalid type" % str(target))

    @classmethod
    def _type_check(kls, target, operation):
        if ((operation & kls.TARGET_ENTITY and isinstance(target, import_module('entity.models').Entity) or
            (operation & kls.TARGET_ATTR and isinstance(target, import_module('entity.models').EntityAttr)) or
            (operation & kls.TARGET_ENTRY and isinstance(target, import_module('entry.models').Entry)))):
            return True
        else:
            return False
