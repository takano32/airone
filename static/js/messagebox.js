
// namespace
var MessageBox = MessageBox || {
  ERROR: 0,
  WARN: 1,
  INFO: 2,
  SUCCESS: 3,

  SEVERITY_TEXT: ["error", "warn", "info", "success"],
  CSS_STYLE: ["alert-danger", "alert-warning", "alert-info", "alert-success"]
};

MessageBox.error = function(text) {
  MessageBox._showMessage(text, MessageBox.CSS_STYLE[MessageBox.ERROR]);
};

MessageBox.warn = function(text) {
  MessageBox._showMessage(text, MessageBox.CSS_STYLE[MessageBox.WARN]);
};

MessageBox.info = function(text) {
  MessageBox._showMessage(text, MessageBox.CSS_STYLE[MessageBox.INFO]);
};

MessageBox.success = function(text) {
  MessageBox._showMessage(text, MessageBox.CSS_STYLE[MessageBox.SUCCESS]);
};

MessageBox.registerReadyFunction = function() {
  $(".airone-messagebox").ready(function() {
    if($.cookie("airone-message-code")) {
      code = $.cookie("airone-message-code");
      text = $.cookie("airone-message-text");
      
      $.removeCookie("airone-message-code");
      $.removeCookie("airone-message-text");

      switch(Number(code)) {
      case MessageBox.ERROR:
        MessageBox.error(text);
        break;
      case MessageBox.WARN:
        MessageBox.warn(text);
        break;
      case MessageBox.INFO:
        MessageBox.info(text);
        break;
      case MessageBox.SUCCESS:
        MessageBox.success(text);
        break;
      }
    }
  });
};
MessageBox.registerReadyFunction();

MessageBox.setNextOnLoadMessage = function(code, text){
  $.cookie("airone-message-code", code.toString());
  $.cookie("airone-message-text", text);
};

MessageBox._showMessage = function(text, style) {
  var content = '<div class="alert alert-dismissible ' + style + ' fade show in" role="alert">'+
    '<button type="button" class="close" data-dismiss="alert" aria-label="close">' +
      '<span aria-hidden="true">&times;</span>' +
    '</button>' + text + '</div>';
  $(".airone-messagebox").append(content);
  $(".alert").alert();
};

