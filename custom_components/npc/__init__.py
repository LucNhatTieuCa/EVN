"""EVN VN Integration"""

import logging
from pathlib import Path
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv

from .const import (
    DOMAIN,
    CONF_USERNAME,
    CONF_CUSTOMER_ID,
    CONF_NGAYDAUKY,
)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
_LOGGER = logging.getLogger(__name__)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Preserve legacy add-on accounts without inventing API credentials."""
    if entry.version > 2:
        return False
    if entry.version == 1:
        data = dict(entry.data)
        username = data.get(CONF_USERNAME)
        if not isinstance(username, str) or not username.strip():
            _LOGGER.error("Legacy EVN entry has no account identifier")
            return False
        # Version 1 uses the add-on database; username is the sensor ID prefix.
        data.setdefault(CONF_CUSTOMER_ID, username)
        hass.config_entries.async_update_entry(entry, data=data, version=2, minor_version=1)
    return True


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up EVN VN from yaml configuration."""
    from .paths import configure
    configure(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Serialize account initialization and sensor creation."""
    import asyncio
    from .paths import configure
    configure(hass)
    lock = hass.data.setdefault('npc_initialization_lock', asyncio.Lock())
    async with lock:
        return await _async_setup_entry(hass, entry)


async def _async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up EVN VN from a config entry."""
    from .native_coordinator import EVNCoordinator
    from .views import EVNStaticView, EVNPingView, EVNOptionsView, EVNMonthlyDataView, EVNDailyDataView, EVNCurrentPeriodView
    customer_id = entry.data[CONF_CUSTOMER_ID]
    ngaydauky = entry.options.get(CONF_NGAYDAUKY, entry.data.get(CONF_NGAYDAUKY, 1))
    if not isinstance(customer_id,str) or not customer_id.startswith('PC'):
        raise ValueError('This local EVN integration supports CPC customer accounts')
    coordinator = EVNCoordinator(hass, customer_id)

    from .database import ensure_database
    await hass.async_add_executor_job(ensure_database)

    siblings = entry.data.get('linked_customers', [])
    if siblings:
        async def import_linked():
            for code in siblings:
                if not any(e.data.get(CONF_CUSTOMER_ID) == code for e in hass.config_entries.async_entries(DOMAIN)):
                    await hass.config_entries.flow.async_init(DOMAIN, context={'source': 'import'}, data={'customer_id': code})
        hass.async_create_task(import_linked())

    # Fetch initial data
    await coordinator.async_config_entry_first_refresh()

    # Store coordinator
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "customer_id": customer_id,
        "ngaydauky": ngaydauky,
    }

    from .meter_comparison import async_manager
    await async_manager(hass)

    # Forward to sensor platform
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])

    # Register webui views (only once)
    if "api_registered" not in hass.data.get(DOMAIN, {}):
        webui_path = str(Path(__file__).parent / "webui")
        hass.http.register_view(EVNStaticView(webui_path, hass))
        hass.http.register_view(EVNPingView(hass))
        hass.http.register_view(EVNOptionsView(hass))
        hass.http.register_view(EVNMonthlyDataView(hass))
        hass.http.register_view(EVNDailyDataView(hass))
        hass.http.register_view(EVNCurrentPeriodView(hass))
        hass.data.setdefault(DOMAIN, {})["api_registered"] = True
        _LOGGER.info("Registered NPC API endpoints and WebUI at %s", webui_path)

    # Register WebUI panel (only once)
    if not hass.data.get(DOMAIN, {}).get("panel_registered"):
        try:
            from homeassistant.components import frontend

            frontend.async_register_built_in_panel(
                hass,
                component_name="iframe",
                sidebar_title="EVN Monitor",
                sidebar_icon="mdi:lightning-bolt",
                frontend_url_path="npc_monitor",
                config={"url": "/npc-monitor/index.html"},
                require_admin=False,
            )
            hass.data.setdefault(DOMAIN, {})["panel_registered"] = True
            _LOGGER.info("Registered EVN Monitor panel")
        except Exception as ex:
            _LOGGER.debug("Could not register panel: %s", str(ex))

    coordinator.start_history()
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # Stop sensor listeners before closing the API session.
    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["sensor"])
    if not unload_ok:
        return False

    from .meter_comparison import KEY
    manager=hass.data.get(KEY)
    if manager:await manager.detach(entry.data[CONF_CUSTOMER_ID])

    coordinator=hass.data.get(DOMAIN,{}).get(entry.entry_id,{}).get('coordinator')
    if coordinator and hasattr(coordinator,'stop_history'):await coordinator.stop_history()

    # Unload sensor platform
    unload_ok = True
    
    if unload_ok and entry.entry_id in hass.data.get(DOMAIN, {}):
        hass.data[DOMAIN].pop(entry.entry_id)

    remaining=[value for value in hass.data.get(DOMAIN,{}).values() if isinstance(value,dict) and 'coordinator' in value]
    if not remaining and hass.data.get(DOMAIN,{}).get('panel_registered'):
        from homeassistant.components import frontend
        frontend.async_remove_panel(hass,'npc_monitor')
        hass.data[DOMAIN]['panel_registered']=False
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_remove_entry(hass:HomeAssistant,entry:ConfigEntry)->None:
    """Disconnect only: keep invoice history, identity map and chosen source for re-add."""
    from .meter_comparison import KEY
    manager=hass.data.get(KEY)
    if manager:await manager.detach(entry.data[CONF_CUSTOMER_ID])
