/** The bookmarklet reads schema.org JobPosting JSON-LD from whichever job
 * page the user is viewing, falls back to heading/description heuristics,
 * and posts one message to this app's origin. It is served for dragging to
 * the bookmarks bar, which is why it is one long javascript: URL. */
export function bookmarkletSource(origin: string): string {
  return `(function(){
  var on='${origin}';
  function job(){
    var t='',c='',d='',u=location.href;
    var lds=document.querySelectorAll('script[type="application/ld+json"]');
    for(var i=0;i<lds.length;i++){
      try{
        var j=JSON.parse(lds[i].textContent);
        var arr=Array.isArray(j['@graph'])?j['@graph']:[j];
        for(var m=0;m<arr.length;m++){
          var g=arr[m];
          if(g['@type']==='JobPosting'){
            var org=g.hiringOrganization||{};
            return {title:String(g.title||''),company:String(org.name||''),description:String(g.description||''),url:u};
          }
        }
      }catch(e){}
    }
    var h=document.querySelector('h1');
    t=h?h.innerText.trim():document.title;
    d=document.querySelector('[class*="description" i],[id*="description" i]');
    d=d?d.innerText:document.body.innerText;
    return {title:t,company:c,description:d.slice(0,20000),url:u};
  }
  var data=job();
  var w=window.open(on+'#importing','_blank');
  if(!w){alert('TrackAJob: the import window was blocked. Allow popups for this site and try again.');return;}
  var tries=0;
  var timer=setInterval(function(){
    tries++;
    try{w.postMessage({type:'trackajob-import',job:data},on);}catch(e){}
    if(tries>=25)clearInterval(timer);
  },800);
  window.addEventListener('message',function ack(ev){
    if(ev.origin!==on)return;
    var d=ev.data||{};
    if(d.type==='trackajob-import-ack')clearInterval(timer);
  });
})();`
}

export function bookmarkletUrl(origin: string): string {
  return 'javascript:' + encodeURIComponent(bookmarkletSource(origin))
}
