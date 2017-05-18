$('form').submit(function(){
  var data = parseJson($('form').serializeArray());

  // set selected values if they exist
  var elem_select = $('form').find('select');
  if (elem_select.length) {
    data[elem_select.attr('name')] = elem_select.val();
  }

  $.ajax({
    url:           $('form').attr('url'),
    type:          'post',
    dataType:      'json',
    contentType:   'application/x-www-form-urlencoded;charset=utf-8',
    scriptCharset: 'utf-8',
    headers: {
      'X-CSRFToken': $('input[name=csrfmiddlewaretoken]').val(),
    },
    data:          JSON.stringify(data)
  }).always(function(data){
    location.reload();
  });

  return false;
});

var parseJson = function(data) {
  var returnJson = {};
  for (idx = 0; idx < data.length; idx++) {
    returnJson[data[idx].name] = data[idx].value
  }
  return returnJson;
}
