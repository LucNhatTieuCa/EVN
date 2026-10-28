"""Display names only; never create or alter a meter/account mapping."""
from .paths import data_path, auth_path

import json,sqlite3,unicodedata
DB=str(data_path('evndata.db'))

def clean_name(value):
    if not isinstance(value,str):raise ValueError('Tên khách hàng phải là văn bản')
    value=value.strip()
    if len(value)>80 or any(unicodedata.category(c).startswith('C') for c in value):raise ValueError('Tên tối đa 80 ký tự, không chứa ký tự điều khiển')
    return value

def official_names(accounts):
    names={}
    with sqlite3.connect('file:'+DB+'?mode=ro',uri=True,timeout=10) as db:
        for account in accounts:
            row=db.execute('SELECT payload FROM npc_invoice_index WHERE account=? ORDER BY year DESC,month DESC,id DESC LIMIT 1',(account,)).fetchone()
            if row:
                raw=json.loads(row[0]);name=raw.get('TEN_KHANG')
                if isinstance(name,str):names[account]=''.join(c for c in name.strip() if not unicodedata.category(c).startswith('C'))[:160]
    return names

def label(account,aliases,official):
    alias=aliases.get(account,'')
    if not isinstance(alias,str):alias=''
    return {'account':account,'custom_name':alias,'official_name':official.get(account,''),'name':alias or official.get(account) or account}
