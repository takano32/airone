from acl.models import ACLBase
from entity.models import Entity, EntityAttr
from entry.models import Entry

from django.db import models
from user.models import User


class Job(models.Model):
    """
    This manage processing which is executed on backend.

    NOTE: This is similar to the user.models.History. That focus on
          the chaning history of Schema, while this focus on managing
          the jobs that user operated.
    """

    # Constant to describes status of each jobs
    OP_CREATE = 1
    OP_EDIT   = 2
    OP_DELETE = 3
    OP_COPY   = 4

    TARGET_UNKNOWN  = 0
    TARGET_ENTRY    = 1

    STATUS_PROCESSING   = 1
    STATUS_DONE         = 2
    STATUS_ERROR        = 3
    STATUS_TIMEOUT      = 4

    user = models.ForeignKey(User)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    target = models.ForeignKey(ACLBase, null=True)
    target_type = models.IntegerField(default=0)
    status = models.IntegerField(default=0)
    operation = models.IntegerField(default=0)

    # This parameter will be used for supplementing this job
    text = models.TextField()

    # This has serialized parameters to which user sent
    params = models.TextField()

    @classmethod
    def _create_new_job(kls, user, target, operation, text, params):
        t_type = kls.TARGET_UNKNOWN
        if isinstance(target, Entry):
            t_type = kls.TARGET_ENTRY

        params = {
            'user': user,
            'target': target,
            'target_type': t_type,
            'status': kls.STATUS_PROCESSING,
            'operation': operation,
            'text': text,
            'params': params,
        }

        return kls.objects.create(**params)

    @classmethod
    def new_create(kls, user, target, text='', params={}):
        return kls._create_new_job(user, target, kls.OP_CREATE, text, params)

    @classmethod
    def new_edit(kls, user, target, text='', params={}):
        return kls._create_new_job(user, target, kls.OP_EDIT, text, params)

    @classmethod
    def new_delete(kls, user, target, text='', params={}):
        return kls._create_new_job(user, target, kls.OP_DELETE, text, params)

    @classmethod
    def new_copy(kls, user, target, text='', params={}):
        return kls._create_new_job(user, target, kls.OP_COPY, text, params)
