(() => {
  'use strict';
  const el=id=>document.getElementById(id), number=value=>value===null||value===undefined?'—':Number(value).toLocaleString('vi-VN');
  const time=value=>value?new Date(value).toLocaleString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh'}):'Chưa có';
  let sequence=0,last=null,lastAccount='';
  const account=()=>el('accountSelect')?.value||'';
  function message() {
    if(!last||account()!==lastAccount)return;
    const p=last;let text='';
    if(p.phase==='paused') {
      const reason=p.last_error||'';
      text=reason.includes('429')?'EVN giới hạn tốc độ truy vấn.':reason.includes('403')||reason.includes('401')?'EVN từ chối đăng nhập/quyền truy cập.':'Nguồn EVN hoặc kết nối đang tạm thời chưa sẵn sàng.';
      if(p.retry_at){const seconds=Math.max(0,Math.ceil((Date.parse(p.retry_at)-Date.now())/1000));text+=` Tự thử lại lúc ${time(p.retry_at)}${seconds>0?` (còn ${Math.ceil(seconds/60)} phút)`:' (đang chờ lượt)'}.`;}
      else text+=' Giữ điểm dừng và chờ lần cập nhật tiếp theo.';
    } else if(p.phase==='queued')text='Đang chờ lượt trong hàng đợi chung; không tải đồng loạt các mã.';
    else if(p.phase==='monthly')text=`Đang quét năm ${p.monthly_cursor||'đầu tiên'}. Mỗi đợt lấy tối đa 2 năm rồi lưu điểm dừng.`;
    else if(p.phase==='daily'||p.phase==='partial')text=p.window_start&&p.window_end?`Đang bổ sung khoảng ${p.window_start} → ${p.window_end}. Tổng lịch sử ngày chưa biết trước; dừng tại giới hạn EVN còn cung cấp.`:'Đang bổ sung các khoảng ngày EVN còn cung cấp.';
    else if(p.phase==='ready')text=p.pdf_remaining?`Đã xử lý các PDF hiện có thể tải; ${number(p.pdf_remaining)} PDF còn thiếu được ghi riêng, không tính là đã lưu.`:'Đã hoàn tất khởi tạo trong phạm vi dữ liệu EVN cung cấp. Các lần sau đối soát dữ liệu mới.';
    else if(p.phase==='pdf')text='Đang tải từng PDF và lưu điểm dừng. Giữ dữ liệu đã tải khi tạm nghỉ hoặc khởi động lại HA.';
    else text='Đang lấy danh mục để xác định tổng dữ liệu. Chưa có tổng thì không tính phần trăm.';
    if(p.pdf_unavailable)text+=` EVN chưa cung cấp ${number(p.pdf_unavailable)} PDF; sẽ kiểm tra lại sau.`;
    el('syncMessage').textContent=text;
  }
  function render(data,code) {
    const p=data.account;last=p;lastAccount=code;
    el('syncProgress').hidden=p.phase==='ready'&&p.monthly_complete&&p.daily_boundary_reached&&p.pdf_pending===0;
    el('syncProgress').dataset.phase=p.phase;
    el('syncPhase').textContent=p.label;
    el('syncCustomer').textContent=code;
    el('syncDownloaded').textContent=number(p.pdf_downloaded);
    el('syncTotal').textContent=number(p.pdf_total);
    el('syncRemaining').textContent=number(p.pdf_remaining);
    if(p.pdf_percent===null||p.pdf_percent===undefined){el('syncBar').removeAttribute('value');el('syncPercent').textContent='Đang xác định';}
    else{const percent=Math.max(0,Math.min(100,Number(p.pdf_percent)));el('syncBar').value=percent;el('syncPercent').textContent=number(percent)+'% đã lưu';}
    el('syncRecords').textContent=`Lịch sử đã nhập: ${number(p.months_imported)} tháng · ${number(p.days_imported)} ngày. Tháng: ${p.monthly_complete?'đã quét':'đang bổ sung'}; ngày: ${p.daily_boundary_reached?'đã tới giới hạn nguồn':'đang bổ sung'}.`;
    const all=data.overall;
    el('syncOverall').textContent=all.totals_known?`Tất cả ${number(all.accounts)} mã: đã lưu ${number(all.pdf_downloaded)}/${number(all.pdf_total)} PDF · còn thiếu ${number(all.pdf_remaining)}.`:`Tất cả ${number(all.accounts)} mã: đã lưu ${number(all.pdf_downloaded)} PDF · tổng còn đang xác định.`;
    el('syncUpdated').textContent=`Tiến trình cập nhật: ${time(p.updated_at)} · kiểm tra tại HA mỗi 10 giây.`;
    message();
  }
  async function refresh(clear=false) {
    const code=account(),request=++sequence;
    if(clear){last=null;el('syncProgress').hidden=true;el('syncPhase').textContent='Đang đọc tiến trình…';el('syncCustomer').textContent=code;for(const id of ['syncDownloaded','syncTotal','syncRemaining'])el(id).textContent='—';el('syncRecords').textContent='';el('syncMessage').textContent='';el('syncOverall').textContent='';el('syncUpdated').textContent='';el('syncPercent').textContent='Đang xác định';el('syncBar').removeAttribute('value');}
    if(!code)return;
    try{const data=await window.EVNApi.json('/api/npc/sync-progress/'+encodeURIComponent(code));if(request===sequence&&account()===code)render(data,code);}
    catch(error){if(request===sequence&&account()===code){el('syncProgress').hidden=false;el('syncPhase').textContent='Chưa đọc được tiến trình';el('syncMessage').textContent='Chưa đọc được tiến trình từ HA. '+(error.message||'Sẽ tự thử lại.');}}
  }
  document.addEventListener('DOMContentLoaded',()=>{
    el('accountSelect').addEventListener('change',()=>refresh(true));
    let timer;new MutationObserver(()=>{clearTimeout(timer);timer=setTimeout(()=>refresh(true),150);}).observe(el('accountSelect'),{childList:true});
    setTimeout(()=>refresh(true),500);
    setInterval(()=>{if(!document.hidden)refresh();},10000);
    setInterval(()=>{if(!document.hidden)message();},1000);
  });
})();
