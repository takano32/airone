__all__ = ['ACLType', 'ACLObjType']

class Iteratable(object):
    def __iter__(self):
        return self._types.__iter__()

class ACLObjType(Iteratable):
    Entity = (1 << 0)
    EntityAttr = (1 << 1)
    Entry = (1 << 2)
    EntryAttr = (1 << 3)

    def __init__(self):
        self._types = [self.Entity, self.Entry, self.EntityAttr, self.EntryAttr]

class ACLType(Iteratable):
    Nothing = type('ACLTypeNone', (object,),
                   {'id': (1 << 0), 'name': 'nothing', 'label': 'Nothing'})
    Readable = type('ACLTypeReadable', (object,),
                    {'id': (1 << 1), 'name': 'readable','label': 'Readable'})
    Writable = type('ACLTypeWritable', (object,),
                    {'id': (1 << 2), 'name': 'writable', 'label': 'Writable'})
    Full = type('ACLTypeFull', (object,),
                {'id': (1 << 3), 'name': 'full', 'label': 'Full Controllable'})

    @classmethod
    def all(cls):
        return [cls.Nothing, cls.Readable, cls.Writable, cls.Full]

    @classmethod
    def availables(cls):
        return [cls.Readable, cls.Writable, cls.Full]

def get_permitted_objects(user, model, permission_level):
    return [x for x in model.objects.all() if user.has_permission(x, permission_level)]
