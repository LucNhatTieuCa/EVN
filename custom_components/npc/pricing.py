"""Daily estimates anchored to official billing index, never the visible range."""
from .paths import data_path, auth_path

from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
import json
import math
import sqlite3
from pathlib import Path

DB = str(data_path('evndata.db'))
TIERS = [(50,1984),(50,2050),(100,2380),(100,2998),(100,3350),(None,3460)]
VAT = Decimal('0.08')

def number(value):
    try:
        n = float(value)
        return n if math.isfinite(n) and n >= 0 else None
    except (ValueError, TypeError):
        return None

def day(value):
    for fmt in ('%d/%m/%Y','%d-%m-%Y','%Y-%m-%d'):
        try:return datetime.strptime(str(value),fmt).date()
        except ValueError:pass
    return None

def total_cost(kwh, vat=VAT, tiers=TIERS):
    remaining = Decimal(str(kwh)); before_tax = Decimal(0)
    for limit,price in tiers:
        used = min(remaining,Decimal(limit)) if limit is not None else remaining
        before_tax += used * price
        remaining -= used
        if remaining <= 0:break
    return int((before_tax * (1 + vat)).quantize(Decimal('1'),rounding=ROUND_HALF_UP))

def tier_parts(before, after, vat=VAT, tiers=TIERS):
    start=Decimal(str(before));end=Decimal(str(after));lower=Decimal(0);parts=[]
    for index,(width,price) in enumerate(tiers,1):
        upper=lower+Decimal(width) if width is not None else end
        used=max(Decimal(0),min(end,upper)-max(start,lower))
        if used>0:
            parts.append({'tier':index,'kwh':float(used),'unit_before_vat':price,
                'unit_with_vat':float(Decimal(price)*(1+vat))})
        lower=upper
        if lower>=end:break
    return parts


def invoice_reference(account, bills):
    path=Path(__file__).with_name('tariff_reference.json')
    reference=json.loads(path.read_text()) if path.exists() else {}
    tiers=list(TIERS);proof=(reference.get('invoice_items') or {}).get(account)
    if proof:
        for item in proof['items']:
            index=int(item['tier'])-1
            if 0<=index<len(tiers):tiers[index]=(tiers[index][0],int(item['unit_before_vat']))
    vat=VAT;check={'status':'no_invoice','vat_source':'configured','confirmed_pdf_tiers':[x['tier'] for x in proof['items']] if proof else [],'pdf_period':proof.get('period') if proof else None,
        'official_tariff_source':reference.get('official_source'),'tariff_effective_from':reference.get('tariff_effective_from')}
    if not bills:return tiers,vat,check
    latest=max(bills,key=lambda row:(int(row.get('NAM') or 0),int(row.get('THANG') or 0)))
    net,tax,gross,used=(number(latest.get(key)) for key in ['SO_TIEN','TIEN_GTGT','TONG_TIEN','DIEN_TTHU'])
    check['invoice_period']=f"{int(latest['NAM'])}-{int(latest['THANG']):02d}"
    if net is None or tax is None or gross is None or used is None or net<=0 or abs(net+tax-gross)>2:
        check['status']='invoice_not_comparable';return tiers,vat,check
    candidates=[Decimal(str(rate)) for rate in [0,.05,.08,.1] if abs(int((Decimal(str(net))*Decimal(str(rate))).quantize(Decimal('1'),rounding=ROUND_HALF_UP))-tax)<=1]
    if len(candidates)!=1:
        check['status']='invoice_vat_unverified';return tiers,vat,check
    vat=candidates[0];check.update({'vat_source':'latest_official_invoice','invoice_total_vnd':gross,'invoice_kwh':used,'vat_percent':float(vat*100)})
    expected=total_cost(used,vat,tiers);check['expected_invoice_total_vnd']=expected
    check['status']='matched' if abs(expected-gross)<=2 else 'invoice_tariff_mismatch'
    return tiers,vat,check


def tariff_profile(account,conn=None):
    if conn is None:
        with sqlite3.connect('file:'+DB+'?mode=ro',uri=True,timeout=10) as db:return tariff_profile(account,db)
    bills=[json.loads(row[0]) for row in conn.execute("SELECT payload FROM codex_cpc_records WHERE account=? AND kind='bill'",(account,))]
    tiers,vat,check=invoice_reference(account,bills)
    return {'tiers':tiers,'vat_percent':float(vat*100),'check':check,
        'valid':check['status']=='matched'}

def estimate_profile(kwh,profile):
    if kwh is None or not profile.get('valid'):return None
    return total_cost(kwh,Decimal(str(profile['vat_percent']))/100,profile['tiers'])

def _read_prices_period(account, rf):
    with sqlite3.connect('file:'+DB+'?mode=ro',uri=True,timeout=10) as conn:
        records = {day(row.get('NGAY')): row for raw, in conn.execute(
            "SELECT payload FROM codex_cpc_records WHERE account=? AND kind='daily'",(account,)) if (row:=json.loads(raw))}
        bills=[json.loads(raw) for raw, in conn.execute("SELECT payload FROM codex_cpc_records WHERE account=? AND kind='bill'",(account,))]
    target=datetime.fromisoformat(rf['declared_period_start']).date() if rf and rf.get('declared_period_start') else None
    if target:bills=[row for row in bills if (int(row.get('NAM') or 0),int(row.get('THANG') or 0))<=(target.year,target.month)]
    tiers,vat,check=invoice_reference(account,bills)
    result={'account':account,'vat_percent':float(vat*100),'invoice_check':check,'vat_included':True,'tiers_before_vat':[{'limit_kwh':n,'vnd_per_kwh':p} for n,p in tiers],
            'daily':{},'period':None,'method':'EVN-new API month baseline; daily fee is rounded cumulative difference; invoice verifies rates'}
    if check['status']!='matched':
        result['status']='invoice_needs_verification';return result
    if not rf or not rf.get('declared_period_start') or number(rf.get('initial_reading')) is None:
        result['status']='missing_verified_billing_baseline';return result
    # Price the same API-defined month shown in EVN-new, using invoice-verified rates.
    start=datetime.fromisoformat(rf['declared_period_start']).date()
    prior=records.get(start-timedelta(days=1),{})
    baseline=number(prior.get('CHISO_MOI'))
    cutoff_at=prior.get('THOI_DIEM')
    if baseline is None or not cutoff_at:
        result['status']='missing_evn_api_baseline';return result
    end_day=datetime.fromisoformat(rf.get('read_at') or rf['declared_period_start']).date() if rf.get('read_at') else max((date for date in records if date),default=start)
    active=[(date,row) for date,row in records.items() if date and start<=date<=end_day]
    active.sort(key=lambda x:x[0]);opening=None;last=None
    for date,row in active:
        before=records.get(date-timedelta(days=1),{})
        a,b=number(before.get('CHISO_MOI')),number(row.get('CHISO_MOI'))
        factor=number(row.get('HSN') or 1);previous_factor=number(before.get('HSN') or 1)
        if a is None or b is None or b<a or a<baseline or factor!=previous_factor:
            continue
        used=round((b-a)*factor,6);cum_before=round((a-baseline)*factor,6);cum_after=round((b-baseline)*factor,6)
        fee=total_cost(cum_after,vat,tiers)-total_cost(cum_before,vat,tiers)
        key=date.strftime('%d-%m-%Y')
        result['daily'][key]={'vat_percent':float(vat*100),'kwh':used,'tier_parts':tier_parts(cum_before,cum_after,vat,tiers),'multiplier':factor,'daily_cost_vnd':fee,'average_unit_vnd':fee/used if used else 0,
            'cumulative_before_kwh':cum_before,'cumulative_after_kwh':cum_after,
            'read_at':row.get('THOI_DIEM'),'before_read_at':before.get('THOI_DIEM')}
        if opening is None:
            opening={'before_day':key,'kwh':cum_before,'estimated_vnd':total_cost(cum_before,vat,tiers),'until_read_at':before.get('THOI_DIEM')}
        last={'through_day':key,'kwh':cum_after,'estimated_vnd':total_cost(cum_after,vat,tiers),'read_at':row.get('THOI_DIEM')}
    result['period']={'declared_start':rf['declared_period_start'],'billing_cutoff_at':cutoff_at,'baseline_source':'evn_new_daily_api','baseline_index':baseline,
        'baseline_clock_verified':True,'opening':opening,'total':last}
    result['status']='ready' if result['daily'] else 'missing_daily_boundary_readings'
    return result


def read_prices(account,period):
    current=_read_prices_period(account,period)
    with sqlite3.connect('file:'+DB+'?mode=ro',uri=True,timeout=10) as db:
        dates=[day(json.loads(row[0]).get('NGAY')) for row in db.execute("SELECT payload FROM codex_cpc_records WHERE account=? AND kind='daily'",(account,))]
    months=sorted({(date.year,date.month) for date in dates if date})
    current['periods']={};current['period_checks']={};daily={}
    for year,month in months:
        start=datetime(year,month,1)
        following=datetime(year+1,1,1) if month==12 else datetime(year,month+1,1)
        # Never apply the configured2025 tariff to unverified older daily periods.
        if start<datetime(2025,5,10):continue
        row=_read_prices_period(account,{'declared_period_start':start.isoformat(),'initial_reading':0,'read_at':(following-timedelta(seconds=1)).isoformat()})
        key=f'{year}-{month:02d}'
        if row.get('period'):current['periods'][key]={**row['period'],'vat_percent':row['vat_percent']}
        current['period_checks'][key]=row['invoice_check']
        for date,value in row['daily'].items():daily[date]={**value,'period':key}
    current['daily']=daily
    return current
