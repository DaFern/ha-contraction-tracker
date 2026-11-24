"""Isolated native HA lifecycle checks; no live instance or legacy resources.

HA setup, platforms, services, panels, options and public Store APIs are real.
The official test package supplies disposable HA/network/storage fixtures.
Only the explicit panel-registration failure test injects a failing dependency.
"""

from copy import deepcopy
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.components import frontend
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import Context
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.storage import Store
from pytest_homeassistant.common import MockConfigEntry

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
from custom_components.contraction_tracker.model import InvalidCommand


@pytest.fixture(autouse=True)
def isolated_storage(hass_storage):
    """Keep synthetic records in the official test backend, never a live store."""
    yield


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
    assert hass.states.get(old.tracker.entity_id) is None
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


async def test_phone_dispatch_rejects_anonymous_wrong_tag_and_stale_actions(hass, hass_user):
    entry = await setup_entry(hass)
    await command(hass, entry, "show")
    before = deepcopy(await stored(hass, entry))
    action = f"CT|{entry.entry_id}|start|{before['k']}"
    tag = f"contraction_tracker_{entry.entry_id}"
    for context, supplied_tag in (
        (Context(), tag),
        (Context(user_id=hass_user.id), "unrelated_notification"),
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
        context=Context(user_id=hass_user.id),
    )
    await hass.async_block_till_done()
    started = deepcopy(await stored(hass, entry))
    assert started["p"] == "active"
    assert started["n"] == 1
    hass.bus.async_fire(
        "mobile_app_notification_action",
        {"action": action, "tag": tag},
        context=Context(user_id=hass_user.id),
    )
    await hass.async_block_till_done()
    assert await stored(hass, entry) == started
