__all__ = ['ACLType', 'ACLObjType']

class Iteratable(object):
    def __iter__(self):
        return self._types.__iter__()

class ACLObjType(Iteratable):
    Entity = (1 << 0)
    AttrBase = (1 << 1)
    Attr = (1 << 2)

    def __init__(self):
        self._types = [self.Entity, self.AttrBase, self.Attr]

class ACLType(Iteratable):
    Readable = type('ACLTypeReadable', (object,), {'id': (1 << 0), 'name': 'readable'})
    Writable = type('ACLTypeWritable', (object,), {'id': (1 << 1), 'name': 'writable'})
    Deletable = type('ACLTypeDeletable', (object,), {'id': (1 << 2), 'name': 'deletable'})

    def __init__(self):
        self._types = [self.Readable, self.Writable, self.Deletable]
