import unittest

from tests.support import model, notifications


class NotificationTests(unittest.TestCase):
    def setUp(self):
        self.state = model.transition(model.new_state(), "show", "", 1000)

    def payload(self, state=None, public=False, entry="test-entry"):
        return notifications.build_notification(model.snapshot(state or self.state, 2000),
                                                 entry, "/contractions-test", public)

    def test_lock_screen_is_private_unless_explicitly_enabled(self):
        self.assertEqual(self.payload()["data"]["visibility"], "private")
        self.assertEqual(self.payload(public=True)["data"]["visibility"], "public")

    def test_bundled_icon_uses_no_external_hosts(self):
        self.assertTrue(self.payload()["data"]["icon_url"].startswith("/contraction_tracker_static/"))

    def test_each_entry_has_independent_tags_and_revision_actions(self):
        left, right = self.payload(), self.payload(entry="second-entry")
        self.assertNotEqual(left["data"]["tag"], right["data"]["tag"])
        self.assertIn(f"|{self.state['k']}", left["data"]["actions"][0]["action"])

    def test_movement_stays_available_within_android_three_button_limit(self):
        started = model.transition(self.state, "start", self.state["k"], 1000)
        self.assertEqual([action["title"] for action in self.payload(started)["data"]["actions"]], ["Stop", "Movement"])
        stopped = model.transition(started, "stop", started["k"], 1045)
        self.assertEqual([action["title"] for action in self.payload(stopped)["data"]["actions"]],
                         ["Intensity", "Movement"])
        choices = notifications.build_rating(model.snapshot(stopped, 2000), "test", "/contractions-test")
        self.assertEqual([action["title"] for action in choices["data"]["actions"]], ["Mild", "Moderate", "Strong"])

    def test_inactive_phase_clears_its_tag_only(self):
        payload = self.payload(model.new_state())
        self.assertEqual(payload["message"], "clear_notification")
        self.assertEqual(set(payload["data"]), {"tag"})

    def test_new_session_does_not_show_a_1970_notification_time(self):
        self.assertNotIn("when", self.payload()["data"])

    def test_restart_and_save_warning_are_explicit(self):
        view = model.snapshot(self.state, 2000)
        view.update(restored=True, persistence_failed=True)
        payload = notifications.build_notification(view, "test", "/contractions-test")
        self.assertIn("SAVE NOT CONFIRMED", payload["message"])
        self.assertIn("restart", payload["message"])

    def test_completed_notification_includes_averages(self):
        state = model.transition(self.state, "start", self.state["k"], 1000)
        state = model.transition(state, "stop", state["k"], 1045)
        self.assertIn("Avg length: 0:45", self.payload(state)["message"])
