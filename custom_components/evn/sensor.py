from homeassistant.components.sensor import SensorEntity
from homeassistant.const import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity
import logging
from .const import DOMAIN, CONF_CUSTOMER_ID, CONF_NGAYDAUKY

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up EVN VN sensors from a config entry."""
    customer_id = config_entry.data[CONF_CUSTOMER_ID]
    ngaydauky = None
    if config_entry.options and CONF_NGAYDAUKY in config_entry.options:
        ngaydauky = int(config_entry.options[CONF_NGAYDAUKY])
        _LOGGER.info(f"Setting up EVN VN sensors with ngaydauky={ngaydauky} from options")
    else:
        ngaydauky = int(config_entry.data.get(CONF_NGAYDAUKY, 1))
        _LOGGER.info(f"Setting up EVN VN sensors with ngaydauky={ngaydauky} from data")

    # Get coordinator from hass.data
    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]

    SENSOR_TYPES = [
        "chi_so_cuoi_ky", "chi_so_tam_chot",
        "tieu_thu_ky_nay", "tien_dien_ky_nay",
        "tieu_thu_ky_truoc", "tien_dien_ky_truoc",
        "tieu_thu_ky_truoc_nua", "tien_dien_ky_truoc_nua",
        "tieu_thu_hom_nay", "tieu_thu_hom_qua", "tieu_thu_hom_kia",
        "chi_tiet_dien_tieu_thu_ky_nay", "tien_dien_san_luong_nam_nay",
        "lich_cat_dien", "lan_cap_nhat_cuoi", "tien_no",
        "dong_bo_du_lieu", "tien_do_tai_pdf"
    ]
    from homeassistant.helpers import entity_registry as er
    from .database import save_entity_ids,entity_ids
    registry=er.async_get(hass)
    await hass.async_add_executor_job(save_entity_ids,{e.unique_id:e.entity_id for e in registry.entities.values() if e.platform=='evn' and e.unique_id.startswith(customer_id+'_')})
    saved=await hass.async_add_executor_job(entity_ids,customer_id)
    entities = []
    for sensor_type in SENSOR_TYPES:
        unique_id = f"{customer_id}_{sensor_type}"
        unit = None
        entity=EVNSensor(coordinator,customer_id,sensor_type,unique_id,unit,ngaydauky)
        desired=saved.get(unique_id);occupied=registry.async_get(desired) if desired else None
        if desired and (not occupied or (occupied.platform=='evn' and occupied.unique_id==unique_id)):entity.entity_id=desired
        entities.append(entity)
        _LOGGER.debug(f"Adding {len(entities)} sensors for {customer_id}")
    from .meter_comparison import async_manager
    manager = await async_manager(hass)
    manager.register_platform(customer_id, async_add_entities)
    config_entry.async_on_unload(lambda: manager.platforms.pop(customer_id, None))
    config_entry.async_on_unload(lambda: manager.outputs.discard(customer_id))
    async_add_entities(entities)
    return True


VIETNAMESE_NAMES = {
    "chi_so_cuoi_ky": "Chỉ số cuối kỳ trước",
    "chi_so_tam_chot": "Chỉ số tạm chốt",
    "tieu_thu_ky_nay": "Tiêu thụ kỳ này",
    "tien_dien_ky_nay": "Kỳ này",
    "tieu_thu_ky_truoc": "Tiêu thụ kỳ trước",
    "tien_dien_ky_truoc": "Kỳ trước",
    "tieu_thu_ky_truoc_nua": "Tiêu thụ kỳ trước nữa",
    "tien_dien_ky_truoc_nua": "Kỳ trước nữa",
    "tieu_thu_hom_nay": "Tiêu thụ hôm nay",
    "tieu_thu_hom_qua": "Tiêu thụ hôm qua",
    "tieu_thu_hom_kia": "Tiêu thụ hôm kia",
    "chi_tiet_dien_tieu_thu_ky_nay": "Chi tiết kỳ này",
    "tien_dien_san_luong_nam_nay": "Hóa đơn năm nay",
    "lich_cat_dien": "Lịch cắt điện",
    "lan_cap_nhat_cuoi": "Update Last",
    "tien_no": "Tiền nợ",
    "dong_bo_du_lieu": "Đồng bộ dữ liệu",
    "tien_do_tai_pdf": "Tiến độ tải PDF",
}


class EVNSensor(CoordinatorEntity, SensorEntity):
    """EVN VN Sensor Entity using Coordinator."""

    def __init__(self, coordinator, customer_id, sensor_type, unique_id, unit=None, ngaydauky=1):
        """Initialize the sensor."""
        super().__init__(coordinator)  # type: ignore
        self._userevn = customer_id
        self._customer_id = customer_id
        self._sensor_type = sensor_type
        self._unique_id = unique_id
        self._unit = unit
        self._ngaydauky = ngaydauky
        self._attributes = {}

    async def async_added_to_hass(self):
        """Run when entity is added to hass."""
        await super().async_added_to_hass()
        from .database import save_entity_ids
        await self.coordinator.hass.async_add_executor_job(save_entity_ids,{self.unique_id:self.entity_id})
        _LOGGER.debug(f"Added {self._sensor_type} sensor to hass for {self._userevn}")

    @property
    def name(self):
        return VIETNAMESE_NAMES.get(
            self._sensor_type,
            self._sensor_type.replace('_', ' ').title()
        )

    @property
    def unique_id(self):
        return self._unique_id

    @property
    def state(self):
        row=((self.coordinator.data or {}).get('sensor_values') or {}).get(self._sensor_type,{})
        return row.get('value')

    @property
    def icon(self):
        ICON_MAPPING = {
            "chi_so_cuoi_ky": "mdi:transmission-tower-export",
            "chi_so_tam_chot": "mdi:transmission-tower-export",
            "tieu_thu_ky_nay": "mdi:transmission-tower-export",
            "tieu_thu_hom_nay": "mdi:transmission-tower-export",
            "tieu_thu_hom_qua": "mdi:transmission-tower-export",
            "tieu_thu_hom_kia": "mdi:transmission-tower-export",
            "tieu_thu_ky_truoc": "mdi:transmission-tower-export",
            "tieu_thu_ky_truoc_nua": "mdi:transmission-tower-export",
            "tien_dien_ky_truoc": "mdi:cash-multiple",
            "tien_dien_ky_nay": "mdi:cash-multiple",
            "tien_dien_ky_truoc_nua": "mdi:cash-multiple",
            "lan_cap_nhat_cuoi": "mdi:clock-time-eight",
            "chi_tiet_dien_tieu_thu_ky_nay": "mdi:calendar-month",
            "tien_dien_san_luong_nam_nay": "mdi:calendar-month",
            "tien_no": "mdi:cash-multiple",
            "lich_cat_dien": "mdi:calendar-alert",
            "dong_bo_du_lieu": "mdi:cloud-sync",
            "tien_do_tai_pdf": "mdi:file-download-outline"
        }
        return ICON_MAPPING.get(self._sensor_type, None)

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._customer_id)},
            "name": f"EVN VN Device ({self._customer_id})",
            "manufacturer": "LucNhatTieuCa",
            "model": "EVN VN",
            "sw_version": "2026.10.28.6",
        }

    @property
    def entity_category(self):
        if self._sensor_type in ('dong_bo_du_lieu','tien_do_tai_pdf'):
            return EntityCategory.DIAGNOSTIC
        return None

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        # Lịch cắt điện luôn available, ngay cả khi không có data
        if self._sensor_type in ("lich_cat_dien", "dong_bo_du_lieu", "tien_do_tai_pdf"):
            return True
        return self.coordinator.last_update_success

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return ((self.coordinator.data or {}).get('sensor_values') or {}).get(self._sensor_type,{}).get('attributes',{})

    @property
    def unit_of_measurement(self):
        if self._sensor_type == "tien_do_tai_pdf":return "%"
        if self._sensor_type == "tien_dien_san_luong_nam_nay":
            return None
        if self._sensor_type.startswith("chi_so_"):
            return "kWh"
        if self._sensor_type.startswith("tieu_thu"):
            return "kWh"
        if self._sensor_type.startswith("tien_"):
            return "VNĐ"
        return self._unit
