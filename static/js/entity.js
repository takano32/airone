
var toggle_referral = function() {
  if($(this).val() == '1') {
    $(this).parent().find('.attr_referral').show();
  } else {
    $(this).parent().find('.attr_referral').hide();
  }
}

$('button[name=add_attr]').on('click', function() {
  append_attr_column();
  return false;
});

$('form').submit(function(){
  var attrs = $('.attr').map(function(index, elem){
    return {
      'name': $(this).find('.attr_name').val(),
      'type': $(this).find('.attr_type').val(),
      'is_mandatory': $(this).find('.is_mandatory:checked').val() != undefined ? true : false,
      'ref_id': $(this).find('.attr_referral').val(),
    };
  });

  HttpPost($(this), {'attrs': attrs.get()});

  return false;
});
$('.attr_type').change(toggle_referral);

var table_column = $('div[name=attr_template]').html();
var append_attr_column = function() {
  var new_column = $('<div class="row attr" />');

  new_column.append($.parseHTML(table_column));
  new_column.find('.attr_type').on('change', toggle_referral);

  $('div[name=attributes]').append(new_column);
}
