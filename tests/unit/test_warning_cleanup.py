"""Phone-order simulation of actual pure warning payload/cleanup decisions."""

from copy import deepcopy
from itertools import permutations
import unittest

from tests.support import model, notifications


def started():
    state = model.transition(model.new_state(), "show", "", 1000)
    return model.transition(state, "start", state["k"], 1000)


def deliver(visible, payload):
    """A tagged phone notification replaces/clears only its exact tag."""
    tag = payload["data"]["tag"]
    if payload["message"] == "clear_notification":
        visible.pop(tag, None)
    else:
        visible[tag] = payload


class WarningCleanupTests(unittest.TestCase):
    def test_no_warning_clear_before_threshold_or_during_active_refresh(self):
        state = started()
        for attempted in (False, True):
            state["long_warning_attempted"] = attempted
            before = deepcopy(state)
            for now in (1000, 1050, 1120, 1121, 1500):
                view = model.snapshot(state, now)
                self.assertEqual(notifications.long_warning_cleanup_tags(view, "entry"), [])
            self.assertEqual(state, before)
        self.assertEqual(notifications.long_warning_cleanup_tags(
            model.snapshot(model.new_state(), 1000), "entry"), [])

    def test_tag_stable_across_restore_and_nonidentity_changes_but_unique_per_contraction(self):
        state = started()
        before = deepcopy(state)
        tag = notifications.long_warning_tag(state, "entry")
        self.assertRegex(tag, r"^contraction_tracker_long_entry_[0-9a-f]{32}$")
        self.assertNotIn(state["session_id"], tag)
        self.assertNotIn(state["k"], tag)
        self.assertEqual(notifications.long_warning_tag(model.load_state(state), "entry"), tag)
        state["long_warning_attempted"] = True
        state["k"] = "a" * 32
        state["movement"]["count"] += 1
        self.assertEqual(notifications.long_warning_tag(state, "entry"), tag)
        for key, value in (("session_id", "another-session"), ("n", 2), ("s", 1001)):
            changed = {**state, key: value}
            self.assertNotEqual(notifications.long_warning_tag(changed, "entry"), tag)
        self.assertNotEqual(notifications.long_warning_tag(state, "other-entry"), tag)
        self.assertEqual(notifications.long_warning_tag(before, "entry"), tag)

    def test_delayed_previous_clears_cannot_remove_new_warning_in_any_order(self):
        state = started()
        state["long_warning_attempted"] = True
        old_warning = notifications.build_long_warning(model.snapshot(state, 1121), "entry", "/test")
        state = model.transition(state, "stop", state["k"], 1122)
        completed = model.snapshot(state, 1122)
        clears = [{"message": "clear_notification", "data": {"tag": tag}}
                  for tag in notifications.long_warning_cleanup_tags(completed, "entry")]
        self.assertEqual(len(clears), 2)
        self.assertIn(old_warning["data"]["tag"], [item["data"]["tag"] for item in clears])
        state = model.transition(state, "Mild", state["k"], 1123)
        state = model.transition(state, "start", state["k"], 1300)
        self.assertEqual(notifications.long_warning_cleanup_tags(
            model.snapshot(state, 1300), "entry"), [])
        state["long_warning_attempted"] = True
        warning = notifications.build_long_warning(model.snapshot(state, 1421), "entry", "/test")
        self.assertNotEqual(warning["data"]["tag"], old_warning["data"]["tag"])
        for order in permutations([warning, *clears]):
            visible = {old_warning["data"]["tag"]: old_warning}
            for payload in order:
                deliver(visible, payload)
            self.assertIn(warning["data"]["tag"], visible)
            self.assertNotIn(old_warning["data"]["tag"], visible)

    def test_cleanup_requires_verified_completed_record_not_shutdown_off_presentation(self):
        state = started()
        state["long_warning_attempted"] = True
        active = model.snapshot(state, 1121)
        self.assertEqual(notifications.long_warning_cleanup_tags(
            {**active, "p": "off"}, "entry"), [])
        state = model.transition(state, "stop", state["k"], 1122)
        view = model.snapshot(state, 1122)
        self.assertEqual(notifications.long_warning_cleanup_tags(view, "entry"), [
            notifications.long_warning_tag(view, "entry"), "contraction_tracker_long_entry"])
        view["long_warning_attempted"] = False
        self.assertEqual(notifications.long_warning_cleanup_tags(view, "entry"), [])

    def test_zero_length_previous_record_does_not_look_like_active_shutdown_completion(self):
        state = started()
        state = model.transition(state, "stop", state["k"], 1000)
        state = model.transition(state, "Mild", state["k"], 1000)
        state = model.transition(state, "start", state["k"], 1000)
        state["long_warning_attempted"] = True
        view = model.snapshot(state, 1121)
        self.assertEqual(view["e"], view["s"])
        self.assertEqual(notifications.long_warning_cleanup_tags(
            {**view, "p": "off"}, "entry"), [])
