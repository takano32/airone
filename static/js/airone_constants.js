// This bitmap indicates the data-type that Attribute can take.
var ATTR_TYPE = {
  object: 1 << 0,
  string: 1 << 1,
  array: 1 << 10,
  named_object: 1 << 11,
};

// This phrase is used in the confirmation popup.
var CHECK_PHRASE = '本当に削除しますか？';

// This limit is used in the file import(10M byte)
var LIMIT_FILE_SIZE = 10485760;

// This phrase is used in the import alert
var LIMIT_PHRASE = "※サイズが10Mを超えているのでUP不可※";


// 
var DICTIONARY = {
  ja: {
    button_communicating: '通信中...',
    button_copy: 'コピー',
    button_create: '作成',
    button_edit: '編集',
    button_save: '保存',
    button_update: '更新',
    entity_edit_desc_mandatory: 'エントリを作成・更新する際、値の入力が無い場合、作成・更新を出来無いようにします。',
    entity_edit_desc_delete_in_chain: 'エントリを削除する際、参照するエントリも削除します。',
  },
  en: { /* not implemented */ }
};

var DEFAULT_DICTIONARY = DICTIONARY['ja'];

var setlang = function(lang) {
  DEFAULT_DICTIONARY = DICTIONARY[lang];
};

var gettext = function(key, lang) {
  if(lang) {
    return DICTIONARY[lang][key];
  }else {
    return DEFAULT_DICTIONARY[key];
  }
};
