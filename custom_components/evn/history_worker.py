"""Cancellable, checkpointed initial history; bounded jobs, no data clearing."""
import json,sqlite3,threading,time
import urllib.error
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
from .database import DB,ensure_database,official_transaction,sync_status
_LOCK=threading.Lock()
TZ=ZoneInfo('Asia/Ho_Chi_Minh')

def _stamp():return datetime.now(TZ).isoformat()

def _state(account,**values):
    allowed={'history_cursor','history_status','history_empty_windows','history_first_day','monthly_scanned','monthly_cursor','last_error'}
    if not set(values)<=allowed:raise ValueError('Invalid sync field')
    with sqlite3.connect(DB,timeout=30) as db:
        db.execute('INSERT OR IGNORE INTO npc_sync_state(account) VALUES(?)',(account,))
        db.execute('UPDATE npc_sync_state SET '+','.join(key+'=?' for key in values)+' WHERE account=?',(*values.values(),account))

def _validate(account,rows):
    if not isinstance(rows,list):raise ValueError('Invalid EVN rows')
    for row in rows:
        if row.get('MA_KHANG') and row['MA_KHANG']!=account:raise ValueError('EVN history account mismatch')
        if row.get('MA_DDO') and row['MA_DDO']!=account+'001':raise ValueError('EVN meter point mismatch')
    return rows

def import_days(account,rows):
    _validate(account,rows);now=_stamp()
    with official_transaction(account,DB) as db:
        for row in rows:
            day=datetime.strptime(row['NGAY'],'%d/%m/%Y').strftime('%d-%m-%Y');float(row['CHISO_MOI'])
            db.execute('INSERT OR REPLACE INTO codex_cpc_records VALUES(?,?,?,?,?)',(account,'daily',day,json.dumps(row),now))
        cached=[json.loads(row[0]) for row in db.execute("SELECT payload FROM codex_cpc_records WHERE account=? AND kind='daily'",(account,))]
        cached.sort(key=lambda row:datetime.strptime(row['NGAY'],'%d/%m/%Y'))
        previous=None
        for row in cached:
            date=datetime.strptime(row['NGAY'],'%d/%m/%Y');index=float(row['CHISO_MOI']);factor=float(row.get('HSN') or 1);used=None
            if previous and (date-previous[0]).days==1 and factor==previous[2] and index>=previous[1]:used=round((index-previous[1])*factor,6)
            db.execute('INSERT INTO daily_consumption(userevn,ngay,chi_so,dien_tieu_thu_kwh) VALUES(?,?,?,?) ON CONFLICT(userevn,ngay) DO UPDATE SET chi_so=excluded.chi_so,dien_tieu_thu_kwh=excluded.dien_tieu_thu_kwh',(account,date.strftime('%d-%m-%Y'),str(index),str(used) if used is not None else None))
            previous=(date,index,factor)

def run(account,cancel):
    while not _LOCK.acquire(timeout=.5):
        if cancel.is_set():return {'cancelled':True}
    try:
        if cancel.is_set():return {'cancelled':True}
        result = _run(account,cancel)
        if not result.get('cancelled'):
            _state(account,last_error=None)
        return result
    except Exception as error:
        kind = type(error).__name__
        if isinstance(error,urllib.error.HTTPError):kind += ':' + str(error.code)
        _state(account,history_status='paused',last_error=kind)
        raise
    finally:_LOCK.release()

def _run(account,cancel):
    from .cpc_session import Client
    from .billing_history import sync_index,missing_pdfs
    ensure_database(DB);status=sync_status(account,DB);now=datetime.now(TZ)
    invoice_checked=datetime.fromisoformat(status['invoice_checked_at']) if status.get('invoice_checked_at') else None
    if invoice_checked and invoice_checked.tzinfo is None:invoice_checked=invoice_checked.replace(tzinfo=TZ)
    if not invoice_checked or (now-invoice_checked).total_seconds()>=86400:
        _state(account,history_status='invoices')
        sync_index(account)
    if cancel.is_set():return {'cancelled':True}
    status=sync_status(account,DB);client=None
    if not status.get('monthly_scanned'):
        _state(account,history_status='monthly')
        with sqlite3.connect(DB,timeout=30) as db:earliest=db.execute('SELECT MIN(year) FROM npc_invoice_index WHERE account=?',(account,)).fetchone()[0]
        client=Client(account)
        year=int(status.get('monthly_cursor') or earliest or 2010)
        for _ in range(2):
            if cancel.is_set():return {'cancelled':True}
            rows=_validate(account,client.request('https://cskh-api.cpc.vn/api/evn/tracuu/chisothang',{'MA_DVIQLY':account[:6],'MA_DDO':account+'001','TU_THANG_NAM':f'01/{year}','DEN_THANG_NAM':f'{now.month:02d}/{year}' if year==now.year else f'12/{year}'}))
            totals={}
            for row in rows:
                key=(int(row['NAM']),int(row['THANG']));totals[key]=totals.get(key,0)+float(row['DIEN_TTHU'])
            with official_transaction(account,DB) as db:
                for (y,m),value in totals.items():
                    db.execute('INSERT INTO monthly_bill(userevn,nam,thang,tien_dien,san_luong_kwh) VALUES(?,?,?,NULL,?) ON CONFLICT(userevn,thang,nam) DO UPDATE SET san_luong_kwh=excluded.san_luong_kwh',(account,y,m,str(value)))
                db.execute('UPDATE npc_sync_state SET monthly_cursor=?,monthly_scanned=? WHERE account=?',(year+1,int(year>=now.year),account))
            year+=1
            if year>now.year:break
        if year<=now.year:return {'complete':False}
    status=sync_status(account,DB)
    # Walk backwards from retained boundary; two empty windows define current API availability.
    if status.get('history_status')!='ready' and int(status.get('history_empty_windows') or 0)<2:
        client=client or Client(account)
        if status.get('history_cursor'):cursor=datetime.fromisoformat(status['history_cursor']).date()
        else:
            with sqlite3.connect(DB,timeout=30) as db:keys=[row[0] for row in db.execute("SELECT record_key FROM codex_cpc_records WHERE account=? AND kind='daily'",(account,))]
            cursor=min(datetime.strptime(k,'%d-%m-%Y').date() for k in keys)-timedelta(days=1) if keys else now.date()
        empty=int(status.get('history_empty_windows') or 0)
        for _ in range(4):
            if cancel.is_set():return {'cancelled':True}
            first=cursor-timedelta(days=14);_state(account,history_status='daily',history_cursor=cursor.isoformat())
            rows=_validate(account,client.request('https://cskh-api.cpc.vn/api/evn/tracuu/chisongay',{'MA_DVIQLY':account[:6],'MA_DDO':account+'001','TU_NGAY':first.strftime('%d/%m/%Y'),'DEN_NGAY':cursor.strftime('%d/%m/%Y')}))
            if cancel.is_set():return {'cancelled':True}
            if rows:import_days(account,rows);empty=0
            else:empty+=1
            cursor=first-timedelta(days=1)
            _state(account,history_cursor=cursor.isoformat(),history_empty_windows=empty)
            if empty>=2:break
            time.sleep(.15)
        if empty<2:
            _state(account,history_status='partial');return {'complete':False}
    if cancel.is_set():return {'cancelled':True}
    _state(account,history_status='pdf')
    progress=missing_pdfs(account,cancel,limit=8)
    if progress['pending']:return {'complete':False}
    with sqlite3.connect(DB,timeout=30) as db:keys=[row[0] for row in db.execute("SELECT record_key FROM codex_cpc_records WHERE account=? AND kind='daily'",(account,))]
    earliest=min((datetime.strptime(k,'%d-%m-%Y').date() for k in keys),default=None)
    _state(account,history_status='ready',history_first_day=earliest.isoformat() if earliest else None,last_error=None)
    return {'complete':True,'daily_since':earliest.isoformat() if earliest else None}
