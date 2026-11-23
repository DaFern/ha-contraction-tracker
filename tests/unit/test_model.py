import unittest
from unittest.mock import patch

from tests.support import model


def apply(state, command, now):
    return model.transition(state, command, state["k"], now)


class ModelTests(unittest.TestCase):
    def setUp(self):
        self.state = apply(model.new_state(), "show", 1000)

    def test_full_cycle_and_start_to_start_interval(self):
        started = apply(self.state, "start", 1000)
        stopped = apply(started, "stop", 1045)
        rated = apply(stopped, "Moderate", 1046)
        next_start = apply(rated, "start", 1300)
        self.assertEqual((stopped["d"], next_start["i"], next_start["r"]), (45, 300, 255))
        self.assertEqual(stopped["records"][0]["intensity"], "Not rated")
        self.assertEqual(rated["records"][0]["intensity"], "Moderate")
        self.assertEqual(stopped["records"][0]["id"], rated["records"][0]["id"])
        self.assertEqual(next_start["n"], 2)

    def test_first_contraction_has_no_interval(self):
        started = apply(self.state, "start", 2000)
        self.assertEqual((started["i"], started["r"]), (0, 0))

    def test_input_state_and_records_are_not_mutated(self):
        started = apply(self.state, "start", 1000)
        self.assertEqual(self.state["p"], "rest")
        stopped = apply(started, "stop", 1010)
        stopped["records"][0]["duration"] = 900
        self.assertEqual(started["records"], [])

    def test_duplicate_and_stale_actions_are_rejected(self):
        started = apply(self.state, "start", 1000)
        with self.assertRaises(model.InvalidCommand):
            model.transition(started, "start", self.state["k"], 1001)
        with self.assertRaises(model.InvalidCommand):
            model.transition(started, "stop", "", 1010)

    def test_invalid_phases_do_not_create_records(self):
        for command in ("stop", "Mild", "Moderate", "Strong", "nonsense"):
            with self.subTest(command=command), self.assertRaises(model.InvalidCommand):
                apply(self.state, command, 1000)

    def test_cannot_end_or_start_an_active_contraction(self):
        started = apply(self.state, "start", 1000)
        for command in ("end", "start", "Strong"):
            with self.subTest(command=command), self.assertRaises(model.InvalidCommand):
                apply(started, command, 1010)

    def test_show_and_notify_do_not_reset_active_timing(self):
        started = apply(self.state, "start", 1000)
        self.assertEqual(apply(started, "show", 2000), started)
        self.assertEqual(apply(started, "notify", 2000), started)

    def test_end_and_new_session_preserve_history(self):
        state = apply(apply(apply(self.state, "start", 1000), "stop", 1045), "Mild", 1046)
        ended = apply(state, "end", 1100)
        opened = apply(ended, "show", 2000)
        self.assertEqual(len(opened["records"]), 1)
        self.assertNotEqual(opened["session_id"], state["session_id"])
        self.assertEqual(opened["n"], 0)
        self.assertEqual(len(model.snapshot(opened, 2000)["recent"]), 1)
        self.assertEqual(model.snapshot(opened, 2000)["hourly"]["count"], 1)

    def test_storage_roundtrip_for_every_phase(self):
        states = [model.new_state(), self.state]
        states.append(apply(states[-1], "start", 1000))
        states.append(apply(states[-1], "stop", 1045))
        states.append(apply(states[-1], "Strong", 1046))
        states.append(apply(states[-1], "end", 1050))
        for state in states:
            with self.subTest(phase=state["p"]):
                self.assertEqual(model.load_state(state), state)
                self.assertIsNot(model.load_state(state), state)

    def test_invalid_storage_is_not_silently_replaced(self):
        for data in ({}, [], {"schema": 2}, {**self.state, "n": -1},
                     {**self.state, "k": None}, {**self.state, "session_id": ""}):
            with self.subTest(data=data), self.assertRaises(model.InvalidStorage):
                model.load_state(data)

    def test_inconsistent_or_duplicate_records_are_rejected(self):
        state = apply(apply(self.state, "start", 1000), "stop", 1045)
        wrong = model.load_state(state)
        wrong["records"][0]["duration"] = 99
        with self.assertRaises(model.InvalidStorage):
            model.load_state(wrong)
        wrong = model.load_state(state)
        wrong["records"].append(dict(wrong["records"][0]))
        with self.assertRaises(model.InvalidStorage):
            model.load_state(wrong)

    def test_last_six_rows_remain_visible_while_hourly_figures_age_out(self):
        state = self.state
        for index in range(8):
            start = 1000 + index * 100
            state = apply(state, "start", start)
            state = apply(state, "stop", start + 30)
            state = apply(state, "Mild", start + 31)
        self.assertEqual(len(model.snapshot(state, 1800)["recent"]), 6)
        self.assertEqual(len(model.snapshot(state, 10000)["recent"]), 6)
        self.assertEqual(model.snapshot(state, 10000)["hourly"]["count"], 0)
        self.assertIsNone(model.snapshot(state, 10000)["hourly"]["duration"])
        snapshot = model.snapshot(state, 1800)
        self.assertNotIn("records", snapshot)
        self.assertEqual(snapshot["records_count"], 8)

    def test_backwards_or_invalid_clock_is_rejected(self):
        state = apply(self.state, "start", 1000)
        for now in (999, float("nan"), float("inf"), True):
            with self.subTest(now=now), self.assertRaises(model.InvalidCommand):
                apply(state, "stop", now)

    def test_history_limit_never_discards_existing_records(self):
        state = apply(apply(apply(self.state, "start", 1000), "stop", 1045), "Mild", 1046)
        with patch.object(model, "MAX_RECORDS", 1), self.assertRaises(model.InvalidCommand):
            apply(state, "start", 1200)
        self.assertEqual(len(state["records"]), 1)

    def test_notification_summary_uses_recent_averages_and_descriptive_trends(self):
        rows = [[1000 + i * 200, 30 if i < 3 else 60, 300 if i < 3 else 180,
                 1 if i < 3 else 3] for i in range(6)]
        summary = model.summarize(rows)
        self.assertEqual(summary["duration"], 48)
        self.assertEqual(summary["interval"], 228)
        self.assertEqual(summary["samples"], 5)
        self.assertIn("Recent starts are closer together.", summary["trends"])
        self.assertIn("Recent durations are longer.", summary["trends"])
        self.assertIn("Recent intensity ratings are higher.", summary["trends"])
        self.assertNotIn("stage", " ".join(summary["trends"]).lower())
