"""Authenticated CPC source; preserve old bills, never synthesize missing days."""
from .paths import data_path, auth_path

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

AUTH = auth_path()
DB = str(data_path('evndata.db'))


def supports(account):
    if not AUTH.exists():
        return False
    root = json.loads(AUTH.read_text())
    return account in root.get('accounts', {}) or root.get('customer_id') == account


def _sync(account):
    """Run wholly in an executor; SQLite commits the complete update atomically."""
    from .database import ensure_database
    ensure_database(DB)
    from .cpc_session import Client
    client=Client(account,AUTH)
    request=client.request
    from zoneinfo import ZoneInfo
    now = datetime.now(ZoneInfo('Asia/Ho_Chi_Minh'))
    start = now.replace(day=1) - timedelta(days=1)
    from .database import sync_status
    status=sync_status(account,DB)
    if status.get('daily_watermark'):
        watermark=datetime.fromisoformat(status['daily_watermark']).replace(tzinfo=now.tzinfo)
        reconciled=datetime.fromisoformat(status['reconciled_at']) if status.get('reconciled_at') else None
        if reconciled and reconciled.tzinfo is None:reconciled=reconciled.replace(tzinfo=now.tzinfo)
        if reconciled and (now-reconciled).total_seconds()<86400:
            start=max(start,watermark-timedelta(days=2))
    full_reconcile=start.date()==(now.replace(day=1)-timedelta(days=1)).date()
    days = []
    while start.date() <= now.date():
        end = min(start + timedelta(days=14), now)
        rows = request('https://cskh-api.cpc.vn/api/evn/tracuu/chisongay', {
            'MA_DVIQLY': account[:6], 'MA_DDO': account + '001',
            'TU_NGAY': start.strftime('%d/%m/%Y'), 'DEN_NGAY': end.strftime('%d/%m/%Y')})
        if not isinstance(rows, list):
            raise ValueError('Unexpected CPC daily response')
        days.extend(rows)
        start = end + timedelta(days=1)
    if not days:
        raise ValueError('No current CPC daily data')
    bills = request('https://cskh-api.cpc.vn/api/evn/tracuu/hoadon', {})
    for row in days + bills:
        if row.get('MA_KHANG') and row['MA_KHANG'] != account:
            raise ValueError('CPC response account mismatch')
    fetched = now.isoformat()
    with sqlite3.connect(DB, timeout=30) as db:
        db.execute('CREATE TABLE IF NOT EXISTS codex_cpc_writer(account TEXT PRIMARY KEY,active INTEGER NOT NULL)')
        db.execute('INSERT OR IGNORE INTO codex_cpc_writer VALUES(?,0)', (account,))
        db.execute('UPDATE codex_cpc_writer SET active=1 WHERE account=?', (account,))
        # Preserve installed writer guards while the native transaction commits.
        if not account.isalnum():
            raise ValueError('Invalid account identifier')
        for table in ['daily_consumption', 'monthly_bill']:
            for operation in ['INSERT', 'UPDATE', 'DELETE']:
                row = 'OLD' if operation == 'DELETE' else 'NEW'
                trigger = 'codex_cpc_' + account + '_' + table + '_' + operation
                sql = (f"CREATE TRIGGER IF NOT EXISTS {trigger} BEFORE {operation} ON {table} "
                       f"WHEN {row}.userevn='{account}' AND COALESCE((SELECT active FROM codex_cpc_writer WHERE account='{account}'),0)=0 "
                       "BEGIN SELECT RAISE(IGNORE); END")
                db.execute(sql)
        db.execute('CREATE TABLE IF NOT EXISTS codex_cpc_records(account TEXT,kind TEXT,record_key TEXT,payload TEXT,fetched_at TEXT,PRIMARY KEY(account,kind,record_key))')
        initialized = db.execute("SELECT 1 FROM codex_cpc_records WHERE account=? AND kind='initialized'", (account,)).fetchone()
        stored=[json.loads(row[0]) for row in db.execute("SELECT payload FROM codex_cpc_records WHERE account=? AND kind='daily'",(account,))]
        unique = {row['NGAY']: row for row in stored+days}
        ordered = sorted(unique.values(), key=lambda row: datetime.strptime(row['NGAY'], '%d/%m/%Y'))
        previous = None
        changed={row['NGAY'] for row in days}
        for row in ordered:
            when = datetime.strptime(row['NGAY'], '%d/%m/%Y')
            reading = float(row['CHISO_MOI'])
            production = None
            if previous and (when - previous[0]).days == 1 and float(row.get('HSN') or 1)==previous[2]:
                production = round((reading - previous[1]) * float(row.get('HSN') or 1), 6)
                if production < 0:
                    raise ValueError('CPC meter reset needs review')
            if row['NGAY'] not in changed:
                previous=when,reading,float(row.get('HSN') or 1)
                continue
            day = when.strftime('%d-%m-%Y')
            db.execute('INSERT OR REPLACE INTO codex_cpc_records VALUES(?,?,?,?,?)', (account, 'daily', day, json.dumps(row), fetched))
            existing = db.execute('SELECT 1 FROM daily_consumption WHERE userevn=? AND ngay=?', (account, day)).fetchone()
            if existing:
                if initialized and production is None:
                    prior = db.execute('SELECT dien_tieu_thu_kwh FROM daily_consumption WHERE userevn=? AND ngay=?', (account, day)).fetchone()[0]
                    production = float(prior) if prior is not None else None
                db.execute('UPDATE daily_consumption SET chi_so=?,dien_tieu_thu_kwh=? WHERE userevn=? AND ngay=?', (str(reading), str(production) if production is not None else None, account, day))
            else:
                db.execute('INSERT INTO daily_consumption(userevn,ngay,chi_so,dien_tieu_thu_kwh) VALUES(?,?,?,?)', (account, day, str(reading), str(production) if production is not None else None))
            previous = when, reading, float(row.get('HSN') or 1)
        for row in bills:
            if row.get('MA_KHANG') and row['MA_KHANG'] != account:
                continue
            year, month = int(row['NAM']), int(row['THANG'])
            exists = db.execute('SELECT 1 FROM monthly_bill WHERE userevn=? AND nam=? AND thang=?', (account, year, month)).fetchone()
            if exists:
                db.execute('UPDATE monthly_bill SET tien_dien=?,san_luong_kwh=? WHERE userevn=? AND nam=? AND thang=?', (str(row['TONG_TIEN']), str(row['DIEN_TTHU']), account, year, month))
            else:
                db.execute('INSERT INTO monthly_bill(userevn,nam,thang,tien_dien,san_luong_kwh) VALUES(?,?,?,?,?)', (account, year, month, str(row['TONG_TIEN']), str(row['DIEN_TTHU'])))
            db.execute('INSERT OR REPLACE INTO codex_cpc_records VALUES(?,?,?,?,?)', (account, 'bill', f'{year}-{month:02d}', json.dumps(row), fetched))
        db.execute('INSERT OR REPLACE INTO codex_cpc_records VALUES(?,?,?,?,?)', (account, 'initialized', '1', '{}', fetched))
        db.execute("INSERT INTO npc_sync_state(account,last_attempt,last_success,daily_watermark,history_status,last_error) VALUES(?,?,?,?,?,NULL) ON CONFLICT(account) DO UPDATE SET last_attempt=excluded.last_attempt,last_success=excluded.last_success,daily_watermark=excluded.daily_watermark,last_error=NULL",(account,fetched,fetched,previous[0].date().isoformat(),'pending'))
        if full_reconcile:
            db.execute('UPDATE npc_sync_state SET reconciled_at=? WHERE account=?',(fetched,account))
        db.execute('UPDATE codex_cpc_writer SET active=0 WHERE account=?', (account,))
    return {'source': 'authenticated CPC', 'latest_day': previous[0].isoformat(), 'fetched_at': fetched}


def sync(account):
    from .database import ensure_database
    from datetime import datetime
    from zoneinfo import ZoneInfo
    ensure_database(DB)
    attempted=datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).isoformat()
    with sqlite3.connect(DB,timeout=30) as db:
        db.execute('INSERT OR IGNORE INTO npc_sync_state(account) VALUES(?)',(account,))
        db.execute('UPDATE npc_sync_state SET last_attempt=? WHERE account=?',(attempted,account))
    try:return _sync(account)
    except Exception as error:
        with sqlite3.connect(DB,timeout=30) as db:db.execute('UPDATE npc_sync_state SET last_error=? WHERE account=?',(type(error).__name__,account))
        raise
