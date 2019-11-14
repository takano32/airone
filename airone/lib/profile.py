from django.conf import settings
from django.http.request import HttpRequest
from time import time


class SimpleProfiler(object):
    def __init__(self):
        self.start_time = time()

    def check(self, msg=''):
        if self._is_enable():
            print('[Profiling result] (%f) %s' % (time() - self.start_time, msg))

    def _is_enable(self):
        if (hasattr(settings, 'AIRONE') and
                'ENABLE_PROFILE' in settings.AIRONE and
                settings.AIRONE['ENABLE_PROFILE']):
            return True

        return False


def airone_profile(func):
    def wrapper(*args, **kwargs):
        # reset Profiling status
        prof = SimpleProfiler()

        ret = func(*args, **kwargs)

        # show the profiling results
        req = None
        if isinstance(args[0], HttpRequest):
            req = args[0]
        elif isinstance(args[1], HttpRequest):
            # The case of decorating API handler, the HttpRequest object will be stored at
            # the second argument because an APIView object will be set at the first argument.
            req = args[1]

        if req:
            prof.check("(user-id: %s) Total time of the request: %s" % (req.user.id, req.path))
        else:
            prof.check("Total time of the request")

        return ret

    return wrapper
