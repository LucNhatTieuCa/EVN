"""Read-only initialization progress. Counts are local, never provider requests."""
from datetime import datetime
import sqlite3
from zoneinfo import ZoneInfo
from .database import DB

TZ = ZoneInfo('Asia/Ho_Chi_Minh')
LABELS = {'pending':'Đang chuẩn bị','queued':'Đang chờ lượt','invoices':'Đang lấy danh mục hóa đơn',
          'monthly':'Đang lấy lịch sử tháng','daily':'Đang lấy lịch sử ngày',
          'partial':'Đang bổ sung lịch sử ngày','pdf':'Đang tải PDF hóa đơn',
          'paused':'Tạm nghỉ, sẽ thử lại','ready':'Đã đồng bộ'}


def read(account, connection=None):
    if connection is None:
        with sqlite3.connect('file:'+DB+'?mode=ro',uri=True,timeout=10) as db:
            return read(account, db)
    db = connection
    cursor = db.execute('SELECT * FROM npc_sync_state WHERE account=?',(account,))
    row = cursor.fetchone()
    state = dict(zip((column[0] for column in cursor.description),row)) if row else {}
    total = db.execute('SELECT COUNT(*) FROM npc_invoice_index WHERE account=?',(account,)).fetchone()[0]
    downloaded = db.execute("SELECT COUNT(*) FROM npc_invoice_index i JOIN npc_invoice_files f ON f.invoice_row_id=i.id AND f.kind='HDON' WHERE i.account=?",(account,)).fetchone()[0]
    unavailable = db.execute("SELECT COUNT(*) FROM npc_invoice_index i JOIN npc_pdf_attempts a ON a.invoice_row_id=i.id LEFT JOIN npc_invoice_files f ON f.invoice_row_id=i.id AND f.kind='HDON' WHERE i.account=? AND a.status='unavailable' AND a.retry_after>? AND f.id IS NULL",(account,datetime.now(TZ).isoformat())).fetchone()[0]
    months = db.execute('SELECT COUNT(*) FROM monthly_bill WHERE userevn=?',(account,)).fetchone()[0]
    days = db.execute('SELECT COUNT(*) FROM daily_consumption WHERE userevn=?',(account,)).fetchone()[0]
    known = bool(state.get('invoice_checked_at'))
    phase = state.get('history_status') or 'pending'
    missing = max(0,total-downloaded)
    percentage = round(100*downloaded/total,1) if total else 100.0 if known else None
    label = LABELS.get(phase,'Đang chờ cập nhật')
    if phase == 'ready' and missing:
        label = 'Đã xử lý; còn PDF EVN chưa cung cấp'
    return {'account':account,'phase':phase,'label':label,'invoice_total_known':known,
            'pdf_total':total if known else None,'pdf_downloaded':downloaded,
            'pdf_remaining':missing if known else None,'pdf_pending':max(0,missing-unavailable) if known else None,
            'pdf_unavailable':unavailable,'pdf_percent':percentage,
            'months_imported':months,'days_imported':days,'monthly_complete':bool(state.get('monthly_scanned')),
            'monthly_cursor':state.get('monthly_cursor'),'daily_cursor':state.get('history_cursor'),
            'window_start':state.get('history_window_start'),'window_end':state.get('history_window_end'),
            'daily_boundary_reached':int(state.get('history_empty_windows') or 0)>=2,
            'updated_at':state.get('history_updated_at') or state.get('pdf_checked_at') or state.get('last_success'),
            'retry_at':state.get('history_retry_at'),'last_error':state.get('last_error'),
            'automatic_retry':phase=='paused' and bool(state.get('history_retry_at'))}


def sensors(account):
    progress = read(account)
    attrs = {'Giai đoạn':progress['phase'],'Đã lưu PDF':progress['pdf_downloaded'],
             'Tổng hóa đơn':progress['pdf_total'],'Còn thiếu PDF':progress['pdf_remaining'],
             'Chờ tải':progress['pdf_pending'],'EVN chưa cung cấp':progress['pdf_unavailable'],
             'Tháng đã nhập':progress['months_imported'],'Ngày đã nhập':progress['days_imported'],
             'Lịch sử tháng đã quét':progress['monthly_complete'],
             'Đã tới giới hạn lịch sử ngày':progress['daily_boundary_reached'],
             'Cập nhật tiến trình':progress['updated_at'],'Thử lại lúc':progress['retry_at'],
             'Lỗi gần nhất':progress['last_error']}
    return {'dong_bo_du_lieu':{'value':progress['label'],'attributes':attrs},
            'tien_do_tai_pdf':{'value':progress['pdf_percent'],'attributes':attrs}}


def overview(accounts, selected):
    with sqlite3.connect('file:'+DB+'?mode=ro',uri=True,timeout=10) as db:
        rows = [read(code,db) for code in sorted(accounts)]
    current = next(row for row in rows if row['account']==selected)
    known = all(row['invoice_total_known'] for row in rows)
    return {'account':current,'overall':{'accounts':len(rows),'totals_known':known,
            'pdf_downloaded':sum(row['pdf_downloaded'] for row in rows),
            'pdf_total':sum(row['pdf_total'] or 0 for row in rows) if known else None,
            'pdf_remaining':sum(row['pdf_remaining'] or 0 for row in rows) if known else None}}
