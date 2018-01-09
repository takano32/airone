from six import with_metaclass

_ATTR_OBJECT_TYPE = 1 << 0
_ATTR_STRING_TYPE = 1 << 1
_ATTR_TEXT_TYPE = 1 << 2
_ATTR_BOOL_TYPE = 1 << 3
_ATTR_NAMED_OBJECT_TYPE = 1 << 4
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

# STRING-type restricts data size to AttributeValue.MAXIMUM_VALUE_LENGTH
class AttrTypeStr(with_metaclass(MetaAttrType)):
    NAME = 'string'
    TYPE = _ATTR_STRING_TYPE

class AttrTypeNamedObj(with_metaclass(MetaAttrType)):
    NAME = 'named_entry'
    TYPE = _ATTR_NAMED_OBJECT_TYPE

class AttrTypeArrObj(with_metaclass(MetaAttrType)):
    NAME = 'array_entry'
    TYPE = _ATTR_OBJECT_TYPE | _ATTR_ARRAY_TYPE

class AttrTypeArrStr(with_metaclass(MetaAttrType)):
    NAME = 'array_string'
    TYPE = _ATTR_STRING_TYPE | _ATTR_ARRAY_TYPE

class AttrTypeArrNamedObj(with_metaclass(MetaAttrType)):
    NAME = 'array_named_entry'
    TYPE = _ATTR_NAMED_OBJECT_TYPE | _ATTR_ARRAY_TYPE

class AttrTypeText(with_metaclass(MetaAttrType)):
    NAME = 'textarea'
    TYPE = _ATTR_TEXT_TYPE

class AttrTypeBoolean(with_metaclass(MetaAttrType)):
    NAME = 'boolean'
    TYPE = _ATTR_BOOL_TYPE

AttrTypes = [
    AttrTypeStr,
    AttrTypeObj,
    AttrTypeNamedObj,
    AttrTypeArrStr,
    AttrTypeArrObj,
    AttrTypeArrNamedObj,
    AttrTypeText,
    AttrTypeBoolean,
]
AttrTypeValue = {
    'object': AttrTypeObj.TYPE,
    'string': AttrTypeStr.TYPE,
    'named_object': AttrTypeNamedObj.TYPE,
    'array': _ATTR_ARRAY_TYPE,
    'array_object': AttrTypeArrObj.TYPE,
    'array_string': AttrTypeArrStr.TYPE,
    'array_named_object': AttrTypeArrNamedObj.TYPE,
    'text': AttrTypeText.TYPE,
    'boolean': AttrTypeBoolean.TYPE,
}
