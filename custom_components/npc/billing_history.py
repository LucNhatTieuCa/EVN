"""Official invoice history and immutable private PDF cache; no RF readings."""
from .paths import data_path, auth_path

import base64,hashlib,json,math,os,sqlite3,threading,urllib.parse
from uuid import uuid4
from pathlib import Path
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
from .database import DB,official_transaction,ensure_database
ROOT=data_path('invoices')
TZ=ZoneInfo('Asia/Ho_Chi_Minh')
OFFSET=1000000000
_LOCK=threading.Lock()

def _request(account,path,payload=None):
    from .billing_session import Client
    return Client(account).request(path,payload)

def _number(value):
    try:v=float(value);return v if math.isfinite(v) and v>=0 else None
    except (TypeError,ValueError):return None

def import_index(account,rows):
    if not isinstance(rows,list):raise ValueError('Invalid invoice list')
    if any(row.get('MA_KHANG')!=account for row in rows):raise ValueError('Invoice account mismatch')
    now=datetime.now(TZ).isoformat();unique={};periods={}
    for row in rows:
        try:y,m=int(row['NAM']),int(row['THANG']);ident=str(row['ID_HDON'])
        except (KeyError,ValueError,TypeError):continue
        amount=_number(row.get('TONG_TIEN'));used=_number(row.get('DIEN_TTHU'))
        if not 1900<=y<=2200 or not 1<=m<=12 or not ident.isdigit() or amount is None:continue
        # Multiple BCS rows may share a single invoice; never count its gross twice.
        unique.setdefault(ident,(y,m,amount,used,row))
    with official_transaction(account,DB) as db:
        for ident,(y,m,amount,used,row) in unique.items():
            db.execute('INSERT INTO npc_invoice_index(account,invoice_id,year,month,amount,consumption,org_code,payload,updated_at) VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(account,invoice_id) DO UPDATE SET amount=excluded.amount,consumption=excluded.consumption,payload=excluded.payload,updated_at=excluded.updated_at',(account,ident,y,m,amount,used,account[:6],json.dumps(row),now))
            periods.setdefault((y,m),[]).append((amount,used))
        for (y,m),values in periods.items():
            amount=sum(v[0] for v in values);used=sum(v[1] for v in values) if all(v[1] is not None for v in values) else None
            old=db.execute('SELECT tien_dien FROM monthly_bill WHERE userevn=? AND nam=? AND thang=?',(account,y,m)).fetchone()
            if not old:db.execute('INSERT INTO monthly_bill(userevn,nam,thang,tien_dien,san_luong_kwh) VALUES(?,?,?,?,?)',(account,y,m,str(amount),str(used) if used is not None else None))
            elif old[0] is None or str(old[0]).strip() in ('','None','null'):db.execute('UPDATE monthly_bill SET tien_dien=? WHERE userevn=? AND nam=? AND thang=?',(str(amount),account,y,m))
            elif _number(old[0]) is not None and abs(float(old[0])-amount)>1:
                db.execute('INSERT OR REPLACE INTO npc_invoice_conflicts VALUES(?,?,?,?,?,?)',(account,y,m,float(old[0]),amount,now))
        db.execute('UPDATE npc_sync_state SET invoice_checked_at=? WHERE account=?',(now,account))
    return len(unique)

def sync_index(account):
    ensure_database(DB)
    payload=_request(account,'/api/remote/thongTinHoaDonSpider?'+urllib.parse.urlencode({'customerCode':account,'orgCode':account[:6],'maDonViQuanLy':account[:6]}))
    return import_index(account,payload.get('result'))

def _cached(row_id,kind='HDON'):
    with sqlite3.connect('file:'+DB+'?mode=ro',uri=True,timeout=10) as db:row=db.execute('SELECT path,sha256 FROM npc_invoice_files WHERE invoice_row_id=? AND kind=?',(row_id,kind)).fetchone()
    if not row:return None
    path=(ROOT/row[0]).resolve()
    if not path.is_relative_to(ROOT.resolve()):raise ValueError('Invalid private PDF path')
    if not path.exists():return None
    data=path.read_bytes()
    if hashlib.sha256(data).hexdigest()!=row[1]:raise ValueError('PDF cache integrity mismatch')
    return data

def ensure_pdf(account,row_id):
    with _LOCK:
        with sqlite3.connect('file:'+DB+'?mode=ro',uri=True,timeout=10) as db:
            row=db.execute('SELECT invoice_id,year,month,org_code FROM npc_invoice_index WHERE account=? AND id=?',(account,row_id)).fetchone()
        if not row:return None
        ident,year,month,org=row;data=_cached(row_id)
        if data:return year,month,data
        payload=_request(account,'/api/remote/invoice/file/pdf',{'orgCode':org,'billId':ident,'customerCode':account,'fileType':'HDON'})
        if not isinstance(payload,dict) or not payload.get('pdf'):return None
        for field,kind in [('pdf','HDON'),('pdfDetail','DETAIL')]:
            value=payload.get(field)
            if not value:continue
            encoded=str(value).split('base64,')[-1]
            content=base64.b64decode(''.join(encoded.split()),validate=True)
            if not content.startswith(b'%PDF-'):raise ValueError('Provider did not return PDF')
            digest=hashlib.sha256(content).hexdigest();relative=f'{account}/{digest}.pdf';target=ROOT/relative;target.parent.mkdir(parents=True,exist_ok=True)
            if target.exists():
                if hashlib.sha256(target.read_bytes()).hexdigest()!=digest:raise ValueError('Existing PDF integrity mismatch')
            else:
                temp=target.with_name(target.name+'.part-'+uuid4().hex)
                try:
                    with temp.open('xb') as stream:stream.write(content);stream.flush();os.fsync(stream.fileno())
                    temp.chmod(0o444)
                    try:os.link(temp,target)
                    except FileExistsError:
                        if hashlib.sha256(target.read_bytes()).hexdigest()!=digest:raise ValueError('PDF collision')
                finally:temp.unlink(missing_ok=True)
            with sqlite3.connect(DB,timeout=30) as db:db.execute('INSERT INTO npc_invoice_files(invoice_row_id,kind,path,sha256,size_bytes,fetched_at) VALUES(?,?,?,?,?,?) ON CONFLICT(invoice_row_id,kind) DO UPDATE SET path=excluded.path,sha256=excluded.sha256,size_bytes=excluded.size_bytes,fetched_at=excluded.fetched_at',(row_id,kind,relative,digest,len(content),datetime.now(TZ).isoformat()))
            if kind=='HDON':data=content
        return year,month,data

def pdf_progress(account):
    with sqlite3.connect('file:'+DB+'?mode=ro',uri=True,timeout=10) as db:
        total=db.execute('SELECT COUNT(*) FROM npc_invoice_index WHERE account=?',(account,)).fetchone()[0]
        done=db.execute("SELECT COUNT(*) FROM npc_invoice_index i JOIN npc_invoice_files f ON i.id=f.invoice_row_id AND f.kind='HDON' WHERE i.account=?",(account,)).fetchone()[0]
        unavailable=db.execute("SELECT COUNT(*) FROM npc_invoice_index i JOIN npc_pdf_attempts a ON i.id=a.invoice_row_id WHERE i.account=? AND a.status='unavailable' AND a.retry_after>?",(account,datetime.now(TZ).isoformat())).fetchone()[0]
    return {'total':total,'downloaded':done,'unavailable':unavailable,'pending':max(0,total-done-unavailable)}


def missing_pdfs(account,cancel,limit=8):
    now=datetime.now(TZ)
    with sqlite3.connect('file:'+DB+'?mode=ro',uri=True,timeout=10) as db:
        ids=[row[0] for row in db.execute("SELECT i.id FROM npc_invoice_index i LEFT JOIN npc_invoice_files f ON f.invoice_row_id=i.id AND f.kind='HDON' LEFT JOIN npc_pdf_attempts a ON a.invoice_row_id=i.id WHERE i.account=? AND f.id IS NULL AND (a.retry_after IS NULL OR a.retry_after<=?) ORDER BY i.year DESC,i.month DESC,i.id DESC LIMIT ?",(account,now.isoformat(),limit))]
    for ident in ids:
        if cancel.is_set():return pdf_progress(account)
        result=ensure_pdf(account,ident)
        checked=datetime.now(TZ)
        with sqlite3.connect(DB,timeout=30) as db:
            db.execute('INSERT OR REPLACE INTO npc_pdf_attempts VALUES(?,?,?,?)',(ident,'downloaded' if result else 'unavailable',None if result else (checked+timedelta(days=7)).isoformat(),checked.isoformat()))
    with sqlite3.connect(DB,timeout=30) as db:db.execute('UPDATE npc_sync_state SET pdf_checked_at=? WHERE account=?',(datetime.now(TZ).isoformat(),account))
    return pdf_progress(account)
