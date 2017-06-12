class AttrTypeBase(object):
    def __init__(self, name, type):
        self.name = name
        self.type = type

    def __eq__(self, comp):
        return self.type == comp or self.name == comp

    def __ne__(self, comp):
        return self.type != comp or self.name != comp

class AttrTypeObj(AttrTypeBase):
    def __init__(self):
        super(AttrTypeObj, self).__init__('entry', 1 << 0)

class AttrTypeStr(AttrTypeBase):
    def __init__(self):
        super(AttrTypeStr, self).__init__('str', 1 << 1)

class AttrTypeArr(AttrTypeBase):
    def __init__(self):
        super(AttrTypeArr, self).__init__('arr', 1 << 2)

AttrTypes = [
  AttrTypeStr(),
  AttrTypeObj(),
]
