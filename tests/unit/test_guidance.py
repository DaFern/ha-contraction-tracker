from copy import deepcopy
import unittest

from tests.support import model, manager, notifications


def recorded(starts, duration=45, now=10000, location="unspecified", interval=300):
    state = model.transition(model.new_state(), "show", "", 100)
    for stamp in starts:
        state = model.transition(state, "start", state["k"], stamp)
        state = model.transition(state, "stop", state["k"], stamp + duration)
        state = model.transition(state, "Mild", state["k"], stamp + duration)
    return model.configure_guidance(state, state["guidance"]["k"], location, interval)


class GuidanceTests(unittest.TestCase):
    def test_default_is_unspecified_without_location_detection(self):
        settings = model.new_state()["guidance"]
        self.assertEqual(settings["location"], "unspecified")
        self.assertEqual(settings["interval"], 300)

    def test_repeated_gaps_trigger_contact_without_waiting_an_hour(self):
        state = recorded([9000, 9300, 9600, 9900])
        prompt = model.snapshot(state, 10000)["recommendation"]
        self.assertEqual(prompt["level"], "contact")
        self.assertIn("maternity care team", prompt["text"])

    def test_location_changes_only_contact_wording(self):
        for location, phrase in (("home", "Contact your maternity unit"),
                                 ("hospital", "Tell your midwife"),
                                 ("unspecified", "Contact your maternity care team")):
            state = recorded([9000, 9300, 9600, 9900], location=location)
            self.assertIn(phrase, model.snapshot(state, 10000)["recommendation"]["text"])

    def test_hourly_average_cannot_hide_one_long_recent_gap(self):
        state = recorded([9000, 9060, 9660, 9900])
        self.assertEqual(model.snapshot(state, 10000)["hourly"]["interval"], 300)
        self.assertEqual(model.snapshot(state, 10000)["recommendation"]["level"], "routine")

    def test_insufficient_stale_and_other_session_records_do_not_trigger(self):
        for starts, now in (([9000, 9300, 9600], 10000),
                            ([7000, 7300, 7600, 7900], 10000)):
            state = recorded(starts)
            self.assertEqual(model.snapshot(state, now)["recommendation"]["level"], "routine")
        state = recorded([9000, 9300, 9600, 9900])
        state = model.transition(state, "end", state["k"], 10000)
        state = model.transition(state, "show", "", 10000)
        self.assertEqual(model.snapshot(state, 10000)["recommendation"]["level"], "routine")

    def test_active_fourth_start_counts_without_resetting_timer(self):
        state = recorded([9000, 9300, 9600])
        state = model.transition(state, "start", state["k"], 9900)
        self.assertEqual(model.snapshot(state, 9950)["recommendation"]["level"], "contact")

    def test_custom_interval_does_not_change_urgent_thresholds(self):
        state = recorded([9000, 9300, 9600, 9900], interval=240)
        self.assertEqual(model.snapshot(state, 10000)["recommendation"]["level"], "routine")
        for state in (recorded([9700], duration=121, interval=60),
                      recorded([9401, 9500, 9600, 9700, 9800, 9900], interval=600)):
            self.assertEqual(model.snapshot(state, 10000)["recommendation"]["level"], "urgent")

    def test_urgent_limits_and_old_records_age_out(self):
        self.assertNotEqual(model.snapshot(recorded([9700], duration=120), 10000)["recommendation"]["level"], "urgent")
        self.assertEqual(model.snapshot(recorded([9700], duration=121), 10500)["recommendation"]["level"], "routine")
        state = recorded([9400, 9500, 9600, 9700, 9800, 9900])
        self.assertNotEqual(model.snapshot(state, 10000)["recommendation"]["level"], "urgent")
        active = model.transition(model.new_state(), "show", "", 9000)
        active = model.transition(active, "start", active["k"], 9000)
        self.assertEqual(model.snapshot(active, 9121)["recommendation"]["level"], "urgent")

    def test_settings_have_an_independent_revision_and_validate_inputs(self):
        state = recorded([9000])
        moved = model.configure_guidance(state, state["guidance"]["k"], "hospital", 240)
        self.assertEqual(moved["k"], state["k"])
        self.assertEqual(moved["movement"], state["movement"])
        self.assertEqual(moved["records"], state["records"])
        with self.assertRaises(model.InvalidCommand):
            model.configure_guidance(moved, state["guidance"]["k"], "home", 300)
        for location, interval in (("auto", 300), ("home", True), ("home", 0),
                                   ("home", 301), ("home", 300.5), ("home", 660)):
            with self.subTest(location=location, interval=interval), self.assertRaises(model.InvalidCommand):
                model.configure_guidance(state, state["guidance"]["k"], location, interval)
        model.load_state(moved)

    def test_schema_two_migration_preserves_all_existing_data(self):
        state = recorded([9000])
        old = deepcopy(state)
        old["schema"] = 2
        del old["guidance"]
        migrated = model.load_state(old)
        self.assertEqual(migrated["schema"], 7)
        for key in old:
            if key != "schema":
                self.assertEqual(migrated[key], old[key])
        self.assertEqual(migrated["guidance"]["location"], "unspecified")

    def test_plain_notification_preserves_last_completed_while_active(self):
        state = recorded([9000])
        state = model.transition(state, "start", state["k"], 9900)
        message = notifications.build_notification(model.snapshot(state, 9950), "test", "/test")["message"]
        self.assertTrue(message.startswith("Last length: 0:45\nAvg interval:"))
        self.assertIn("\nAvg length: 0:45\n\n• ", message)
        self.assertNotIn("Tap ", message)
        self.assertNotIn("<", message)
        self.assertNotIn("not medical advice", message)
        rest = notifications.build_notification(model.snapshot(recorded([9000]), 9950), "test", "/test")
        self.assertEqual(rest["data"]["actions"][-1]["title"], "Close")
        self.assertIn("|end|", rest["data"]["actions"][-1]["action"])


class GuidancePersistenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_failed_save_is_not_published_and_success_preserves_timer(self):
        state = recorded([9000])
        async def notify(view):
            pass
        async def fail(candidate):
            raise OSError("synthetic failure")
        async def readback():
            return saved[-1]
        tracker = manager.Tracker(state, fail, notify, lambda: 10000, readback=readback)
        before = tracker.view()
        with self.assertRaises(manager.PersistenceError):
            await tracker.configure_guidance(state["guidance"]["k"], "hospital", 240)
        self.assertEqual(tracker.view()["guidance"], before["guidance"])
        saved = []
        async def save(candidate):
            saved.append(candidate)
        tracker._save = save
        with self.assertRaises(model.InvalidCommand):
            await tracker.configure_guidance(state["guidance"]["k"], "hospital", 240)
        self.assertEqual(saved, [])
        # Only a fresh instance, loaded from storage, clears the uncertainty latch.
        tracker = manager.Tracker(state, save, notify, lambda: 10000, readback=readback)
        await tracker.configure_guidance(state["guidance"]["k"], "hospital", 240)
        self.assertEqual(saved[-1]["guidance"]["location"], "hospital")
        self.assertEqual(tracker.view()["k"], before["k"])
        self.assertTrue(tracker.restored)
