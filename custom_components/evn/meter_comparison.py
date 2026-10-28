"""Per-customer local utility meters and authenticated EVN comparison endpoints."""
from __future__ import annotations

from .paths import data_path, auth_path

import asyncio
from copy import deepcopy
from datetime import datetime, timedelta
from functools import partial
import hashlib
import json
import logging
import os
from pathlib import Path
import sqlite3

from aiohttp import web
from homeassistant.core import callback
from homeassistant.config_entries import ConfigEntryDisabler
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.components.recorder.statistics import statistics_during_period
from homeassistant.helpers.start import async_at_started
from homeassistant.components.http import HomeAssistantView
from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.history import get_significant_states
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.storage import Store
from homeassistant.helpers.event import async_track_time_interval, async_track_time_change, async_call_later
from homeassistant.util import dt as dt_util

from .meter_math import number, integrate
from .meter_window import consumption, cumulative_at

_LOGGER = logging.getLogger(__name__)
KEY = 'npc_meter_comparison'
DB = str(data_path('evndata.db'))
FACTORS = {'kWh': 1, 'Wh': 0.001, 'MWh': 1000}


def _snapshot(payload):
    """Configuration-only snapshots; telemetry is maintained by HA Recorder."""
    stamp = dt_util.now().strftime('%Y%m%d-%H%M%S-%f')
    directory = data_path('private', 'history', 'meter-selection') / stamp
    directory.mkdir(parents=True, exist_ok=False)
    content = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2).encode()
    target = directory / 'configuration.json'
    with target.open('xb') as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    if target.read_bytes() != content:
        raise OSError('Meter selection backup verification failed')
    target.chmod(0o444)
    manifest = directory / 'manifest.json'
    manifest.write_text(json.dumps({'sha256': hashlib.sha256(content).hexdigest(),
                                   'timezone': 'Asia/Ho_Chi_Minh'}))
    manifest.chmod(0o444)
    return str(directory)


def _parse_day(value):
    for fmt in ('%d/%m/%Y', '%d-%m-%Y', '%Y-%m-%d'):
        try:
            return datetime.strptime(str(value)[:10], fmt).date()
        except ValueError:
            pass
    return None


def _recorded_time(payload):
    value = payload.get('THOI_DIEM')
    if not isinstance(value, str):
        return None
    for fmt in ('%d/%m/%Y %H:%M:%S', '%d/%m/%Y %H:%M', '%Y-%m-%dT%H:%M:%S'):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
        except ValueError:
            pass
    return None


def _official(account, now):
    """Official calendar-month daily statistics anchored to API timestamps."""
    first = now.date().replace(day=1)
    yesterday = now.date() - timedelta(days=1)
    with sqlite3.connect('file:' + DB + '?mode=ro', uri=True, timeout=10) as conn:
        records = { _parse_day(json.loads(row[0]).get('NGAY')): json.loads(row[0])
                   for row in conn.execute("SELECT payload FROM codex_cpc_records WHERE account=? AND kind='daily'", (account,)) }
        days = [(day, number(value)) for raw, value in conn.execute('SELECT ngay,dien_tieu_thu_kwh FROM daily_consumption WHERE userevn=?',(account,))
                if (day := _parse_day(raw)) and first <= day <= yesterday and number(value) is not None]
        last = max((day for day, _ in days), default=None)
        last_row = records.get(last, {})
        initial = records.get(first - timedelta(days=1), {})
        total = round(sum(value for _, value in days), 6) if days else None
        complete=last is not None and len({day for day,_ in days})==(last-first).days+1
        known_total=total
        if not complete:total=None
        yrow=conn.execute('SELECT dien_tieu_thu_kwh FROM daily_consumption WHERE userevn=? AND ngay=?',(account,yesterday.strftime('%d-%m-%Y'))).fetchone()
        yday=number(yrow[0]) if yrow else None
        ytime = _recorded_time(records.get(yesterday, {}))
        ystart = _recorded_time(records.get(yesterday - timedelta(days=1), {}))
        latest_time = _recorded_time(last_row)
        begin = _recorded_time(initial)
        fetched = conn.execute("SELECT MAX(fetched_at) FROM codex_cpc_records WHERE account=? AND kind='daily'",(account,)).fetchone()[0]
        if fetched:
            parsed_fetch = dt_util.parse_datetime(fetched)
            if parsed_fetch and parsed_fetch.tzinfo is None:
                fetched = parsed_fetch.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE).isoformat()
        from .database import sync_status
        status=sync_status(account,DB)
        from .billing_history import pdf_progress
        status["pdf_progress"]=pdf_progress(account)
        if status.get('last_success'):fetched=status['last_success']
        from .pricing import tariff_profile,estimate_profile
        profile=tariff_profile(account,conn)
        cost=lambda value:estimate_profile(value,profile)
        ybase=number(records.get(yesterday.replace(day=1)-timedelta(days=1),{}).get('CHISO_MOI'))
        ybefore=number(records.get(yesterday-timedelta(days=1),{}).get('CHISO_MOI'))
        yafter=number(records.get(yesterday,{}).get('CHISO_MOI'))
        yfactor=number(records.get(yesterday,{}).get('HSN') or 1)
        yesterday_money=(cost(round((yafter-ybase)*yfactor,6))-cost(round((ybefore-ybase)*yfactor,6))) if profile['valid'] and None not in (ybase,ybefore,yafter,yfactor) and yafter>=ybefore>=ybase else None
        return {'sync':status,'tariff':profile,'kwh': total, 'estimated_vnd': cost(total), 'through_day': last.isoformat() if last else None,
                'cutoff': latest_time.isoformat() if latest_time else None,
                'complete':complete,'known_kwh':known_total,
                'period_start': begin.isoformat() if begin else None, 'period_source': 'Thống kê ngày theo app EVN mới',
                'initial_reading': number(initial.get('CHISO_MOI')), 'latest_reading': number(last_row.get('CHISO_MOI')),
                'yesterday_kwh': yday, 'yesterday_date': yesterday.isoformat(),
                'yesterday_read_at': ytime.isoformat() if ytime else None,
                'yesterday_start_at': ystart.isoformat() if ystart else None,
                'yesterday_estimated_vnd': yesterday_money,
                'fetched_at': fetched}


async def async_manager(hass):
    if KEY not in hass.data:
        # Assign before awaiting so simultaneous NPC entries share one manager.
        manager = MeterManager(hass)
        hass.data[KEY] = manager
        manager.ready = hass.async_create_task(manager.async_load())
    manager = hass.data[KEY]
    await manager.ready
    return manager


class MeterManager:
    def __init__(self, hass):
        self.hass = hass
        self.store = Store(hass, 1, KEY, atomic_writes=True)
        self.data = {'accounts': {}, 'archive': []}
        self.lock = asyncio.Lock()
        self.listeners = {}
        self.cache = {}
        self.electric_cache = {}
        self.ready = None
        self.platforms = {}
        self.outputs = set()
        self.series_cache = {}
        self.live_points = {}
        self.refresh_tasks = {}
        self._unsubscribers=[]

    async def async_load(self):
        self.data = await self.store.async_load() or self.data
        self.hass.http.register_view(MeterSensorsView(self))
        self.hass.http.register_view(DailyPricingView(self))
        from .invoice_pdf import InvoiceCatalogView, InvoicePDFView
        self.hass.http.register_view(InvoiceCatalogView(self))
        self.hass.http.register_view(InvoicePDFView(self))
        self.hass.http.register_view(MeterCheckView(self))
        self.hass.http.register_view(MeterAccountView(self))
        self.hass.http.register_view(CustomerNameView(self))
        self.hass.http.register_view(SyncProgressView(self))
        self.activate()

    @callback
    def activate(self):
        if self._unsubscribers:return
        self._unsubscribers=[
            self.hass.bus.async_listen('entity_registry_updated',self._registry_changed),
            self.hass.bus.async_listen('state_changed',self._source_changed),
            async_track_time_change(self.hass,self._tick,minute=[0,15,30,45],second=0),
            async_at_started(self.hass,self._started)]

    async def _registry_changed(self,event):
        if event.data.get('action')!='update':return
        entry=er.async_get(self.hass).async_get(event.data.get('entity_id',''))
        if entry and entry.platform=='evn':
            from .database import save_entity_ids
            await self.hass.async_add_executor_job(save_entity_ids,{entry.unique_id:entry.entity_id})

    async def detach(self,account):
        self.platforms.pop(account,None);self.outputs.discard(account)
        self.listeners.pop(account,None);self.cache.pop(account,None);self.electric_cache.pop(account,None)
        task=self.refresh_tasks.pop(account,None)
        if task and not task.done():
            task.cancel();await asyncio.gather(task,return_exceptions=True)
        if not self.platforms:
            for unsubscribe in self._unsubscribers:
                if unsubscribe:unsubscribe()
            self._unsubscribers=[]
            self.series_cache.clear();self.live_points.clear()

    async def _started(self, _hass):
        await self.migrate_legacy()
        await self._tick(dt_util.now())

    async def migrate_legacy(self):
        async with self.lock:
            for account, cfg in list(self.data['accounts'].items()):
                if cfg.get('engine') == '32d-v1':
                    continue
                entry = self.hass.config_entries.async_get_entry(cfg.get('entry_id', ''))
                if entry and entry.domain == 'utility_meter':
                    if entry.options.get('source') != cfg['source']:
                        raise ValueError('Legacy source mismatch; refusing to change helper')
                    await self.backup({'action': 'archive_legacy_partial_meter', 'account': account,
                                       'entry_id': entry.entry_id, 'preserve_history': True})
                    await self.hass.config_entries.async_set_disabled_by(entry.entry_id, ConfigEntryDisabler.USER)
                await self.backup({'action': 'migrate_mapping_to_two_32day_counters', 'account': account})
                new = deepcopy(self.data)
                old = new['accounts'][account]
                old['legacy_entry_id'] = old.get('entry_id')
                old['legacy_meter_entity'] = old.get('meter_entity')
                old['engine'] = '32d-v1'
                await self.store.async_save(new)
                self.data = new

    @callback
    def register_platform(self, account, add_entities):
        self.activate()
        self.platforms[account] = add_entities
        self.ensure_outputs(account)

    @callback
    def ensure_outputs(self, account):
        if account not in self.data['accounts'] or account not in self.platforms or account in self.outputs:
            return
        self.platforms[account]([MeterWindowSensor(self, account, 'actual'), MeterWindowSensor(self, account, 'evn')])
        self.outputs.add(account)

    @callback
    def _source_changed(self, event):
        entity = event.data.get('entity_id')
        if entity not in {cfg['source'] for cfg in self.data['accounts'].values()}:
            return
        state = event.data.get('new_state')
        if state:
            buffer = self.live_points.setdefault(entity, [])
            buffer.append((state.last_updated.timestamp(), state.state))
            del buffer[:-4096]
        for account, cfg in self.data['accounts'].items():
            if cfg['source'] == entity:
                self.cache.pop(account, None)
                # Source events are buffered; visible Electric Meter snapshots update every 15 minutes.

    @callback
    def schedule_refresh(self, account):
        task = self.refresh_tasks.get(account)
        if task is None or task.done():
            self.refresh_tasks[account] = self.hass.async_create_task(self.refresh_notify(account))

    async def refresh_notify(self, account):
        try:
            result = await self.comparison(account)
            for listener in list(self.listeners.get(account, [])):
                listener(result)
        except Exception:
            _LOGGER.exception('32-day comparison refresh failed for %s', account)

    async def _tick(self, _now):
        self.electric_cache.clear()
        self.cache.clear()
        for account in set(self.data['accounts']) & self.accounts():
            if account in self.platforms:self.schedule_refresh(account)

    def accounts(self):
        return {entry.data.get('customer_id') or entry.data.get('username')
                for entry in self.hass.config_entries.async_entries('evn') if entry.disabled_by is None}

    def sources(self):
        registry = er.async_get(self.hass)
        blocked = {entry.entity_id for entry in registry.entities.values()
                   if entry.platform in ('evn', 'utility_meter')}
        return [{'entity_id': state.entity_id,
                 'name': state.attributes.get('friendly_name', state.entity_id),
                 'unit': state.attributes.get('unit_of_measurement'),
                 'value': number(state.state), 'state_class': state.attributes.get('state_class')}
                for state in self.hass.states.async_all('sensor')
                if state.attributes.get('device_class') == 'energy'
                and state.attributes.get('state_class') in ('total', 'total_increasing')
                and state.attributes.get('unit_of_measurement') in FACTORS
                and state.entity_id not in blocked
                and state.entity_id not in {cfg.get('legacy_meter_entity') for cfg in self.data['accounts'].values()}]

    async def history(self, entity, start, end):
        query = partial(get_significant_states, self.hass, dt_util.as_utc(start),
                        dt_util.as_utc(end), [entity], include_start_time_state=True,
                        significant_changes_only=False, minimal_response=False, no_attributes=True)
        result = await get_instance(self.hass).async_add_executor_job(query)
        return [(state.last_updated.timestamp(), state.state) for state in result.get(entity, [])]

    async def backup(self, intent):
        payload = {'mapping': deepcopy(self.data), 'intent': intent,
                   'utility_entries': [{'entry_id': e.entry_id, 'title': e.title,
                                        'data': dict(e.data), 'options': dict(e.options)}
                                       for e in self.hass.config_entries.async_entries('utility_meter')]}
        return await self.hass.async_add_executor_job(_snapshot, payload)

    async def check_source(self, source, resetting=True):
        state = self.hass.states.get(source) if isinstance(source, str) else None
        eligible = {row['entity_id']: row for row in self.sources()}
        errors, warnings = [], []
        if not state:
            errors.append('Sensor không tồn tại trong Home Assistant')
        elif source not in eligible:
            errors.append('Phải là sensor điện năng tích lũy, device_class energy, state_class total/total_increasing và đơn vị Wh/kWh/MWh; không dùng công suất hay bộ đếm EVN làm nguồn')
        elif number(state.state) is None:
            errors.append('Sensor đang unknown/unavailable hoặc giá trị không hợp lệ')
        now = dt_util.now()
        sample = None
        if not errors:
            age = max(0, (now - state.last_updated).total_seconds())
            if age > 14400:
                warnings.append('Giá trị nguồn chưa cập nhật hơn 4 giờ; cần kiểm tra công tơ có đang báo dữ liệu không')
            points = await self.history(source, now - timedelta(days=2), now)
            sample = integrate(points, (now - timedelta(days=2)).timestamp(), now.timestamp(), resetting)
            if len(points) < 2:
                warnings.append('HA chưa có đủ lịch sử để kiểm tra mức tăng điện năng')
            if sample['resets']:
                warnings.append('Lịch sử có lần giảm chỉ số/reset; cần chọn đúng tùy chọn sensor nguồn có thể reset')
            if sample['uncertain']:
                warnings.append('Lịch sử có đoạn thiếu/không hợp lệ; chưa xác nhận đủ dữ liệu cả kỳ')
        return {'source': source, 'valid': not errors, 'errors': errors, 'warnings': warnings,
                'value': number(state.state) if state else None,
                'unit': state.attributes.get('unit_of_measurement') if state else None,
                'device_class': state.attributes.get('device_class') if state else None,
                'state_class': state.attributes.get('state_class') if state else None,
                'last_updated': state.last_updated.isoformat() if state else None,
                'history': sample,
                'physical_accuracy': 'Chỉ kiểm tra cấu trúc và lịch sử dữ liệu. Không xác nhận công tơ đo đủ tải hoặc thuộc đúng mã EVN.'}

    async def configure(self, account, body):
        if account not in self.accounts():
            raise ValueError('Mã khách hàng không tồn tại')
        official = await self.hass.async_add_executor_job(_official, account, dt_util.now())
        source = body.get('source')
        resetting = body.get('resetting', True)
        if not isinstance(resetting, bool):
            raise ValueError('resetting phải là true hoặc false')
        async with self.lock:
            old = self.data['accounts'].get(account)
            allow_approx = body.get('allow_approximate_baseline', old.get('allow_approximate_baseline', False) if old else False)
            baseline_at = body.get('baseline_at', old.get('baseline_at') if old else None)
            baseline_raw = body.get('baseline_raw', old.get('baseline_raw') if old else None)
            if baseline_at:
                parsed = dt_util.parse_datetime(baseline_at)
                if parsed is None or parsed.tzinfo is None or parsed > dt_util.now():
                    raise ValueError('Mốc gốc phải có múi giờ và không nằm trong tương lai')
                baseline_at = parsed.isoformat()
                if baseline_at != official.get('period_start'):
                    raise ValueError('Mốc gốc phải đúng mốc đầu kỳ API EVN mới')

            if baseline_raw is not None and number(baseline_raw) is None:
                raise ValueError('Chỉ số gốc Electric Meter không hợp lệ')
            if not isinstance(allow_approx, bool):
                raise ValueError('Tùy chọn xấp xỉ không hợp lệ')
            if not source:
                if old:
                    await self.backup({'action': 'unlink', 'account': account})
                    new = deepcopy(self.data)
                    new['archive'].append({'account': account, **new['accounts'].pop(account)})
                    await self.store.async_save(new)
                    self.data = new
                self.cache.pop(account, None)
                await self.refresh_notify(account)
                return
            validation = await self.check_source(source, resetting)
            if not validation['valid']:
                raise ValueError('; '.join(validation['errors']))
            if not old or old['source'] != source or old['resetting'] != resetting or old.get('baseline_at') != baseline_at or old.get('baseline_raw') != baseline_raw or old.get('allow_approximate_baseline', False) != allow_approx:
                await self.backup({'action': 'select_source_for_two_counters', 'account': account, 'source': source,
                                   'new_components': ['actual energy sensor', 'energy sensor at EVN cutoff']})
                new = deepcopy(self.data)
                if old:
                    new['archive'].append({'account': account, **old})
                new['accounts'][account] = {'source': source, 'resetting': resetting,
                    'unit': validation['unit'], 'factor': FACTORS[validation['unit']],
                    'engine': '32d-v1', 'configured_at': dt_util.now().isoformat(),
                    'baseline_at': baseline_at, 'baseline_raw': baseline_raw, 'allow_approximate_baseline': allow_approx,
                    'baseline_period_id': official.get('period_start')}
                await self.store.async_save(new)
                self.data = new
            self.cache.pop(account, None)
            self.electric_cache.pop(account, None)
            self.ensure_outputs(account)
        await self.refresh_notify(account)

    async def series(self, source, now):
        cached = self.series_cache.get(source)
        if cached and now.timestamp() - cached[0] < 900:
            return cached[1], list(cached[2])
        lower = now - timedelta(days=32)
        query = partial(statistics_during_period, self.hass, dt_util.as_utc(lower),
                        dt_util.as_utc(now), {source}, 'hour', {'energy': 'kWh'}, {'state', 'sum'})
        stats = await get_instance(self.hass).async_add_executor_job(query)
        details = await self.history(source, lower, now)
        rows = stats.get(source, [])
        self.series_cache[source] = (now.timestamp(), rows, details)
        return rows, list(details)

    async def comparison(self, account):
        if account not in self.accounts():
            raise ValueError('Mã khách hàng không tồn tại')
        now = dt_util.now()
        cached = self.cache.get(account)
        if cached and now.timestamp() - cached[0] < 5:
            return cached[1]
        official = await self.hass.async_add_executor_job(_official, account, now)
        from .pricing import estimate_profile
        estimate=lambda value:estimate_profile(value,official['tariff'])
        result = {'account': account, 'month': now.strftime('%Y-%m'),
                  'updated_at': now.isoformat(), 'evn': official, 'configured': False,
                  'period_start': official['period_start'], 'period_source': official['period_source'],
                  'history_window_days': 32, 'sources': ['evn_new_api', 'electric_meter'],
                  'electric_update_minutes': 15,
                  'tariff_note': f"Giá dự kiến theo hồ sơ hóa đơn, VAT {official['tariff']['vat_percent']:g}%; số phải trả theo hóa đơn EVN."}
        from .services_cpc import sensors as service_sensors
        result['services'] = await self.hass.async_add_executor_job(service_sensors, account, now)
        day_start = dt_util.parse_datetime(official['yesterday_read_at']) if official.get('yesterday_read_at') else None
        day_valid = bool(day_start and dt_util.as_local(day_start).date() == now.date())
        cfg = self.data['accounts'].get(account)
        if cfg:
            source = self.hass.states.get(cfg['source'])
            rows, points = await self.series(cfg['source'], now)
            points += self.live_points.get(cfg['source'], [])
            if source:
                points.append((source.last_updated.timestamp(), source.state))
            points = sorted(set((ts, None if number(value) is None else number(value) * cfg['factor']) for ts, value in points), key=lambda row: row[0])
            declared = official.get('period_start')
            shared_start = official.get('period_start')
            override_current = cfg.get('baseline_period_id', declared) == declared
            verified_override = cfg.get('baseline_at') if override_current and cfg.get('baseline_at') == shared_start else None
            start_value = shared_start
            start = dt_util.parse_datetime(start_value) if start_value else None
            cutoff = dt_util.parse_datetime(official['cutoff']) if official.get('cutoff') else None
            result['period_start'] = start.isoformat() if start else None
            result['shared_period_start'] = start.isoformat() if start else None
            result['shared_comparison_end'] = cutoff.isoformat() if cutoff else None
            result['alignment_status'] = 'evn_new_api_period' if start else 'missing_evn_new_api_period'
            result['period_source'] = 'Mốc đầu kỳ API EVN mới; Electric dùng chỉ số riêng' if start else 'Chờ mốc đầu kỳ API EVN mới'
            missing = {'kwh': None, 'complete': False, 'coverage_start': None, 'sample_at': None, 'method': 'no_evn_period'}
            baseline = cfg.get('period_baselines', {}).get(start.isoformat()) if start else None
            calculated_base = cumulative_at(rows, points, start.timestamp(), cfg['resetting']) if start else None
            anchor_error = 0.0  # Electric uses its own reading at the API timestamp.
            if start and calculated_base and not calculated_base.get('exact'):
                after = [row for row in rows if float(row['end']) >= start.timestamp() and row.get('sum') is not None]
                if after:
                    upper = min(after, key=lambda row: float(row['end']))
                    error = max(0, float(upper['sum']) - calculated_base['value'])
                    if 0 <= float(upper['end']) - start.timestamp() <= 3600:
                        calculated_base.update({'bounded_approximation': round(error + anchor_error, 6) < 1, 'error_bound_kwh': round(error, 6),
                            'upper_sample_at': float(upper['end']), 'target_at': start.timestamp()})
            if start and verified_override and cfg.get('baseline_raw') is not None:
                anchors = [row for row in rows if start.timestamp() <= float(row['end']) <= start.timestamp()+3600 and row.get('sum') is not None and row.get('state') is not None]
                if anchors:
                    anchor = min(anchors, key=lambda row: row['end'])
                    calculated_base = {'value': anchor['sum'] + float(cfg['baseline_raw'])*cfg['factor'] - anchor['state'], 'sample_at': start.timestamp(), 'complete': True, 'exact': True}
            if calculated_base and (not baseline or (calculated_base.get('exact') and not baseline.get('exact'))):
                async with self.lock:
                    latest_cfg = self.data['accounts'].get(account, {})
                    existing = latest_cfg.get('period_baselines', {}).get(start.isoformat())
                    if latest_cfg.get('source') == cfg['source']:
                        if existing and (existing.get('exact') or not calculated_base.get('exact')):
                            baseline = existing
                        else:
                            await self.backup({'action': 'record_evn_timed_source_baseline', 'account': account, 'period_start': start.isoformat(), 'baseline': calculated_base})
                            new = deepcopy(self.data)
                            new['accounts'][account].setdefault('period_baselines', {})[start.isoformat()] = calculated_base
                            await self.store.async_save(new)
                            self.data = new
                            baseline = calculated_base
                        cfg = self.data['accounts'][account]
            bounded_base = baseline and baseline.get('bounded_approximation') and round(float(baseline.get('error_bound_kwh', 1)) + anchor_error, 6) < 1
            usable_base = baseline and (baseline.get('exact') or bounded_base)
            current = consumption(rows, points, start.timestamp(), now.timestamp(), cfg['resetting'], baseline) if start and usable_base else missing
            at = consumption(rows, points, start.timestamp(), cutoff.timestamp(), cfg['resetting'], baseline) if start and cutoff and usable_base else missing
            if start and cutoff and at['kwh'] is not None:
                snapshot_id = f"{start.isoformat()}|{cutoff.isoformat()}|{baseline.get('value') if baseline else None}"
                async with self.lock:
                    latest_cfg = self.data['accounts'].get(account, {})
                    previous = latest_cfg.get('evn_counter_snapshot', {})
                    if latest_cfg.get('source') == cfg['source']:
                        if previous.get('id') == snapshot_id:
                            at = previous['result']
                        else:
                            await self.backup({'action': 'freeze_counter_at_actual_evn_timestamp', 'account': account, 'cutoff': cutoff.isoformat()})
                            new = deepcopy(self.data)
                            new['accounts'][account]['evn_counter_snapshot'] = {'id': snapshot_id, 'result': at}
                            await self.store.async_save(new)
                            self.data = new
            yesterday_start = dt_util.parse_datetime(official['yesterday_start_at']) if official.get('yesterday_start_at') else None
            yesterday_end = dt_util.parse_datetime(official['yesterday_read_at']) if official.get('yesterday_read_at') else None
            yesterday_local = consumption(rows, points, yesterday_start.timestamp(), yesterday_end.timestamp(), cfg['resetting']) if yesterday_start and yesterday_end else missing
            result.update({'electric_yesterday_kwh': yesterday_local['kwh'] if yesterday_local['complete'] else None,
                           'electric_yesterday_complete': yesterday_local['complete'],
                           'electric_yesterday_exact': yesterday_local.get('exact', False),
                           'electric_yesterday_start_at': official.get('yesterday_start_at'),
                           'electric_yesterday_end_at': official.get('yesterday_read_at'),
                           'electric_yesterday_sample_at': datetime.fromtimestamp(yesterday_local['sample_at'], dt_util.DEFAULT_TIME_ZONE).isoformat() if yesterday_local['sample_at'] is not None else None})
            today_local = consumption(rows, points, day_start.timestamp(), now.timestamp(), cfg['resetting']) if day_valid else missing
            today_base = consumption(rows, points, start.timestamp(), day_start.timestamp(), cfg['resetting'], baseline) if start and usable_base and day_valid else missing
            today_used = today_local['kwh'] if today_local['complete'] and source is not None and number(source.state) is not None else None
            result.update(electric_today_kwh=today_used,
                          electric_today_start_at=day_start.isoformat() if day_valid else None,
                          electric_today_end_at=now.isoformat(),
                          electric_today_exact=today_local.get('exact', False),
                          electric_today_estimated_vnd=(estimate(current['kwh'])-estimate(today_base['kwh'])
                              if official['tariff']['valid'] and today_used is not None and current['complete'] and today_base['complete'] else None))
            available = source is not None and number(source.state) is not None
            current_kwh = current['kwh'] if available else None
            result.update({'configured': True, 'source': cfg['source'], 'resetting': cfg['resetting'],
                'current_kwh': current_kwh, 'current_estimated_vnd': estimate(current_kwh),
                'at_evn_kwh': at['kwh'], 'at_evn_estimated_vnd': estimate(at['kwh']),
                'delta_kwh': round(at['kwh'] - official['kwh'], 6) if official.get('kwh') is not None and at['complete'] and at['kwh'] is not None else None,
                'after_evn_kwh': round(current_kwh - at['kwh'], 6) if current_kwh is not None and at['kwh'] is not None else None,
                'coverage_start': datetime.fromtimestamp(current['coverage_start'], dt_util.DEFAULT_TIME_ZONE).isoformat() if current['coverage_start'] is not None else None,
                'complete_month': current['complete'], 'at_evn_complete': at['complete'],
                'source_available': available, 'sample_at_evn': datetime.fromtimestamp(at['sample_at'], dt_util.DEFAULT_TIME_ZONE).isoformat() if at['sample_at'] is not None else None,
                'meter_updated_at': source.last_updated.isoformat() if source else None,
                'current_method': current['method'], 'at_evn_method': at['method'],
                'baseline_exact': bool(shared_start and baseline and baseline.get('exact') and official.get('period_start') == shared_start),
                'baseline_error_bound_kwh': baseline.get('error_bound_kwh', 0) if baseline else None,
                'alignment_error_bound_kwh': round(anchor_error + float(baseline.get('error_bound_kwh', 0)), 6) if baseline else None,
                'baseline_at_override': cfg.get('baseline_at'), 'baseline_raw': cfg.get('baseline_raw'), 'allow_approximate_baseline': cfg.get('allow_approximate_baseline',False),
                'baseline_sample_at': datetime.fromtimestamp(baseline['sample_at'], dt_util.DEFAULT_TIME_ZONE).isoformat() if baseline and baseline.get('sample_at') is not None else None,
                'baseline_lag_seconds': round(start.timestamp() - baseline['sample_at']) if start and baseline and baseline.get('sample_at') is not None else None,
                'at_evn_exact': at.get('exact', False),
                'actual_sensor': f'sensor.evn_{account.lower()}_electric_meter_actual',
                'evn_sensor': f'sensor.evn_{account.lower()}_electric_meter_evn'})
        if cfg:
            electric_keys = ['electric_today_kwh','electric_today_start_at','electric_today_end_at','electric_today_exact','electric_today_estimated_vnd','current_kwh','current_estimated_vnd','meter_updated_at','complete_month','coverage_start','electric_reference']
            reference = '|'.join(str(official.get(key)) for key in ['period_start','initial_reading','cutoff'])
            previous = self.electric_cache.get(account)
            if previous and now.timestamp() - previous[0] < 900 and previous[1].get('electric_reference') == reference:
                result.update(previous[1])
            else:
                result['electric_reference'] = reference
                result['electric_snapshot_at'] = now.isoformat()
                result['source_reading'] = number(source.state) if source else None
                result['source_unit'] = cfg['unit']
                self.electric_cache[account] = (now.timestamp(), {key:result.get(key) for key in electric_keys + ['electric_snapshot_at','source_reading','source_unit']})
        if result.get('current_kwh') is not None and result.get('at_evn_kwh') is not None:
            result['after_evn_kwh'] = round(result['current_kwh'] - result['at_evn_kwh'], 6)
        self.cache[account] = (now.timestamp(), result)
        return result


class MeterCheckView(HomeAssistantView):
    url = '/api/npc/meter/check'
    name = 'api:npc:meter:check'
    requires_auth = True

    def __init__(self, manager):
        self.manager = manager

    async def post(self, request):
        if not request['hass_user'].is_admin:
            return web.json_response({'error': 'Cần tài khoản quản trị'}, status=403)
        try:
            body = await request.json()
            if not isinstance(body, dict):
                raise ValueError('Dữ liệu không hợp lệ')
            return web.json_response(await self.manager.check_source(body.get('source'), body.get('resetting', True)))
        except (ValueError, TypeError) as error:
            return web.json_response({'error': str(error)}, status=400)


class MeterSensorsView(HomeAssistantView):
    url = '/api/npc/meter/sources'
    name = 'api:npc:meter:sources'
    requires_auth = True

    def __init__(self, manager):
        self.manager = manager

    async def get(self, request):
        if not request['hass_user'].is_admin:
            return web.json_response({'error': 'Cần tài khoản quản trị để chọn sensor'}, status=403)
        return web.json_response({'sources': self.manager.sources()})


class MeterAccountView(HomeAssistantView):
    url = '/api/npc/meter/account/{account}'
    name = 'api:npc:meter:account'
    requires_auth = True

    def __init__(self, manager):
        self.manager = manager

    async def get(self, request, account):
        try:
            return web.json_response(await self.manager.comparison(account))
        except ValueError as error:
            return web.json_response({'error': str(error)}, status=400)

    async def post(self, request, account):
        if not request['hass_user'].is_admin:
            return web.json_response({'error': 'Cần tài khoản quản trị'}, status=403)
        try:
            body = await request.json()
            if not isinstance(body, dict):
                raise ValueError('Dữ liệu cấu hình không hợp lệ')
            await self.manager.configure(account, body)
            return web.json_response(await self.manager.comparison(account))
        except (ValueError, TypeError) as error:
            return web.json_response({'error': str(error)}, status=400)
        except Exception:
            _LOGGER.exception('Local meter configuration failed for %s', account)
            return web.json_response({'error': 'Không lưu được bộ đếm. Liên kết cũ được giữ; xem log HA.'}, status=500)


class MeterWindowSensor(SensorEntity):
    _attr_should_poll = False
    _attr_native_unit_of_measurement = 'kWh'
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL

    def __init__(self, manager, account, kind):
        self.manager, self.account, self.kind = manager, account, kind
        self.entity_id = f'sensor.evn_{account.lower()}_electric_meter_{kind}'
        self._attr_unique_id = f'{account}_electric_meter_{kind}_32d'
        self._attr_name = f'EVN {account} ' + ('Bộ đếm thực tế' if kind == 'actual' else 'Bộ đếm tại mốc EVN')
        self._attr_device_info = {'identifiers': {('evn', account)}}
        self._attr_available = False
        self._period_start = None

    async def async_added_to_hass(self):
        listeners = self.manager.listeners.setdefault(self.account, [])
        listeners.append(self.apply)
        self.async_on_remove(lambda: listeners.remove(self.apply) if self.apply in listeners else None)
        self.manager.schedule_refresh(self.account)

    @property
    def last_reset(self):
        return self._period_start

    @callback
    def apply(self, result):
        value = result.get('current_kwh' if self.kind == 'actual' else 'at_evn_kwh')
        self._attr_native_value = value
        self._attr_available = value is not None
        self._period_start = dt_util.parse_datetime(result['period_start']) if result.get('period_start') else None
        self._attr_extra_state_attributes = {'customer_id': self.account,
            'source_entity': result.get('source'), 'period_start': result.get('period_start'),
            'evn_cutoff': result.get('evn',{}).get('cutoff'), 'history_window_days': 32,
            'complete_period': result.get('complete_month' if self.kind == 'actual' else 'at_evn_complete'),
            'snapshot_at': result.get('electric_snapshot_at'),
            'estimated_vnd': result.get('current_estimated_vnd' if self.kind == 'actual' else 'at_evn_estimated_vnd')}
        self.async_write_ha_state()


class DailyPricingView(HomeAssistantView):
    url = '/api/npc/pricing/{account}'
    name = 'api:npc:pricing'
    requires_auth = True

    def __init__(self, manager):
        self.manager = manager

    async def get(self, request, account):
        if account not in self.manager.accounts():
            return web.json_response({'error': 'Mã khách hàng không tồn tại'}, status=404)
        from .pricing import read_prices
        official = await self.manager.hass.async_add_executor_job(_official, account, dt_util.now())
        period = {'declared_period_start': official.get('period_start'), 'initial_reading': official.get('initial_reading'), 'read_at': official.get('cutoff')}
        result = await self.manager.hass.async_add_executor_job(read_prices, account, period)
        return web.json_response(result)


class CustomerNameView(HomeAssistantView):
    url='/api/npc/customer-name/{account}'
    name='api:npc:customer_name'
    requires_auth=True
    def __init__(self,manager):self.manager=manager
    async def payload(self,account):
        from .customer_names import official_names,label
        official=await self.manager.hass.async_add_executor_job(official_names,[account])
        return label(account,self.manager.data.get('names',{}),official)
    async def get(self,request,account):
        if account not in self.manager.accounts():raise web.HTTPNotFound()
        return web.json_response(await self.payload(account),headers={'Cache-Control':'private, no-store'})
    async def post(self,request,account):
        if not request['hass_user'].is_admin:return web.json_response({'error':'Cần quyền quản trị để đổi tên khách hàng'},status=403)
        if account not in self.manager.accounts():raise web.HTTPNotFound()
        from .customer_names import clean_name,official_names,label
        try:
            body=await request.json()
            if not isinstance(body,dict) or set(body)-{'name','expected_custom_name'} or 'name' not in body:raise ValueError('Dữ liệu tên không hợp lệ')
            value=clean_name(body['name'])
            official=await self.manager.hass.async_add_executor_job(official_names,[account])
            async with self.manager.lock:
                current=self.manager.data.get('names',{}).get(account,'')
                if 'expected_custom_name' in body and body['expected_custom_name']!=current:
                    return web.json_response({'error':'Tên đã được đổi ở nơi khác. Hãy mở lại cấu hình.'},status=409)
                if current!=value:
                    await self.manager.backup({'action':'set_customer_display_name','account':account})
                    new=deepcopy(self.manager.data)
                    names=new.setdefault('names',{})
                    if value:names[account]=value
                    else:names.pop(account,None)
                    await self.manager.store.async_save(new)
                    self.manager.data=new
            return web.json_response(label(account,self.manager.data.get('names',{}),official),headers={'Cache-Control':'private, no-store'})
        except (ValueError,TypeError) as error:return web.json_response({'error':str(error)},status=400)
        except Exception:
            _LOGGER.warning('Could not save customer display name for %s',account)
            return web.json_response({'error':'Chưa lưu được tên. Cấu hình bộ đếm được giữ nguyên.'},status=503)


class SyncProgressView(HomeAssistantView):
    url='/api/npc/sync-progress/{account}'
    name='api:npc:sync-progress'
    requires_auth=True
    def __init__(self,manager):self.manager=manager
    async def get(self,request,account):
        accounts=self.manager.accounts()
        if account not in accounts:raise web.HTTPNotFound()
        from .sync_progress import overview
        result=await self.manager.hass.async_add_executor_job(overview,accounts,account)
        return web.json_response(result,headers={'Cache-Control':'private, no-store'})
