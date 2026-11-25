"""Use real blueprint expansion, automation schemas, triggers and script runner."""

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import pytest
from homeassistant.components.automation import DATA_COMPONENT
from homeassistant.components.automation.config import (
    AUTOMATION_BLUEPRINT_SCHEMA, async_validate_config_item,
)
from homeassistant.components.blueprint.models import Blueprint, BlueprintInputs
from homeassistant.core import callback
from homeassistant.setup import async_setup_component
from homeassistant.util import yaml as yaml_util
from pytest_homeassistant.common import async_fire_time_changed

from tests.ha.test_automation_entities import entity
from tests.ha.test_lifecycle import command, frozen_tracker_clock, record, setup_entry

pytestmark = pytest.mark.usefixtures("hass_storage")
ROOT = Path(__file__).resolve().parents[2]


def capture(kind):
    return [{"action": "test.capture", "data": {"kind": kind}}]


async def timed_command(hass, entry, name):
    """Dispatch normally, without waiting for an intentionally suspended script.

    The lifecycle helper drains *all* HA work, which includes an automation's
    delay/wait. A frozen-clock test must reach its clock advancement first.
    """
    from custom_components.contraction_tracker.const import DOMAIN

    result = await hass.services.async_call(
        DOMAIN, "command",
        {"entry_id": entry.entry_id, "command": name,
         "token": entry.runtime_data.tracker.view()["k"]},
        blocking=True, return_response=True,
    )
    # Flush the ready state/trigger callbacks, not future timers.
    await asyncio.sleep(0)
    return result


async def timed_record(hass, entry):
    for name in ("show", "start", "stop", "Mild"):
        await timed_command(hass, entry, name)
    return entry.runtime_data.tracker.history()


def step_matches(actual, expected):
    """HA labels a delay with its duration; other action names stay exact."""
    return actual == expected or (
        expected == "delay" and isinstance(actual, str) and actual.startswith("delay ")
    )


@pytest.mark.parametrize(("actual", "expected", "matches"), [
    ("delay", "delay", True),
    ("delay 0:01:00", "delay", True),
    ("delay 0:00:30", "delay", True),
    ("wait for trigger", "wait for trigger", True),
    (None, "delay", False),
    ("delayed action", "delay", False),
    ("wait for trigger", "delay", False),
    ("delay 0:01:00", "wait for trigger", False),
    ("wait for trigger extra", "wait for trigger", False),
])
def test_observer_matches_only_the_requested_action(actual, expected, matches):
    assert step_matches(actual, expected) is matches


async def wait_for_step(hass, name, expected):
    """Observe the real script reaching its wait/delay, preserving HA's listener.

    This is the same action-observer approach used in HA's own script tests,
    not a mock of actions, clocks, timers or trigger dispatch.
    """
    automation = hass.data[DATA_COMPONENT].get_entity(f"automation.synthetic_{name}")
    script = automation.action_script
    reached = asyncio.Event()
    previous_listener = script.change_listener

    @callback
    def changed():
        if previous_listener is not None:
            previous_listener()
        if script.is_running and step_matches(script.last_action, expected):
            reached.set()

    script.change_listener = changed
    try:
        changed()
        await asyncio.wait_for(reached.wait(), 5)
    finally:
        script.change_listener = previous_listener
    assert script.is_running
    assert step_matches(script.last_action, expected)


async def stop_test_automation(hass, name):
    """Cancel any deliberate remaining wait before the final full task drain."""
    await hass.services.async_call(
        "automation", "turn_off",
        {"entity_id": f"automation.synthetic_{name}", "stop_actions": True},
        blocking=True,
    )
    await hass.async_block_till_done()


async def load_automation(hass, name, inputs):
    path = ROOT / "blueprints" / "automation" / f"{name}.yaml"
    raw = await hass.async_add_executor_job(yaml_util.load_yaml, str(path))
    blueprint = Blueprint(raw, schema=AUTOMATION_BLUEPRINT_SCHEMA, expected_domain="automation")
    assert blueprint.validate() is None
    instance = BlueprintInputs(blueprint, {
        "id": f"synthetic_{name}", "alias": f"Synthetic {name}",
        "use_blueprint": {"path": f"{name}.yaml", "input": inputs},
    })
    instance.validate()
    expanded = instance.async_substitute()
    validated = await async_validate_config_item(hass, "automation", expanded)
    assert validated.validation_status == "ok"
    assert await async_setup_component(hass, "automation", {"automation": [expanded]})
    await hass.async_start()
    await hass.async_block_till_done()
    assert hass.states.get(f"automation.synthetic_{name}").state == "on"
    return expanded


async def install(hass, name, **settings):
    entry = await setup_entry(hass)
    calls = []
    async def action(call):
        calls.append(dict(call.data))
    hass.services.async_register("test", "capture", action)
    inputs = {
        "calming_session": {
            "activity_entity": entity(hass, entry, "event", "activity"),
            "start_actions": capture("start"), "end_actions": capture("end"),
        },
        "partner_update": {
            "activity_entity": entity(hass, entry, "event", "activity"),
            "update_actions": capture("update"), "cooldown_seconds": 0,
        },
        "timer_reminder": {
            "start_entity": entity(hass, entry, "sensor", "current_start"),
            "reminder_actions": capture("reminder"), "reminder_seconds": 30,
        },
    }[name]
    inputs.update(settings)
    await load_automation(hass, name, inputs)
    return entry, calls


async def test_calming_blueprint_distinguishes_sessions_and_skips_restore(hass):
    entry, calls = await install(hass, "calming_session")
    await record(hass, entry)
    assert calls == [{"kind": "start"}]
    await command(hass, entry, "start")
    await command(hass, entry, "stop")
    await command(hass, entry, "Mild")
    assert calls == [{"kind": "start"}]
    await command(hass, entry, "end")
    assert calls == [{"kind": "start"}, {"kind": "end"}]
    activity_id = entity(hass, entry, "event", "activity")
    saved = hass.states.get(activity_id)
    hass.states.async_set(activity_id, "unavailable", {"restored": True})
    await hass.async_block_till_done()
    hass.states.async_set(activity_id, saved.state, dict(saved.attributes))
    await hass.async_block_till_done()
    assert calls == [{"kind": "start"}, {"kind": "end"}]
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert calls == [{"kind": "start"}, {"kind": "end"}]
    await command(hass, entry, "show")
    assert calls[-1] == {"kind": "start"}
    assert len(calls) == 3


@pytest.mark.parametrize("update_when", ["contraction_completed", "contraction_rated"])
async def test_partner_blueprint_fires_for_equal_records_once_at_selected_stage(hass, update_when):
    entry, calls = await install(hass, "partner_update", update_when=update_when)
    await command(hass, entry, "show")
    await command(hass, entry, "start")
    await command(hass, entry, "stop")
    assert len(calls) == int(update_when == "contraction_completed")
    await command(hass, entry, "Mild")
    assert calls == [{"kind": "update"}]
    await record(hass, entry)
    assert calls == [{"kind": "update"}, {"kind": "update"}]
    row = entry.runtime_data.tracker.history()[-1]
    await entry.runtime_data.tracker.edit(
        row["id"], row["revision"], row["start"], row["end"], "Strong")
    await command(hass, entry, "notify")
    await hass.async_block_till_done()
    assert len(calls) == 2


async def test_partner_cooldown_ignores_extra_events_without_extending_window(hass, freezer, frozen_tracker_clock):
    entry, calls = await install(hass, "partner_update", cooldown_seconds=60)
    await timed_record(hass, entry)
    await wait_for_step(hass, "partner_update", "delay")
    await timed_record(hass, entry)
    assert len(calls) == 1
    freezer.tick(61)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    await timed_record(hass, entry)
    await wait_for_step(hass, "partner_update", "delay")
    assert len(calls) == 2
    await stop_test_automation(hass, "partner_update")


async def test_calming_blueprint_receives_real_downtime_inactivity_closure(hass, freezer, frozen_tracker_clock):
    entry, calls = await install(hass, "calming_session")
    await record(hass, entry)
    last_end = entry.runtime_data.tracker.view()["e"]
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    freezer.move_to(datetime.fromtimestamp(last_end + 3600, UTC))
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert calls == [{"kind": "start"}, {"kind": "end"}]


async def test_timer_blueprint_cancels_on_stop_and_is_guarded_for_new_contraction(hass, freezer, frozen_tracker_clock):
    entry, calls = await install(hass, "timer_reminder")
    await timed_command(hass, entry, "show")
    await timed_command(hass, entry, "start")
    await wait_for_step(hass, "timer_reminder", "wait for trigger")
    freezer.tick(10)
    await timed_command(hass, entry, "stop")
    await command(hass, entry, "Mild")
    freezer.tick(25)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert calls == []
    await timed_command(hass, entry, "start")
    await wait_for_step(hass, "timer_reminder", "wait for trigger")
    freezer.tick(29)
    async_fire_time_changed(hass)
    await asyncio.sleep(0)
    await wait_for_step(hass, "timer_reminder", "wait for trigger")
    assert calls == []
    freezer.tick(2)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert calls == [{"kind": "reminder"}]
    freezer.tick(60)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert len(calls) == 1
    assert entry.runtime_data.tracker.view()["p"] == "active"
    await stop_test_automation(hass, "timer_reminder")


async def test_timer_blueprint_reload_cancels_old_wait_without_catchup(hass, freezer, frozen_tracker_clock):
    entry, calls = await install(hass, "timer_reminder")
    await timed_command(hass, entry, "show")
    await timed_command(hass, entry, "start")
    await wait_for_step(hass, "timer_reminder", "wait for trigger")
    freezer.tick(10)
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    freezer.tick(40)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert calls == []
    await command(hass, entry, "stop")
    await command(hass, entry, "Mild")
    await timed_command(hass, entry, "start")
    await wait_for_step(hass, "timer_reminder", "wait for trigger")
    freezer.tick(31)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert calls == [{"kind": "reminder"}]
    await stop_test_automation(hass, "timer_reminder")
