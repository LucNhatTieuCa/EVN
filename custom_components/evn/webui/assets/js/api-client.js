(() => {
 'use strict';
 function hass(){for(const w of [window,window.parent,window.top]){try{const h=w.document.querySelector('home-assistant')?.hass;if(h)return h;}catch(_){}}}
 async function request(path,init={}){
  const url=new URL(path,location.origin);if(url.origin!==location.origin||!url.pathname.startsWith('/api/npc/'))throw new Error('Nguồn API EVN không hợp lệ');
  const h=hass();let response;
  if(h?.fetchWithAuth)response=await h.fetchWithAuth(url.pathname+url.search,init);
  else{let token;try{token=JSON.parse(localStorage.getItem('hassTokens')||'null')?.access_token;}catch(_){}
   if(!token)throw new Error('Mở EVN Monitor trong Home Assistant đã đăng nhập.');
   response=await fetch(url.pathname+url.search,{...init,headers:{...init.headers,Authorization:`Bearer ${token}`}});}
  return response;
 }
 window.EVNApi={fetch:request,json:async(path,init)=>{const response=await request(path,init);if(!response.ok)throw new Error('Không tải được dữ liệu EVN ('+response.status+').');return response.json();}};
})();
