const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=process.env.EVN_COMPONENT||path.resolve(__dirname,'../custom_components/evn');
function setup(instant='2026-11-01T08:00:00Z'){
 class Clock extends Date{constructor(...args){super(...(args.length?args:[instant]));}static now(){return new Date(instant).getTime();}}
 const context=vm.createContext({Date:Clock,Intl,window:{},localStorage:{removeItem(){}},console:{warn(){},error(){}}});
 vm.runInContext(fs.readFileSync(path.join(source,'webui/assets/js/data.js'),'utf8'),context);
 const dm=new context.window.DataManager();dm.currentAccount='PCDEMO12345';dm.dailyData=[];dm.monthlyData={SanLuong:[],TienDien:[]};
 dm.currentPeriodFromSensor={tieu_thu_ky_nay:null,tien_dien_ky_nay:null,ngay_dau_ky:'2026-11-01T00:22:00+07:00'};
 return dm;
}
function october(dm,count=31){dm.dailyData=Array.from({length:count},(_,i)=>({'Ngày':String(i+1).padStart(2,'0')+'-10-2026','Điện tiêu thụ (kWh)':10,'Tiền điện (VND)':100}));}
test('first November day adds actual current month and retains unbilled October',()=>{
 const dm=setup();october(dm);dm.monthlyData={SanLuong:[{'Tháng':9,'Năm':2026,'Điện tiêu thụ (KWh)':57}],TienDien:[{'Tháng':9,'Năm':2026,'Tiền Điện':122634}]};
 const keys=dm.getUniqueMonths(2026);assert.deepEqual(Array.from(keys),['11-2026','10-2026','09-2026']);
 const rows=dm.calculateTrendData(keys);assert.equal(rows[0].isCurrentPeriod,true);assert.equal(rows[0].totalConsumption,null);assert.equal(rows[0].monthlyCost,null);assert.equal(rows[0].min,null);
 assert.equal(rows[1].isCurrentPeriod,false);assert.equal(rows[1].totalConsumption,310);assert.equal(rows[1].monthlyCost,3100);assert.match(rows[1].periodStatus,/Chờ hóa đơn/);assert.equal(rows[2].monthlyCost,122634);
 const chart=dm.getFilteredMonthlyData(2026);assert.equal(chart.SanLuong[10]['Điện tiêu thụ (KWh)'],null);assert.equal(chart.TienDien[9]['Tiền Điện'],null);
});
test('an issued bill replaces provisional daily totals, including official zero',()=>{
 const dm=setup();october(dm);dm.monthlyData={SanLuong:[{'Tháng':10,'Năm':2026,'Điện tiêu thụ (KWh)':300}],TienDien:[{'Tháng':10,'Năm':2026,'Tiền Điện':750000}]};
 let row=dm.calculateTrendData(['10-2026'])[0];assert.equal(row.totalConsumption,300);assert.equal(row.monthlyCost,750000);assert.equal(row.hasOfficialBill,true);
 dm.monthlyData.TienDien[0]['Tiền Điện']=0;dm.monthlyData.SanLuong[0]['Điện tiêu thụ (KWh)']=0;row=dm.calculateTrendData(['10-2026'])[0];assert.equal(row.totalConsumption,0);assert.equal(row.monthlyCost,0);
});
test('partial daily history stays provisional and does not invent a monthly fee',()=>{const dm=setup();october(dm,10);const row=dm.calculateTrendData(['10-2026'])[0];assert.equal(row.totalConsumption,100);assert.equal(row.monthlyCost,null);assert.match(row.periodStatus,/10 ngày/);});
test('a complete real zero-consumption month is distinct from missing data',()=>{const dm=setup();october(dm);for(const d of dm.dailyData){d['Điện tiêu thụ (kWh)']=0;d['Tiền điện (VND)']=0;}const row=dm.calculateTrendData(['10-2026'])[0];assert.equal(row.totalConsumption,0);assert.equal(row.monthlyCost,0);assert.equal(row.dataCount,31);assert.equal(row.min,0);});
test('missing daily fees never turn into zero monthly forecasts',()=>{const dm=setup();october(dm);dm.dailyData[10]['Tiền điện (VND)']=null;assert.equal(dm.calculateTrendData(['10-2026'])[0].monthlyCost,null);});
test('Jan rollover distinguishes the prior year and excludes current from an old year filter',()=>{const dm=setup('2027-01-01T00:30:00Z');dm.dailyData=[{'Ngày':'31-12-2026','Điện tiêu thụ (kWh)':9}];const all=dm.getUniqueMonths();assert.deepEqual(Array.from(all),['01-2027','12-2026']);assert.equal(dm.calculateTrendData(all)[1].isCurrentPeriod,false);assert.deepEqual(Array.from(dm.getUniqueMonths(2026)),['12-2026']);assert.ok(dm.getAvailableYears().includes(2027));});
test('a stale previous-month API snapshot is not reused as this month',()=>{const dm=setup();dm.currentPeriodFromSensor={tieu_thu_ky_nay:310,tien_dien_ky_nay:800000,ngay_dau_ky:'2026-10-01T00:33:00+07:00'};assert.equal(dm.calculateTrendData(['11-2026'])[0].totalConsumption,null);assert.equal(dm.calculateCurrentPeriod(),null);});
test('a verified current API zero is retained as zero',()=>{const dm=setup();dm.currentPeriodFromSensor.tieu_thu_ky_nay=0;dm.currentPeriodFromSensor.tien_dien_ky_nay=0;const row=dm.calculateTrendData(['11-2026'])[0];assert.equal(row.totalConsumption,0);assert.equal(row.monthlyCost,0);});
test('Vietnam month boundary is independent of the browser timezone',()=>{const dm=setup('2026-10-31T17:30:00Z');assert.equal(dm.getUniqueMonths()[0],'11-2026');});
