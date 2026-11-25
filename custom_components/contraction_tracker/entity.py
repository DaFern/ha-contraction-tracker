"""Shared device and push subscription for derived native entities."""

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN


class TrackerEntity(Entity):
    """Derived entities never participate in Session discovery or control auth."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _subscribe_state = True

    def __init__(self, entry, key):
        self._entry = entry
        self._runtime = entry.runtime_data
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)}, name=entry.title,
            manufacturer="Community", model="Contraction Tracker",
        )

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        if self._subscribe_state:
            self.async_on_remove(self._runtime.tracker.subscribe(self.async_write_ha_state))

    @property
    def available(self):
        return not (self._runtime.tracker.persistence_uncertain
                    or self._runtime.tracker.import_uncertain)
