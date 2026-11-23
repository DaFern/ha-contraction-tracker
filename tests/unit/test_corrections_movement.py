import unittest
from copy import deepcopy

from tests.support import manager, model


def apply(state, command, now, movement=False):
    return model.transition(state, command, state["movement"]["k"] if movement else state["k"], now)


def records():
    state = apply(model.new_state(), "show", 1000)
    for start in (1000, 1300, 1600):
        state = apply(state, "start", start)
        state = apply(state, "stop", start + 40)
        state = apply(state, "Mild", start + 41)
    return state


class CorrectionTests(unittest.TestCase):
    def test_edit_recalculates_both_neighbors_and_preserves_original(self):
        state = records()
        row = state["records"][1]
        result = model.correct(state, row["id"], row["revision"], 1310, 1360, "Strong", 2000)
        self.assertEqual(result["records"][1]["duration"], 50)
        self.assertEqual(result["records"][1]["interval"], 310)
        self.assertEqual(result["records"][2]["interval"], 290)
        self.assertEqual(result["records"][2]["rest"], 240)
        self.assertEqual(result["records"][1]["original"]["start"], 1300)
        self.assertEqual(len(result["records"][1]["audit"]), 1)
        self.assertEqual(state["records"][1]["start"], 1300)
        model.load_state(result)

    def test_stale_overlap_future_and_repeated_edits_are_rejected(self):
        state = records()
        row = state["records"][1]
        for revision, start, end in (("stale", 1310, 1360),
                                     (row["revision"], 1030, 1360),
                                     (row["revision"], 1310, 1700),
                                     (row["revision"], 1310, 3000)):
            with self.subTest(start=start, end=end), self.assertRaises(model.InvalidCommand):
                model.correct(state, row["id"], revision, start, end, "Mild", 2000)

    def test_latest_correction_updates_current_fields_without_starting_recording(self):
        state = records()
        state = apply(state, "end", 1700)
        row = state["records"][-1]
        result = model.correct(state, row["id"], row["revision"], 1605, 1650, "Moderate", 2000)
        self.assertEqual(result["p"], "off")
        self.assertEqual((result["s"], result["e"], result["d"], result["v"]), (1605, 1650, 45, "Moderate"))

    def test_active_timer_is_not_reset_by_editing_previous_record(self):
        state = apply(records(), "start", 1900)
        row = state["records"][-1]
        result = model.correct(state, row["id"], row["revision"], 1610, 1650, "Mild", 2000)
        self.assertEqual((result["p"], result["s"], result["k"]), ("active", 1900, state["k"]))
        self.assertEqual((result["i"], result["r"]), (290, 250))

    def test_hourly_figures_are_not_limited_to_six_recent_rows(self):
        state = apply(model.new_state(), "show", 1000)
        for index in range(20):
            start = 1000 + 100 * index
            state = apply(apply(apply(state, "start", start), "stop", start + 40), "Mild", start + 41)
        view = model.snapshot(state, 3000)
        self.assertEqual(view["hourly"]["count"], 20)
        self.assertEqual(len(view["recent"]), 6)
        self.assertEqual(view["hourly"]["interval"], 100)

    def test_first_alpha_store_migrates_without_losing_records(self):
        state = records()
        state["schema"] = 1
        state.pop("movement")
        for row in state["records"]:
            for key in ("revision", "audit", "original"):
                row.pop(key)
        restored = model.load_state(state)
        self.assertEqual(restored["schema"], 5)
        self.assertEqual(len(restored["records"]), 3)
        self.assertFalse(restored["movement"]["enabled"])


class MovementTests(unittest.TestCase):
    def setUp(self):
        self.state = apply(model.new_state(), "show", 1000)

    def test_movement_never_resets_or_invalidates_the_contraction_timer(self):
        state = apply(self.state, "start", 1000)
        moved = apply(state, "movement", 1050, True)
        self.assertEqual((moved["p"], moved["s"], moved["k"]), (state["p"], state["s"], state["k"]))
        self.assertEqual((moved["movement"]["last"], moved["movement"]["count"]), (1050, 1))
        with self.assertRaises(model.InvalidCommand):
            model.transition(moved, "movement", state["movement"]["k"], 1051)

    def test_reminder_is_off_by_default_and_only_due_after_one_hour_when_enabled(self):
        self.assertFalse(model.reminder_due(self.state, 10000))
        enabled = apply(self.state, "reminders_on", 1000, True)
        self.assertFalse(model.reminder_due(enabled, 4599))
        self.assertTrue(model.reminder_due(enabled, 4600))
        moved = apply(enabled, "movement", 4500, True)
        self.assertFalse(model.reminder_due(moved, 4600))
        self.assertTrue(model.reminder_due(moved, 8100))

    def test_disabling_or_stopping_recording_cancels_reminders(self):
        enabled = apply(self.state, "reminders_on", 1000, True)
        disabled = apply(enabled, "reminders_off", 1100, True)
        self.assertFalse(model.reminder_due(disabled, 10000))
        ended = apply(enabled, "end", 1100)
        self.assertFalse(ended["movement"]["enabled"])
        self.assertFalse(model.reminder_due(ended, 10000))


class EditPersistenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_edit_is_saved_before_publish_and_failed_save_keeps_original(self):
        saved = []
        async def save(value):
            saved.append(value)
        async def notify(value):
            pass
        async def readback():
            return deepcopy(saved[-1])
        tracker = manager.Tracker(records(), save, notify, lambda: 2000, readback=readback)
        row = tracker.history()[-1]
        await tracker.edit(row["id"], row["revision"], 1605, 1650, "Strong")
        self.assertEqual(saved[-1]["records"][-1]["start"], 1605)
        before = tracker.history()
        async def fail(value):
            raise OSError("synthetic storage failure")
        tracker._save = fail
        row = tracker.history()[-1]
        with self.assertRaises(manager.PersistenceError):
            await tracker.edit(row["id"], row["revision"], 1610, 1655, "Mild")
        self.assertEqual(tracker._state["records"], before)
        with self.assertRaises(model.InvalidCommand):
            tracker.history()
