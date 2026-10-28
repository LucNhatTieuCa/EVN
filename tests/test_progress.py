"""Progress counts, unavailable documents, retry metadata and local-only publishing."""
import ast
import asyncio
from datetime import datetime,timedelta
import logging
import sqlite3
import sys
import threading
import types
import unittest
from unittest.mock import patch
import test_runtime
from test_removal_worker import BaseCoordinator

class ProgressTests(unittest.TestCase):
    def setUp(self):
        self.fixture=test_runtime.RuntimeTests();self.fixture.setUp()
        self.db=self.fixture.db;self.module=test_runtime.module('sync_progress')
        self.patch=patch.object(self.module,'DB',self.db.DB);self.patch.start()
    def tearDown(self):self.patch.stop();self.fixture.tearDown()
    def test_total_unknown_is_not_zero_percent_or_complete(self):
        p=self.module.read('PCDEMO12345')
        self.assertIsNone(p['pdf_total']);self.assertIsNone(p['pdf_percent']);self.assertIsNone(p['pdf_remaining'])
    def test_known_empty_catalog_has_no_missing_documents(self):
        self.fixture.billing.import_index('PCDEMO12345',[])
        p=self.module.read('PCDEMO12345')
        self.assertEqual(p['pdf_total'],0);self.assertEqual(p['pdf_percent'],100);self.assertEqual(p['pdf_remaining'],0)
    def test_unavailable_is_not_downloaded_or_100_percent(self):
        for n in range(1,4):self.fixture.invoice(str(n),n)
        with sqlite3.connect(self.db.DB) as db:
            ids=[row[0] for row in db.execute('SELECT id FROM npc_invoice_index ORDER BY id')]
            db.execute("INSERT INTO npc_invoice_files(invoice_row_id,kind,path,sha256,size_bytes,fetched_at) VALUES(?,'HDON','fixture.pdf','fixture',12,'fixture')",(ids[0],))
            db.execute("INSERT INTO npc_pdf_attempts VALUES(?,'unavailable',?,'fixture')",(ids[1],(datetime.now(self.module.TZ)+timedelta(days=7)).isoformat()))
            db.execute("UPDATE npc_sync_state SET history_status='paused',history_retry_at='2099-01-01T00:00:00+07:00',last_error='ProviderCooldown:429'")
        p=self.module.read('PCDEMO12345')
        self.assertEqual((p['pdf_downloaded'],p['pdf_total'],p['pdf_remaining'],p['pdf_pending'],p['pdf_unavailable']),(1,3,2,1,1))
        self.assertEqual(p['pdf_percent'],33.3);self.assertTrue(p['automatic_retry'])
        self.assertEqual(self.module.sensors('PCDEMO12345')['dong_bo_du_lieu']['attributes']['Còn thiếu PDF'],2)
    def test_overall_does_not_claim_all_totals_known_early(self):
        self.fixture.invoice()
        with sqlite3.connect(self.db.DB) as db:db.execute("INSERT INTO npc_sync_state(account) VALUES('PCSECOND1234')")
        data=self.module.overview({'PCDEMO12345','PCSECOND1234'},'PCDEMO12345')
        self.assertEqual(data['overall']['accounts'],2);self.assertFalse(data['overall']['totals_known']);self.assertIsNone(data['overall']['pdf_total'])
    def test_failed_batch_records_retry_without_losing_checkpoint(self):
        h=self.fixture.history
        with sqlite3.connect(self.db.DB) as db:db.execute("UPDATE npc_sync_state SET history_cursor='2026-07-01'")
        policy=test_runtime.module('request_policy')
        with patch.object(h,'_run',side_effect=policy.ProviderCooldown('no private details',429)):
            with self.assertRaises(policy.ProviderCooldown):h.run('PCDEMO12345',threading.Event())
        state=self.db.sync_status('PCDEMO12345')
        self.assertEqual(state['history_cursor'],'2026-07-01');self.assertEqual(state['last_error'],'ProviderCooldown:429')
        self.assertIsNotNone(state['history_retry_at']);self.assertIsNotNone(state['history_updated_at'])
    def test_diagnostic_pdf_unit_precedes_money_prefix(self):
        tree=ast.parse((test_runtime.ROOT/'sensor.py').read_text())
        cls=next(n for n in tree.body if isinstance(n,ast.ClassDef))
        namespace={'CoordinatorEntity':object,'SensorEntity':type('SensorEntity',(),{})}
        # Extract only property under test, no HA runtime import.
        method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='unit_of_measurement')
        exec(compile(ast.Module(body=[method],type_ignores=[]),'sensor.py','exec'),namespace)
        self.assertEqual(namespace['unit_of_measurement'].fget(types.SimpleNamespace(_sensor_type='tien_do_tai_pdf')),'%')

class PublishingTests(unittest.IsolatedAsyncioTestCase):
    async def test_local_updates_after_batch_do_not_reset_evN_poll_timer_or_mark_network_success(self):
        tree=ast.parse((test_runtime.ROOT/'native_coordinator.py').read_text());cls=next(n for n in tree.body if isinstance(n,ast.ClassDef))
        namespace={'__package__':'progress_fixture','DataUpdateCoordinator':BaseCoordinator,'asyncio':asyncio,'threading':threading,'timedelta':timedelta,'sqlite3':sqlite3,'_LOGGER':logging.getLogger(__name__)}
        exec(compile(ast.Module(body=[cls],type_ignores=[]),'native_coordinator.py','exec'),namespace)
        calls=[]
        async def executor(fn,*args):calls.append(fn.__name__);return fn(*args)
        hass=types.SimpleNamespace(async_add_executor_job=executor)
        co=namespace['EVNCoordinator'](hass,'PCDEMO12345');co._active=True;co.data={'fetched_at':'original','sensor_values':{'old':1}};co.last_update_success=False
        listeners=[];co.async_update_listeners=lambda:listeners.append(True)
        co.async_set_updated_data=lambda data:self.fail('Would postpone the EVN poll timer')
        full=types.ModuleType('progress_fixture.account_snapshot');full.build=lambda account:{'history_value':{'value':9}}
        progress=types.ModuleType('progress_fixture.sync_progress');progress.sensors=lambda account:{'dong_bo_du_lieu':{'value':'pdf'}}
        with patch.dict(sys.modules,{'progress_fixture':types.ModuleType('progress_fixture'),'progress_fixture.account_snapshot':full,'progress_fixture.sync_progress':progress}):
            await co._publish_local_snapshot(full=True)
            self.assertEqual(co.data['sensor_values']['history_value']['value'],9)
            await co._publish_local_snapshot()
        self.assertEqual(len(listeners),2);self.assertFalse(co.last_update_success);self.assertEqual(co.data['fetched_at'],'original')
        self.assertEqual(co.data['sensor_values']['history_value']['value'],9)

if __name__=='__main__':unittest.main()
