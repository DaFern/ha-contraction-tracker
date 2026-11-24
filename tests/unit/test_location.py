from copy import deepcopy
import importlib
import unittest

from tests.support import model, manager, notifications
from tests.unit.test_guidance import recorded

location = importlib.import_module(f"{model.__package__}.location")


def automatic(state=None):
    state = state or recorded([9000, 9300, 9600, 9900])
    return model.configure_guidance(state, state["guidance"]["k"], "hospital", 300,
                                    mode="automatic", person="person.patient", home="zone.home",
                                    hospitals=["zone.hospital"])


def entities(now=10000):
    return {
        "person.patient": {"state": "Hospital", "attributes": {"source": "device_tracker.patient"}},
        "device_tracker.patient": {"state": "Hospital", "reported": now,
                                   "attributes": {"source_type": "gps", "latitude": 0,
                                                  "longitude": 0, "gps_accuracy": 10}},
        "zone.home": {"state": "0", "attributes": {"latitude": 1, "longitude": 1, "radius": 100}},
        "zone.hospital": {"state": "0", "attributes": {"latitude": 0, "longitude": 0, "radius": 100}},
    }


class LocationTests(unittest.TestCase):
    def test_geometry_checks_accuracy_age_boundaries_overlap_and_elsewhere(self):
        for accuracy, age, zones, expected in (
            (10, 0, [("home", 0, 100), ("hospital", 1000, 100)], "home"),
            (10, 900, [("home", 1000, 100), ("hospital", 0, 100)], "hospital"),
            (10, 901, [("hospital", 0, 100)], "uncertain"),
            (101, 0, [("hospital", 0, 100)], "uncertain"),
            (10, -31, [("hospital", 0, 100)], "uncertain"),
            (10, 0, [("hospital", 90, 100)], "uncertain"),
            (10, 0, [("hospital", 110, 100)], "uncertain"),
            (10, 0, [("hospital", 0, 100), ("home", 0, 100)], "uncertain"),
            (10, 0, [("hospital", 0, 100), ("hospital", 0, 100)], "uncertain"),
            (10, 0, [("hospital", 0, 100), ("home", 90, 100)], "uncertain"),
            (10, 0, [("hospital", 500, 100), ("home", 500, 100)], "elsewhere"),
            (float("nan"), 0, [("home", 0, 100)], "uncertain"),
            (10, 0, [("home", 0, float("inf"))], "uncertain"),
        ):
            with self.subTest(expected=expected, accuracy=accuracy, age=age):
                self.assertEqual(location.classify(accuracy, age, zones)["location"], expected)

    def test_uses_selected_person_source_and_not_zone_occupancy_or_names(self):
        state = automatic()
        states = entities()
        states["person.someone_else"] = {"state": "home", "attributes": {"source": "device_tracker.other"}}
        result = location.resolve(state["guidance"], states, 10000)
        self.assertEqual(result["location"], "hospital")
        self.assertEqual(result["label"], "Hospital zone · automatic")
        states["device_tracker.patient"]["attributes"]["latitude"] = 1
        states["device_tracker.patient"]["attributes"]["longitude"] = 1
        self.assertEqual(location.resolve(state["guidance"], states, 10000)["location"], "home")
        states["device_tracker.patient"]["attributes"]["latitude"] = 2
        self.assertEqual(location.resolve(state["guidance"], states, 10000)["location"], "elsewhere")

    def test_bad_sources_unavailable_missing_and_stale_fixes_are_uncertain(self):
        config = automatic()["guidance"]
        for mutation in ("router", "restored", "accuracy", "stale", "missing", "person", "zone", "coords"):
            states = entities()
            if mutation == "router":
                states["device_tracker.patient"]["attributes"]["source_type"] = "router"
            elif mutation == "restored":
                states["device_tracker.patient"]["attributes"]["restored"] = True
            elif mutation == "accuracy":
                del states["device_tracker.patient"]["attributes"]["gps_accuracy"]
            elif mutation == "stale":
                states["device_tracker.patient"]["reported"] = 9099
            elif mutation == "missing":
                del states["device_tracker.patient"]
            elif mutation == "person":
                states["person.patient"]["state"] = "unavailable"
            elif mutation == "zone":
                del states["zone.home"]
            else:
                states["device_tracker.patient"]["attributes"]["latitude"] = float("nan")
            with self.subTest(mutation=mutation):
                self.assertEqual(location.resolve(config, states, 10000)["location"], "uncertain")

    def test_automatic_hospital_never_implies_admission_or_changes_threshold(self):
        state = automatic()
        resolved = location.resolve(state["guidance"], entities(), 10000)
        view = model.snapshot(state, 10000, resolved)
        self.assertEqual(view["recommendation"]["level"], "contact")
        self.assertIn("Contact your maternity care team", view["recommendation"]["text"])
        self.assertNotIn("Tell your midwife", view["recommendation"]["text"])
        self.assertEqual(view["guidance"]["interval"], 300)
        message = notifications.build_notification(view, "test", "/test")["message"]
        self.assertIn("Hospital zone · automatic", message)
        self.assertNotIn("latitude", message)
        self.assertNotIn("zone.hospital", message)

    def test_manual_override_wins_and_does_not_read_gps(self):
        state = automatic()
        state = model.configure_guidance(state, state["guidance"]["k"], "hospital", 300)
        resolved = location.resolve(state["guidance"], {}, 10000)
        self.assertEqual(resolved["source"], "manual")
        self.assertIn("Tell your midwife", model.snapshot(state, 10000)["recommendation"]["text"])

    def test_validation_requires_complete_distinct_explicit_zones(self):
        state = recorded([])
        for params in (dict(person="", home="zone.home", hospitals=["zone.hospital"]),
                       dict(person="device_tracker.other", home="zone.home", hospitals=["zone.hospital"]),
                       dict(person="person.patient", home="zone.home", hospitals=["zone.home"]),
                       dict(person="person.patient", home="zone.home", hospitals=[]),
                       dict(person="person.patient", home="zone.home", hospitals=["zone.a", "zone.a"])):
            with self.subTest(params=params), self.assertRaises(model.InvalidCommand):
                model.configure_guidance(state, state["guidance"]["k"], "home", 300, mode="automatic", **params)

    def test_schema_three_migrates_manual_choice_and_all_existing_tokens(self):
        state = recorded([9000], location="hospital")
        old = deepcopy(state)
        old["schema"] = 3
        old["guidance"] = {key: old["guidance"][key] for key in ("location", "interval", "k")}
        new = model.load_state(old)
        self.assertEqual(new["schema"], 6)
        for key in ("location", "interval", "k"):
            self.assertEqual(new["guidance"][key], old["guidance"][key])
        self.assertEqual(new["k"], old["k"])
        self.assertEqual(new["records"], old["records"])
        self.assertEqual(new["guidance"]["mode"], "manual")
        bad = deepcopy(old)
        bad["guidance"] = "broken"
        with self.assertRaises(model.InvalidStorage):
            model.load_state(bad)

    def test_configured_zone_list_is_not_aliased_to_the_callers_payload(self):
        state = recorded([])
        zones = ["zone.hospital"]
        configured = model.configure_guidance(state, state["guidance"]["k"], "home", 300,
                                              mode="automatic", person="person.patient",
                                              home="zone.home", hospitals=zones)
        zones.append("zone.other")
        self.assertEqual(configured["guidance"]["hospitals"], ["zone.hospital"])


class LocationRefreshTests(unittest.IsolatedAsyncioTestCase):
    async def test_location_refresh_and_staleness_never_save_or_reset_timer(self):
        state = automatic(recorded([9000, 9300, 9600]))
        state = model.transition(state, "start", state["k"], 9900)
        states, now, sent, saved = entities(), [10000], [], []
        async def save(value):
            saved.append(value)
        async def notify(view):
            sent.append(view)
        tracker = manager.Tracker(state, save, notify, lambda: now[0],
                                  lambda settings, stamp: location.resolve(settings, states, stamp))
        before = deepcopy(tracker._state)
        await tracker.refresh_location()
        self.assertEqual(sent[-1]["location"]["location"], "hospital")
        await tracker.refresh_location()
        self.assertEqual(len(sent), 1)
        now[0] += 901
        await tracker.tick()
        self.assertEqual(sent[-1]["location"]["location"], "uncertain")
        self.assertEqual(saved, [])
        self.assertEqual(tracker._state, before)
        self.assertEqual(tracker.location_references(), {"person.patient", "zone.home", "zone.hospital"})
