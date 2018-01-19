// This bitmap indicates the data-type that Attribute can take.
var ATTR_TYPE = {
  object: 1 << 0,
  string: 1 << 1,
  named_object: 1 << 4,
  array: 1 << 10,
};

// This phrase is used in the confirmation popup.
var CHECK_PHRASE = '本当に削除しますか？';

// This limit is used in the file import(10M byte)
var LIMIT_FILE_SIZE = 10485760;

// This phrase is used in the import alert
var LIMIT_PHRASE = "※サイズが10Mを超えているのでUP不可※";
