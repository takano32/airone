from django.http import HttpResponseRedirect
from .types import AttrTypeInt, AttrTypeStr, AttrTypeArr

AttrTypes = [
  AttrTypeInt(),
  AttrTypeStr(),
  AttrTypeArr(),
]


class HttpResponseSeeOther(HttpResponseRedirect):
    status_code = 303
