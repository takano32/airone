// Confirm deletion of data
function confirm_delete( form_data ) {
  if (window.confirm(CHECK_PHRASE)) {
      HttpPost(form_data, {});
  }
}
