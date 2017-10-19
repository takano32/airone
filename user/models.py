from importlib import import_module

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

    # operations for registering History
    def seth_entity_add(self, target, detail=''):
        History.register(self, target, History.ADD_ENTITY, detail)
    def seth_entity_mod(self, target, detail=''):
        History.register(self, target, History.MOD_ENTITY, detail)
    def seth_entity_del(self, target, detail=''):
        History.register(self, target, History.DEL_ENTITY, detail)
    def seth_attr_add(self, target, detail=''):
        History.register(self, target, History.ADD_ATTR, detail)
    def seth_attr_mod(self, target, detail=''):
        History.register(self, target, History.MOD_ATTR, detail)
    def seth_attr_del(self, target, detail=''):
        History.register(self, target, History.DEL_ATTR, detail)
    def seth_entry_del(self, target, detail=''):
        History.register(self, target, History.DEL_ENTRY, detail)


class History(models.Model):
    """
    These constants describe operations of History and bit-map construct following
    * The last 2-bits (0000xx)[2]: describe operation flag
      - 01 : ADD
      - 10 : MOD
      - 10 : DEL
    * The last 3-bit or later (xxxx00)[2] describe operation target
      - 001 : Entity
      - 010 : EntityAttr
      - 100 : Entry
    """
    TARGET_ENTITY = 1 << 2
    TARGET_ATTR = 1 << 3
    TARGET_ENTRY = 1 << 4

    OP_ADD = 1
    OP_MOD = 2
    OP_DEL = 3

    ADD_ENTITY  = OP_ADD + TARGET_ENTITY
    ADD_ATTR    = OP_ADD + TARGET_ATTR
    MOD_ENTITY  = OP_MOD + TARGET_ENTITY
    MOD_ATTR    = OP_MOD + TARGET_ATTR
    DEL_ENTITY  = OP_DEL + TARGET_ENTITY
    DEL_ATTR    = OP_DEL + TARGET_ATTR
    DEL_ENTRY   = OP_DEL + TARGET_ENTRY

    target_obj = models.ForeignKey(import_module('acl.models').ACLBase,
                                   related_name='referred_target_obj')
    related_obj = models.ForeignKey(import_module('acl.models').ACLBase,
                                    null=True)
    time = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(User)
    operation = models.IntegerField(default=0)
    detail = models.CharField(max_length=200)

    @classmethod
    def register(kls, user, target, operation, detail=''):
        if kls._type_check(target, operation):
            return kls.objects.create(target_obj=target,
                                      user=user,
                                      operation=operation,
                                      detail=detail)
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
