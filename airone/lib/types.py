class AttrTypeBase(object):
    def __init__(self, name, type):
        self.name = name
        self.type = type

class AttrTypeInt(AttrTypeBase):
    def __init__(self):
        super(AttrTypeInt, self).__init__('int', 1 << 0)

class AttrTypeStr(AttrTypeBase):
    def __init__(self):
        super(AttrTypeStr, self).__init__('str', 1 << 1)

class AttrTypeArr(AttrTypeBase):
    def __init__(self):
        super(AttrTypeArr, self).__init__('arr', 1 << 2)

AttrTypes = [
  AttrTypeStr(),
  AttrTypeInt(),
  AttrTypeArr(),
]
