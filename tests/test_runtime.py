"""Offline behavioral tests; no real EVN credentials, network or HA configuration."""
import asyncio
import base64
import importlib
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import types
import unittest
from unittest.mock import patch
import urllib.error

ROOT = Path(__file__).resolve().parents[1] / 'custom_components/npc'
pkg=types.ModuleType('evn_test');pkg.__path__=[str(ROOT)];sys.modules['evn_test']=pkg

def module(name):return importlib.import_module('evn_test.'+name)

class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.db=module('database');self.db.DB=str(self.root/'data.db');self.db.ensure_database()
        self.billing=module('billing_history');self.billing.DB=self.db.DB;self.billing.ROOT=self.root/'invoices'
        self.history=module('history_worker');self.history.DB=self.db.DB
        with sqlite3.connect(self.db.DB) as db:db.execute("INSERT INTO npc_sync_state(account) VALUES('PCDEMO12345')")
    def tearDown(self):self.temp.cleanup()

    def invoice(self, ident='1', month=1):
        self.billing.import_index('PCDEMO12345',[{'MA_KHANG':'PCDEMO12345','NAM':2026,'THANG':month,'ID_HDON':ident,'TONG_TIEN':100,'DIEN_TTHU':1}])

    def test_all_pdfs_checkpoint_skip_cached_and_unavailable(self):
        for n in range(1,4):self.invoice(str(n),n)
        data=base64.b64encode(b'%PDF-1.4\nfixture').decode()
        calls=[]
        def fetch(account,path,payload):
            calls.append(payload['billId']);return {} if payload['billId']=='2' else {'pdf':data,'pdfDetail':data}
        with patch.object(self.billing,'_request',fetch):
            a=self.billing.missing_pdfs('PCDEMO12345',threading.Event(),limit=1)
            self.assertEqual(a,{'total':3,'downloaded':1,'unavailable':0,'pending':2})
            b=self.billing.missing_pdfs('PCDEMO12345',threading.Event(),limit=8)
            self.assertEqual(b,{'total':3,'downloaded':2,'unavailable':1,'pending':0})
            self.billing.missing_pdfs('PCDEMO12345',threading.Event(),limit=8)
        self.assertEqual(calls,['3','2','1'])
        self.assertEqual(len(list(self.billing.ROOT.rglob('*.pdf'))),1) # identical bytes content-addressed per customer
        self.invoice('4',4)
        self.assertEqual(self.billing.pdf_progress('PCDEMO12345')['pending'],1)

    def test_pdf_error_does_not_checkpoint_false_success(self):
        self.invoice()
        with patch.object(self.billing,'_request',side_effect=OSError('provider down')):
            with self.assertRaises(OSError):self.billing.missing_pdfs('PCDEMO12345',threading.Event())
        self.assertEqual(self.billing.pdf_progress('PCDEMO12345')['pending'],1)

    def test_monthly_scan_bounded_and_resumes_after_restart(self):
        self.invoice()
        year=self.history.datetime.now(self.history.TZ).year
        with sqlite3.connect(self.db.DB) as db:
            db.execute("UPDATE npc_invoice_index SET year=?",(year-2,))
        calls=[]
        fake=types.ModuleType('evn_test.cpc_session')
        class Client:
            def __init__(self,account):pass
            def request(self,url,payload):calls.append(payload);return []
        fake.Client=Client
        with patch.dict(sys.modules,{'evn_test.cpc_session':fake}),patch.object(self.billing,'sync_index',return_value=1):
            a=self.history.run('PCDEMO12345',threading.Event())
            self.assertFalse(a['complete']);self.assertEqual(len(calls),2)
            self.assertEqual(self.db.sync_status('PCDEMO12345')['monthly_cursor'],year)
            with patch.object(self.billing,'missing_pdfs',return_value={'pending':0}):
                b=self.history.run('PCDEMO12345',threading.Event())
            self.assertTrue(b['complete'])
        self.assertEqual(calls[2]['TU_THANG_NAM'],f'01/{year}')
        self.assertEqual(self.db.sync_status('PCDEMO12345')['history_status'],'ready')

    def test_cancel_before_start_no_requests(self):
        cancel=threading.Event();cancel.set()
        self.assertTrue(self.history.run('PCDEMO12345',cancel)['cancelled'])

    def test_daily_import_preserves_gaps_not_zero(self):
        rows=[{'NGAY':'01/10/2026','CHISO_MOI':100,'HSN':1},{'NGAY':'02/10/2026','CHISO_MOI':110,'HSN':1},{'NGAY':'04/10/2026','CHISO_MOI':130,'HSN':1}]
        self.history.import_days('PCDEMO12345',rows)
        with sqlite3.connect(self.db.DB) as db:values=[r[0] for r in db.execute('SELECT dien_tieu_thu_kwh FROM daily_consumption ORDER BY ngay')]
        self.assertEqual(values,[None,'10.0',None])

    def test_tiers_vat_and_incremental_day(self):
        pricing=module('pricing')
        self.assertEqual(pricing.tier_parts(95,105),[{'tier':2,'kwh':5.0,'unit_before_vat':2050,'unit_with_vat':2214.0},{'tier':3,'kwh':5.0,'unit_before_vat':2380,'unit_with_vat':2570.4}])
        chunks=[10,40,45,10,100]
        cumulative=0;fees=[]
        for used in chunks:
            fees.append(pricing.total_cost(cumulative+used)-pricing.total_cost(cumulative));cumulative+=used
        self.assertEqual(sum(fees),pricing.total_cost(sum(chunks)))
        self.assertEqual(pricing.invoice_reference('PCDEMO12345',[])[2]['status'],'no_invoice')

    def test_fresh_schema_migration_repeat_integrity(self):
        for _ in range(3):self.db.ensure_database()
        with sqlite3.connect(self.db.DB) as db:self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')

    def test_migration_concurrent_accounts(self):
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda n:self.db.ensure_database(),range(12)))
        with sqlite3.connect(self.db.DB) as db:self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')

    def test_unverified_tariff_not_presented_as_money(self):
        pricing=module('pricing')
        with patch.object(pricing,'DB',self.db.DB):
            self.assertFalse(pricing.tariff_profile('PCDEMO12345')['valid'])
            bill={'NAM':2026,'THANG':9,'SO_TIEN':113550,'TIEN_GTGT':9084,'TONG_TIEN':122634,'DIEN_TTHU':57}
            with sqlite3.connect(self.db.DB) as db:
                db.execute('INSERT INTO codex_cpc_records VALUES(?,?,?,?,?)',('PCDEMO12345','bill','2026-09',json.dumps(bill),'fixture'))
            self.assertTrue(pricing.tariff_profile('PCDEMO12345')['valid'])
            bill.update(SO_TIEN=200000,TIEN_GTGT=16000,TONG_TIEN=216000)
            with sqlite3.connect(self.db.DB) as db:db.execute("UPDATE codex_cpc_records SET payload=? WHERE kind='bill'",(json.dumps(bill),))
            self.assertFalse(pricing.tariff_profile('PCDEMO12345')['valid'])

class TransportTests(unittest.TestCase):
    def setUp(self):
        self.policy=module('request_policy');self.policy._next_request=0;self.policy._cooldown=0
        self.now=1000.0
    def clock(self):return self.now
    def sleep(self,n):self.now+=n
    def success(self,*args,**kw):return io.BytesIO(b'{"ok":true}')
    def test_global_spacing(self):
        times=[]
        def request(*a,**kw):times.append(self.now);return self.success()
        with patch.object(self.policy.time,'monotonic',self.clock),patch.object(self.policy.time,'sleep',self.sleep),patch.object(self.policy.urllib.request,'urlopen',request):
            self.policy.request_json('x');self.policy.request_json('y')
        self.assertGreaterEqual(times[1]-times[0],2)
    def test_429_honors_shared_cooldown_no_retry_storm(self):
        error=urllib.error.HTTPError('x',429,'limited',{'Retry-After':'120'},None)
        with patch.object(self.policy.time,'monotonic',self.clock),patch.object(self.policy.urllib.request,'urlopen',side_effect=error) as call:
            with self.assertRaises(self.policy.ProviderCooldown):self.policy.request_json('x')
            with self.assertRaises(self.policy.ProviderCooldown):self.policy.request_json('y')
            self.assertEqual(call.call_count,1);self.assertEqual(self.policy._cooldown,1120)
    def test_403_not_retried(self):
        error=urllib.error.HTTPError('x',403,'forbidden',{},None)
        with patch.object(self.policy.urllib.request,'urlopen',side_effect=error) as call:
            with self.assertRaises(urllib.error.HTTPError):self.policy.request_json('x')
            self.assertEqual(call.call_count,1)
    def test_transient_error_retries_bounded(self):
        error=urllib.error.HTTPError('x',503,'down',{},None)
        with patch.object(self.policy.time,'monotonic',self.clock),patch.object(self.policy.time,'sleep',self.sleep),patch.object(self.policy.urllib.request,'urlopen',side_effect=[error,self.success()]) as call:
            self.assertEqual(self.policy.request_json('x'),{'ok':True});self.assertEqual(call.call_count,2)
    def test_response_size_bounded(self):
        with patch.object(self.policy,'MAX_RESPONSE_BYTES',4),patch.object(self.policy.urllib.request,'urlopen',self.success):
            with self.assertRaises(ValueError):self.policy.request_json('x')

if __name__=='__main__':unittest.main()
