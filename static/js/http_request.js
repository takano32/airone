// This sends HTTP POST request and reloads page
HttpPost = function(form_elem, add_data) {
  // parse form data to JSON object
  var sending_data = parseJson(form_elem.serializeArray());  

  // merge additional object to the form data if needed
  if(add_data != undefined && typeof add_data == 'object') {
    sending_data = Object.assign(sending_data, add_data);
  }

  $.ajax({
    url:           form_elem.attr('url'),
    type:          'post',
    dataType:      'json',
    contentType:   'application/x-www-form-urlencoded;charset=utf-8',
    scriptCharset: 'utf-8',
    headers: {
      'X-CSRFToken': $('input[name=csrfmiddlewaretoken]').val(),
    },
    data:          JSON.stringify(sending_data)
  }).always(function(data){
    location.reload();
  });
}

var parseJson = function(data) {
  var returnJson = {};
  for (idx = 0; idx < data.length; idx++) {
    returnJson[data[idx].name] = data[idx].value
  }
  return returnJson;
}
