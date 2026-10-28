"""Integration-owned, additive SQLite schema and read-only sync metadata."""
from .paths import data_path, auth_path

from pathlib import Path
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo
DB=str(data_path('evndata.db'))
TZ=ZoneInfo('Asia/Ho_Chi_Minh')
SCHEMA_VERSION=1
TABLES=['CREATE TABLE daily_consumption (\n\t\tid INTEGER PRIMARY KEY AUTOINCREMENT,\n\t\tuserevn TEXT,\n\t\tngay TEXT,\n\t\tchi_so TEXT,\n\t\tdien_tieu_thu_kwh TEXT,\n\t\tUNIQUE(userevn, ngay)\n\t)', 'CREATE TABLE monthly_bill (\n\t\tid INTEGER PRIMARY KEY AUTOINCREMENT,\n\t\tuserevn TEXT,\n\t\tthang INTEGER,\n\t\tnam INTEGER,\n\t\ttien_dien TEXT,\n\t\tsan_luong_kwh TEXT,\n\t\tUNIQUE(userevn, thang, nam)\n\t)', 'CREATE TABLE hoadon_pdf (\n\t\tid INTEGER PRIMARY KEY AUTOINCREMENT,\n\t\tuserevn TEXT,\n\t\tthang INTEGER,\n\t\tnam INTEGER,\n\t\tpdf BLOB,\n\t\tUNIQUE(userevn, thang, nam)\n\t)', 'CREATE TABLE codex_cpc_writer(account TEXT PRIMARY KEY,active INTEGER NOT NULL)', 'CREATE TABLE codex_cpc_records(account TEXT,kind TEXT,record_key TEXT,payload TEXT,fetched_at TEXT,PRIMARY KEY(account,kind,record_key))']

def ensure_database(path=None):
    target=path or DB
    Path(target).parent.mkdir(parents=True,exist_ok=True)
    with sqlite3.connect(target,timeout=30) as db:
        # Serialize the complete read/ALTER migration across simultaneous entries/processes.
        db.execute('BEGIN IMMEDIATE')
        for sql in TABLES:db.execute(sql.replace('CREATE TABLE ', 'CREATE TABLE IF NOT EXISTS ',1))
        db.execute('CREATE TABLE IF NOT EXISTS npc_schema(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)')
        db.execute("CREATE TABLE IF NOT EXISTS npc_sync_state(account TEXT PRIMARY KEY,last_attempt TEXT,last_success TEXT,daily_watermark TEXT,monthly_scanned INTEGER DEFAULT 0,history_cursor TEXT,history_status TEXT DEFAULT 'pending',last_error TEXT,reconciled_at TEXT,invoice_checked_at TEXT,pdf_checked_at TEXT)")
        db.execute("CREATE TABLE IF NOT EXISTS npc_invoice_index(id INTEGER PRIMARY KEY AUTOINCREMENT,account TEXT NOT NULL,invoice_id TEXT NOT NULL,year INTEGER NOT NULL,month INTEGER NOT NULL,amount REAL,consumption REAL,org_code TEXT NOT NULL,payload TEXT NOT NULL,updated_at TEXT NOT NULL,UNIQUE(account,invoice_id))")
        db.execute("CREATE TABLE IF NOT EXISTS npc_invoice_files(id INTEGER PRIMARY KEY AUTOINCREMENT,invoice_row_id INTEGER NOT NULL,kind TEXT NOT NULL,path TEXT NOT NULL,sha256 TEXT NOT NULL,size_bytes INTEGER NOT NULL,fetched_at TEXT NOT NULL,UNIQUE(invoice_row_id,kind))")
        db.execute('CREATE TABLE IF NOT EXISTS npc_invoice_conflicts(account TEXT,year INTEGER,month INTEGER,current_amount REAL,incoming_amount REAL,seen_at TEXT,PRIMARY KEY(account,year,month))')
        db.execute("CREATE TABLE IF NOT EXISTS npc_pdf_attempts(invoice_row_id INTEGER PRIMARY KEY,status TEXT NOT NULL,retry_after TEXT,checked_at TEXT NOT NULL)")
        db.execute('CREATE TABLE IF NOT EXISTS npc_entity_ids(unique_id TEXT PRIMARY KEY,entity_id TEXT NOT NULL)')
        columns={row[1] for row in db.execute('PRAGMA table_info(npc_sync_state)')}
        for name,definition in [('history_empty_windows','INTEGER DEFAULT 0'),('history_first_day','TEXT'),('monthly_cursor','INTEGER'),('history_updated_at','TEXT'),('history_retry_at','TEXT'),('history_window_start','TEXT'),('history_window_end','TEXT')]:
            if name not in columns:db.execute('ALTER TABLE npc_sync_state ADD COLUMN '+name+' '+definition)
        db.execute('INSERT OR IGNORE INTO npc_schema VALUES(?,?)',(SCHEMA_VERSION,datetime.now(TZ).isoformat()))

def sync_status(account,path=None):
    try:
        with sqlite3.connect('file:'+(path or DB)+'?mode=ro',uri=True,timeout=10) as db:
            db.row_factory=sqlite3.Row
            row=db.execute('SELECT * FROM npc_sync_state WHERE account=?',(account,)).fetchone()
            return dict(row) if row else {'account':account,'history_status':'pending'}
    except sqlite3.OperationalError:
        return {'account':account,'history_status':'pending'}


from contextlib import contextmanager
@contextmanager
def official_transaction(account,path=None):
    with sqlite3.connect(path or DB,timeout=30) as db:
        db.execute('INSERT OR IGNORE INTO codex_cpc_writer VALUES(?,0)',(account,))
        db.execute('UPDATE codex_cpc_writer SET active=1 WHERE account=?',(account,))
        yield db
        db.execute('UPDATE codex_cpc_writer SET active=0 WHERE account=?',(account,))


def save_entity_ids(mapping):
    if not mapping:return
    with sqlite3.connect(DB,timeout=30) as db:
        for unique,entity in mapping.items():
            existing=db.execute('SELECT entity_id FROM npc_entity_ids WHERE unique_id=?',(unique,)).fetchone()
            if not existing or existing[0]!=entity:db.execute('INSERT OR REPLACE INTO npc_entity_ids VALUES(?,?)',(unique,entity))

def entity_ids(account):
    with sqlite3.connect('file:'+DB+'?mode=ro',uri=True,timeout=10) as db:
        return {key:value for key,value in db.execute('SELECT unique_id,entity_id FROM npc_entity_ids') if key.startswith(account+'_')}
