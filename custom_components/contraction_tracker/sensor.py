"""Compatible Session plus small automation-friendly derived measurements."""

from datetime import UTC, datetime

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import UnitOfTime
from homeassistant.helpers.device_registry import DeviceInfo

from .const import CONF_HOME_PATH, CONF_NOTIFY, DOMAIN
from .entity import TrackerEntity


def last(view, key):
    return view["last_record"][key] if view["last_record"] else None


def timestamp(value):
    return datetime.fromtimestamp(value, UTC) if value is not None else None


# No state_class: these are personal session/rolling values, not lifetime totals
# or long-term statistics. Missing values remain unknown, never coerced to zero.
MEASUREMENTS = (
    ("session_count", "Session contraction count", lambda v: v["n"], None),
    ("hourly_starts", "Starts in last hour", lambda v: v["hourly"]["count"], None),
    ("hourly_completed", "Completed contractions in last hour", lambda v: v["hourly"]["completed"], None),
    ("last_duration", "Last contraction duration", lambda v: last(v, "duration"), "duration"),
    ("last_interval", "Last start-to-start interval", lambda v: last(v, "interval"), "duration"),
    ("last_rest", "Last rest period", lambda v: last(v, "rest"), "duration"),
    ("hourly_duration", "Average duration in last hour", lambda v: v["hourly"]["duration"], "duration"),
    ("hourly_interval", "Average start-to-start interval in last hour", lambda v: v["hourly"]["interval"], "duration"),
    ("hourly_interval_samples", "Interval sample count in last hour", lambda v: v["hourly"]["interval_samples"], None),
    ("current_start", "Current contraction started", lambda v: timestamp(v["s"]) if v["p"] == "active" else None, "timestamp"),
    ("last_end", "Last contraction ended", lambda v: timestamp(last(v, "end")), "timestamp"),
    ("last_movement", "Last movement logged", lambda v: timestamp(v["movement"]["last"]) if v["movement"]["count"] else None, "timestamp"),
    ("last_intensity", "Last recorded intensity", lambda v: last(v, "intensity"), "enum"),
    ("resolved_location", "Resolved location", lambda v: v["location"]["location"], "enum"),
)


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([SessionSensor(entry), *(
        MeasurementSensor(entry, *description) for description in MEASUREMENTS
    )])


class MeasurementSensor(TrackerEntity, SensorEntity):
    """One bounded fact from the shared snapshot."""

    def __init__(self, entry, key, name, value, kind):
        super().__init__(entry, key)
        self._attr_name = name
        self._value = value
        self._key = key
        if kind == "duration":
            self._attr_device_class = SensorDeviceClass.DURATION
            self._attr_native_unit_of_measurement = UnitOfTime.SECONDS
            self._attr_suggested_display_precision = 0
        elif kind == "timestamp":
            self._attr_device_class = SensorDeviceClass.TIMESTAMP
        elif kind == "enum":
            self._attr_device_class = SensorDeviceClass.ENUM
            self._attr_options = (["Not rated", "Mild", "Moderate", "Strong"]
                                  if key == "last_intensity" else
                                  ["unspecified", "home", "hospital", "elsewhere", "uncertain"])

    @property
    def native_value(self):
        return self._value(self._runtime.tracker.view())

    @property
    def extra_state_attributes(self):
        if self._key == "resolved_location":
            return {"source": self._runtime.tracker.view()["location"]["source"]}
        return None


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
