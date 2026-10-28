"""Authenticated access to EVN PDF documents already stored in SQLite."""
from .paths import data_path, auth_path

import sqlite3
from aiohttp import web
from homeassistant.components.http import HomeAssistantView
DB = str(data_path('evndata.db'))

def catalog(account,include_id=None):
    from .billing_history import OFFSET
    periods={}
    with sqlite3.connect('file:'+DB+'?mode=ro',uri=True,timeout=10) as db:
        legacy=db.execute("SELECT id,CAST(nam AS INTEGER),CAST(thang AS INTEGER),length(pdf) FROM hoadon_pdf WHERE userevn=? AND typeof(pdf)='blob' AND substr(pdf,1,5)=? ORDER BY nam DESC,thang DESC,id DESC",(account,b'%PDF-')).fetchall()
        for i,y,m,size in legacy:
            if 1<=m<=12 and 1900<=y<=2200:periods.setdefault((y,m),{'id':i,'year':y,'month':m,'bytes':size,'cached':True,'kind':'stored_notice'})
        native=db.execute("SELECT n.id,n.year,n.month,f.size_bytes FROM npc_invoice_index n LEFT JOIN npc_invoice_files f ON f.invoice_row_id=n.id AND f.kind='HDON' WHERE n.account=? ORDER BY n.year DESC,n.month DESC,n.id DESC",(account,)).fetchall()
        for i,y,m,size in native:
            if size is not None or (y,m) not in periods:periods[(y,m)]={'id':OFFSET+i,'year':y,'month':m,'bytes':size,'cached':size is not None,'kind':'official_invoice'}
        rows=[periods[key] for key in sorted(periods,reverse=True)]
        if include_id and include_id<OFFSET and not any(r['id']==include_id for r in rows):
            old=next((r for r in legacy if r[0]==include_id),None)
            if old:rows.append({'id':old[0],'year':old[1],'month':old[2],'bytes':old[3],'cached':True,'kind':'stored_notice'})
    return rows

def document(account,invoice_id):
    from .billing_history import OFFSET,ensure_pdf
    if invoice_id>=OFFSET:return ensure_pdf(account,invoice_id-OFFSET)
    with sqlite3.connect('file:'+DB+'?mode=ro',uri=True,timeout=10) as db:
        row=db.execute('SELECT nam,thang,pdf FROM hoadon_pdf WHERE userevn=? AND id=?',(account,invoice_id)).fetchone()
    if not row or not isinstance(row[2],bytes) or not row[2].startswith(b'%PDF-'):return None
    return int(row[0]),int(row[1]),row[2]

class InvoiceCatalogView(HomeAssistantView):
    url='/api/npc/invoices/{account}'
    name='api:npc:invoices'
    requires_auth=True
    def __init__(self,manager):self.manager=manager
    async def get(self,request,account):
        if account not in self.manager.accounts():raise web.HTTPNotFound()
        try:include_id=int(request.query.get('include','0'))
        except ValueError:include_id=0
        rows=await self.manager.hass.async_add_executor_job(catalog,account,include_id)
        return web.json_response({'account':account,'invoices':rows,'source':'stored_evn_pdf'},headers={'Cache-Control':'private, no-store'})

class InvoicePDFView(HomeAssistantView):
    url='/api/npc/invoice/{account}/{invoice_id}'
    name='api:npc:invoice:pdf'
    requires_auth=True
    def __init__(self,manager):self.manager=manager
    async def get(self,request,account,invoice_id):
        if account not in self.manager.accounts():raise web.HTTPNotFound()
        try:ident=int(invoice_id)
        except (ValueError,TypeError):raise web.HTTPNotFound()
        row=await self.manager.hass.async_add_executor_job(document,account,ident)
        if row is None:raise web.HTTPNotFound()
        year,month,body=row
        filename=f'EVN-{year}-{month:02d}-{ident}.pdf'
        return web.Response(body=body,content_type='application/pdf',headers={'Content-Disposition':f'inline; filename="{filename}"','Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'})
