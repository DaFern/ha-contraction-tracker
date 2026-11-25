"""Isolated native HA lifecycle checks; no live instance or legacy resources.

HA setup, platforms, services, panels, options and public Store APIs are real.
The official test package supplies disposable HA/network/storage fixtures.
Only the explicit panel-registration failure test injects a failing dependency.
"""

from copy import deepcopy
from datetime import UTC, datetime
from functools import partial
import time
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.components import frontend
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import Context
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.storage import Store
from pytest_homeassistant.common import MockConfigEntry, async_fire_time_changed

from custom_components.contraction_tracker import get_runtime
from custom_components.contraction_tracker.const import (
    CONF_HOME_PATH,
    CONF_NOTIFY,
    CONF_PUBLIC,
    CONF_WARNING,
    DOMAIN,
    MODULE_URL,
    STATIC_URL,
    STORAGE_VERSION,
)
from custom_components.contraction_tracker.model import InvalidCommand, new_state, transition
from custom_components.contraction_tracker.manager import Tracker
from custom_components.contraction_tracker.notifications import long_warning_tag


@pytest.fixture(autouse=True)
def isolated_storage(hass_storage):
    """Keep synthetic records in the official test backend, never a live store."""
    yield


@pytest.fixture
def frozen_tracker_clock(freezer, monkeypatch):
    """Inject the fixture clock, not the real time.time captured at module import.

    Setup/unload, the real Tracker, HA's scheduler and storage stay unmocked.
    Resolve time.time on each call so later freezer.move_to calls are observed,
    including by a new Tracker constructed during reload.
    """
    monkeypatch.setattr(
        "custom_components.contraction_tracker.Tracker",
        partial(Tracker, clock=lambda: time.time()),
    )


def new_entry(hass, title="Synthetic tracker", notification="none"):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=title,
        data={
            "name": title,
            CONF_NOTIFY: notification,
            CONF_HOME_PATH: "/lovelace/0",
            CONF_PUBLIC: False,
        },
    )
    entry.add_to_hass(hass)
    return entry


async def setup_entry(hass, title="Synthetic tracker", notification="none"):
    entry = new_entry(hass, title, notification)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data.tracker.entity_id
    return entry


async def command(hass, entry, name):
    current = entry.runtime_data.tracker.view()
    token = current["movement"]["k"] if name in (
        "movement", "reminders_on", "reminders_off"
    ) else current["k"]
    result = await hass.services.async_call(
        DOMAIN,
        "command",
        {"entry_id": entry.entry_id, "command": name, "token": token},
        blocking=True,
        return_response=True,
    )
    await hass.async_block_till_done()
    return result


async def record(hass, entry):
    """Exercise real service dispatch using only synthetic disposable entries."""
    await command(hass, entry, "show")
    await command(hass, entry, "start")
    await command(hass, entry, "stop")
    await command(hass, entry, "Mild")
    return entry.runtime_data.tracker.history()


async def stored(hass, entry):
    return await Store(
        hass,
        STORAGE_VERSION,
        f"{DOMAIN}.{entry.entry_id}",
        private=True,
        atomic_writes=True,
        read_only=True,
    ).async_load()


def module_urls(hass):
    return hass.data[frontend.DATA_EXTRA_MODULE_URL].urls


async def test_fresh_setup_registers_native_sensor_services_and_panel_without_legacy(hass):
    entry = await setup_entry(hass)
    runtime = entry.runtime_data
    state = hass.states.get(runtime.tracker.entity_id)
    assert state.state == "off"
    assert state.attributes["entry_id"] == entry.entry_id
    assert state.attributes["current"]["records_count"] == 0
    assert state.attributes["notifications_enabled"] is False
    assert not any(
        state.domain in {"input_text", "input_button", "todo"}
        for state in hass.states.async_all()
    )
    for service in ("command", "edit", "configure_guidance", "import_legacy"):
        assert hass.services.has_service(DOMAIN, service)
    assert MODULE_URL in module_urls(hass)
    panel = hass.data[frontend.DATA_PANELS][runtime.panel_path]
    assert panel.config["entry_id"] == entry.entry_id
    assert panel.config["_panel_custom"]["module_url"] == MODULE_URL
    assert panel.config["_panel_custom"]["name"] == "contraction-tracker-panel"
    assert get_runtime(hass, entry.entry_id) is runtime


async def test_clean_install_serves_bundled_assets_without_legacy_resource(hass, hass_client):
    await setup_entry(hass)
    client = await hass_client()
    checks = {
        "tracker.js": "contraction-tracker-app-card",
        "state.js": "readCurrent",
        "transport.js": "contraction_tracker/history",
        "tracker.css": ".app",
    }
    for filename, marker in checks.items():
        response = await client.get(f"{STATIC_URL}/{filename}")
        assert response.status == 200
        assert marker in await response.text()
    image = await client.get(f"{STATIC_URL}/icon.png")
    assert image.status == 200
    assert (await image.read()).startswith(b"\x89PNG\r\n\x1a\n")
    legacy = await client.get("/local/contraction-tracker-card.js")
    assert legacy.status == 404


async def test_native_websocket_exposes_panel_and_authorized_history(hass, hass_ws_client):
    entry = await setup_entry(hass)
    history = await record(hass, entry)
    client = await hass_ws_client(hass)
    await client.send_json({"id": 1, "type": "get_panels"})
    panels = await client.receive_json()
    assert panels["success"]
    assert panels["result"][entry.runtime_data.panel_path]["config"]["entry_id"] == entry.entry_id
    await client.send_json({
        "id": 2, "type": f"{DOMAIN}/history", "entry_id": entry.entry_id, "limit": 50,
    })
    result = await client.receive_json()
    assert result["success"]
    assert result["result"]["items"] == history


@pytest.mark.parametrize("phase", ["off", "rest", "active", "rate"])
async def test_unload_reload_preserves_durable_phase_records_and_timer_anchors(hass, phase):
    entry = await setup_entry(hass)
    if phase in ("off", "rest"):
        await record(hass, entry)
        if phase == "off":
            await command(hass, entry, "end")
    else:
        await command(hass, entry, "show")
        await command(hass, entry, "start")
        if phase == "rate":
            await command(hass, entry, "stop")
    old = entry.runtime_data
    before = deepcopy(await stored(hass, entry))
    assert before["p"] == phase
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert old.tracker.closed
    # HA retains a dormant registry placeholder after platform unload.
    # It must not expose the old tracker's actionable session payload.
    unloaded = hass.states.get(old.tracker.entity_id)
    assert unloaded is not None
    assert unloaded.state == STATE_UNAVAILABLE
    assert unloaded.attributes.get("restored") is True
    assert "current" not in unloaded.attributes
    assert not frontend.async_panel_exists(hass, old.panel_path)
    assert MODULE_URL not in module_urls(hass)
    assert await stored(hass, entry) == before
    with pytest.raises(ServiceValidationError):
        get_runtime(hass, entry.entry_id)
    with pytest.raises(InvalidCommand):
        await old.tracker.command("show")
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    restored = entry.runtime_data
    assert restored is not old
    assert restored.tracker is not old.tracker
    assert await stored(hass, entry) == before
    assert restored.tracker.history() == before["records"]
    for key in ("p", "s", "e", "i", "r", "n", "d", "v", "k"):
        assert restored.tracker.view()[key] == before[key]
    assert restored.tracker.view()["restored"] is (phase != "off")
    assert MODULE_URL in module_urls(hass)
    assert frontend.async_panel_exists(hass, restored.panel_path)


async def test_options_flow_reloads_target_and_retains_records_with_private_phone_payload(hass):
    calls = []
    async def fake_phone(call):
        calls.append(deepcopy(dict(call.data)))
    hass.services.async_register("notify", "mobile_app_synthetic_test_phone", fake_phone)
    entry = await setup_entry(hass)
    history = await record(hass, entry)
    old = entry.runtime_data
    before = await stored(hass, entry)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_NOTIFY: "notify.mobile_app_synthetic_test_phone",
            CONF_HOME_PATH: "/test-dashboard/home",
            CONF_PUBLIC: False,
            CONF_WARNING: True,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    assert old.tracker.closed
    assert entry.runtime_data is not old
    assert await stored(hass, entry) == before
    assert entry.runtime_data.tracker.history() == history
    state = hass.states.get(entry.runtime_data.tracker.entity_id)
    assert state.attributes["notifications_enabled"] is True
    assert state.attributes["home_path"] == "/test-dashboard/home"
    main = [call for call in calls if call.get("message") != "clear_notification"]
    assert main
    assert main[-1]["data"]["visibility"] == "private"
    assert main[-1]["data"]["tag"] == f"contraction_tracker_{entry.entry_id}"


async def test_multiple_entries_keep_history_and_module_panel_leases_independent(hass):
    first = await setup_entry(hass, "Synthetic first")
    second = await setup_entry(hass, "Synthetic second")
    await record(hass, first)
    first_runtime, second_runtime = first.runtime_data, second.runtime_data
    assert first_runtime.tracker.entity_id != second_runtime.tracker.entity_id
    assert first_runtime.panel_path != second_runtime.panel_path
    assert len(first_runtime.tracker.history()) == 1
    assert second_runtime.tracker.history() == []
    assert second_runtime.tracker.view()["p"] == "off"
    assert await hass.config_entries.async_unload(first.entry_id)
    await hass.async_block_till_done()
    assert MODULE_URL in module_urls(hass)
    assert not frontend.async_panel_exists(hass, first_runtime.panel_path)
    assert frontend.async_panel_exists(hass, second_runtime.panel_path)
    assert second.state is ConfigEntryState.LOADED
    assert await hass.config_entries.async_unload(second.entry_id)
    await hass.async_block_till_done()
    assert MODULE_URL not in module_urls(hass)
    assert not frontend.async_panel_exists(hass, second_runtime.panel_path)


async def test_removing_one_entry_deletes_only_its_store_and_preserves_the_other(hass):
    first = await setup_entry(hass, "Synthetic remove")
    second = await setup_entry(hass, "Synthetic retain")
    await record(hass, first)
    await record(hass, second)
    second_before = deepcopy(await stored(hass, second))
    removed_path = first.runtime_data.panel_path
    await hass.config_entries.async_remove(first.entry_id)
    await hass.async_block_till_done()
    assert hass.config_entries.async_get_entry(first.entry_id) is None
    assert await stored(hass, first) is None
    assert await stored(hass, second) == second_before
    assert second.state is ConfigEntryState.LOADED
    assert frontend.async_panel_exists(hass, second.runtime_data.panel_path)
    assert not frontend.async_panel_exists(hass, removed_path)
    assert MODULE_URL in module_urls(hass)


async def test_failed_panel_registration_cleans_up_sensor_and_module_lease(hass):
    entry = new_entry(hass)
    with patch(
        "custom_components.contraction_tracker.panel_custom.async_register_panel",
        new=AsyncMock(side_effect=RuntimeError("synthetic panel failure")),
    ):
        assert not await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert hass.data[DOMAIN]["entries"] == set()
    assert MODULE_URL not in module_urls(hass)
    assert not any(
        state.attributes.get("entry_id") == entry.entry_id
        for state in hass.states.async_all()
    )
    assert not frontend.async_panel_exists(hass, f"contractions-{entry.entry_id.lower()}")


async def test_invalid_stored_logical_state_refuses_setup_without_reset(hass):
    entry = new_entry(hass)
    writer = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}")
    invalid = {"schema": 999, "synthetic_note": "must be retained, not reset"}
    await writer.async_save(deepcopy(invalid))
    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert await stored(hass, entry) == invalid
    assert hass.data[DOMAIN]["entries"] == set()
    assert MODULE_URL not in module_urls(hass)


async def test_phone_dispatch_rejects_anonymous_wrong_tag_and_stale_actions(hass, hass_admin_user):
    entry = await setup_entry(hass)
    await command(hass, entry, "show")
    before = deepcopy(await stored(hass, entry))
    action = f"CT|{entry.entry_id}|start|{before['k']}"
    tag = f"contraction_tracker_{entry.entry_id}"
    for context, supplied_tag in (
        (Context(), tag),
        (Context(user_id=hass_admin_user.id), "unrelated_notification"),
    ):
        hass.bus.async_fire(
            "mobile_app_notification_action",
            {"action": action, "tag": supplied_tag},
            context=context,
        )
        await hass.async_block_till_done()
        assert await stored(hass, entry) == before
    hass.bus.async_fire(
        "mobile_app_notification_action",
        {"action": action, "tag": tag},
        context=Context(user_id=hass_admin_user.id),
    )
    await hass.async_block_till_done()
    started = deepcopy(await stored(hass, entry))
    assert started["p"] == "active"
    assert started["n"] == 1
    hass.bus.async_fire(
        "mobile_app_notification_action",
        {"action": action, "tag": tag},
        context=Context(user_id=hass_admin_user.id),
    )
    await hass.async_block_till_done()
    assert await stored(hass, entry) == started


@pytest.mark.parametrize("close", [False, True])
async def test_idle_notification_survives_reload_and_phone_start_or_close(hass, hass_admin_user, close):
    calls = []
    async def phone(call):
        calls.append(deepcopy(dict(call.data)))
    hass.services.async_register("notify", "mobile_app_idle_test", phone)
    entry = await setup_entry(hass, notification="notify.mobile_app_idle_test")
    tracker = entry.runtime_data.tracker
    base = int(time.time()) - 4000
    tracker._clock = lambda: base
    await command(hass, entry, "show")
    await command(hass, entry, "start")
    tracker._clock = lambda: base + 60
    await command(hass, entry, "stop")
    await command(hass, entry, "Mild")
    before = deepcopy(await stored(hass, entry))
    # Reload is the startup/downtime path: reconcile before exposing controls.
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    ended = await stored(hass, entry)
    assert ended["idle_ended"] and ended["p"] == "off"
    assert ended["records"] == before["records"]
    main = [call for call in calls if call.get("message") != "clear_notification"]
    assert "Recording ended after inactivity" in main[-1]["message"]
    assert main[-1]["data"]["persistent"]
    assert not main[-1]["data"]["chronometer"]
    name = "end" if close else "start"
    hass.bus.async_fire(
        "mobile_app_notification_action",
        {"action": f"CT|{entry.entry_id}|{name}|{ended['k']}",
         "tag": f"contraction_tracker_{entry.entry_id}"},
        context=Context(user_id=hass_admin_user.id),
    )
    await hass.async_block_till_done()
    after = await stored(hass, entry)
    assert not after["idle_ended"]
    assert after["records"] == before["records"]
    if close:
        assert after["p"] == "off"
        assert calls[-1]["message"] == "clear_notification"
    else:
        assert after["p"] == "active" and after["n"] == 1
        assert after["i"] == 0 and after["r"] == 0
        assert after["session_id"] != before["session_id"]


@pytest.mark.parametrize("enabled", [False, True])
async def test_reminder_preference_upgrade_and_pause_reload_resume_preserve_records(hass, enabled):
    async def phone(call):
        pass
    hass.services.async_register("notify", "mobile_app_preference_test", phone)
    entry = new_entry(hass, notification="notify.mobile_app_preference_test")
    now = int(time.time())
    state = transition(new_state(), "show", "", now - 120)
    for name,stamp in [("start", now - 120), ("stop", now - 75), ("Mild", now - 70)]:
        state = transition(state, name, state["k"], stamp)
    if enabled:
        state = transition(state, "reminders_on", state["movement"]["k"], now - 60)
    state = transition(state, "movement", state["movement"]["k"], now - 30)
    state["schema"] = 6
    state["movement"].pop("preferred")
    await Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}").async_save(state)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    upgraded = await stored(hass, entry)
    assert upgraded["schema"] == 8
    assert upgraded["movement"]["preferred"] is enabled
    assert upgraded["records"] == state["records"]
    await command(hass, entry, "end")
    paused = await stored(hass, entry)
    assert not paused["movement"]["enabled"]
    assert paused["movement"]["preferred"] is enabled
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    await command(hass, entry, "show")
    resumed = await stored(hass, entry)
    assert resumed["movement"]["enabled"] is enabled
    assert resumed["records"] == state["records"]
    for key in ("last", "enabled_at", "last_alert", "count"):
        assert resumed["movement"][key] == state["movement"][key]
    await command(hass, entry, "end")
    await command(hass, entry, "reminders_off")
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    await command(hass, entry, "show")
    final = await stored(hass, entry)
    assert not final["movement"]["preferred"] and not final["movement"]["enabled"]
    assert final["records"] == state["records"]


@pytest.mark.parametrize("fraction", [0.0, 0.2, 0.8, 0.999])
async def test_scheduled_long_warning_at_threshold_once_across_reload_and_phone_stop(
    hass, hass_admin_user, freezer, frozen_tracker_clock, fraction
):
    freezer.move_to(datetime.fromtimestamp(int(time.time()) + fraction, UTC))
    calls = []
    async def phone(call):
        calls.append(deepcopy(dict(call.data)))
    hass.services.async_register("notify", "mobile_app_long_test", phone)
    entry = await setup_entry(hass, notification="notify.mobile_app_long_test")
    await command(hass, entry, "show")
    await command(hass, entry, "start")
    before = await stored(hass, entry)
    tag = long_warning_tag(entry.runtime_data.tracker.view(), entry.entry_id)
    def alerts():
        return [c for c in calls if c.get("data", {}).get("tag") == tag
                and c.get("message") != "clear_notification"]
    freezer.move_to(datetime.fromtimestamp(before["s"] + 120, UTC))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert alerts() == []
    assert await stored(hass, entry) == before
    freezer.move_to(datetime.fromtimestamp(before["s"] + 121, UTC))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    warned = await stored(hass, entry)
    assert warned == {**before, "long_warning_attempted": True}
    assert len(alerts()) == 1
    assert alerts()[0]["data"]["visibility"] == "private"
    assert "If this contraction is still continuing" in alerts()[0]["message"]
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    freezer.move_to(datetime.fromtimestamp(before["s"] + 180, UTC))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert len(alerts()) == 1
    hass.bus.async_fire(
        "mobile_app_notification_action",
        {"tag": tag, "action": f"CT|{entry.entry_id}|stop|{before['k']}"},
        context=Context(user_id=hass_admin_user.id),
    )
    await hass.async_block_till_done()
    stopped = await stored(hass, entry)
    assert stopped["p"] == "rate"
    assert len(stopped["records"]) == 1
    assert stopped["records"][0]["duration"] == 180
    assert any(c.get("message") == "clear_notification" and c["data"]["tag"] == tag for c in calls)


async def test_unload_cancels_long_warning_and_overdue_setup_recovers_one_attempt(
    hass, freezer, frozen_tracker_clock
):
    calls = []
    async def phone(call):
        calls.append(deepcopy(dict(call.data)))
    hass.services.async_register("notify", "mobile_app_long_recovery", phone)
    entry = await setup_entry(hass, notification="notify.mobile_app_long_recovery")
    await command(hass, entry, "show")
    await command(hass, entry, "start")
    before = await stored(hass, entry)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    freezer.move_to(datetime.fromtimestamp(before["s"] + 180, UTC))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    tag = long_warning_tag(entry.runtime_data.tracker.view(), entry.entry_id)
    def alerts():
        return [c for c in calls if c.get("data", {}).get("tag") == tag
                and c.get("message") != "clear_notification"]
    assert alerts() == []
    assert await stored(hass, entry) == before
    assert await hass.config_entries.async_setup(entry.entry_id)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert len(alerts()) == 1
    assert await stored(hass, entry) == {**before, "long_warning_attempted": True}


async def test_schema_seven_upgrade_keeps_active_timing_and_records(hass):
    entry = new_entry(hass)
    now = int(time.time())
    state = transition(new_state(), "show", "", now - 60)
    state = transition(state, "start", state["k"], now - 60)
    state["schema"] = 7
    state.pop("long_warning_attempted")
    await Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}").async_save(state)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert await stored(hass, entry) == {**state, "schema": 8, "long_warning_attempted": False}
    assert entry.runtime_data.tracker.view()["p"] == "active"


async def test_real_notification_queue_survives_delayed_early_and_previous_clears(
    hass, freezer, frozen_tracker_clock
):
    """Capture real adapter sends, then deliver them in hostile phone order."""
    calls = []
    async def phone(call):
        calls.append(deepcopy(dict(call.data)))
    hass.services.async_register("notify", "mobile_app_reordered_test", phone)
    entry = await setup_entry(hass, notification="notify.mobile_app_reordered_test")
    await command(hass, entry, "show")
    await command(hass, entry, "start")
    await command(hass, entry, "notify")
    before = deepcopy(await stored(hass, entry))
    first_tag = long_warning_tag(entry.runtime_data.tracker.view(), entry.entry_id)
    legacy_tag = f"contraction_tracker_long_{entry.entry_id}"
    early = deepcopy(calls)
    assert not any(item.get("message") == "clear_notification" and
                   item["data"]["tag"] in (first_tag, legacy_tag) for item in early)
    freezer.move_to(datetime.fromtimestamp(before["s"] + 121, UTC))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    first_warning = next(item for item in calls
                         if item.get("data", {}).get("tag") == first_tag
                         and item["message"] != "clear_notification")
    def deliver(visible, payload):
        tag = payload.get("data", {}).get("tag")
        if payload["message"] == "clear_notification":
            visible.pop(tag, None)
        else:
            visible[tag] = payload
    visible = {}
    deliver(visible, first_warning)
    for payload in reversed(early):
        deliver(visible, payload)
    assert first_tag in visible
    assert await stored(hass, entry) == {**before, "long_warning_attempted": True}
    # Unload must not erase an active warning that will not be sent again.
    mark = len(calls)
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert long_warning_tag(entry.runtime_data.tracker.view(), entry.entry_id) == first_tag
    assert not any(item["message"] == "clear_notification" and
                   item["data"]["tag"] in (first_tag, legacy_tag) for item in calls[mark:])
    assert sum(item.get("data", {}).get("tag") == first_tag and
               item["message"] != "clear_notification" for item in calls) == 1
    mark = len(calls)
    await command(hass, entry, "stop")
    stopped = await stored(hass, entry)
    assert stopped["records"][0]["duration"] == 121
    previous_clears = [item for item in calls[mark:] if item["message"] == "clear_notification"]
    assert any(item["data"]["tag"] == first_tag for item in previous_clears)
    await command(hass, entry, "Mild")
    freezer.move_to(datetime.fromtimestamp(before["s"] + 180, UTC))
    await command(hass, entry, "start")
    second = deepcopy(await stored(hass, entry))
    second_tag = long_warning_tag(entry.runtime_data.tracker.view(), entry.entry_id)
    assert second_tag != first_tag
    freezer.move_to(datetime.fromtimestamp(second["s"] + 121, UTC))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    second_warning = next(item for item in calls
                          if item.get("data", {}).get("tag") == second_tag
                          and item["message"] != "clear_notification")
    deliver(visible, second_warning)
    for payload in reversed(previous_clears):
        deliver(visible, payload)
    assert second_tag in visible and first_tag not in visible
    assert await stored(hass, entry) == {**second, "long_warning_attempted": True}


async def test_warning_stop_tags_reject_stale_and_unauthorized_actions_but_accept_legacy_stop(
    hass, hass_admin_user
):
    entry = await setup_entry(hass)
    await command(hass, entry, "show")
    await command(hass, entry, "start")
    first = deepcopy(await stored(hass, entry))
    stale_tag = long_warning_tag(entry.runtime_data.tracker.view(), entry.entry_id)
    await command(hass, entry, "stop")
    await command(hass, entry, "Mild")
    await command(hass, entry, "start")
    before = deepcopy(await stored(hass, entry))
    current_tag = long_warning_tag(entry.runtime_data.tracker.view(), entry.entry_id)
    legacy_tag = f"contraction_tracker_long_{entry.entry_id}"
    for supplied_tag, context, action, token in (
        (stale_tag, Context(user_id=hass_admin_user.id), "stop", before["k"]),
        (current_tag, Context(), "stop", before["k"]),
        (current_tag, Context(user_id=hass_admin_user.id), "stop", first["k"]),
        (current_tag, Context(user_id=hass_admin_user.id), "movement", before["movement"]["k"]),
        (legacy_tag, Context(user_id=hass_admin_user.id), "movement", before["movement"]["k"]),
    ):
        hass.bus.async_fire(
            "mobile_app_notification_action",
            {"tag": supplied_tag, "action": f"CT|{entry.entry_id}|{action}|{token}"},
            context=context,
        )
        await hass.async_block_till_done()
        assert await stored(hass, entry) == before
    hass.bus.async_fire(
        "mobile_app_notification_action",
        {"tag": legacy_tag, "action": f"CT|{entry.entry_id}|stop|{before['k']}"},
        context=Context(user_id=hass_admin_user.id),
    )
    await hass.async_block_till_done()
    after = await stored(hass, entry)
    assert after["p"] == "rate"
    assert len(after["records"]) == len(before["records"]) + 1
