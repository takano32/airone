import atexit

from django.conf import settings
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
        prof.check("Total time of the request: %s" % args[0].path)

        return ret

    return wrapper
