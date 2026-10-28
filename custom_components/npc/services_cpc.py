"""Native official CPC debt/outage snapshots; no add-on cache or notifications."""
from .paths import data_path, auth_path

from datetime import datetime,timedelta
from decimal import Decimal,InvalidOperation
import json,sqlite3
from zoneinfo import ZoneInfo
DB=str(data_path('evndata.db'))
TZ=ZoneInfo('Asia/Ho_Chi_Minh')
BASE='https://cskh-api.cpc.vn/api/evn/tracuu/'

def ensure_schema():
    with sqlite3.connect(DB,timeout=30) as db:
        db.execute('CREATE TABLE IF NOT EXISTS npc_service_cache(account TEXT,kind TEXT,payload TEXT,fetched_at TEXT,last_attempt TEXT,last_error TEXT,PRIMARY KEY(account,kind))')

def amount(value):
    try:n=Decimal(str(value))
    except (InvalidOperation,TypeError,ValueError):raise ValueError('Invalid debt amount') from None
    if not n.is_finite() or n<0:raise ValueError('Invalid debt amount')
    return n

def validate(account,rows):
    if not isinstance(rows,list) or any(not isinstance(row,dict) for row in rows):raise ValueError('Invalid CPC response')
    for row in rows:
        if row.get('MA_KHANG') and row['MA_KHANG']!=account:raise ValueError('CPC account mismatch')
        if row.get('MA_DDO') and row['MA_DDO']!=account+'001':raise ValueError('CPC meter mismatch')

def parse_debt(account,rows):
    validate(account,rows);bills={}
    for row in rows:
        ident=row.get('ID_HDON')
        if not ident:raise ValueError('Missing invoice identity')
        if row.get('TONG_NO') is not None:
            debt=amount(row['TONG_NO'])
            if row.get('TIEN_NO') is not None and row.get('THUE_NO') is not None and abs(amount(row['TIEN_NO'])+amount(row['THUE_NO'])-debt)>1:raise ValueError('Inconsistent debt total')
        elif row.get('TTRANG_TTOAN')=='DATT':debt=Decimal(0)
        elif row.get('TTRANG_TTOAN')=='CHUATT':debt=amount(row.get('TONG_TIEN'))
        else:raise ValueError('Unverified payment status')
        key=(str(ident),str(row.get('LOAI_HDON') or ''),str(row.get('LOAI_PSINH') or ''))
        if key in bills and bills[key]['amount']!=debt:raise ValueError('Conflicting duplicate invoice')
        bills[key]={'amount':debt,'year':row.get('NAM'),'month':row.get('THANG')}
    return {'total_vnd':float(sum((row['amount'] for row in bills.values()),Decimal(0))),
        'invoice_count':len(bills),'unpaid_count':sum(row['amount']>0 for row in bills.values()),
        'periods':sorted({str(row['year'])+'-'+str(row['month']).zfill(2) for row in bills.values()}),
        'scope':'Tổng nợ của các hóa đơn API EVN trả về; không cộng tiền dự kiến kỳ đang chạy'}

def clock(value):
    for fmt in ('%d/%m/%Y %H:%M:%S','%d/%m/%Y %H:%M','%Y-%m-%dT%H:%M:%S'):
        try:return datetime.strptime(str(value),fmt).replace(tzinfo=TZ)
        except ValueError:pass
    raise ValueError('Invalid outage time')

def parse_outages(account,rows):
    validate(account,rows);events={}
    for row in rows:
        start=clock(row.get('TGIAN_BDAU'));end=clock(row.get('TGIAN_KTHUC'))
        if end<=start:raise ValueError('Invalid outage interval')
        reason=str(row.get('LY_DO') or '');area=str(row.get('KHUVUCMATDIEN') or row.get('KHU_VUC') or '')
        key=(start.isoformat(),end.isoformat(),area)
        events[key]={'start':start.isoformat(),'end':end.isoformat(),'reason':reason,'area':area}
    return {'events':sorted(events.values(),key=lambda row:row['start'])}

def _record(account,kind,stamp,payload=None,error=None):
    with sqlite3.connect(DB,timeout=30) as db:
        db.execute('INSERT OR IGNORE INTO npc_service_cache(account,kind) VALUES(?,?)',(account,kind))
        if payload is not None:
            db.execute('UPDATE npc_service_cache SET payload=?,fetched_at=?,last_attempt=?,last_error=NULL WHERE account=? AND kind=?',(json.dumps(payload,ensure_ascii=False),stamp,stamp,account,kind))
        else:db.execute('UPDATE npc_service_cache SET last_attempt=?,last_error=? WHERE account=? AND kind=?',(stamp,error,account,kind))

def sync(account,now=None,force=False):
    ensure_schema();now=now or datetime.now(TZ);cached=read(account);pending=[]
    for kind in ('debt','outages'):
        row=cached.get(kind,{})
        if not force and row.get('fetched_at') and not row.get('last_error') and (now-datetime.fromisoformat(row['fetched_at'])).total_seconds()<4*3600:continue
        pending.append(kind)
    if not pending:return {'cached':True}
    from .cpc_session import Client
    try:client=Client(account)
    except Exception as error:
        for kind in pending:_record(account,kind,now.isoformat(),error=type(error).__name__)
        return {'errors':pending}
    errors=[]
    for kind in pending:
        stamp=datetime.now(TZ).isoformat()
        try:
            if kind=='debt':value=parse_debt(account,client.request(BASE+'hoadon',{}))
            else:
                first=now.date()-timedelta(days=7);last=now.date()+timedelta(days=30)
                value=parse_outages(account,client.request(BASE+'ngungcapdien',{'TU_NGAY':first.strftime('%d/%m/%Y'),'DEN_NGAY':last.strftime('%d/%m/%Y')}))
                value.update(window_start=first.isoformat(),window_end=last.isoformat())
            _record(account,kind,stamp,payload=value)
        except Exception as error:
            _record(account,kind,stamp,error=type(error).__name__);errors.append(kind)
    return {'errors':errors}

def read(account):
    try:
        with sqlite3.connect('file:'+DB+'?mode=ro',uri=True,timeout=10) as db:
            db.row_factory=sqlite3.Row
            return {row['kind']:{**dict(row),'payload':json.loads(row['payload']) if row['payload'] else None} for row in db.execute('SELECT * FROM npc_service_cache WHERE account=?',(account,))}
    except sqlite3.OperationalError as error:
        if 'no such table' in str(error):return {}
        raise

def sensors(account,now=None):
    now=now or datetime.now(TZ);data=read(account);result={}
    for kind,key in [('debt','tien_no'),('outages','lich_cat_dien')]:
        row=data.get(kind,{});payload=row.get('payload');attrs={'Nguồn':'API EVN CPC trực tiếp','Cập nhật nguồn':row.get('fetched_at'),
            'Lần thử gần nhất':row.get('last_attempt'),'Lỗi cập nhật':row.get('last_error'),
            'Trạng thái cập nhật':'Lỗi – giữ dữ liệu lần thành công trước' if row.get('last_error') else ('Đã cập nhật' if payload is not None else 'Chưa có dữ liệu'),
            'Dữ liệu cũ':bool(row.get('fetched_at') and (now-datetime.fromisoformat(row['fetched_at'])).total_seconds()>8*3600)}
        value=None
        if payload is not None and kind=='debt':
            value=payload['total_vnd'];attrs.update({'Ngày cập nhật':row.get('fetched_at'),'Số hóa đơn':payload['invoice_count'],'Hóa đơn còn nợ':payload['unpaid_count'],'Kỳ hóa đơn':payload['periods'],'Phạm vi':payload['scope']})
        elif payload is not None:
            future=[];past=[]
            for event in payload['events']:
                start=datetime.fromisoformat(event['start']);end=datetime.fromisoformat(event['end'])
                item={'Ngày':start.strftime('%d-%m-%Y'),'Ngày kết thúc':end.strftime('%d-%m-%Y'),'Thời gian từ':start.strftime('%H:%M'),'Thời gian đến':end.strftime('%H:%M'),'Lý do':event['reason'],'Khu vực':event['area'],'Bắt đầu':event['start'],'Kết thúc':event['end']}
                (future if end>now else past).append(item)
            ongoing=next((event for event in future if datetime.fromisoformat(event['Bắt đầu'])<=now),None)
            value='Đang ngừng cấp điện' if ongoing else (future[0]['Ngày'] if future else 'Không có lịch cắt điện')
            attrs.update({'Tương Lai':future,'Quá Khứ':list(reversed(past)),'Số lịch sắp tới':len(future),'Đang ngừng cấp điện':ongoing is not None,
                'Tra cứu từ':payload.get('window_start'),'Tra cứu đến':payload.get('window_end')})
        result[key]={'value':value,'attributes':attrs}
    return result
