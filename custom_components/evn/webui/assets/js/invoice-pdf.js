(() => {
 'use strict';
 const el=id=>document.getElementById(id);
 let seq=0,blobURL=null,selectedAccount='',catalogRows=[],pdfTask=null,renderTask=null;
 const account=()=>el('accountSelect')?.value||'';
 async function request(path,blob=false){
  let hass;
  for(const w of [window,window.parent,window.top]){try{hass=w.document.querySelector('home-assistant')?.hass;if(hass)break;}catch(_){}}
  let response;
  if(hass?.fetchWithAuth)response=await hass.fetchWithAuth('/api/'+path);
  else if(hass?.callApiRaw)response=await hass.callApiRaw('GET',path);
  else{
   let token;try{token=JSON.parse(localStorage.getItem('hassTokens')||'null')?.access_token;}catch(_){}
   if(!token)throw new Error('Chưa lấy được phiên đăng nhập HA. Mở lại EVN Monitor trong Home Assistant.');
   response=await fetch('/api/'+path,{headers:{Authorization:'Bearer '+token}});
  }
  if(!response.ok)throw new Error(response.status===404?'Không tìm thấy PDF cho tháng đã chọn.':'Không tải được PDF. Vui lòng thử lại.');
  if(blob){if(!response.headers.get('content-type')?.includes('application/pdf'))throw new Error('Tệp trả về không phải PDF.');return response.blob();}
  return response.json();
 }
 function close(){
  renderTask?.cancel();renderTask=null;if(pdfTask){pdfTask.destroy().catch(()=>{});pdfTask=null;}
  el('invoicePDFPages').replaceChildren();el('invoicePDFPages').hidden=true;
  el('invoicePDFFrame').removeAttribute('src');el('invoicePDFFrame').hidden=true;
  for(const id of ['invoicePDFDownload','invoicePDFOpen','invoicePDFClose']){el(id).hidden=true;el(id).removeAttribute('href');}
  if(blobURL){URL.revokeObjectURL(blobURL);blobURL=null;}
 }
 async function load(){
  const a=account(),s=++seq;selectedAccount=a;close();catalogRows=[];
  el('invoicePDFPeriod').replaceChildren(new Option('Đang tải…',''));el('invoicePDFPeriod').disabled=true;el('invoicePDFView').disabled=true;
  if(!a){el('invoicePDFStatus').textContent='Chọn mã khách hàng để xem PDF.';return;}
  el('invoicePDFStatus').textContent='Đang lấy danh sách PDF đã lưu…';
  try{const d=await request('npc/invoices/'+encodeURIComponent(a)+'?include='+encodeURIComponent(new URLSearchParams(location.search).get('invoice')||'0'));if(s!==seq||a!==account())return;
   catalogRows=d.invoices;const groups=new Map();for(const row of catalogRows){if(!groups.has(row.year)){const group=document.createElement('optgroup');group.label=String(row.year);groups.set(row.year,group);}groups.get(row.year).append(new Option(`${String(row.month).padStart(2,'0')}/${row.year}`,String(row.id)));}el('invoicePDFPeriod').replaceChildren(...groups.values());
   const available=catalogRows.length>0;el('invoicePDFPeriod').disabled=!available;el('invoicePDFView').disabled=!available;
   if(!available)el('invoicePDFPeriod').add(new Option('Chưa có PDF',''));
   el('invoicePDFStatus').textContent=available?`${catalogRows.length} kỳ có hồ sơ cho ${a}; ${catalogRows.filter(r=>r.cached!==false).length} PDF đã lưu. PDF còn thiếu được lấy từ EVN khi mở; loại chứng từ theo nội dung tệp.`:'Mã này chưa có PDF được lưu. Không có tệp thì chưa thể xem hóa đơn.';
  }catch(e){if(s===seq){el('invoicePDFStatus').textContent=e.message;el('invoicePDFPeriod').replaceChildren(new Option('Chưa tải được',''));}}
 }
 async function view(){
  const a=account(),id=Number(el('invoicePDFPeriod').value),row=catalogRows.find(r=>r.id===id);if(a!==selectedAccount||!row)return;
  const s=++seq;close();el('invoicePDFView').disabled=true;el('invoicePDFStatus').textContent='Đang tải PDF…';
  try{const file=await request(`npc/invoice/${encodeURIComponent(a)}/${id}`,true);if(s!==seq||a!==account())return;
   blobURL=URL.createObjectURL(file);el('invoicePDFPages').hidden=false;
   el('invoicePDFDownload').href=blobURL;el('invoicePDFDownload').hidden=false;
   el('invoicePDFOpen').href=`/npc-monitor/invoice-viewer.html?account=${encodeURIComponent(a)}&invoice=${id}`;el('invoicePDFOpen').target='_self';el('invoicePDFOpen').hidden=false;
   el('invoicePDFDownload').download=`EVN-${a}-${row.year}-${String(row.month).padStart(2,'0')}.pdf`;el('invoicePDFClose').hidden=false;
   el('invoicePDFStatus').textContent=`${a} · Tháng ${row.month}/${row.year}. Đang hiển thị nội dung PDF…`;
   if(!Promise.withResolvers)Promise.withResolvers=function(){let resolve,reject;const promise=new this((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject};};
   const pdfjs=await import('/npc-monitor/assets/vendor/pdf.min.mjs?v=4.10.38');if(s!==seq)return;
   pdfjs.GlobalWorkerOptions.workerSrc='/npc-monitor/assets/vendor/pdf.worker.min.mjs?v=4.10.38';
   pdfTask=pdfjs.getDocument({data:new Uint8Array(await file.arrayBuffer()),isEvalSupported:false});
   const pdf=await pdfTask.promise;if(s!==seq)return;
   for(let number=1;number<=pdf.numPages;number++){
    const page=await pdf.getPage(number);if(s!==seq)return;
    const native=page.getViewport({scale:1}),width=Math.max(240,Math.min(900,el('invoicePDFPages').clientWidth-16));
    const ratio=Math.min(window.devicePixelRatio||1,2),viewport=page.getViewport({scale:width/native.width*ratio});
    const canvas=document.createElement('canvas');canvas.width=Math.ceil(viewport.width);canvas.height=Math.ceil(viewport.height);canvas.style.width=`${width}px`;canvas.setAttribute('aria-label',`Trang ${number} / ${pdf.numPages}`);el('invoicePDFPages').appendChild(canvas);
    renderTask=page.render({canvasContext:canvas.getContext('2d'),viewport});await renderTask.promise;if(s!==seq)return;
   }
   renderTask=null;el('invoicePDFStatus').textContent=`${a} · Tháng ${row.month}/${row.year} · ${pdf.numPages} trang. Có thể tải PDF hoặc mở riêng.`;
  }catch(e){if(s===seq){el('invoicePDFStatus').textContent='Không hiển thị trực tiếp được. Chọn Mở riêng hoặc Tải PDF. '+e.message;}}finally{if(s===seq)el('invoicePDFView').disabled=false;}
 }
 document.addEventListener('DOMContentLoaded',()=>{
  el('invoicePDFView').addEventListener('click',view);el('invoicePDFClose').addEventListener('click',()=>{++seq;close();el('invoicePDFView').disabled=false;});
  el('invoicePDFPeriod').addEventListener('change',()=>{++seq;close();el('invoicePDFView').disabled=false;});
  el('accountSelect').addEventListener('change',load);
  document.addEventListener('evn-history-updated',()=>{if(el('invoicePDFPages').hidden)load();});
  let timer;new MutationObserver(()=>{clearTimeout(timer);timer=setTimeout(load,200);}).observe(el('accountSelect'),{childList:true});
  setTimeout(load,1200);window.addEventListener('pagehide',close);
 });
})();
