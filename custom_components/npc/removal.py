"""Delete integration-owned data only when a config entry is removed."""
import asyncio
from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
import sqlite3
from uuid import uuid4

from .const import DOMAIN, CONF_CUSTOMER_ID


def _remove(path):
    """Do not follow links while deleting an owned file tree."""
    path = Path(path)
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.exists():
        shutil.rmtree(path)


def purge_files(root, auth, account, remaining):
    """Executor only. Never touch the HA database, source sensors or backups."""
    root, auth = Path(root), Path(auth)
    if not isinstance(account, str) or not account.startswith('PC') or not account.isalnum():
        raise ValueError('Invalid EVN account for removal')
    if root.is_symlink():
        raise ValueError('Refusing linked EVN data root')
    if auth.is_symlink():
        raise ValueError('Refusing linked credential file')
    if not remaining:
        _remove(root)
        # Legacy credentials live outside evnvn. Delete exact owned files only.
        for path in (auth, auth.parent / 'evn-credentials-history.key',
                     auth.parent / 'evn-cpc-history.fernet'):
            _remove(path)
        return

    db_path = root / 'evndata.db'
    if db_path.is_symlink():
        raise ValueError('Refusing linked EVN database')
    if db_path.exists():
        with sqlite3.connect(db_path, timeout=30) as db:
            db.execute('BEGIN IMMEDIATE')
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            # Remove legacy protection triggers for this customer before DELETE.
            for (name,) in db.execute("SELECT name FROM sqlite_master WHERE type='trigger'").fetchall():
                if name.startswith('codex_cpc_' + account + '_'):
                    db.execute('DROP TRIGGER "' + name.replace('"', '""') + '"')
            if 'npc_invoice_index' in tables:
                for table in ('npc_invoice_files', 'npc_pdf_attempts'):
                    if table in tables:
                        db.execute(f'DELETE FROM {table} WHERE invoice_row_id IN (SELECT id FROM npc_invoice_index WHERE account=?)', (account,))
            for table in tables:
                quoted = '"' + table.replace('"', '""') + '"'
                columns = {r[1] for r in db.execute('PRAGMA table_info(' + quoted + ')')}
                column = 'account' if 'account' in columns else 'userevn' if 'userevn' in columns else None
                if column:
                    db.execute(f'DELETE FROM {quoted} WHERE {column}=?', (account,))
            if 'npc_entity_ids' in tables:
                db.execute('DELETE FROM npc_entity_ids WHERE substr(unique_id,1,?)=?', (len(account)+1, account+'_'))
    # PDFs are stored by customer, with old PDF/PNG files at the root.
    invoices = root / 'invoices'
    if invoices.is_symlink():
        raise ValueError('Refusing linked invoice directory')
    _remove(invoices / account)
    if root.exists():
        for path in root.iterdir():
            if path.name.startswith(account + '_') and path.suffix.lower() in {'.pdf', '.png', '.jpg', '.jpeg'}:
                _remove(path)
    # Shared private snapshots may contain this customer's data; do not retain it.
    if (root / 'private').is_symlink():
        raise ValueError('Refusing linked private directory')
    _remove(root / 'private' / 'history')
    if auth.exists():
        before = auth.read_bytes()
        old = json.loads(before)
        profiles = dict(old.get('accounts') or {})
        if old.get('customer_id') and old.get('username') and old.get('password'):
            profiles.setdefault(old['customer_id'], {k: old[k] for k in ('customer_id','username','password')})
        profiles.pop(account, None)
        profiles = {k: v for k, v in profiles.items() if k in remaining}
        if profiles:
            primary = next(iter(profiles.values()))
            after = json.dumps({**primary, 'accounts': profiles}, ensure_ascii=False).encode()
            temporary = auth.parent / ('.evn-remove-' + uuid4().hex)
            try:
                fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                with os.fdopen(fd, 'wb') as stream:
                    stream.write(after); stream.flush(); os.fsync(stream.fileno())
                if auth.read_bytes() != before:
                    raise RuntimeError('Credentials changed during removal')
                os.replace(temporary, auth)
            finally:
                temporary.unlink(missing_ok=True)
        else:
            auth.unlink()
    _remove(auth.parent / 'evn-cpc-history.fernet')


async def async_remove(hass, entry):
    """Called after unload; disabled/failed entries are cleaned as well."""
    from homeassistant.helpers import entity_registry as er
    from homeassistant.helpers.storage import Store
    from .credentials import AUTH, _LOCK
    from .meter_comparison import KEY
    account = entry.data.get(CONF_CUSTOMER_ID) or entry.data.get('username')
    lock = hass.data.setdefault('npc_initialization_lock', asyncio.Lock())
    async with lock:
        remaining = {e.data.get(CONF_CUSTOMER_ID) or e.data.get('username')
                     for e in hass.config_entries.async_entries(DOMAIN)
                     if e.entry_id != entry.entry_id}
        # A duplicate entry does not own the account exclusively.
        if account in remaining:
            return
        runtime = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
        coordinator = runtime.get('coordinator')
        if coordinator:
            await coordinator.stop_history()
        for other in hass.config_entries.async_entries(DOMAIN):
            if other.entry_id != entry.entry_id and account in other.data.get('linked_customers', []):
                values = dict(other.data)
                values['linked_customers'] = [c for c in values['linked_customers'] if c != account]
                hass.config_entries.async_update_entry(other, data=values)
        registry = er.async_get(hass)
        owned = [e for e in er.async_entries_for_config_entry(registry, entry.entry_id)
                 if e.platform == DOMAIN]
        manager = hass.data.get(KEY)
        if manager:
            await manager.detach(account)
            store = manager.store
        else:
            store = Store(hass, 1, KEY, atomic_writes=True)
        store_lock = manager.lock if manager else asyncio.Lock()
        legacy_ids = {}
        async with store_lock:
            data = deepcopy(manager.data) if manager else await store.async_load() or {}
            configs = [data.get('accounts', {}).get(account, {})]
            configs += [row for row in data.get('archive', []) if row.get('account') == account]
            for config in configs:
                expected = config.get('legacy_meter_entity') or config.get('meter_entity')
                for key in ('legacy_entry_id', 'entry_id'):
                    legacy_id = config.get(key)
                    if not legacy_id:
                        continue
                    legacy = hass.config_entries.async_get_entry(legacy_id)
                    if (legacy and legacy.domain == 'utility_meter'
                        and legacy.title.startswith('EVN ' + account + ' Electric Meter')
                        and legacy.options.get('source') == config.get('source')
                        and expected and expected != config.get('source')):
                        entities = er.async_entries_for_config_entry(registry, legacy_id)
                        if any(e.entity_id == expected and e.platform == 'utility_meter' for e in entities):
                            legacy_ids[legacy_id] = [e.entity_id for e in entities]
            if remaining:
                for key in ('accounts', 'names'):
                    data.get(key, {}).pop(account, None)
                data['archive'] = [row for row in data.get('archive', []) if row.get('account') != account]
                await store.async_save(data)
            else:
                data = {'accounts': {}, 'archive': []}
                await store.async_remove()
            if manager:
                manager.data = data
                manager.cache.clear(); manager.electric_cache.clear()
                manager.series_cache.clear(); manager.live_points.clear()
        for legacy_id in legacy_ids:
            await hass.config_entries.async_remove(legacy_id)
        def purge():
            with _LOCK:
                purge_files(hass.config.path('evnvn'), AUTH, account, remaining)
        await hass.async_add_executor_job(purge)
        # Remove states/registry via HA APIs; never remove the selected physical sensor.
        entity_ids = [e.entity_id for e in owned]
        for entity_id in entity_ids:
            hass.states.async_remove(entity_id)
            registry.async_remove(entity_id)
        entity_ids += [entity for entities in legacy_ids.values() for entity in entities]
        if entity_ids and hass.services.has_service('recorder', 'purge_entities'):
            await hass.services.async_call('recorder', 'purge_entities',
                {'entity_id': entity_ids, 'keep_days': 0}, blocking=True)
            from homeassistant.components.recorder import get_instance
            recorder = get_instance(hass)
            done = asyncio.Event()
            recorder.async_clear_statistics(
                entity_ids, on_done=lambda: hass.loop.call_soon_threadsafe(done.set))
            async with asyncio.timeout(60):
                await done.wait()
        # Login sessions contain tokens. Their locks may be held by an HTTP worker.
        def clear_sessions():
            import sys
            for module_name in ('cpc_session', 'billing_session'):
                module = sys.modules.get(__package__ + '.' + module_name)
                if module:
                    with module._LOCK:
                        module._SESSIONS.clear()
        await hass.async_add_executor_job(clear_sessions)
