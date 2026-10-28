"""One executor-built sensor snapshot per account, never SQL in HA state getters."""
from .paths import data_path, auth_path

import sqlite3
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
DB=str(data_path('evndata.db'))

def build(account):
    from .meter_comparison import _official
    from .meter_math import number
    now=datetime.now(ZoneInfo('Asia/Ho_Chi_Minh'));today=now.date()
    data=_official(account,now);result={}
    def put(key,value,attrs=None):result[key]={'value':value,'attributes':attrs or {}}
    origin={'Nguồn':'API EVN mới','Mốc đầu':data.get('period_start'),'Mốc cuối':data.get('cutoff'),'Cập nhật nguồn':data.get('fetched_at')}
    with sqlite3.connect('file:'+DB+'?mode=ro',uri=True,timeout=10) as db:
        daily={row[0]:(number(row[1]),number(row[2])) for row in db.execute('SELECT ngay,chi_so,dien_tieu_thu_kwh FROM daily_consumption WHERE userevn=?',(account,))}
        monthly={(int(y),int(m)):(number(money),number(used)) for y,m,money,used in db.execute('SELECT nam,thang,tien_dien,san_luong_kwh FROM monthly_bill WHERE userevn=?',(account,))}
    put('chi_so_cuoi_ky',data['initial_reading'],{**origin,'Ngày':(today.replace(day=1)-timedelta(days=1)).strftime('%d-%m-%Y')});put('chi_so_tam_chot',data['latest_reading'],{**origin,'Ngày':data.get('through_day')})
    put('tieu_thu_ky_nay',data['kwh'],origin);put('tien_dien_ky_nay',data['estimated_vnd'],{**origin,'Loại tiền':'Dự kiến','VAT':data['tariff']['vat_percent']})
    closed=today.replace(day=1)-timedelta(days=1)
    for suffix,period in [('ky_truoc',closed),('ky_truoc_nua',closed.replace(day=1)-timedelta(days=1))]:
        money,used=monthly.get((period.year,period.month),(None,None));attrs={'Tháng':f'{period.month:02d}','Năm':str(period.year),'Nguồn tiền':'Hóa đơn EVN' if money is not None else 'Chưa có dữ liệu'}
        put('tieu_thu_'+suffix,used,attrs);put('tien_dien_'+suffix,money,attrs)
    for key,offset in [('tieu_thu_hom_nay',0),('tieu_thu_hom_qua',1),('tieu_thu_hom_kia',2)]:
        date=today-timedelta(days=offset);put(key,daily.get(date.strftime('%d-%m-%Y'),(None,None))[1],{'Ngày':date.strftime('%d-%m-%Y')})
    details=[];date=today
    while date>=today.replace(day=1):
        index,used=daily.get(date.strftime('%d-%m-%Y'),(None,None));details.append({'Ngày':date.strftime('%d-%m-%Y'),'Chỉ số':index,'Điện tiêu thụ (kWh)':used});date-=timedelta(days=1)
    put('chi_tiet_dien_tieu_thu_ky_nay',today.strftime('%m-%Y'),{'Bắt đầu':today.replace(day=1).strftime('%d-%m-%Y'),'Kết thúc':today.strftime('%d-%m-%Y'),'Chi Tiết':details})
    bills=[];production=[]
    for (year,month),(money,used) in sorted(monthly.items(),reverse=True):
        if year!=today.year:continue
        row={'Tháng':f'01-{month:02d}-{year}','Năm':year}
        if money is not None:bills.append({**row,'Tiền Điện':str(money)})
        production.append({**row,'Điện tiêu thụ (KWh)':str(used) if used is not None else None})
    put('tien_dien_san_luong_nam_nay',str(today.year),{'TienDien':bills,'SanLuong':production})
    from .services_cpc import sensors
    result.update(sensors(account,now))
    put('lan_cap_nhat_cuoi',data.get('fetched_at'),{'device_class':'timestamp','Nguồn':'Lần tải EVN thành công'})
    return result
