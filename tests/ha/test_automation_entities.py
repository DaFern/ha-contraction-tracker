"""Native entity registration, verified activity ordering and no-phone timers."""

from copy import deepcopy
from datetime import UTC, datetime
import time

import pytest
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant.common import async_fire_time_changed

from custom_components.contraction_tracker.activity import EVENT_TYPES
from custom_components.contraction_tracker.const import DOMAIN
from tests.ha.test_lifecycle import (
    command, frozen_tracker_clock, new_entry, record, setup_entry, stored,
)

pytestmark = pytest.mark.usefixtures("hass_storage")


def entity(hass, entry, domain, key):
    result = er.async_get(hass).async_get_entity_id(
        domain, DOMAIN, f"{entry.entry_id}_{key}")
    assert result is not None
    return result


async def test_all_entities_share_device_stable_ids_and_only_session_is_discoverable(hass):
    entry = await setup_entry(hass)
    registry = er.async_get(hass)
    rows = er.async_entries_for_config_entry(registry, entry.entry_id)
    assert len(rows) == 22
    assert len({row.device_id for row in rows}) == 1
    assert rows[0].device_id is not None
    assert len({row.unique_id for row in rows}) == 22
    discovery = [row.entity_id for row in rows
                 if hass.states.get(row.entity_id).attributes.get("contraction_tracker")]
    assert discovery == [entry.runtime_data.tracker.entity_id]
    for key in ("save_uncertain", "notification_failed"):
        row = registry.async_get(entity(hass, entry, "binary_sensor", key))
        assert row.entity_category == "diagnostic"
    for key in ("last_duration", "last_interval", "last_rest", "hourly_duration", "hourly_interval"):
        state = hass.states.get(entity(hass, entry, "sensor", key))
        assert state.attributes["unit_of_measurement"] == "s"
        assert state.attributes["device_class"] == "duration"
        assert "state_class" not in state.attributes
        assert state.state == "unknown"
    assert hass.states.get(entity(hass, entry, "sensor", "session_count")).state == "0"
    activity = hass.states.get(entity(hass, entry, "event", "activity"))
    assert set(activity.attributes["event_types"]) == set(EVENT_TYPES)
    assert activity.state == "unknown"
    ids = {row.unique_id: row.entity_id for row in rows}
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert {row.unique_id: row.entity_id for row in
            er.async_entries_for_config_entry(registry, entry.entry_id)} == ids


async def test_activity_observers_read_committed_measurements_before_event(hass):
    entry = await setup_entry(hass)
    activity_id = entity(hass, entry, "event", "activity")
    duration_id = entity(hass, entry, "sensor", "last_duration")
    awaiting_id = entity(hass, entry, "binary_sensor", "awaiting_rating")
    seen = []

    @callback
    def changed(event):
        if event.data["entity_id"] != activity_id or event.data["new_state"] is None:
            return
        state = event.data["new_state"]
        seen.append((state.state, dict(state.attributes), hass.states.get(duration_id).state,
                     hass.states.get(awaiting_id).state, entry.runtime_data.tracker._lock.locked()))

    remove = hass.bus.async_listen("state_changed", changed)
    await record(hass, entry)
    await command(hass, entry, "start")
    await command(hass, entry, "stop")
    await command(hass, entry, "Mild")
    remove()
    assert [row[1]["event_type"] for row in seen] == [
        "session_started", "contraction_started", "contraction_completed", "contraction_rated",
        "contraction_started", "contraction_completed", "contraction_rated"]
    completed = [row for row in seen if row[1]["event_type"] == "contraction_completed"]
    assert len({row[0] for row in seen}) == 7
    assert len({row[1]["record_id"] for row in completed}) == 2
    # The state bus is delivered by HA asynchronously; by then rating may already
    # have happened. Direct adapter callback ordering is tested below.
    assert hass.states.get(duration_id).state != "unknown"


async def test_adapter_handoff_has_synchronous_sensor_state_and_no_tokens(hass):
    entry = await setup_entry(hass)
    tracker = entry.runtime_data.tracker
    snapshots = []
    def observe(metadata):
        snapshots.append((metadata, hass.states.get(entity(hass, entry, "sensor", "last_duration")).state,
                          hass.states.get(entity(hass, entry, "binary_sensor", "awaiting_rating")).state,
                          tracker._lock.locked()))
    tracker.subscribe_activity(observe)
    await record(hass, entry)
    completed = next(row for row in snapshots if row[0]["event_type"] == "contraction_completed")
    assert completed[1] == str(completed[0]["duration"])
    assert completed[2] == "on"
    assert completed[3] is False
    activity = hass.states.get(entity(hass, entry, "event", "activity"))
    assert activity.attributes["entry_id"] == entry.entry_id
    assert not ({"k", "revision", "records", "audit", "original", "legacy", "latitude",
                 "longitude", "phone"} & set(activity.attributes))
    before = activity.state
    await command(hass, entry, "notify")
    await tracker.tick()
    await tracker.refresh_location()
    await hass.async_block_till_done()
    assert hass.states.get(activity.entity_id).state == before


async def test_correction_updates_sensor_and_only_emits_correction(hass):
    entry = await setup_entry(hass)
    await record(hass, entry)
    tracker = entry.runtime_data.tracker
    events = []
    tracker.subscribe_activity(events.append)
    row = tracker.history()[-1]
    await tracker.edit(row["id"], row["revision"], row["start"], row["end"], "Strong")
    await hass.async_block_till_done()
    assert [event["event_type"] for event in events] == ["record_corrected"]
    assert hass.states.get(entity(hass, entry, "sensor", "last_intensity")).state == "Strong"
    assert hass.states.get(entity(hass, entry, "event", "activity")).attributes["event_type"] == "record_corrected"


async def test_rejected_and_ambiguous_operations_do_not_publish_activity(hass):
    from custom_components.contraction_tracker.manager import PersistenceError
    from custom_components.contraction_tracker.model import InvalidCommand
    entry = await setup_entry(hass)
    tracker = entry.runtime_data.tracker
    await command(hass, entry, "show")
    activity_id = entity(hass, entry, "event", "activity")
    before = hass.states.get(activity_id).state
    with pytest.raises(InvalidCommand):
        await tracker.command("start", "stale")
    async def inconsistent_readback():
        return None
    tracker._readback = inconsistent_readback
    with pytest.raises(PersistenceError):
        await tracker.command("start", tracker.view()["k"])
    await hass.async_block_till_done()
    assert hass.states.get(activity_id).state == before
    assert hass.states.get(entity(hass, entry, "binary_sensor", "save_uncertain")).state == "on"
    assert hass.states.get(entity(hass, entry, "sensor", "session_count")).state == "unavailable"


@pytest.mark.parametrize("fraction", [0, 0.2, 0.8, 0.999])
async def test_phone_none_exact_threshold_stop_and_reload(hass, freezer, frozen_tracker_clock, fraction):
    freezer.move_to(datetime.fromtimestamp(int(time.time()) + fraction, UTC))
    entry = await setup_entry(hass)
    await command(hass, entry, "show")
    await command(hass, entry, "start")
    before = deepcopy(await stored(hass, entry))
    threshold_id = entity(hass, entry, "binary_sensor", "timer_over_two_minutes")
    start_id = entity(hass, entry, "sensor", "current_start")
    assert hass.states.get(start_id).attributes["device_class"] == "timestamp"
    assert datetime.fromisoformat(hass.states.get(start_id).state).tzinfo is not None
    freezer.move_to(datetime.fromtimestamp(before["s"] + 120, UTC))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(threshold_id).state == "off"
    freezer.move_to(datetime.fromtimestamp(before["s"] + 121.001, UTC))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(threshold_id).state == "on"
    assert await stored(hass, entry) == before  # No phantom notification claim.
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(threshold_id).state == "on"
    assert await stored(hass, entry) == before
    await command(hass, entry, "stop")
    assert hass.states.get(threshold_id).state == "off"
    assert hass.states.get(start_id).state == "unknown"


async def test_downtime_inactivity_closure_is_new_activity_not_history_replay(hass, freezer, frozen_tracker_clock):
    entry = await setup_entry(hass)
    await record(hass, entry)
    before = await stored(hass, entry)
    activity_id = entity(hass, entry, "event", "activity")
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    freezer.move_to(datetime.fromtimestamp(before["e"] + 3600, UTC))
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    activity = hass.states.get(activity_id)
    assert activity.attributes["event_type"] == "session_ended"
    assert activity.attributes["reason"] == "inactivity"
    assert activity.attributes["session_id"] == before["session_id"]
    assert hass.states.get(entity(hass, entry, "binary_sensor", "session_recording")).state == "off"
    assert (await stored(hass, entry))["records"] == before["records"]
    closure = activity.state
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    # EventEntity may restore the old timestamp or remain unknown without a
    # persisted restore-state fixture, but it must never generate a new timestamp.
    assert hass.states.get(activity_id).state in (closure, "unknown")


async def test_disabled_entity_and_second_entry_remain_independent(hass):
    first = new_entry(hass, "First")
    registry = er.async_get(hass)
    disabled = registry.async_get_or_create(
        "sensor", DOMAIN, f"{first.entry_id}_last_duration",
        config_entry=first, disabled_by=er.RegistryEntryDisabler.USER)
    assert await hass.config_entries.async_setup(first.entry_id)
    await hass.async_block_till_done()
    second = await setup_entry(hass, "Second")
    await record(hass, first)
    assert hass.states.get(disabled.entity_id) is None
    assert hass.states.get(entity(hass, second, "sensor", "session_count")).state == "0"
    assert hass.states.get(entity(hass, second, "event", "activity")).state == "unknown"
    old = first.runtime_data.tracker
    assert await hass.config_entries.async_unload(first.entry_id)
    await hass.async_block_till_done()
    assert old._activity_listeners == set()
    assert old._listeners == set()
    assert hass.states.get(entity(hass, second, "binary_sensor", "session_recording")).state == "off"


@pytest.mark.parametrize("action", ["stop", "unload"])
async def test_no_phone_stale_deadline_cancelled_before_due(hass, freezer, frozen_tracker_clock, action):
    entry = await setup_entry(hass)
    await command(hass, entry, "show")
    await command(hass, entry, "start")
    tracker = entry.runtime_data.tracker
    start = tracker.view()["s"]
    freezer.move_to(datetime.fromtimestamp(start + 45, UTC))
    if action == "stop":
        await command(hass, entry, "stop")
    else:
        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
    before = await stored(hass, entry)
    freezer.move_to(datetime.fromtimestamp(start + 122, UTC))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert await stored(hass, entry) == before
    if action == "stop":
        assert hass.states.get(entity(hass, entry, "binary_sensor", "timer_over_two_minutes")).state == "off"
    else:
        assert tracker.closed
        assert not tracker._listeners


async def test_no_phone_clock_rollback_rearms_native_state(hass, freezer, frozen_tracker_clock):
    entry = await setup_entry(hass)
    await command(hass, entry, "show")
    await command(hass, entry, "start")
    tracker = entry.runtime_data.tracker
    start = tracker.view()["s"]
    state_id = entity(hass, entry, "binary_sensor", "timer_over_two_minutes")
    before = await stored(hass, entry)
    freezer.move_to(datetime.fromtimestamp(start + 121.001, UTC))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(state_id).state == "on"
    freezer.move_to(datetime.fromtimestamp(start + 100, UTC))
    await tracker.tick()
    await hass.async_block_till_done()
    assert hass.states.get(state_id).state == "off"
    freezer.move_to(datetime.fromtimestamp(start + 121.001, UTC))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(state_id).state == "on"
    assert await stored(hass, entry) == before


async def test_notification_failure_diagnostic_does_not_hide_completed_activity(hass):
    async def broken_phone(call):
        raise RuntimeError("Synthetic phone failure")
    hass.services.async_register("notify", "mobile_app_broken_synthetic", broken_phone)
    entry = await setup_entry(hass, notification="notify.mobile_app_broken_synthetic")
    await record(hass, entry)
    assert len((await stored(hass, entry))["records"]) == 1
    assert hass.states.get(entity(hass, entry, "binary_sensor", "notification_failed")).state == "on"
    assert hass.states.get(entity(hass, entry, "binary_sensor", "save_uncertain")).state == "off"
    assert hass.states.get(entity(hass, entry, "event", "activity")).attributes["event_type"] == "contraction_rated"
