var toggle_referral = function() {
  if($(this).val() & ATTR_TYPE.object) {
    $(this).parent().find('.attr_referral').show();
  } else {
    $(this).parent().find('.attr_referral').hide();
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

$('button[name=add_attr]').on('click', function() {
  append_attr_column();
  return false;
});

$('form').submit(function(){
  var attrs = $('.attr').map(function(index, elem){
    var ret = {
      'name': $(this).find('.attr_name').val(),
      'type': $(this).find('.attr_type').val(),
      'is_mandatory': $(this).find('.is_mandatory:checked').val() != undefined ? true : false,
      'ref_id': $(this).find('.attr_referral').val(),
      'row_index': $(this).find('.row_index').val(),
    };
    if($(this).attr('attr_id')) {
      ret['id'] = $(this).attr('attr_id');
      if($(this).attr('deleted')) {
        ret['deleted'] = true;
      }
    }
    return ret;
  });

  HttpPost($(this), {'attrs': attrs.get()});

  return false;
});
$('.attr_type').change(toggle_referral);

var table_column = $('[name=attr_template]').html();
var append_attr_column = function() {
  var new_column = $('<tr class="attr" />');

  new_column.append($.parseHTML(table_column));
  new_column.find('.attr_type').on('change', toggle_referral);
  new_column.find('button[name=del_attr]').on('click', del_attr);

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

$('#sortdata').sortable();

$('#sortdata').on('sortstop', update_row_index);
$("button[name=del_attr]").on('click', del_attr);
