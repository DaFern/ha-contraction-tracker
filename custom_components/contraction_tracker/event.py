"""Native activity event entity; only verified live operations trigger events."""

from homeassistant.components.event import EventEntity
from homeassistant.core import callback

from .activity import EVENT_TYPES
from .entity import TrackerEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([ActivityEvent(entry)])


class ActivityEvent(TrackerEntity, EventEntity):
    _attr_name = "Activity"
    _attr_event_types = list(EVENT_TYPES)
    _attr_icon = "mdi:calendar-heart"
    _subscribe_state = False

    def __init__(self, entry):
        super().__init__(entry, "activity")

    @property
    def available(self):
        # A later ambiguous write must not make old activity look newly delivered.
        return True

    async def async_added_to_hass(self):
        # EventEntity restores the last timestamp/attributes; never _trigger_event
        # for restored data. Do not subscribe to generic measurement publications.
        await super().async_added_to_hass()
        self._runtime.activity_entity = self
        self.async_on_remove(self._runtime.tracker.subscribe_activity(self.publish_activity))
        self.async_on_remove(self._clear_runtime)

    @callback
    def _clear_runtime(self):
        self._runtime.activity_entity = None

    @callback
    def publish_activity(self, metadata):
        kind = metadata["event_type"]
        attributes = {key: value for key, value in metadata.items() if key != "event_type"}
        self._trigger_event(kind, {"entry_id": self._entry.entry_id, **attributes})
        self.async_write_ha_state()
