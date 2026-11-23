"""One bounded session entity per tracker; complete history stays out of states."""

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.helpers.device_registry import DeviceInfo

from .const import CONF_HOME_PATH, CONF_NOTIFY, DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([SessionSensor(entry)])


class SessionSensor(SensorEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_name = "Session"
    _attr_icon = "mdi:baby-face-outline"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["off", "rest", "active", "rate"]

    def __init__(self, entry):
        self._entry = entry
        self._runtime = entry.runtime_data
        self._attr_unique_id = f"{entry.entry_id}_session"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)}, name=entry.title,
            manufacturer="Community", model="Contraction Tracker",
        )

    async def async_added_to_hass(self):
        self._runtime.tracker.entity_id = self.entity_id
        self.async_on_remove(self._runtime.tracker.subscribe(self.async_write_ha_state))

    @property
    def native_value(self):
        return self._runtime.tracker.view()["p"]

    @property
    def extra_state_attributes(self):
        current = self._runtime.tracker.view()
        return {
            "contraction_tracker": True,
            "entry_id": self._entry.entry_id,
            "current": current,
            "home_path": self._runtime.settings.get(CONF_HOME_PATH, "/lovelace/0"),
            "notifications_enabled": self._runtime.settings.get(CONF_NOTIFY, "none") != "none",
        }
