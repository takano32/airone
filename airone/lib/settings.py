class Settings(object):
    def __init__(self, conf={}):
        self.conf = conf

    def __getattr__(self, key):
        return self.conf[key]
