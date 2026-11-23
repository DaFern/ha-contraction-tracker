from copy import deepcopy
import importlib
import json
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

from tests.support import model
from tests.unit.test_legacy import bundle

migration = importlib.import_module(f"{model.__package__}.migration")


def setup():
    source = bundle()
    values = {source["entities"][key]: SimpleNamespace(state=json.dumps(source[key]), attributes={})
              for key in ("state", "movement", "guidance")}
    values[source["entities"]["automation"]] = SimpleNamespace(state="off", attributes={"current": 0})
    response = {source["entities"]["records"]: {"items": deepcopy(source["items"])}}
    hass = SimpleNamespace(states=SimpleNamespace(get=values.get),
                           services=SimpleNamespace(async_call=AsyncMock(return_value=response)))
    return hass, values, source, response


class MigrationReaderTests(unittest.IsolatedAsyncioTestCase):
    async def test_snapshot_uses_todo_api_and_preserves_all_statuses(self):
        hass, values, source, response = setup()
        response[source["entities"]["records"]]["items"][0]["status"] = "completed"
        result = await migration.read_source(hass, source["entities"], "context", stopped=True)
        self.assertEqual(result["state"], source["state"])
        self.assertEqual(result["items"][0]["status"], "completed")
        hass.services.async_call.assert_awaited_once_with(
            "todo", "get_items", target={"entity_id": source["entities"]["records"]},
            blocking=True, return_response=True, context="context")

    async def test_running_or_queued_legacy_tracker_blocks_apply_but_allows_preview(self):
        for state, queued in (("on", 0), ("off", 1)):
            hass, values, source, _ = setup()
            values[source["entities"]["automation"]].state = state
            values[source["entities"]["automation"]].attributes["current"] = queued
            with self.subTest(state=state, queued=queued), self.assertRaises(model.InvalidCommand):
                await migration.read_source(hass, source["entities"], None, stopped=True)
            hass.services.async_call.assert_not_awaited()
            await migration.read_source(hass, source["entities"], None, stopped=False)

    async def test_changed_helpers_or_restarted_source_abort_the_snapshot(self):
        for change in ("helper", "automation"):
            hass, values, source, response = setup()
            async def read(*args, **kwargs):
                if change == "helper":
                    values[source["entities"]["state"]].state += " "
                else:
                    values[source["entities"]["automation"]].state = "on"
                return response
            hass.services.async_call = read
            with self.subTest(change=change), self.assertRaises(model.InvalidCommand):
                await migration.read_source(hass, source["entities"], None, stopped=True)

    async def test_wrong_domains_unavailable_helpers_and_bad_responses_are_refused(self):
        for invalid in ("domain", "unavailable", "response"):
            hass, values, source, _ = setup()
            if invalid == "domain":
                source["entities"]["state"] = "sensor.wrong_domain"
            elif invalid == "unavailable":
                values[source["entities"]["state"]].state = "unavailable"
            else:
                hass.services.async_call.return_value = {}
            with self.subTest(invalid=invalid), self.assertRaises(model.InvalidCommand):
                await migration.read_source(hass, source["entities"], None)
