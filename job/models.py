import json
import pickle

from acl.models import ACLBase
from datetime import date
from entity.models import Entity, EntityAttr
from entry.models import Entry

from django.conf import settings
from django.core.cache import cache
from django.db import models
from user.models import User


def _support_time_default(o):
    if isinstance(o, date):
        return o.isoformat()
    raise TypeError(repr(o) + " is not JSON serializable")

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
    OP_IMPORT = 5
    OP_EXPORT = 6

    TARGET_UNKNOWN  = 0
    TARGET_ENTRY    = 1
    TARGET_ENTITY   = 2

    STATUS_PREPARING    = 1
    STATUS_DONE         = 2
    STATUS_ERROR        = 3
    STATUS_TIMEOUT      = 4
    STATUS_PROCESSING   = 5

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
        elif isinstance(target, Entity):
            t_type = kls.TARGET_ENTITY

        params = {
            'user': user,
            'target': target,
            'target_type': t_type,
            'status': kls.STATUS_PREPARING,
            'operation': operation,
            'text': text,
            'params': params,
        }

        return kls.objects.create(**params)

    @classmethod
    def get_job_with_params(kls, user, params):
        return kls.objects.filter(user=user, params=json.dumps(params, default=_support_time_default))

    @classmethod
    def new_create(kls, user, target, text='', params={}):
        return kls._create_new_job(user, target, kls.OP_CREATE, text, json.dumps(params, default=_support_time_default))

    @classmethod
    def new_edit(kls, user, target, text='', params={}):
        return kls._create_new_job(user, target, kls.OP_EDIT, text, json.dumps(params, default=_support_time_default))

    @classmethod
    def new_delete(kls, user, target, text='', params={}):
        return kls._create_new_job(user, target, kls.OP_DELETE, text, params)

    @classmethod
    def new_copy(kls, user, target, text='', params={}):
        return kls._create_new_job(user, target, kls.OP_COPY, text, params)

    @classmethod
    def new_import(kls, user, entity, text='', params={}):
        return kls._create_new_job(user, entity, kls.OP_IMPORT, text, json.dumps(params, default=_support_time_default))

    @classmethod
    def new_export(kls, user, target=None, text='', params={}):
        return kls._create_new_job(user, target, kls.OP_EXPORT, text, json.dumps(params, default=_support_time_default))

    def set_status(self, status):
        self.status = status
        self.save(update_fields=['status', 'updated_at'])

    def set_cache(self, value):
        with open('%s/job_%d' % (settings.AIRONE['FILE_STORE_PATH'], self.id), 'wb') as fp:
            pickle.dump(value, fp)

    def get_cache(self):
        value = ''
        with open('%s/job_%d' % (settings.AIRONE['FILE_STORE_PATH'], self.id), 'rb') as fp:
            value = pickle.load(fp)

        return value
