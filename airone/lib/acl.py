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
        self._types = [self.Entity, self.Entry, self.AttrBase, self.Attr]

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

def has_object_permission(user, target_obj, permission_level):
    perm = getattr(target_obj, permission_level)

    if (target_obj.is_public or
        # checks that current uesr is created this document
        target_obj.created_user == user or
        # checks user permission
        any([perm <= x for x in user.permissions.all() if target_obj.id == x.get_objid()]) or
        # checks group permission
        sum([[perm <= x for x in g.permissions.all() if target_obj.id == x.get_objid()]
            for g in user.groups.all()], [])):
        return True
    else:
        return False

def get_permitted_objects(user, model, permission_level):
    return [x for x in model.objects.all() if has_object_permission(user, x, permission_level)]
