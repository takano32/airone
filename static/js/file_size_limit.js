// Check the limit of file size when import
var upfile = document.getElementById("upfile");
var response = document.getElementById("response");
var file_size;

if(upfile){
  upfile.addEventListener("change", function(evt){
    var str = "";
    var file = evt.target.files;
    file_size = file[0].size;

    // Inform when file size over the limit
    if( file_size >= LIMIT_FILE_SIZE ){
      str += LIMIT_PHRASE + "<br>";;
      str += "ファイル名：" + file[0].name + "<br>";
      str += "ファイルサイズ：" + file_size + "byte<br>";
      response.innerHTML    = str;
      response.style.color  = STYLE["color"];
      response.style.font   = STYLE["font"];
      response.style.width  = STYLE["width"];
      response.style.backgroundColor = STYLE["background"];
      document.send.elements[2].disabled = true;  // disable submit
    } else {
      response.innerHTML    ='';
      document.send.elements[2].disabled = false; // enable submit
    }
  },false);
}
