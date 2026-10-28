(() => {
  'use strict';
  const el = id => document.getElementById(id);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const fmt = (v, unit='kWh') => v === null || v === undefined ? 'Chưa có dữ liệu' : `${Number(v).toLocaleString('vi-VN',{maximumFractionDigits:unit==='VND'?0:2})} ${unit}`;
  const date = value => value ? new Date(value).toLocaleString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh'}) : 'Chưa có dữ liệu';
  let sequence=0, pending=false, configAccount='',historyRevision=new Map();
  const account=()=>el('accountSelect')?.value||'';
  async function api(method,path,body) {
    let ha;
    try { ha=window.parent.document.querySelector('home-assistant')?.hass; } catch (_) {}
    if(ha?.callApi) return ha.callApi(method,path,body);
    let token;
    try { token=JSON.parse(localStorage.getItem('hassTokens')||'null')?.access_token; } catch (_) {}
    if(!token) throw new Error('Đăng nhập và mở EVN Monitor trong Home Assistant để xem bộ đếm.');
    const response=await fetch(`/api/${path}`,{method,headers:{Authorization:`Bearer ${token}`,'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});
    const data=await response.json();if(!response.ok)throw new Error(data.error||`HA: ${response.status}`);return data;
  }
  function metric(title,value,money,detail) {
    return `<div class="meter-tile"><h4>${esc(title)}</h4><strong>${esc(fmt(value))}</strong><div class="meter-money">${esc(fmt(money,'VND'))}</div><small>${esc(detail)}</small></div>`;
  }
  function group(title,tag,tiles,notes,cls) {
    return `<section class="source-group ${cls}"><header><h4>${esc(title)}</h4><span>${esc(tag)}</span></header><div class="source-tiles">${tiles}</div><details class="source-details"><summary>Chi tiết</summary><p class="meter-status">${esc(notes)}</p></details></section>`;
  }
  function renderServices(services, customer, loading=false) {
    if(!el('evnServices'))return;
    el('evnServicesAccount').textContent=customer;
    el('evnServicesError').hidden=true;
    const debt=services?.tien_no, outages=services?.lich_cat_dien;
    const info=row=>{
      const a=row?.attributes||{},parts=[];
      if(a['Cập nhật nguồn'])parts.push(`Lấy từ EVN: ${date(a['Cập nhật nguồn'])}`);
      if(a['Lỗi cập nhật'])parts.push(a['Cập nhật nguồn']?'Chưa cập nhật được; đang giữ dữ liệu lần thành công trước.':'Chưa lấy được dữ liệu từ EVN.');
      else if(a['Dữ liệu cũ'])parts.push('Dữ liệu đã cũ, đang chờ lần cập nhật tiếp theo.');
      return `<small>${parts.map(esc).join('<br>')}</small>`;
    };
    const d=debt?.value, da=debt?.attributes||{},known=d!==null&&d!==undefined;
    const debtClass=da['Lỗi cập nhật']||da['Dữ liệu cũ']?'warning':known?(Number(d)>0?'danger':'good'):'';
    el('evnDebt').className='evn-service-card '+debtClass;
    el('evnDebt').innerHTML=`<h4>Tiền nợ EVN</h4><div class="evn-service-value">${loading?'Đang tải…':esc(known?fmt(d,'VND'):'Chưa có dữ liệu')}</div>${known?`<p>${Number(d)>0?`${esc(da['Hóa đơn còn nợ']??'')} hóa đơn còn nợ`:'Không có tiền nợ theo hóa đơn EVN trả về'}</p>`:''}${info(debt)}`;
    const o=outages?.value,oa=outages?.attributes||{},events=Array.isArray(oa['Tương Lai'])?oa['Tương Lai']:[];
    const eventHTML=e=>`<div class="evn-outage-event"><b>${esc(e['Ngày'])} · ${esc(e['Thời gian từ'])} → ${esc(e['Ngày kết thúc']!==e['Ngày']?(e['Ngày kết thúc']+' '):'')}${esc(e['Thời gian đến'])}</b>${e['Khu vực']?`<p>Khu vực: ${esc(e['Khu vực'])}</p>`:''}${e['Lý do']?`<p>Lý do: ${esc(e['Lý do'])}</p>`:''}</div>`;
    const outageClass=oa['Lỗi cập nhật']||oa['Dữ liệu cũ']?'warning':o?(oa['Đang ngừng cấp điện']?'danger':events.length?'warning':'good'):'';
    el('evnOutages').className='evn-service-card '+outageClass;
    const title=loading?'Đang tải…':!o?'Chưa có dữ liệu':oa['Đang ngừng cấp điện']?'Đang ngừng cấp điện':events.length?`${events.length} lịch mất điện sắp tới`:'Không có lịch mất điện';
    const windowText=oa['Tra cứu từ']&&oa['Tra cứu đến']?`Trong khoảng ${oa['Tra cứu từ'].split('-').reverse().join('/')} – ${oa['Tra cứu đến'].split('-').reverse().join('/')}`:'';
    el('evnOutages').innerHTML=`<h4>Lịch mất điện</h4><div class="evn-service-value">${esc(title)}</div>${events.slice(0,2).map(eventHTML).join('')}${events.length>2?`<details><summary>Xem thêm ${events.length-2} lịch</summary>${events.slice(2).map(eventHTML).join('')}</details>`:''}${!events.length&&o?`<p>${esc(windowText)}</p>`:''}${info(outages)}`;
  }
  function render(d) {
    renderServices(d.services,d.account);
    el('meterAccountLabel').textContent=`${d.account} · Tháng ${d.month.slice(5)}/${d.month.slice(0,4)} · Giờ Việt Nam`;
    const n=d.evn, vat=n.tariff?.vat_percent??8, interval=(a,b)=>`${date(a)} → ${date(b)}`;
    const evnTiles=metric('Điện tháng',n.kwh,n.estimated_vnd,interval(n.period_start,n.cutoff))+metric('Hôm qua',n.yesterday_kwh,n.yesterday_estimated_vnd,interval(n.yesterday_start_at,n.yesterday_read_at));
    const evnNotes=`Tổng điện theo API EVN mới. Chỉ số đầu: ${fmt(n.initial_reading)} → cuối: ${fmt(n.latest_reading)}. HA đồng bộ: ${date(n.fetched_at)}. Tiền dự kiến lũy tiến theo tổng API, đã gồm VAT ${vat}%. Tiền ngày là phần tăng tiền tháng tại hai mốc API.`;
    const sync=n.sync||{};let status={pending:'Đang chuẩn bị',invoices:'Đang lấy hóa đơn',monthly:'Đang lấy lịch sử tháng',daily:'Đang lấy lịch sử ngày',pdf:'Đang lưu PDF',partial:'Đang bổ sung lịch sử',paused:'Tạm dừng, sẽ thử lại',ready:'Đã đồng bộ'}[sync.history_status];
    if(sync.pdf_progress){const p=sync.pdf_progress;status=(status||'Đang đồng bộ')+` · PDF ${p.downloaded}/${p.total}`+(p.unavailable?` · ${p.unavailable} chưa được EVN cung cấp`:'');}
    if(sync.monthly_cursor&&!sync.monthly_scanned)status+=( ` · đang quét năm ${sync.monthly_cursor}`);
    const revision=d.account+'|'+(sync.invoice_checked_at||'')+'|'+(sync.history_status==='ready');
    if(historyRevision.has(d.account)&&historyRevision.get(d.account)!==revision)document.dispatchEvent(new CustomEvent('evn-history-updated'));historyRevision.set(d.account,revision);
    let tiles, notes;
    if(!d.configured) {
      tiles='<div class="meter-empty">Chưa chọn sensor cho mã này. Vào Cấu hình để chọn; chưa chọn thì không tạo bộ đếm.</div>';
      notes='Electric cập nhật 15 phút/lần sau khi chọn sensor.';
    } else {
      const available=d.current_kwh!=null&&d.complete_month, approx=available&&!d.baseline_exact;
      tiles=metric('Điện tháng'+(approx?' (xấp xỉ)':''),available?d.current_kwh:null,available?d.current_estimated_vnd:null,interval(d.shared_period_start,d.electric_snapshot_at))+metric('Hôm nay',d.electric_today_kwh,d.electric_today_estimated_vnd,interval(d.electric_today_start_at,d.electric_today_end_at));
      notes=`Nguồn: ${d.source}. Chỉ số hiện tại: ${fmt(d.source_reading,d.source_unit||'kWh')}. Đọc nguồn: ${date(d.meter_updated_at)}. Điện tháng = chỉ số riêng Electric hiện tại trừ gốc riêng Electric tại mốc đầu API EVN mới. Electric tại mốc EVN ${date(n.cutoff)}: ${fmt(d.at_evn_kwh)} · ${fmt(d.at_evn_estimated_vnd,'VND')}. Chênh lệch Electric − EVN tại cùng mốc: ${fmt(d.delta_kwh)}. Hôm qua theo cùng mốc API: ${fmt(d.electric_yesterday_kwh)}. Cập nhật 15 phút/lần.`;
      if(!available)notes+=' Chưa đủ gốc Electric tại mốc đầu API hoặc sensor chưa sẵn sàng; không biến thiếu dữ liệu thành 0.';
      if(approx)notes+=` Gốc xấp xỉ từ thống kê lúc ${date(d.baseline_sample_at)}, độ bất định tối đa ${fmt(d.baseline_error_bound_kwh)}.`;
    }
    el('meterValues').style.gridTemplateColumns=d.configured?'':'1fr';
    const heading=document.querySelector('.meter-heading h3');if(heading)heading.textContent=d.configured?'Điện năng · EVN và Electric Meter':'Điện năng · EVN';
    el('meterValues').innerHTML=group('EVN mới','Theo API',evnTiles,evnNotes+(status?' Lịch sử: '+status+(sync.history_first_day?' · ngày từ '+sync.history_first_day:'')+'.':''),'source-new')+(d.configured?group('Electric Meter','15 phút/lần',tiles,notes,'source-local'):'');
    el('meterStatus').textContent=d.configured?`Chuẩn đối chiếu: mốc đầu kỳ và tổng điện API EVN mới. Electric dùng chỉ số riêng tại cùng mốc. Tiền đang chạy là dự kiến, gồm VAT ${vat}%; số phải trả theo hóa đơn EVN phát hành.`:`Dữ liệu theo API EVN mới. Tiền đang chạy là dự kiến, gồm VAT ${vat}%; số phải trả theo hóa đơn EVN phát hành.`;
    if(status)el('meterStatus').textContent='Đồng bộ: '+status+'. '+el('meterStatus').textContent;
  }
  async function refresh() {
    const a=account();if(!a||pending)return;const request=++sequence;
    try {const d=await api('GET',`npc/meter/account/${encodeURIComponent(a)}`);if(request===sequence&&account()===a)render(d);}
    catch(e){if(request===sequence){el('meterStatus').textContent=e.message||'Không tải được số liệu.';el('evnServicesError').textContent='Chưa tải được tiền nợ và lịch mất điện. Vui lòng thử lại.';el('evnServicesError').hidden=false;}}
  }
  async function checkSource() {
    const source=el('meterSource').value;el('meterSaveBtn').disabled=true;
    if(!source){el('meterCheckResult').textContent='Chưa chọn sensor: không tạo bộ đếm.';el('meterSaveBtn').disabled=false;return;}
    el('meterCheckResult').textContent='Đang kiểm tra sensor…';
    try {const d=await api('POST','npc/meter/check',{source,resetting:el('meterMayReset').checked});if(el('meterSource').value!==source)return;
      el('meterCheckResult').textContent=d.valid?[`✓ Sensor phù hợp: ${fmt(d.value,d.unit)}. Cập nhật ${date(d.last_updated)}.`,...d.warnings,d.physical_accuracy].join(' '):d.errors.join('; ');el('meterSaveBtn').disabled=!d.valid;
    }catch(e){el('meterCheckResult').textContent=e.message;}
  }
  async function loadSettings() {
    configAccount=account();el('meterConfigAccount').textContent=configAccount;el('meterSaveBtn').disabled=true;
    try {const [catalog,d]=await Promise.all([api('GET','npc/meter/sources'),api('GET',`npc/meter/account/${encodeURIComponent(configAccount)}`)]);
      el('meterSource').replaceChildren(new Option('Không liên kết sensor',''));for(const source of catalog.sources)el('meterSource').add(new Option(`${source.name} · ${source.entity_id} (${source.value??'unavailable'} ${source.unit})`,source.entity_id));
      if(d.source&&!catalog.sources.some(x=>x.entity_id===d.source))el('meterSource').add(new Option(d.source,d.source));el('meterSource').value=d.source||'';el('meterMayReset').checked=d.resetting!==false;
      const at=d.baseline_at_override?new Date(d.baseline_at_override):null;
      if(at){const parts=new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Ho_Chi_Minh',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false}).format(at);el('meterBaselineAt').value=parts.replace(' ','T');}else el('meterBaselineAt').value='';
      el('meterBaselineValue').value=d.baseline_raw??'';el('meterApprox').checked=!!d.allow_approximate_baseline;
      el('meterConfigMsg').textContent='Nhập gốc của chính Electric Meter tại mốc chốt EVN, không nhập chỉ số của công tơ EVN. Không có gốc thì để trống; phần cả kỳ sẽ chờ xác nhận.';await checkSource();
    }catch(e){el('meterConfigMsg').textContent=e.message;}
  }
  async function save(event) {
    event.preventDefault();if(pending)return;pending=true;el('meterSaveBtn').disabled=true;el('meterConfigMsg').textContent='Đang sao lưu và lưu cấu hình…';
    try {const at=el('meterBaselineAt').value;const raw=el('meterBaselineValue').value;
      const d=await api('POST',`npc/meter/account/${encodeURIComponent(configAccount)}`,{source:el('meterSource').value||null,resetting:el('meterMayReset').checked,baseline_at:at?`${at}${at.length===16?':00':''}+07:00`:null,baseline_raw:raw===''?null:Number(raw),allow_approximate_baseline:el('meterApprox').checked});
      el('meterConfigMsg').textContent=`Đã lưu cho ${configAccount}.`;if(account()===configAccount)render(d);
    }catch(e){el('meterConfigMsg').textContent=e.message||'Không lưu được.';}finally{pending=false;el('meterSaveBtn').disabled=false;}
  }
  document.addEventListener('DOMContentLoaded',()=>{
    el('meterConfigForm').addEventListener('submit',save);el('configBtn').addEventListener('click',loadSettings);el('meterCheckBtn').addEventListener('click',checkSource);el('meterSource').addEventListener('change',checkSource);el('meterMayReset').addEventListener('change',checkSource);el('meterRefreshBtn').addEventListener('click',refresh);el('accountSelect').addEventListener('change',()=>{renderServices(null,account(),true);refresh();});
    let timer;new MutationObserver(()=>{clearTimeout(timer);timer=setTimeout(refresh,200);}).observe(el('accountSelect'),{childList:true});setTimeout(refresh,1200);setInterval(()=>{if(!document.hidden)refresh();},30000);
  });
})();
