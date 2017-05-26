from django.http import HttpResponseRedirect
from .types import AttrTypeInt, AttrTypeStr, AttrTypeArr

AttrTypes = [
  AttrTypeInt(),
  AttrTypeStr(),
  AttrTypeArr(),
]


class HttpResponseSeeOther(HttpResponseRedirect):
    status_code = 303

class ACLObjType(object):
    Entity = (1 << 0)
    AttrBase = (1 << 1)

class ACLType(object):
    Readable = (1 << 0)
    Writable = (1 << 1)
    Deletable = (1 << 2)

    def __init__(self):
        self.acl_types = [self.Readable, self.Writable, self.Deletable]

    def __iter__(self):
        return self.acl_types.__iter__()
