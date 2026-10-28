/* Presentation only: Chart.js colors, with existing data and handlers preserved. */
(() => {
 if (!window.Chart) return;
 Chart.register({id:'evnNightLandscape',beforeUpdate(chart) {
  const scales=chart.options.scales || {};
  for(const scale of Object.values(scales)) {
   if(scale.ticks) scale.ticks.color='#b7cedf';
   if(scale.grid) scale.grid.color='rgba(169,199,217,.09)';
   if(scale.title) scale.title.color='#c6dae8';
  }
  if(chart.options.plugins?.legend?.labels) chart.options.plugins.legend.labels.color='#c6dae8';
  for(const [i,set] of chart.data.datasets.entries()) {
   if(chart.config.type==='bar') {
    set.type=i===0?'bar':'line';
    set.label=i===0?'Cột: Tiêu thụ (kWh)':'Đường: Tiền điện (VND)';
    set.order=i===0?2:1;
    if(i===1) {
     const dm=window.app?.dataManager;
     const series=dm?.getFilteredMonthlyData(window.app.currentYear)?.SanLuong;
     if(dm && series) set.data=set.data.map((value,index)=>{
      const item=series[index];if(!item) return value;
      const now=new Date();const current=Number(item.Tháng)===now.getMonth()+1 && Number(item.Năm)===now.getFullYear();
      const known=dm.monthlyData?.TienDien?.some(row=>Number(row.Tháng)===Number(item.Tháng)&&Number(row.Năm)===Number(item.Năm));
      return current||known?value:null;
     });
     set.borderColor='#c4b5fd'; set.backgroundColor='#c4b5fd';
     set.pointBackgroundColor='#c4b5fd';set.pointBorderColor='#ede9fe';
     set.pointRadius=4;set.pointHoverRadius=6;set.borderWidth=3;set.fill=false;set.tension=.2;
     set.segment={}; continue;
    }
    // Relative to the highest displayed positive monthly consumption.
    const consumption=chart.data.datasets[0].data.map(Number);
    const maximum=Math.max(0,...consumption.filter(Number.isFinite));
    const bands=consumption.map(value => !Number.isFinite(value)||value<=0?'missing':value/maximum>=.8?'high':value/maximum>=.5?'medium':'low');
    const palette={low:['#64c5a2','#a1d5bc'],medium:['#e4bd66','#f1d594'],high:['#e77e7e','#f0a9a2'],missing:['#688293','#849aa7']};
    set.backgroundColor=bands.map(band=>palette[band][i===0?0:1]);
    set.borderColor=bands.map(band=>palette[band][i===0?0:1]); set.borderRadius=3;
   } else if(chart.config.type==='line') {
    const values=set.data.map(value=>value===null||value===undefined?NaN:Number(value && typeof value==='object'?value.y:value));
    const valid=values.filter(v=>Number.isFinite(v)&&v>=0);
    if(!valid.length) {chart.$evnDaily=null;continue;}
    const maximum=Math.max(...valid), minimum=Math.min(...valid);
    const average=valid.reduce((sum,value)=>sum+value,0)/valid.length;
    const pointColors=values.map(value=>!Number.isFinite(value)||value<0?'#849aa7':value===maximum?'#f87171':value===minimum?'#60a5fa':value<=average?'#64d9ac':'#facc15');
    chart.$evnDaily={values,maximum,minimum,average};
    set.borderColor='#80c6e5'; set.backgroundColor='rgba(99,169,193,.12)';
    // Remove legacy segment callbacks so rising/falling segments share one color.
    set.segment={borderColor:context=>{
     const previous=context.p0.parsed.y, current=context.p1.parsed.y;
     return current>previous?'#ffbb75':current<previous?'#a2e6b6':'#c6dce8';
    },backgroundColor:'rgba(99,169,193,.055)'};
    set.borderWidth=3; set.backgroundColor='rgba(99,169,193,.055)';
    set.pointBackgroundColor=pointColors; set.pointBorderColor=pointColors;
    set.pointHoverBackgroundColor=pointColors; set.pointHoverBorderColor='#e4f2fa';
    set.pointRadius=values.map(v=>v===maximum||v===minimum?7:4); set.pointHoverRadius=8; set.pointBorderWidth=2; set.pointStyle='circle'; set.fill=true;
   }
  }

  if(chart.config.type==='bar') {
   const options=chart.options;
   if(options.plugins.legend) options.plugins.legend.display=false;
   options.plugins.tooltip.callbacks.label=context=>{
    const current=String(chart.data.labels[context.dataIndex]).toLowerCase().includes('kỳ này');
    const title=context.datasetIndex===0?'Tiêu thụ':current?'Tiền tạm tính':'Tiền điện (hóa đơn)';
    const unit=context.datasetIndex===0?' kWh':' VND';
    return title+': '+Number(context.parsed.y).toLocaleString('vi-VN',{maximumFractionDigits:2})+unit;
   };
   for(const scale of Object.values(scales)) {
    if(scale.axis==='y'&&scale.title?.text) scale.title.text=scale.position==='right'?'Tiền điện (VND)':'Tiêu thụ (kWh)';
   }
  }
 },afterUpdate(chart) {
  if(chart.config.type==='bar') {
   const container=chart.canvas.parentElement;
   if(!container.parentElement.querySelector('.evn-monthly-legend')) {
    const legend=document.createElement('div');legend.className='evn-monthly-legend';
    legend.style.cssText='display:flex;flex-wrap:wrap;gap:6px 14px;margin:8px 0 12px;font-size:12px;color:#d5e6f1;line-height:1.7';
    for(const [text,color] of [['▥ Cột: tiêu thụ (kWh) · trục trái','#9cd9e7'],['━●━ Đường: tiền điện (VND) · trục phải','#c4b5fd'],['■ Thấp: dưới 50%','#64c5a2'],['■ Vừa: 50–dưới 80%','#e4bd66'],['■ Cao: từ 80%','#e77e7e']]) {
     const item=document.createElement('span');item.textContent=text;item.style.color=color;legend.appendChild(item);
    }
    const note=document.createElement('span');note.style.cssText='flex-basis:100%;color:#b8cddd';
    note.textContent='Màu cột so với tháng tiêu thụ cao nhất đang xem. Kỳ này: tiền tạm tính, chưa phải hóa đơn đã chốt. Thiếu hóa đơn: để trống đường tiền điện.';legend.appendChild(note);
    container.insertAdjacentElement('beforebegin',legend);
   }
   return;
  }
  if(chart.config.type!=='line'||!chart.$evnDaily) return;
  const {values,maximum,minimum,average}=chart.$evnDaily;
  const signature=JSON.stringify([chart.data.labels,values]);
  const previous=chart.canvas.parentElement.parentElement.querySelector('.evn-day-summary');
  if(previous?.dataset.signature===signature) return;
  const old=chart.canvas.parentElement.querySelector('.evn-day-summary');
  if(old) old.remove();
  const panel=document.createElement('div');panel.className='evn-day-summary';panel.dataset.signature=signature;
  panel.style.cssText='display:flex;flex-wrap:wrap;gap:8px;margin:8px 0 12px;font-size:12px;line-height:1.6';
  const format=v=>Number(v).toLocaleString('vi-VN',{maximumFractionDigits:2});
  for(const [name,value,color] of [['Thấp nhất',minimum,'#60a5fa'],['Trung bình',average,'#e2e8f0'],['Cao nhất',maximum,'#f87171']]) {
   const dates=values.flatMap((v,i)=>v===value?[String(chart.data.labels[i])]:[]);
   if(name!=='Trung bình'&&!dates.length) continue;
   const item=document.createElement('span');item.style.cssText='background:rgba(7,25,39,.48);border:1px solid '+color+'66;border-radius:5px;padding:5px 9px;color:'+color;
   item.textContent=name==='Trung bình'?'Trung bình: '+format(value)+' kWh/ngày':name+': '+dates.slice(0,3).join(', ')+(dates.length>3?' và '+(dates.length-3)+' ngày khác':'')+' · '+format(value)+' kWh';
   panel.appendChild(item);
  }
  const legend=document.createElement('span');legend.style.cssText='color:#c4d8e5;align-self:center';
  legend.textContent='Đường: cam = tăng · xanh lá nhạt = giảm · xám = ngang | Điểm: xanh dương = thấp nhất · xanh lá = bằng hoặc dưới TB · vàng = trên TB · đỏ = cao nhất';panel.appendChild(legend);
  const container=chart.canvas.parentElement;container.insertAdjacentElement('beforebegin',panel);
  // Keep one summary beside this chart, even after repeated filter updates.
  const siblings=[...container.parentElement.querySelectorAll('.evn-day-summary')];siblings.slice(0,-1).forEach(el=>el.remove());
 },afterDatasetsDraw(chart) {
  if(chart.config.type!=='line'||!chart.$evnDaily) return;
  const {values,maximum,minimum}=chart.$evnDaily;
  const ctx=chart.ctx,points=chart.getDatasetMeta(0).data;
  ctx.save();ctx.font='600 11px sans-serif';ctx.textBaseline='middle';
  for(const [value,title,color] of [[maximum,'Cao nhất','#f87171'],[minimum,'Thấp nhất','#60a5fa']]) {
   const i=values.findIndex(v=>v===value),point=points[i];if(!point) continue;
   const text=title+' '+Number(value).toLocaleString('vi-VN',{maximumFractionDigits:2})+' kWh';
   const width=ctx.measureText(text).width+12;
   const x=Math.max(chart.chartArea.left,Math.min(point.x-width/2,chart.chartArea.right-width));
   const y=value===maximum?Math.min(chart.chartArea.bottom-12,point.y+20):Math.max(chart.chartArea.top+12,point.y-20);
   ctx.fillStyle='rgba(12,31,44,.94)';ctx.fillRect(x,y-10,width,20);ctx.fillStyle=color;ctx.fillText(text,x+6,y);
  }
  ctx.restore();
 }});
})();
