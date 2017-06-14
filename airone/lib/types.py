from six import with_metaclass

class ImplAttrType(type):
    def __eq__(cls, comp):
        if isinstance(comp, int):
            return cls.TYPE == comp
        elif isinstance(comp, str):
            return cls.NAME == comp
        elif issubclass(comp, AttrTypeBase):
            return cls.TYPE == comp.TYPE
        return False

    def __ne__(cls, comp):
        return not cls == comp

    def __repr__(cls):
        return str(cls.TYPE)

    def __int__(cls):
        return cls.TYPE

class AttrTypeObj(with_metaclass(ImplAttrType)):
    NAME = 'entry'
    TYPE = 1 << 0

class AttrTypeStr(with_metaclass(ImplAttrType)):
    NAME = 'str'
    TYPE = 1 << 1

AttrTypes = [
  AttrTypeStr,
  AttrTypeObj,
]
