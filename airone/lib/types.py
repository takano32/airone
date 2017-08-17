from six import with_metaclass

_ATTR_OBJECT_TYPE = 1 << 0
_ATTR_STRING_TYPE = 1 << 1
_ATTR_ARRAY_TYPE = 1 << 10

class MetaAttrType(type):
    def __eq__(cls, comp):
        if isinstance(comp, int):
            return cls.TYPE == comp
        elif isinstance(comp, str):
            return cls.NAME == comp
        else:
            return cls.TYPE == comp.TYPE
        return False

    def __ne__(cls, comp):
        return not cls == comp

    def __repr__(cls):
        return str(cls.TYPE)

    def __int__(cls):
        return cls.TYPE

class AttrTypeObj(with_metaclass(MetaAttrType)):
    NAME = 'entry'
    TYPE = _ATTR_OBJECT_TYPE

class AttrTypeStr(with_metaclass(MetaAttrType)):
    NAME = 'string'
    TYPE = _ATTR_STRING_TYPE

class AttrTypeArrObj(with_metaclass(MetaAttrType)):
    NAME = 'array_entry'
    TYPE = _ATTR_OBJECT_TYPE | _ATTR_ARRAY_TYPE

class AttrTypeArrStr(with_metaclass(MetaAttrType)):
    NAME = 'array_string'
    TYPE = _ATTR_STRING_TYPE | _ATTR_ARRAY_TYPE

AttrTypes = [
    AttrTypeStr,
    AttrTypeObj,
    AttrTypeArrStr,
    AttrTypeArrObj,
]
AttrTypeValue = {
    'object': _ATTR_OBJECT_TYPE,
    'string': _ATTR_STRING_TYPE,
    'array': _ATTR_ARRAY_TYPE,
}
