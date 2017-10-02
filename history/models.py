import logging

from django.db import models

from entity.models import Entity
from acl.models import ACLBase
from user.models import User

# Get an instance of a logger
Logger = logging.getLogger(__name__)


class History(models.Model):
    OP_ADD_ENTITY = 1
    OP_DEL_ENTITY = 2
    OP_MOD_ENTITY = 3

    target_obj = models.ForeignKey(ACLBase, related_name='referred_target_obj')
    related_obj = models.ForeignKey(ACLBase, null=True, related_name='referred_related_obj')
    time = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(User)
    operation = models.IntegerField(default=0)
    detail = models.CharField(max_length=200)

    @classmethod
    def add_entity(kls, target, user, detail=''):
        if isinstance(target, Entity):
            if not detail:
                detail = 'エンティティ %s を作成' % target.name
    
            return kls.objects.create(target_obj=target,
                                      user=user,
                                      operation=kls.OP_ADD_ENTITY,
                                      detail=detail)
        else:
            Logger.error('[TYPE_ERROR] Specified object "%s" is not Entity [%s]' % \
                    (str(target), target.__class__.__name__))

    @classmethod
    def del_entity(kls, target, user, detail=''):
        if isinstance(target, Entity):
            if not detail:
                detail = 'エンティティ %s を削除' % target.name
    
            return kls.objects.create(target_obj=target,
                                      user=user,
                                      operation=kls.OP_DEL_ENTITY,
                                      detail=detail)
        else:
            Logger.error('[TYPE_ERROR] Specified object "%s" is not Entity [%s]' % \
                    (str(target), target.__class__.__name__))

    @classmethod
    def mod_entity(kls, target, user, detail=''):
        if isinstance(target, Entity):
            if not detail:
                detail = 'エンティティ %s を変更' % target.name
    
            return kls.objects.create(target_obj=target,
                                      user=user,
                                      operation=kls.OP_MOD_ENTITY,
                                      detail=detail)
        else:
            Logger.error('[TYPE_ERROR] Specified object "%s" is not Entity [%s]' % \
                    (str(target), target.__class__.__name__))

