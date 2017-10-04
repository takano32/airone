import atexit

from profilehooks import profile
from profilehooks import FuncProfile
from profilehooks import AVAILABLE_PROFILERS

from django.conf import settings

from time import time

class AirOneProfiler(FuncProfile):
    Profiles = []

    @classmethod
    def show_result(kls):
        if kls._is_enable():
            [p.print_stats() for p in kls.Profiles]

    @classmethod
    def reset(kls):
        kls.Profiles.clear()

    def __init__(self, *args, **kwargs):
        super(AirOneProfiler, self).__init__(*args, **kwargs)

        # unregister atexit handler
        atexit.unregister(self.atexit)

        # to show the stats during process execution
        self.Profiles.append(self)

    @classmethod
    def _is_enable(kls):
        if (hasattr(settings, 'AIRONE') and
            'ENABLE_PROFILE' in settings.AIRONE and
            settings.AIRONE['ENABLE_PROFILE']):
            return True

        return False

def airone_profile(func):
    def wrapper(*args, **kwargs):
        # reset Profiling status
        AirOneProfiler.reset()

        ret = profile(profiler=('airone_profiler'))(func)(*args, **kwargs)

        # show the profiling results
        AirOneProfiler.show_result()

        return ret

    return wrapper


AVAILABLE_PROFILERS['airone_profiler'] = AirOneProfiler
