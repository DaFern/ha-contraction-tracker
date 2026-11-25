"""Automation foundations exercise only isolated, synthetic tracker state."""

import asyncio
from copy import deepcopy
import unittest
from unittest.mock import patch

from tests.support import manager, model


class AutomationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.now = 1000
        self.disk = None
        self.events = []
        self.published = []
        self.deliveries = []

        async def save(state):
            self.disk = deepcopy(state)

        async def readback():
            return deepcopy(self.disk)

        async def notify(view):
            pass

        self.tracker = manager.Tracker(None, save, notify, lambda: self.now, readback=readback)
        self.tracker.subscribe(lambda: self.published.append(self.tracker.view()))

        def activity(event):
            self.deliveries.append((self.tracker._lock.locked(),
                                    self.published[-1]["records_count"], len(self.disk["records"])))
            self.events.append(event)

        self.tracker.subscribe_activity(activity)

    async def command(self, action):
        view = self.tracker.view()
        return await self.tracker.command(
            action, view["movement"]["k"] if action == "movement" else view["k"])

    async def complete(self, start, end):
        self.now = start
        await self.command("start")
        self.now = end
        await self.command("stop")
        await self.command("Mild")

    async def test_cache_copy_isolation_clock_commit_and_flags(self):
        with patch.object(manager, "snapshot", wraps=model.snapshot) as calculation:
            first = self.tracker.view()
            first["hourly"]["count"] = 999
            self.assertEqual(self.tracker.view()["hourly"]["count"], 0)
            self.assertEqual(calculation.call_count, 1)
            self.tracker.notification_failed = True
            self.assertTrue(self.tracker.view()["notification_failed"])
            self.assertEqual(calculation.call_count, 1)
            await self.command("show")
            self.assertEqual(calculation.call_count, 2)
            self.now += 1
            self.tracker.view()
            self.assertEqual(calculation.call_count, 3)
            self.now -= 2
            self.tracker.view()
            self.assertEqual(calculation.call_count, 4)

    async def test_equal_measurements_are_distinct_operations_and_bounded(self):
        await self.command("show")
        await self.complete(1000, 1060)
        await self.complete(1300, 1360)
        kinds = [e["event_type"] for e in self.events]
        self.assertEqual(kinds, ["session_started", "contraction_started",
                                "contraction_completed", "contraction_rated",
                                "contraction_started", "contraction_completed", "contraction_rated"])
        completions = [e for e in self.events if e["event_type"] == "contraction_completed"]
        self.assertEqual([e["duration"] for e in completions], [60, 60])
        self.assertNotEqual(completions[0]["record_id"], completions[1]["record_id"])
        self.assertTrue(all(not locked and published == stored
                            for locked, published, stored in self.deliveries))
        self.assertTrue(all(set(e) <= {
            "event_type", "session_id", "occurred_at", "record_id", "number",
            "start", "end", "duration", "intensity"} for e in self.events))

    async def test_unknown_zero_hour_boundary_and_paused_latest_record(self):
        self.assertIsNone(self.tracker.view()["last_record"])
        self.assertEqual(self.tracker.view()["hourly"]["completed"], 0)
        await self.command("show")
        await self.complete(1000, 1000)
        first = self.tracker.view()["last_record"]
        self.assertEqual(first["duration"], 0)
        self.assertIsNone(first["interval"])
        self.assertIsNone(first["rest"])
        await self.complete(1000, 1060)
        last = self.tracker.view()["last_record"]
        self.assertEqual(last["rest"], 0)
        self.assertEqual(last["interval"], 0)
        await self.command("end")
        self.assertEqual(self.tracker.view()["last_record"], last)
        self.now = 4600
        self.assertEqual(self.tracker.view()["hourly"]["completed"], 2)
        self.now = 4601
        self.assertEqual(self.tracker.view()["hourly"]["completed"], 0)
        self.assertIsNone(self.tracker.view()["hourly"]["duration"])
        self.assertEqual(self.tracker.view()["last_record"], last)

    async def test_interval_samples_include_active_and_unchanged_hour_rules(self):
        await self.command("show")
        await self.complete(1000, 1060)
        self.now = 1300
        await self.command("start")
        hourly = self.tracker.view()["hourly"]
        self.assertEqual(hourly, {"count": 2, "completed": 1, "duration": 60,
                                  "interval": 300, "interval_samples": 1})
        self.now = 4601
        hourly = self.tracker.view()["hourly"]
        self.assertEqual(hourly["count"], 1)
        self.assertEqual(hourly["interval_samples"], 0)
        self.assertIsNone(hourly["interval"])

    async def test_correction_movement_refresh_and_unsubscribe(self):
        await self.command("show")
        await self.complete(1000, 1060)
        row = self.tracker.history()[-1]
        await self.tracker.edit(row["id"], row["revision"], 1000, 1050, "Strong")
        self.assertEqual(self.events[-1]["event_type"], "record_corrected")
        self.assertEqual(self.tracker.view()["last_record"]["duration"], 50)
        count = len(self.events)
        row = self.tracker.history()[-1]
        await self.tracker.edit(row["id"], row["revision"], 1000, 1050, "Strong")
        await self.command("notify")
        await self.tracker.refresh_location()
        await self.tracker.tick()
        self.assertEqual(len(self.events), count)
        await self.command("movement")
        self.assertEqual(self.events[-1]["event_type"], "movement_logged")
        extra = []
        remove = self.tracker.subscribe_activity(extra.append)
        remove()
        await self.command("movement")
        self.assertEqual(extra, [])

    async def test_rejected_and_unverified_writes_emit_nothing(self):
        await self.command("show")
        count = len(self.events)
        with self.assertRaises(model.InvalidCommand):
            await self.tracker.command("start", "stale")
        async def broken_readback():
            return None
        self.tracker._readback = broken_readback
        with self.assertRaises(manager.PersistenceError):
            await self.command("start")
        self.assertEqual(len(self.events), count)
        self.assertTrue(self.published[-1]["persistence_uncertain"])

    async def test_restart_no_replay_and_overdue_closure_once(self):
        await self.command("show")
        await self.complete(1000, 1060)
        restored = manager.Tracker(self.disk, self.tracker._save, self.tracker._notify,
                                   lambda: self.now, readback=self.tracker._readback)
        events = []
        restored.subscribe_activity(events.append)
        restored.view()
        self.assertEqual(events, [])
        self.now = 4660
        await restored.tick()
        await restored.tick()
        self.assertEqual([e["event_type"] for e in events], ["session_ended"])
        self.assertEqual(events[0]["reason"], "inactivity")
        await restored.command("start", restored.view()["k"])
        self.assertEqual([e["event_type"] for e in events[-2:]],
                         ["session_started", "contraction_started"])
        self.assertNotEqual(events[-1]["session_id"], events[0]["session_id"])

    async def test_notification_and_subscriber_failures_do_not_hide_verified_activity(self):
        async def broken(view):
            raise RuntimeError("delivery")
        def bad_listener(event):
            raise RuntimeError("listener")
        self.tracker._notify = broken
        self.tracker.subscribe_activity(bad_listener)
        await self.command("show")
        await self.complete(1000, 1060)
        self.assertEqual(self.events[-1]["event_type"], "contraction_rated")
        self.assertTrue(self.tracker.view()["notification_failed"])

    async def test_cancelled_waiter_does_not_steal_pending_activity(self):
        await self.tracker._lock.acquire()
        waiting = asyncio.create_task(self.command("show"))
        await asyncio.sleep(0)
        waiting.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await waiting
        self.tracker._lock.release()
        self.assertEqual(self.events, [])
        await self.command("show")
        self.assertEqual(len(self.events), 1)

    async def test_import_does_not_replay_and_invalidates_cached_snapshot(self):
        from tests.unit.test_legacy import bundle
        self.now = 2000
        source = bundle()
        self.tracker.view()
        preview = await self.tracker.import_legacy(source)
        async def source_check():
            return deepcopy(source)
        await self.tracker.import_legacy(
            source, apply=True, expected_source=preview["source_sha256"],
            expected_target=preview["target_sha256"], source_check=source_check)
        self.assertEqual(self.events, [])
        self.assertEqual(self.tracker.view()["records_count"], 3)
        self.assertEqual(self.tracker.history()[-1]["legacy"]["item"], source["items"][-1])

    async def test_manual_end_and_warning_attempt_marker(self):
        await self.command("show")
        await self.complete(1000, 1060)
        await self.command("end")
        self.assertEqual(self.events[-1]["reason"], "manual")
        await self.command("show")
        self.now = 1100
        await self.command("start")
        count = len(self.events)
        async def warning(view):
            pass
        self.tracker.long_warning_notify = warning
        identity, _ = self.tracker.long_warning_schedule()
        self.now = 1221
        await self.tracker.check_long_contraction(identity)
        self.assertTrue(self.disk["long_warning_attempted"])
        self.assertEqual(len(self.events), count)

    async def test_same_second_location_change_invalidates_cache(self):
        settings = self.tracker.view()["guidance"]
        await self.tracker.configure_guidance(
            settings["k"], "unspecified", 300, mode="automatic",
            person="person.example", home="zone.home", hospitals=["zone.hospital"])
        location = {"location": "home", "source": "test", "confidence": "test"}
        self.tracker._location_provider = lambda settings, now: deepcopy(location)
        with patch.object(manager, "snapshot", wraps=model.snapshot) as calculation:
            self.assertEqual(self.tracker.view()["location"], location)
            self.tracker.view()
            self.assertEqual(calculation.call_count, 1)
            location["location"] = "hospital"
            self.assertEqual(self.tracker.view()["location"], location)
            self.assertEqual(calculation.call_count, 2)

    async def test_verified_inactivity_is_delivered_even_if_following_control_is_rejected(self):
        await self.command("show")
        await self.complete(1000, 1060)
        self.now = 4660
        with self.assertRaises(model.InvalidCommand):
            await self.tracker.command("start", "stale")
        self.assertEqual(self.events[-1]["event_type"], "session_ended")
        self.assertEqual(self.events[-1]["reason"], "inactivity")
        self.assertFalse(self.deliveries[-1][0])

    async def test_independent_listener_copies_trackers_and_shutdown(self):
        mutated = []
        def mutate(event):
            event["session_id"] = "changed"
            mutated.append(event)
        self.tracker.subscribe_activity(mutate)
        await self.command("show")
        self.assertNotEqual(self.events[0]["session_id"], "changed")
        self.assertEqual(mutated[0]["session_id"], "changed")
        other = manager.Tracker(None, self.tracker._save, self.tracker._notify,
                                lambda: self.now, readback=self.tracker._readback)
        await other.command("show")
        self.assertEqual(len(self.events), 1)
        await self.tracker.shutdown()
        self.assertEqual(self.tracker._activity_listeners, set())

    async def test_activity_waits_for_independent_verification(self):
        entered = asyncio.Event()
        release = asyncio.Event()
        async def readback():
            entered.set()
            await release.wait()
            return deepcopy(self.disk)
        self.tracker._readback = readback
        task = asyncio.create_task(self.command("show"))
        await entered.wait()
        self.assertEqual(self.events, [])
        self.assertEqual(self.published, [])
        self.assertEqual(self.tracker.view()["p"], "off")
        release.set()
        await task
        self.assertEqual(self.events[0]["event_type"], "session_started")
        self.assertEqual(self.published[-1]["p"], "rest")

    async def test_new_session_keeps_hourly_history_without_cross_session_intervals(self):
        await self.command("show")
        await self.complete(1000, 1060)
        await self.command("end")
        await self.command("show")
        self.assertEqual(self.tracker.view()["n"], 0)
        self.assertEqual(self.tracker.view()["last_record"]["end"], 1060)
        await self.complete(1300, 1360)
        view = self.tracker.view()
        self.assertEqual(view["n"], 1)
        self.assertEqual(view["hourly"]["completed"], 2)
        self.assertEqual(view["hourly"]["interval_samples"], 0)
        self.assertIsNone(view["last_record"]["interval"])
