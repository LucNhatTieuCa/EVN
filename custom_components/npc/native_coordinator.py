"""Native CPC polling, cached sensor snapshots and checkpointed history."""
from datetime import timedelta
import logging
import asyncio
import threading
import sqlite3

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from .official_cpc import supports, sync
from .database import sync_status
from datetime import datetime
from zoneinfo import ZoneInfo

_LOGGER = logging.getLogger(__name__)


class EVNCoordinator(DataUpdateCoordinator):
    """Refresh CPC data directly, without a companion process."""

    def __init__(self,hass,customer_id):
        super().__init__(hass,_LOGGER,name='npc_cpc',update_interval=timedelta(hours=4))
        self.customer_id=customer_id
        self._active=False
        self._history_task=None
        self._history_cancel=None
        self._history_job=None
        self._update_lock=asyncio.Lock()

    async def _async_update_data(self):
        async with self._update_lock:
            if self._shutdown_requested:
                return self.data or {}
            return await self._update_data()

    async def _update_data(self):
        try:
            if not await self.hass.async_add_executor_job(supports,self.customer_id):
                raise ValueError('Configure EVN login for this customer')
            status=await self.hass.async_add_executor_job(sync_status,self.customer_id)
            last=datetime.fromisoformat(status['last_success']) if status.get('last_success') else None
            if last and last.tzinfo is None:last=last.replace(tzinfo=ZoneInfo('Asia/Ho_Chi_Minh'))
            if not self.data and last and (datetime.now(ZoneInfo('Asia/Ho_Chi_Minh'))-last).total_seconds()<4*3600:
                result={'source':'authenticated CPC cache','fetched_at':last.isoformat()}
            else:
                result=await self.hass.async_add_executor_job(sync,self.customer_id)
            from .services_cpc import sync as sync_services
            await self.hass.async_add_executor_job(sync_services,self.customer_id)
            from .account_snapshot import build
            result['sensor_values']=await self.hass.async_add_executor_job(build,self.customer_id)
            if self._active:self.start_history()
            return result
        except (OSError, sqlite3.Error, ValueError) as err:
            raise UpdateFailed("EVN CPC source temporarily unavailable; stored history retained") from err


    def start_history(self):
        self._active=True
        if self._history_task and not self._history_task.done():return
        self._history_cancel=threading.Event()
        async def work():
            try:
                from .history_worker import run
                while self._active and not self._history_cancel.is_set():
                    try:
                        self._history_job = self.hass.async_add_executor_job(run,self.customer_id,self._history_cancel)
                        result = await asyncio.shield(self._history_job)
                    except (OSError, sqlite3.Error):
                        _LOGGER.warning('EVN history temporarily paused; retrying from checkpoint')
                        await asyncio.sleep(300)
                        continue
                    if result.get('complete') or result.get('cancelled'):break
                    await asyncio.sleep(60)
                if self._active and self.data:
                    from .account_snapshot import build
                    data=dict(self.data);data['sensor_values']=await self.hass.async_add_executor_job(build,self.customer_id)
                    self.async_set_updated_data(data)
            except asyncio.CancelledError:
                self._history_cancel.set();raise
            except Exception:
                _LOGGER.warning('EVN history paused for %s; checkpoint and existing data retained',self.customer_id)
        self._history_task=self.hass.async_create_task(work())

    async def stop_history(self):
        self._active=False
        await self.async_shutdown()
        if self._history_cancel:self._history_cancel.set()
        if self._history_task and not self._history_task.done():
            self._history_task.cancel();await asyncio.gather(self._history_task,return_exceptions=True)

        if self._history_job:
            await asyncio.gather(self._history_job, return_exceptions=True)
        # Wait for an already-running poll to finish before deleting its database.
        async with self._update_lock:
            pass
