from django.db import models
from user.models import Member


class ACL(models.Model):
    readable = models.ManyToManyField(Member, related_name='acl_readable')
    writable = models.ManyToManyField(Member, related_name='acl_writable')
    deletable = models.ManyToManyField(Member, related_name='acl_deletable')

class ACLBaseModel(models.Model):
    acl = models.ForeignKey(ACL)

    def __init__(self, **kwargs):
        super(ACLBaseModel, self).__init__(**kwargs)

        # create a default ACL object
        acl = ACL()
        acl.save()

        # set embedded ACL object
        self.acl = acl
