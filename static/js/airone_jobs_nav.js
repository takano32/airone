$(document).ready(function() {
  var sending_request = false;

  $('.dropdown-toggle').on('click', function(e) {
    if (! sending_request) {
      sending_request = true;

      $.ajax({
        type: 'GET',
        url: `/api/v1/job/`,
      }).done(function(data){
        var container = $('.job-container');

        /* clear loading image */
        $('.job-loading').remove();

        if (data['result'].length == 0) {
          container.append(`<a class='dropdown-item job-status-nothing' href='#'>実行タスクなし</a>`);
        }

        for (var jobinfo of data['result']) {
          var operation = '';
          switch(jobinfo['operation']) {
            case data['constant']['operation']['create']:
              operation = '作成';
              break;
            case data['constant']['operation']['edit']:
              operation = '編集';
              break;
            case data['constant']['operation']['delete']:
              operation = '削除';
              break;
            case data['constant']['operation']['copy']:
              operation = 'コピー';
              break;
          }

          switch(jobinfo['status']) {
            case data['constant']['status']['processing']:
              container.append(`<li class='dropdown-item job-status-processing' href='#'>[処理中/${operation}] ${ jobinfo['target']['name'] }</li>`);
              break;
            case data['constant']['status']['done']:
              container.append(`<a class='dropdown-item job-status-done' href="/entry/show/${ jobinfo['target']['id'] }">[完了/${operation}] ${ jobinfo['target']['name'] }</a>`);
              break;
            case data['constant']['status']['error']:
              container.append(`<a class='dropdown-item job-status-error' href='#'>[エラー/${operation}] ${ jobinfo['target']['name'] }</a>`);
              break;
            case data['constant']['status']['timeout']:
              container.append(`<a class='dropdown-item job-status-timeout' href='#'>[タイムアウト/${operation}] ${ jobinfo['target']['name'] }</a>`);
              break;
          }
        }

      }).fail(function(data){
        MessageBox.error('failed to load data from server (Please reload this page or call Administrator)');
      });
    }
  });
});
