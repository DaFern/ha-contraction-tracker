"""Warnings describe the timer, never infer a contraction's end or a diagnosis."""

import asyncio
from copy import deepcopy
import unittest

from tests.support import manager, model, notifications


class LongContractionTests(unittest.IsolatedAsyncioTestCase):
    async def make_tracker(self, initial=None):
        self.now = 1000
        self.disk = deepcopy(initial)
        self.alerts = []
        async def save(state):
            self.disk = deepcopy(state)
        async def readback():
            return deepcopy(self.disk)
        async def notify(view):
            pass
        async def warning(view):
            self.assertTrue(self.disk["long_warning_attempted"])
            self.alerts.append(deepcopy(view))
        tracker = manager.Tracker(initial, save, notify, lambda: self.now, readback=readback)
        tracker.long_warning_notify = warning
        if initial is None:
            await tracker.command("show")
            await tracker.command("start", tracker.view()["k"])
        return tracker

    async def test_exact_threshold_warns_once_without_changing_measurements_or_stop_token(self):
        tracker = await self.make_tracker()
        before = deepcopy(self.disk)
        identity, delay = tracker.long_warning_schedule()
        self.assertEqual(delay, 121)
        self.now = 1120
        await tracker.check_long_contraction(identity)
        self.assertFalse(tracker.view()["long_contraction"])
        self.assertEqual(self.alerts, [])
        self.now = 1121
        await tracker.check_long_contraction(identity)
        self.assertTrue(tracker.view()["long_contraction"])
        self.assertEqual(len(self.alerts), 1)
        self.assertEqual(self.disk, {**before, "long_warning_attempted": True})
        self.assertIsNone(tracker.long_warning_schedule())
        await tracker.check_long_contraction(identity)
        self.assertEqual(len(self.alerts), 1)
        await tracker.command("stop", before["k"])
        self.assertEqual(tracker.history()[0]["duration"], 121)
        self.assertFalse(tracker.view()["long_contraction"])

    async def test_restored_attempt_is_not_sent_again(self):
        tracker = await self.make_tracker()
        identity, _ = tracker.long_warning_schedule()
        self.now = 1121
        await tracker.check_long_contraction(identity)
        disk = deepcopy(self.disk)
        restored = await self.make_tracker(disk)
        self.now = 9000
        self.assertIsNone(restored.long_warning_schedule())
        await restored.check_long_contraction(identity)
        self.assertEqual(self.alerts, [])
        self.assertEqual(self.disk, disk)

    async def test_fractional_scheduling_keeps_the_same_absolute_deadline(self):
        for fraction in (0.0, 0.2, 0.8, 0.999):
            with self.subTest(fraction=fraction):
                tracker = await self.make_tracker()
                before = deepcopy(self.disk)
                self.now = 1000 + fraction
                identity, delay = tracker.long_warning_schedule()
                self.assertAlmostEqual(delay, 121 - fraction, places=7)
                self.assertAlmostEqual(self.now + delay, 1121, places=7)
                self.now = 1120.999
                await tracker.check_long_contraction(identity)
                self.assertEqual(self.alerts, [])
                self.assertEqual(self.disk, before)
                self.now = 1121
                await tracker.check_long_contraction(identity)
                self.assertEqual(len(self.alerts), 1)
                self.assertEqual(self.disk, {**before, "long_warning_attempted": True})
                self.assertEqual(tracker.view()["k"], before["k"])
                self.assertEqual(tracker.history(), [])

    async def test_overdue_restart_schedules_one_immediate_attempt(self):
        tracker = await self.make_tracker()
        disk = deepcopy(self.disk)
        restored = await self.make_tracker(disk)
        self.now = 9000
        identity, delay = restored.long_warning_schedule()
        self.assertEqual(delay, 0)
        await restored.check_long_contraction(identity)
        self.assertEqual(len(self.alerts), 1)
        self.assertEqual(restored.history(), [])
        self.assertEqual(restored.view()["p"], "active")
        self.assertEqual(restored.view()["s"], 1000)

    async def test_stale_timer_cannot_warn_for_next_contraction(self):
        tracker = await self.make_tracker()
        stale, _ = tracker.long_warning_schedule()
        self.now = 1045
        await tracker.command("stop", tracker.view()["k"])
        await tracker.command("Mild", tracker.view()["k"])
        self.now = 1100
        await tracker.command("start", tracker.view()["k"])
        identity, _ = tracker.long_warning_schedule()
        self.now = 1221
        await tracker.check_long_contraction(stale)
        self.assertEqual(self.alerts, [])
        await tracker.check_long_contraction(identity)
        self.assertEqual(len(self.alerts), 1)
        self.assertEqual(tracker.history()[0]["duration"], 45)

    async def test_stopped_or_unloaded_tracker_never_sends_stale_warning(self):
        for unload in (False, True):
            tracker = await self.make_tracker()
            identity, _ = tracker.long_warning_schedule()
            if unload:
                await tracker.shutdown()
            else:
                self.now = 1045
                await tracker.command("stop", tracker.view()["k"])
            self.now = 1121
            await tracker.check_long_contraction(identity)
            self.assertIsNone(tracker.long_warning_schedule())
            self.assertEqual(self.alerts, [])

    async def test_ambiguous_delivery_claim_survives_without_retries(self):
        tracker = await self.make_tracker()
        async def fail(view):
            self.alerts.append(view)
            raise TimeoutError("synthetic unknown phone result")
        tracker.long_warning_notify = fail
        identity, _ = tracker.long_warning_schedule()
        self.now = 1121
        await tracker.check_long_contraction(identity)
        await tracker.check_long_contraction(identity)
        self.assertEqual(len(self.alerts), 1)
        self.assertTrue(tracker.notification_failed)
        self.assertTrue(self.disk["long_warning_attempted"])

    async def test_unverified_save_blocks_alert_and_controls(self):
        for silent in (False, True):
            tracker = await self.make_tracker()
            before = deepcopy(self.disk)
            async def fail(state):
                if not silent:
                    raise OSError("synthetic disk failure")
            tracker._save = fail
            identity, _ = tracker.long_warning_schedule()
            self.now = 1121
            await tracker.check_long_contraction(identity)
            self.assertEqual(self.alerts, [])
            self.assertEqual(self.disk, before)
            self.assertTrue(tracker.persistence_uncertain)
            self.assertIsNone(tracker.long_warning_schedule())
            with self.assertRaises(model.InvalidCommand):
                await tracker.command("stop", tracker.view()["k"])

    async def test_no_selected_phone_schedules_state_evaluation_without_claiming_an_alert(self):
        tracker = await self.make_tracker()
        identity, _ = tracker.long_warning_schedule()
        tracker.long_warning_notify = None
        before = deepcopy(self.disk)
        published = []
        tracker.subscribe(lambda: published.append(tracker.view()["long_contraction"]))
        self.now = 1121
        self.assertEqual(tracker.long_warning_schedule(), (identity, 0))
        await tracker.check_long_contraction(identity)
        self.assertTrue(tracker.view()["long_contraction"])
        self.assertEqual(published, [True])
        self.assertFalse(self.disk["long_warning_attempted"])
        self.assertEqual(self.disk, before)
        self.assertEqual(self.alerts, [])
        self.assertIsNone(tracker.long_warning_schedule())

    async def test_clock_rollback_rearms_state_only_evaluation_without_second_phone_attempt(self):
        for phone in (False, True):
            with self.subTest(phone=phone):
                tracker = await self.make_tracker()
                if not phone:
                    tracker.long_warning_notify = None
                identity, _ = tracker.long_warning_schedule()
                self.now = 1121
                await tracker.check_long_contraction(identity)
                disk = deepcopy(self.disk)
                self.now = 1100
                self.assertFalse(tracker.view()["long_contraction"])
                self.assertEqual(tracker.long_warning_schedule(), (identity, 21))
                await tracker.check_long_contraction(identity)
                self.assertEqual(self.disk, disk)
                self.now = 1121
                await tracker.check_long_contraction(identity)
                self.assertTrue(tracker.view()["long_contraction"])
                self.assertEqual(len(self.alerts), int(phone))
                self.assertEqual(self.disk, disk)
                self.assertIsNone(tracker.long_warning_schedule())

    async def test_settings_and_movement_do_not_duplicate_or_invalidate_warning_or_stop(self):
        tracker = await self.make_tracker()
        identity, _ = tracker.long_warning_schedule()
        stop_token = tracker.view()["k"]
        await tracker.command("movement", tracker.view()["movement"]["k"])
        await tracker.configure_guidance(tracker.view()["guidance"]["k"], "home", 300)
        self.assertEqual(tracker.long_warning_schedule()[0], identity)
        self.now = 1121
        await tracker.check_long_contraction(identity)
        self.assertEqual(tracker.view()["k"], stop_token)
        await tracker.command("stop", stop_token)
        self.assertEqual(len(self.alerts), 1)

    async def test_queued_stop_retains_receipt_time_during_warning_delivery(self):
        tracker = await self.make_tracker()
        entered, release = asyncio.Event(), asyncio.Event()
        async def slow(view):
            entered.set()
            await release.wait()
        tracker.long_warning_notify = slow
        identity, _ = tracker.long_warning_schedule()
        self.now = 1121
        warning = asyncio.create_task(tracker.check_long_contraction(identity))
        await entered.wait()
        self.now = 1122
        stop = asyncio.create_task(tracker.command("stop", tracker.view()["k"]))
        await asyncio.sleep(0)
        self.now = 1200
        release.set()
        await asyncio.gather(warning, stop)
        self.assertEqual(tracker.history()[0]["duration"], 122)

    async def test_notification_payload_is_private_and_stop_uses_current_token(self):
        tracker = await self.make_tracker()
        payload = notifications.build_long_warning(tracker.view(), "synthetic", "/test")
        self.assertEqual(payload["data"]["visibility"], "private")
        self.assertIn("If this contraction is still continuing", payload["message"])
        self.assertIn("correct the record", payload["message"])
        self.assertEqual(payload["data"]["actions"],
                         [{"action": f"CT|synthetic|stop|{tracker.view()['k']}", "title": "Stop"}])
        public = notifications.build_long_warning(tracker.view(), "synthetic", "/test", True)
        self.assertEqual(public["data"]["visibility"], "public")
        self.assertNotIn("critical", payload["data"])

    async def test_schema_seven_upgrade_preserves_every_existing_field(self):
        tracker = await self.make_tracker()
        old = deepcopy(self.disk)
        old["schema"] = 7
        old.pop("long_warning_attempted")
        new = model.load_state(old)
        self.assertFalse(new.pop("long_warning_attempted"))
        new["schema"] = 7
        self.assertEqual(new, old)
