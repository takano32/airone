var toggle_referral = function() {
  if($(this).val() & ATTR_TYPE.object || $(this).val() & ATTR_TYPE.named_object) {
    for(cls_name of ['attr_referral', 'list-group', 'narrow_down_referral']) {
      $(this).parent().parent().parent().find(`.${cls_name}`).show();
    }
  } else {
    for(cls_name of ['attr_referral', 'list-group', 'narrow_down_referral']) {
      $(this).parent().parent().parent().find(`.${cls_name}`).hide();
    }
  }
}

// This function update index of row for sorting them
var update_row_index = function() {
  $('#sortdata').find(".attr:not([deleted='true'])").each(function(index) {
    $(this).find('.row_index').val(index + 1);
  });
}

var del_attr = function() {
  var parent = $(this).parents(".attr");
  if(parent.attr('attr_id')) {
    parent.attr('deleted', true);
    parent.hide();
  } else {
    parent.remove();
  }

  // Re-sort row indexes
  update_row_index();
}

var validate_form = function() {
  var ok = true;

  // check if entity name is not empty
  var name_elem = $('input[name="name"]')
  ok = ok & check_not_empty(name_elem);

  // check attrs
  var attr_elems = $('tbody[name="attributes"]').find('tr.attr')
  attr_elems.map(function(index, dom) {
    var elem = $(dom);
    
    // check if attr name is not empty
    var attr_name_elem = elem.find('.attr_name');
    ok = ok & check_not_empty(attr_name_elem);

    // check if entry ref attr is specified for entry type
    var attr_type_elem = elem.find('.attr_type');
    if(ATTR_TYPE.object & attr_type_elem.val()) {
      var attr_referral_elem = elem.find('.attr_referral');
      var td_elem = attr_type_elem.parent().parent().parent();
      if(attr_referral_elem.val().length == 0) {
        td_elem.addClass('table-danger');
        ok = false;
      } else {
        td_elem.removeClass('table-danger');
      }
    }
  });
  return ok;
}

var check_not_empty = function(elem) {
  if(elem.val() == "") {
    elem.parent().addClass("table-danger");
    return false;
  }

  elem.parent().removeClass("table-danger");
  return true;
}

$('form').submit(function(event){
  if(!validate_form()) {
    MessageBox.error("Some parameters are required to input");
    return false;
  }
  
  var post_data = {
    'attrs': $('.attr').map(function(index, elem){
      var ret = {
        'name': $(this).find('.attr_name').val(),
        'type': $(this).find('.attr_type').val(),
        'is_mandatory': $(this).find('.is_mandatory:checked').val() != undefined ? true : false,
        'ref_ids': $(this).find('.attr_referral').val(),
        'row_index': $(this).find('.row_index').val(),
      };
      if($(this).attr('attr_id')) {
        ret['id'] = $(this).attr('attr_id');
        if($(this).attr('deleted')) {
          ret['deleted'] = true;
        }
      }
      return ret;
    }).get(),
    'is_toplevel': $('input[name=is_toplevel]').is(':checked')
  };

  HttpPost($(this), post_data).done(function(data) {
    // set successful message to the updated page
    MessageBox.setNextOnLoadMessage(MessageBox.SUCCESS, data.msg);

    // redirect to the entity list page
    location.href = `/entry/${ data.entity_id }`;
  }).fail(function(data) {
    MessageBox.error(data.responseText);
  });

  return false;
});
$('.attr_type').change(toggle_referral);

var table_column = $('[name=attr_template]').html();
var append_attr_column = function() {
  var new_column = $('<tr class="attr" />');

  new_column.append($.parseHTML(table_column));
  new_column.find('.attr_type').on('change', toggle_referral);
  new_column.find('.narrow_down_referral').on(narrow_down_handler);
  new_column.find('button[name=del_attr]').on('click', del_attr);
  new_column.find(".attr_referral").on('change', update_selected_referral);

  $('[name=attributes]').append(new_column);

  // Re-sort row indexes
  update_row_index();
}


var bind_del_attr = function(column) {
  $("button[name=del_attr]").on('click', function() {
    var parent = $(this).parents(".attr");
    if(parent.attr('attr_id')) {
      parent.attr('deleted', true);
      parent.hide();
    } else {
      parent.remove();
    }

    // Re-sort row indexes
    update_row_index();
  });
};

var update_option = function(select_elem) {
  var input_str = $(select_elem).val();
  $(select_elem).parent().parent().find('select option').each(function(i, elem) {
    if($(elem).val() != 0) {
      if(($(elem).text().toLowerCase().indexOf(input_str) >= 0) ||
         ($(elem).text().toUpperCase().indexOf(input_str) >= 0)) {
        $(elem).show();
      } else {
        $(elem).hide();
      }
    }
  });
}
var enable_key_handling = true;
var narrow_down_handler = {
  "compositionstart": function() {
    enable_key_handling = false;
  },
  "compositionend": function() {
    enable_key_handling = true;

    update_option(this);
  },
  "keyup": function(e) {
    var inp = String.fromCharCode(e.keyCode);
    var is_BS = (e.keyCode == 8);

    if (!(!enable_key_handling || !(/[a-zA-Z0-9-_ ]/.test(inp) || is_BS))) {
      update_option(this);
    }
  }
}

var update_selected_referral = function() {
  var list_group = $(this).parent().find('ul');
  list_group.empty();

  $(this).find('option:selected').each(function(e) {
    new_elem = $("<li class='list-group-item list-group-item-info' style='height: 30px; padding: 5px 15px;' />");
    new_elem.text($(this).text());

    list_group.append(new_elem);
  });
}

$(document).ready(function() {
  $('#sortdata').sortable();

  $('#sortdata').on('sortstop', update_row_index);
  $("button[name=del_attr]").on('click', del_attr);
  $(".narrow_down_referral").on(narrow_down_handler);
  $(".attr_referral").on('change', update_selected_referral);

  $('button[name=add_attr]').on('click', function() {
    append_attr_column();
    return false;
  });
});
