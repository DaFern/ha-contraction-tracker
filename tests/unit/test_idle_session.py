"""Synthetic idle-session boundaries and durable phone handoff."""

import unittest
from copy import deepcopy

from tests.support import manager, model, notifications


def completed(rated=True):
    state = model.transition(model.new_state(), "show", "", 1000)
    state = model.transition(state, "start", state["k"], 1000)
    state = model.transition(state, "stop", state["k"], 1060)
    if rated:
        state = model.transition(state, "Mild", state["k"], 1065)
    return state


class IdleModelTests(unittest.TestCase):
    def test_exact_boundary_preserves_records_and_disables_reminders(self):
        for rated in (False, True):
            state = completed(rated)
            state = model.transition(state, "reminders_on", state["movement"]["k"], 1070)
            self.assertEqual(model.expire_idle(state, 4659), state)
            ended = model.load_state(model.expire_idle(state, 4660))
            self.assertEqual(ended["p"], "off")
            self.assertTrue(ended["idle_ended"])
            self.assertEqual(ended["records"], state["records"])
            self.assertFalse(ended["movement"]["enabled"])
            self.assertNotEqual(ended["k"], state["k"])
            self.assertNotEqual(ended["movement"]["k"], state["movement"]["k"])
            self.assertEqual(model.expire_idle(ended, 9000), ended)

    def test_never_fabricates_end_for_active_contraction(self):
        state = completed()
        state = model.transition(state, "start", state["k"], 1200)
        self.assertEqual(model.expire_idle(state, 90000), state)
        self.assertEqual(len(state["records"]), 1)

    def test_notification_start_is_new_session_and_old_buttons_fail(self):
        state = completed()
        ended = model.expire_idle(state, 4660)
        for action in ("start", "end", "Mild"):
            with self.assertRaises(model.InvalidCommand):
                model.transition(ended, action, state["k"], 4661)
        new = model.transition(ended, "start", ended["k"], 5000)
        self.assertEqual(new["p"], "active")
        self.assertNotEqual(new["session_id"], ended["session_id"])
        self.assertEqual((new["n"], new["s"], new["e"], new["i"], new["r"]), (1, 5000, 0, 0, 0))
        self.assertEqual(new["records"], state["records"])
        self.assertFalse(new["idle_ended"])
        new = model.transition(new, "stop", new["k"], 5060)
        self.assertEqual(new["records"][-1]["interval"], 0)
        self.assertEqual(new["records"][-1]["rest"], 0)
        model.load_state(new)
        with self.assertRaises(model.InvalidCommand):
            model.transition(new, "end", ended["k"], 5061)

    def test_idle_notification_has_no_running_clock_and_close_clears_it(self):
        ended = model.expire_idle(completed(), 4660)
        payload = notifications.build_notification(model.snapshot(ended, 5000), "synthetic", "/test")
        self.assertIn("Recording ended after inactivity", payload["message"])
        self.assertEqual([a["title"] for a in payload["data"]["actions"]], ["Start", "Movement", "Close"])
        self.assertTrue(payload["data"]["persistent"])
        self.assertTrue(payload["data"]["sticky"])
        self.assertFalse(payload["data"]["chronometer"])
        self.assertNotIn("when", payload["data"])
        closed = model.transition(ended, "end", ended["k"], 5000)
        self.assertFalse(closed["idle_ended"])
        self.assertEqual(closed["records"], ended["records"])
        self.assertEqual(notifications.build_notification(model.snapshot(closed, 5000),
                                                         "synthetic", "/test")["message"],
                         "clear_notification")

    def test_schema_five_upgrade_preserves_every_old_field(self):
        old = completed()
        old["schema"] = 5
        old.pop("idle_ended")
        old.pop("long_warning_attempted")
        old["movement"].pop("preferred")
        new = model.load_state(old)
        self.assertFalse(new.pop("idle_ended"))
        self.assertFalse(new.pop("long_warning_attempted"))
        self.assertFalse(new["movement"].pop("preferred"))
        new["schema"] = 5
        self.assertEqual(new, old)

    def test_movement_and_settings_do_not_extend_contraction_idle_deadline(self):
        state = completed()
        state = model.transition(state, "movement", state["movement"]["k"], 4650)
        ended = model.expire_idle(state, 4660)
        self.assertTrue(ended["idle_ended"])
        self.assertEqual(ended["movement"]["last"], 4650)


class IdleManagerTests(unittest.IsolatedAsyncioTestCase):
    def make_tracker(self, state=None):
        self.disk = deepcopy(state if state is not None else completed())
        self.now = 4659
        self.pushes = []
        async def save(value):
            self.disk = deepcopy(value)
        async def readback():
            return deepcopy(self.disk)
        async def notify(view):
            self.assertEqual(view["p"], self.disk["p"])
            self.pushes.append(view)
        return manager.Tracker(self.disk, save, notify, lambda: self.now, readback=readback)

    async def test_tick_persists_once_and_restart_restores_notification_until_closed(self):
        tracker = self.make_tracker()
        records = tracker.history()
        await tracker.tick()
        self.assertEqual(self.pushes, [])
        self.now = 4660
        await tracker.tick()
        self.assertTrue(self.disk["idle_ended"])
        self.assertEqual(len(self.pushes), 1)
        await tracker.tick()
        self.assertEqual(len(self.pushes), 1)
        tracker = self.make_tracker(self.disk)
        await tracker.command("notify")
        self.assertTrue(self.pushes[-1]["idle_ended"])
        await tracker.command("end", tracker.view()["k"])
        tracker = self.make_tracker(self.disk)
        await tracker.tick()
        self.assertFalse(tracker.view()["idle_ended"])
        self.assertEqual(tracker.history(), records)

    async def test_overdue_start_before_tick_closes_and_rejects_old_token(self):
        tracker = self.make_tracker()
        old = tracker.view()["k"]
        self.now = 9000
        with self.assertRaises(model.InvalidCommand):
            await tracker.command("start", old)
        self.assertTrue(tracker.view()["idle_ended"])
        await tracker.command("start", tracker.view()["k"])
        self.assertEqual(tracker.view()["i"], 0)

    async def test_failed_expiry_save_blocks_controls_without_sending_idle_buttons(self):
        tracker = self.make_tracker()
        before = deepcopy(self.disk)
        async def fail(value):
            raise OSError("synthetic failure")
        tracker._save = fail
        self.now = 4660
        await tracker.tick()
        self.assertEqual(self.disk, before)
        self.assertTrue(tracker.persistence_uncertain)
        self.assertEqual(self.pushes, [])
        with self.assertRaises(model.InvalidCommand):
            await tracker.command("start", tracker.view()["k"])

    async def test_movement_does_not_reopen_ended_session(self):
        tracker = self.make_tracker()
        self.now = 4660
        await tracker.tick()
        await tracker.command("movement", tracker.view()["movement"]["k"])
        self.assertTrue(tracker.view()["idle_ended"])
        self.assertEqual(tracker.view()["p"], "off")
