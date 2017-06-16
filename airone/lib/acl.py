__all__ = ['ACLType', 'ACLObjType']

class Iteratable(object):
    def __iter__(self):
        return self._types.__iter__()

class ACLObjType(Iteratable):
    Entity = (1 << 0)
    AttrBase = (1 << 1)
    Attr = (1 << 2)
    Entry = (1 << 3)

    def __init__(self):
        self._types = [self.Entity, self.AttrBase, self.Attr]

class ACLType(Iteratable):
    Nothing = type('ACLTypeNone', (object,), {'id': (1 << 0), 'name': '権限なし'})
    Readable = type('ACLTypeReadable', (object,), {'id': (1 << 1), 'name': 'readable'})
    Writable = type('ACLTypeWritable', (object,), {'id': (1 << 2), 'name': 'writable'})
    Deletable = type('ACLTypeDeletable', (object,), {'id': (1 << 3), 'name': 'deletable'})

    @classmethod
    def all(cls):
        return [cls.Nothing, cls.Readable, cls.Writable, cls.Deletable]

    @classmethod
    def availables(cls):
        return [cls.Readable, cls.Writable, cls.Deletable]
