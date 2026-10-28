"""Exercise the real coordinator's cancellation boundary without EVN or HA mocks."""
import ast
import asyncio
from datetime import timedelta
import logging
import sqlite3
from pathlib import Path
import tempfile
import threading
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1] / 'custom_components/evn'

class BaseCoordinator:
    def __init__(self, hass, *args, **kwargs):
        self.hass = hass
        self._shutdown_requested = False
        self.data = None
        self.config_entry = None
    async def async_shutdown(self):
        self._shutdown_requested = True

class WorkerTests(unittest.IsolatedAsyncioTestCase):
    def coordinator(self, hass):
        tree = ast.parse((ROOT / 'native_coordinator.py').read_text())
        cls = next(node for node in tree.body if isinstance(node, ast.ClassDef))
        namespace = {'__package__': 'worker_fixture', 'DataUpdateCoordinator': BaseCoordinator,
                     'asyncio': asyncio, 'threading': threading, 'timedelta': timedelta, 'sqlite3': sqlite3,
                     '_LOGGER': logging.getLogger(__name__)}
        exec(compile(ast.Module(body=[cls], type_ignores=[]), 'native_coordinator.py', 'exec'), namespace)
        return namespace['EVNCoordinator'](hass, 'PCDEMO12345')

    async def test_stop_waits_for_inflight_history_before_database_can_be_removed(self):
        started, release = asyncio.Event(), asyncio.Event()
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'writer-finished'
            async def executor_job():
                started.set()
                await release.wait()
                target.write_text('completed')
                return {'complete': True}
            hass = types.SimpleNamespace(async_create_background_task=lambda coro,name,eager_start=False:asyncio.create_task(coro),
                async_add_executor_job=lambda *args: asyncio.create_task(executor_job()))
            worker = types.ModuleType('worker_fixture.history_worker'); worker.run = lambda *args: None
            with patch.dict('sys.modules', {'worker_fixture': types.ModuleType('worker_fixture'),
                                           'worker_fixture.history_worker': worker}):
                coordinator = self.coordinator(hass)
                coordinator.start_history()
                await asyncio.wait_for(started.wait(), 1)
                stop = asyncio.create_task(coordinator.stop_history())
                await asyncio.sleep(0)
                await asyncio.sleep(0)
                self.assertFalse(stop.done())
                self.assertTrue(coordinator._history_cancel.is_set())
                self.assertFalse(target.exists())
                release.set()
                await asyncio.wait_for(stop, 1)
                self.assertEqual(target.read_text(), 'completed')
                self.assertTrue(coordinator._history_job.done())

    async def test_stop_waits_for_active_poll(self):
        coordinator = self.coordinator(types.SimpleNamespace())
        await coordinator._update_lock.acquire()
        stop = asyncio.create_task(coordinator.stop_history())
        await asyncio.sleep(0)
        self.assertFalse(stop.done())
        coordinator._update_lock.release()
        await asyncio.wait_for(stop, 1)
        self.assertTrue(coordinator._shutdown_requested)
