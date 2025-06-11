let textareas = document.getElementsByTagName("textarea");

for(let i =0; i<textareas.length; i++){
    textareas[i].addEventListener('keydown', resize)
}

function resize() {
  var el = this;
  setTimeout(function() {
    el.style.cssText = 'height:auto; padding:0';
    el.style.cssText = 'height:' + el.scrollHeight + 'px';
  }, 1);
}