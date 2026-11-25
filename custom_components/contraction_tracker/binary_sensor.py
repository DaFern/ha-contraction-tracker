"""Recording/timer states and independent technical diagnostics."""

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.const import EntityCategory

from .entity import TrackerEntity

BINARY_STATES = (
    ("session_recording", "Session recording", lambda v: v["p"] != "off", False),
    ("contraction_active", "Contraction active", lambda v: v["p"] == "active", False),
    ("awaiting_rating", "Awaiting rating", lambda v: v["p"] == "rate", False),
    ("timer_over_two_minutes", "Timer over two minutes", lambda v: v["long_contraction"], False),
    ("save_uncertain", "Save outcome uncertain", lambda v: v["persistence_uncertain"] or v["import_uncertain"], True),
    ("notification_failed", "Notification delivery failed", lambda v: v["notification_failed"], True),
)


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(TrackerBinarySensor(entry, *description) for description in BINARY_STATES)


class TrackerBinarySensor(TrackerEntity, BinarySensorEntity):
    def __init__(self, entry, key, name, value, diagnostic):
        super().__init__(entry, key)
        self._attr_name = name
        self._value = value
        self._diagnostic = diagnostic
        if diagnostic:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def available(self):
        return self._diagnostic or super().available

    @property
    def is_on(self):
        return self._value(self._runtime.tracker.view())
