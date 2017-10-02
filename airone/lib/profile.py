from profilehooks import profile
from profilehooks import FuncProfile
from profilehooks import AVAILABLE_PROFILERS

class AirOneProfiler(FuncProfile):
    Profiles = []

    @classmethod
    def show_result(kls):
        for p in kls.Profiles:
            p.print_stats()

    @classmethod
    def reset(kls):
        kls.Profiles.clear()

    def __init__(self, *args, **kwargs):
        super(AirOneProfiler, self).__init__(*args, **kwargs)
        self.Profiles.append(self)

def airone_profile(func):
    def wrapper(*args, **kwargs):
        # reset Profiling status
        AirOneProfiler.reset()

        pf = profile(profiler=('airone_profiler'))(func)(*args, **kwargs)

        # show the profiling results
        AirOneProfiler.show_result()

        return pf

    return wrapper


AVAILABLE_PROFILERS['airone_profiler'] = AirOneProfiler
