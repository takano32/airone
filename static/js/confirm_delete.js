// Confirm deletion of data
function confirm_delete( form_data ) {
  if (window.confirm('本当に削除しますか？')) {
      HttpPost(form_data, {});
  }
}
