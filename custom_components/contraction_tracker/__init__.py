"""Contraction Tracker: local logging, not a medical device."""

from dataclasses import dataclass
from datetime import timedelta
import logging
from pathlib import Path

import probatio as vol

from homeassistant.auth.permissions.const import POLICY_CONTROL, POLICY_READ
from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import Platform
from homeassistant.core import CoreState, HomeAssistant, ServiceCall, SupportsResponse, callback
from homeassistant.exceptions import ConfigEntryError, ServiceValidationError, Unauthorized
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.storage import Store
from homeassistant.helpers.event import async_call_later, async_track_time_interval

from .const import (
    COMMANDS, CONF_HOME_PATH, CONF_NOTIFY, CONF_PUBLIC, DOMAIN, MODULE_URL,
    SERVICE_COMMAND, STATIC_URL, STORAGE_VERSION,
)
from .manager import PersistenceError, Tracker, verified_save
from .model import InvalidCommand, InvalidStorage, load_state
from .notifications import build_long_warning, build_notification, build_rating, build_warning
from .location import resolve as resolve_location
from .migration import read_source

_LOGGER = logging.getLogger(__name__)
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
PLATFORMS = [Platform.SENSOR]


@dataclass
class Runtime:
    """Config-entry-owned resources; no global copy of personal records."""

    tracker: Tracker
    store: Store
    panel_path: str
    settings: dict


def get_runtime(hass: HomeAssistant, entry_id: str) -> Runtime:
    entry = hass.config_entries.async_get_entry(entry_id)
    if (not entry or entry.domain != DOMAIN or entry.state is not ConfigEntryState.LOADED
            or not isinstance(getattr(entry, "runtime_data", None), Runtime)):
        raise ServiceValidationError("This tracker is not loaded.")
    return entry.runtime_data


async def authorize(hass, user_id, runtime, permission=POLICY_CONTROL):
    """Use native entity permissions for authenticated API and phone callers."""
    user = await hass.auth.async_get_user(user_id) if user_id else None
    entity_id = runtime.tracker.entity_id
    if not user or not user.is_active or not entity_id or not user.permissions.check_entity(entity_id, permission):
        raise Unauthorized


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Register public static *code* and authenticated application endpoints."""
    await hass.http.async_register_static_paths([
        StaticPathConfig(STATIC_URL, str(Path(__file__).parent / "frontend"), True),
    ])
    hass.data[DOMAIN] = {"entries": set()}

    async def command(call: ServiceCall):
        runtime = get_runtime(hass, call.data["entry_id"])
        # Native automations may have no user context; authenticated callers must
        # have control permission. Concurrency tokens are never authorization.
        if call.context.user_id is not None:
            await authorize(hass, call.context.user_id, runtime)
        if call.data["command"] == "reminders_on" and runtime.settings.get(CONF_NOTIFY, "none") == "none":
            raise ServiceValidationError("Select a phone notification action before enabling the logging reminder.")
        try:
            return await runtime.tracker.command(call.data["command"], call.data.get("token", ""))
        except (InvalidCommand, PersistenceError) as err:
            raise ServiceValidationError(str(err)) from err

    hass.services.async_register(DOMAIN, SERVICE_COMMAND, command,
        schema=vol.Schema({
            vol.Required("entry_id"): cv.string,
            vol.Required("command"): vol.In(COMMANDS),
            vol.Optional("token", default=""): cv.string,
        }), supports_response=SupportsResponse.OPTIONAL)

    async def edit(call: ServiceCall):
        runtime = get_runtime(hass, call.data["entry_id"])
        if call.context.user_id is not None:
            await authorize(hass, call.context.user_id, runtime)
        try:
            return await runtime.tracker.edit(call.data["record_id"], call.data["revision"],
                call.data["start"], call.data["end"], call.data["intensity"])
        except (InvalidCommand, PersistenceError) as err:
            raise ServiceValidationError(str(err)) from err

    hass.services.async_register(DOMAIN, "edit", edit, schema=vol.Schema({
        vol.Required("entry_id"): cv.string,
        vol.Required("record_id"): cv.string,
        vol.Required("revision"): cv.string,
        vol.Required("start"): vol.Coerce(float),
        vol.Required("end"): vol.Coerce(float),
        vol.Required("intensity"): vol.In(("Not rated", "Mild", "Moderate", "Strong")),
    }), supports_response=SupportsResponse.OPTIONAL)
    async def configure_guidance(call: ServiceCall):
        runtime = get_runtime(hass, call.data["entry_id"])
        if call.context.user_id is not None:
            await authorize(hass, call.context.user_id, runtime)
        mode = call.data.get("mode", "manual")
        person = call.data.get("person", "")
        home = call.data.get("home", "")
        hospitals = call.data.get("hospitals", [])
        if mode == "automatic":
            refs = [person, home, *hospitals]
            if not all(hass.states.get(ref) is not None for ref in refs):
                raise ServiceValidationError("Choose existing person and zone entities.")
            source = hass.states.get(person).attributes.get("source")
            if source:
                refs.append(source)
            if call.context.user_id:
                user = await hass.auth.async_get_user(call.context.user_id)
                if not user or not all(user.permissions.check_entity(ref, POLICY_READ) for ref in refs):
                    raise Unauthorized
        try:
            return await runtime.tracker.configure_guidance(
                call.data["token"], call.data["location"], call.data["interval"],
                mode=mode, person=person, home=home, hospitals=hospitals)
        except (InvalidCommand, PersistenceError) as err:
            raise ServiceValidationError(str(err)) from err

    hass.services.async_register(DOMAIN, "configure_guidance", configure_guidance, schema=vol.Schema({
        vol.Required("entry_id"): cv.string,
        vol.Required("token"): cv.string,
        vol.Required("location"): vol.In(("unspecified", "home", "hospital")),
        vol.Required("interval"): vol.All(vol.In(tuple(range(60, 601, 60))), vol.Coerce(int)),
        vol.Optional("mode", default="manual"): vol.In(("manual", "automatic")),
        vol.Optional("person", default=""): cv.string,
        vol.Optional("home", default=""): cv.string,
        vol.Optional("hospitals", default=[]): [cv.string],
    }), supports_response=SupportsResponse.OPTIONAL)

    async def import_legacy(call: ServiceCall):
        # Migration is never an anonymous automation/phone action.
        user = await hass.auth.async_get_user(call.context.user_id) if call.context.user_id else None
        if not user or not user.is_active or not user.is_admin:
            raise Unauthorized
        runtime = get_runtime(hass, call.data["entry_id"])
        await authorize(hass, call.context.user_id, runtime)
        apply = call.data.get("apply", False)
        if hass.state is not CoreState.running:
            raise ServiceValidationError("Import requires Home Assistant to be fully running.")
        if apply and runtime.settings.get(CONF_NOTIFY, "none") != "none":
            raise ServiceValidationError("Disable native phone notifications until migration is verified.")
        entities = {key: call.data["source_" + key] for key in
                    ("records", "state", "movement", "guidance", "automation")}
        async def fresh_source():
            if hass.state is not CoreState.running:
                raise InvalidCommand("Home Assistant is stopping; migration was refused.")
            return await read_source(hass, entities, call.context, stopped=apply)
        try:
            bundle = await fresh_source()
            return await runtime.tracker.import_legacy(
                bundle, apply=apply, expected_source=call.data.get("expected_source", ""),
                expected_target=call.data.get("expected_target", ""), source_check=fresh_source)
        except (InvalidCommand, PersistenceError) as err:
            raise ServiceValidationError(str(err)) from err

    hass.services.async_register(DOMAIN, "import_legacy", import_legacy, schema=vol.Schema({
        vol.Required("entry_id"): cv.string,
        vol.Required("source_records"): cv.entity_id,
        vol.Required("source_state"): cv.entity_id,
        vol.Required("source_movement"): cv.entity_id,
        vol.Required("source_guidance"): cv.entity_id,
        vol.Required("source_automation"): cv.entity_id,
        vol.Optional("apply", default=False): cv.boolean,
        vol.Optional("expected_source", default=""): cv.string,
        vol.Optional("expected_target", default=""): cv.string,
    }), supports_response=SupportsResponse.ONLY)
    from .websocket import async_register
    async_register(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    settings = {**entry.data, **entry.options}
    store_key = f"{DOMAIN}.{entry.entry_id}"
    store = Store(hass, STORAGE_VERSION, store_key, private=True, atomic_writes=True)
    data = await store.async_load()
    panel_path = f"contractions-{entry.entry_id.lower()}"

    async def notify(view):
        service = settings.get(CONF_NOTIFY, "none")
        if service == "none":
            return
        payload = build_notification(view, entry.entry_id, f"/{panel_path}",
                                     settings.get(CONF_PUBLIC, False), entry.title)
        await hass.services.async_call("notify", service.removeprefix("notify."),
                                       payload, blocking=True)
        for tag in ([f"contraction_tracker_rating_{entry.entry_id}"] if view["p"] != "rate" else []) + (
            [f"contraction_tracker_movement_{entry.entry_id}"] if not view["movement"]["enabled"] or not view["movement"]["last_alert"] else []
        ) + (
            [f"contraction_tracker_long_{entry.entry_id}"]
            if view["p"] != "active" or not view["long_warning_attempted"] else []
        ):
            await hass.services.async_call("notify", service.removeprefix("notify."),
                {"message": "clear_notification", "data": {"tag": tag}}, blocking=True)

    async def send_auxiliary(view, builder):
        service = settings.get(CONF_NOTIFY, "none")
        if service == "none":
            return
        if builder is build_rating:
            payload = builder(view, entry.entry_id, f"/{panel_path}")
            payload["data"]["visibility"] = "public" if settings.get(CONF_PUBLIC, False) else "private"
        else:
            payload = builder(view, entry.entry_id, f"/{panel_path}", settings.get(CONF_PUBLIC, False))
        await hass.services.async_call("notify", service.removeprefix("notify."), payload, blocking=True)

    def location_provider(config, now):
        refs = {config["person"], config["home"], *config["hospitals"]}
        person = hass.states.get(config["person"])
        if person and person.attributes.get("source"):
            refs.add(person.attributes["source"])
        states = {}
        for ref in refs:
            value = hass.states.get(ref)
            if value:
                states[ref] = {"state": value.state, "attributes": value.attributes,
                               "reported": value.last_reported.timestamp()}
        return resolve_location(config, states, now)

    try:
        async def readback():
            # A fresh public Store cannot return the writer's pending buffer.
            return await Store(
                hass, STORAGE_VERSION, store_key, private=True,
                atomic_writes=True, read_only=True,
            ).async_load()
        if isinstance(data, dict) and type(data.get("schema")) is int and data["schema"] in (1, 2, 3, 4, 5, 6, 7):
            data = await verified_save(load_state(data), store.async_save, readback)
        tracker = Tracker(data, store.async_save, notify, location_provider=location_provider, readback=readback)
        # Reconcile elapsed downtime before exposing controls or old rest timers.
        await tracker.tick()
        if tracker.persistence_uncertain:
            raise PersistenceError("Idle-session closure could not be verified.")
    except PersistenceError as err:
        raise ConfigEntryError("Stored data upgrade could not be verified. Inspect storage before retrying; no reset was performed.") from err
    except InvalidStorage as err:
        raise ConfigEntryError("Stored contraction data could not be validated. Restore a backup; no data was reset.") from err
    entry.runtime_data = Runtime(tracker, store, panel_path, settings)
    tracker.rating_notify = lambda view: send_auxiliary(view, build_rating)
    tracker.warning_notify = (
        (lambda view: send_auxiliary(view, build_warning))
        if settings.get(CONF_NOTIFY, "none") != "none" else None
    )
    tracker.long_warning_notify = (
        (lambda view: send_auxiliary(view, build_long_warning))
        if settings.get(CONF_NOTIFY, "none") != "none" else None
    )
    global_state = hass.data[DOMAIN]
    if not global_state["entries"]:
        frontend.add_extra_js_url(hass, MODULE_URL)
    global_state["entries"].add(entry.entry_id)
    try:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        await panel_custom.async_register_panel(
            hass, frontend_url_path=panel_path,
            webcomponent_name="contraction-tracker-panel", sidebar_title=entry.title,
            sidebar_icon="mdi:baby-face-outline", module_url=MODULE_URL,
            config={"entry_id": entry.entry_id}, require_admin=False,
        )
    except Exception:
        # Failed setup must not leave a module lease or an active platform behind.
        await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
        global_state["entries"].discard(entry.entry_id)
        if not global_state["entries"]:
            frontend.remove_extra_js_url(hass, MODULE_URL)
        await tracker.shutdown()
        raise

    async def handle_phone(event):
        action = event.data.get("action")
        if not isinstance(action, str) or not action.startswith(f"CT|{entry.entry_id}|"):
            return
        parts = action.split("|")
        if len(parts) != 4 or event.data.get("tag") not in (
            f"contraction_tracker_{entry.entry_id}", f"contraction_tracker_rating_{entry.entry_id}",
            f"contraction_tracker_long_{entry.entry_id}",
        ):
            return
        try:
            await authorize(hass, event.context.user_id, entry.runtime_data)
            await tracker.command(parts[2], parts[3], received=int(event.time_fired.timestamp()))
        except (InvalidCommand, Unauthorized):
            return  # A stale button must never change the current contraction.
        except PersistenceError:
            _LOGGER.warning("A phone action could not be confirmed in storage")

    @callback
    def phone_event(event):
        entry.async_create_background_task(hass, handle_phone(event), "Contraction phone action")

    entry.async_on_unload(hass.bus.async_listen("mobile_app_notification_action", phone_event))
    @callback
    def location_event(event):
        refs = tracker.location_references()
        if not refs:
            return
        person_id = next((ref for ref in refs if ref.startswith("person.")), "")
        person = hass.states.get(person_id)
        if person and person.attributes.get("source"):
            refs.add(person.attributes["source"])
        if event.data.get("entity_id") in refs:
            entry.async_create_background_task(hass, tracker.refresh_location(), "Refresh tracker location")
    entry.async_on_unload(hass.bus.async_listen("state_changed", location_event))
    entry.async_on_unload(entry.add_update_listener(_options_updated))
    cancel_long_warning = None
    scheduled_identity = None

    @callback
    def clear_long_warning_timer():
        nonlocal cancel_long_warning, scheduled_identity
        if cancel_long_warning is not None:
            cancel_long_warning()
        cancel_long_warning = None
        scheduled_identity = None

    async def check_long_warning(identity):
        await tracker.check_long_contraction(identity)
        schedule_long_warning()  # Reschedule if the clock moved backwards.

    @callback
    def schedule_long_warning():
        nonlocal cancel_long_warning, scheduled_identity
        schedule = tracker.long_warning_schedule()
        if schedule is None:
            clear_long_warning_timer()
            return
        identity, delay = schedule
        if scheduled_identity == identity:
            return
        clear_long_warning_timer()
        scheduled_identity = identity

        @callback
        def due(_now):
            nonlocal cancel_long_warning, scheduled_identity
            cancel_long_warning = None
            scheduled_identity = None
            entry.async_create_background_task(
                hass, check_long_warning(identity), "Check contraction timer warning"
            )

        cancel_long_warning = async_call_later(hass, delay, due)

    entry.async_on_unload(tracker.subscribe(schedule_long_warning))
    entry.async_on_unload(clear_long_warning_timer)
    schedule_long_warning()
    async def tick(_now):
        await tracker.tick()
    entry.async_on_unload(async_track_time_interval(hass, tick, timedelta(minutes=1)))
    if tracker.view()["p"] != "off" or tracker.view()["idle_ended"]:
        entry.async_create_background_task(hass, tracker.refresh_notification(),
                                           "Restore contraction notification")
    return True


async def _options_updated(hass, entry):
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    runtime = entry.runtime_data
    await runtime.tracker.shutdown()
    frontend.async_remove_panel(hass, runtime.panel_path)
    entries = hass.data[DOMAIN]["entries"]
    entries.discard(entry.entry_id)
    if not entries:
        frontend.remove_extra_js_url(hass, MODULE_URL)
    return True


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Explicit integration removal deletes its own local history."""
    await Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}").async_remove()
