"""Remembered opt-in is separate from session activity and movement timing."""

from copy import deepcopy
import unittest

from tests.support import manager, model
from tests.unit.test_idle_session import completed


def apply(state, command, now):
    token = state["movement"]["k"] if command in (
        "movement", "reminders_on", "reminders_off") else state["k"]
    return model.transition(state, command, token, now)


class ReminderPreferenceTests(unittest.TestCase):
    def test_never_enabled_stays_off_in_new_sessions(self):
        state = apply(completed(), "end", 1100)
        state = apply(state, "show", 2000)
        state = apply(state, "start", 2001)
        self.assertFalse(state["movement"]["preferred"])
        self.assertFalse(state["movement"]["enabled"])
        self.assertFalse(model.reminder_due(state, 10000))

    def test_manual_stop_pauses_and_show_resumes_without_resetting_clock(self):
        state = apply(completed(), "reminders_on", 1100)
        state = apply(state, "movement", 1200)
        old = deepcopy(state["movement"])
        records = deepcopy(state["records"])
        state = apply(state, "end", 1300)
        self.assertTrue(state["movement"]["preferred"])
        self.assertFalse(state["movement"]["enabled"])
        self.assertFalse(model.reminder_due(state, 9000))
        state = model.load_state(state)
        state = apply(state, "show", 4700)
        self.assertTrue(state["movement"]["enabled"])
        for key in ("last", "enabled_at", "last_alert", "count"):
            self.assertEqual(state["movement"][key], old[key])
        self.assertFalse(model.reminder_due(state, 4799))
        self.assertTrue(model.reminder_due(state, 4800))
        self.assertEqual(state["records"], records)

    def test_idle_timeout_and_notification_start_resume_only_prior_opt_in(self):
        for opted in (False, True):
            state = completed()
            if opted:
                state = apply(state, "reminders_on", 1100)
            state = model.expire_idle(state, 4660)
            self.assertEqual(state["movement"]["preferred"], opted)
            self.assertFalse(state["movement"]["enabled"])
            state = apply(model.load_state(state), "start", 5000)
            self.assertEqual(state["movement"]["enabled"], opted)
            self.assertEqual(model.reminder_due(state, 5000), opted)
            self.assertEqual(state["i"], 0)
            model.load_state(state)

    def test_explicit_off_while_paused_cancels_future_resume(self):
        state = apply(completed(), "reminders_on", 1100)
        state = apply(state, "end", 1200)
        state = apply(state, "reminders_off", 1300)
        self.assertFalse(state["movement"]["preferred"])
        state = apply(model.load_state(state), "show", 2000)
        self.assertFalse(state["movement"]["enabled"])
        self.assertFalse(model.reminder_due(state, 10000))

    def test_movement_while_paused_prevents_overdue_reminder_on_resume(self):
        state = apply(completed(), "reminders_on", 1100)
        state = apply(state, "end", 1200)
        state = apply(state, "movement", 4900)
        state = apply(state, "show", 5000)
        self.assertFalse(model.reminder_due(state, 8499))
        self.assertTrue(model.reminder_due(state, 8500))

    def test_enabling_without_any_logged_movement_waits_an_hour(self):
        state = apply(model.new_state(), "show", 1000)
        state = apply(state, "reminders_on", 1000)
        self.assertFalse(model.reminder_due(state, 4599))
        self.assertTrue(model.reminder_due(state, 4600))

    def test_recent_alert_cooldown_survives_session_restart(self):
        state = apply(completed(), "reminders_on", 1100)
        state["movement"]["last_alert"] = 5000
        state = apply(state, "end", 5001)
        state = apply(state, "show", 5002)
        self.assertFalse(model.reminder_due(state, 8599))
        self.assertTrue(model.reminder_due(state, 8600))

    def test_schema_six_only_infers_opt_in_from_current_enabled_state(self):
        for enabled in (False, True):
            old = completed()
            if enabled:
                old = apply(old, "reminders_on", 1100)
            old["schema"] = 6
            old.pop("long_warning_attempted")
            old["movement"].pop("preferred")
            # An old timestamp is not evidence that a current Off was automatic.
            old["movement"]["enabled_at"] = 1100
            new = model.load_state(old)
            self.assertEqual(new["movement"].pop("preferred"), enabled)
            self.assertFalse(new.pop("long_warning_attempted"))
            new["schema"] = 6
            self.assertEqual(new, old)


class ReminderDeliveryTests(unittest.IsolatedAsyncioTestCase):
    async def make_tracker(self):
        self.now = 1000
        self.disk = None
        self.attempts = []
        async def save(state):
            self.disk = deepcopy(state)
        async def readback():
            return deepcopy(self.disk)
        async def notify(view):
            pass
        async def warning(view):
            self.assertEqual(self.disk["movement"]["last_alert"], self.now)
            self.attempts.append(self.now)
        tracker = manager.Tracker(None, save, notify, lambda: self.now, readback=readback)
        tracker.warning_notify = warning
        await tracker.command("show")
        await tracker.command("reminders_on", tracker.view()["movement"]["k"])
        return tracker

    async def test_recent_movement_and_once_hourly_dispatch(self):
        tracker = await self.make_tracker()
        self.now = 4500
        await tracker.command("movement", tracker.view()["movement"]["k"])
        self.now = 4600
        await tracker.tick()
        self.assertEqual(self.attempts, [])
        self.now = 8100
        await tracker.tick()
        await tracker.tick()
        self.assertEqual(self.attempts, [8100])
        self.now = 11699
        await tracker.tick()
        self.assertEqual(self.attempts, [8100])
        self.now = 11700
        await tracker.tick()
        self.assertEqual(self.attempts, [8100, 11700])

    async def test_ambiguous_delivery_does_not_retry_every_minute(self):
        tracker = await self.make_tracker()
        async def fail(view):
            self.attempts.append(self.now)
            raise TimeoutError("synthetic ambiguous delivery")
        tracker.warning_notify = fail
        self.now = 4600
        await tracker.tick()
        self.assertTrue(tracker.notification_failed)
        self.now = 4660
        await tracker.tick()
        self.assertEqual(self.attempts, [4600])
        self.assertEqual(self.disk["movement"]["last_alert"], 4600)

    async def test_unverified_cooldown_write_never_sends_reminder(self):
        tracker = await self.make_tracker()
        async def fail(state):
            raise OSError("synthetic write failure")
        tracker._save = fail
        self.now = 4600
        await tracker.tick()
        self.assertEqual(self.attempts, [])
        self.assertTrue(tracker.persistence_uncertain)
