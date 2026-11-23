"""Independent fake disk: a writer buffer is deliberately not read-back evidence."""

import asyncio
from copy import deepcopy
import unittest

from tests.support import manager, model
from tests.unit.test_corrections_movement import records


class VerifiedPersistenceTests(unittest.IsolatedAsyncioTestCase):
    def tracker(self, initial=None):
        self.disk = deepcopy(initial)
        self.writes, self.pushes, self.alerts = [], [], []
        self.events = []
        self.now = 2000

        async def save(candidate):
            self.events.append("save")
            self.writes.append(deepcopy(candidate))
            self.disk = deepcopy(candidate)

        async def readback():
            self.events.append("readback")
            return deepcopy(self.disk)

        async def notify(view):
            self.events.append("notify")
            self.pushes.append(deepcopy(view))

        async def warning(view):
            self.alerts.append(deepcopy(view))

        tracker = manager.Tracker(initial, save, notify, lambda: self.now, readback=readback)
        tracker.warning_notify = warning
        tracker.subscribe(lambda: self.events.append("publish"))
        return tracker

    def operation(self, tracker, name):
        state = tracker._state
        if name == "edit":
            row = state["records"][-1]
            return tracker.edit(row["id"], row["revision"], 1605, 1650, "Strong")
        if name == "settings":
            return tracker.configure_guidance(state["guidance"]["k"], "hospital", 240)
        if name == "tick":
            return tracker.tick()
        token = state["movement"]["k"] if name in ("movement", "reminders_on", "reminders_off") else state["k"]
        return tracker.command(name, token)

    def initial(self, name):
        state = records()
        if name == "show":
            return None
        if name == "stop":
            return model.transition(state, "start", state["k"], 1800)
        if name == "Strong":
            return self.pending_rating(state)
        if name in ("reminders_off", "tick"):
            state = model.transition(state, "reminders_on", state["movement"]["k"], 1700)
        return state

    @staticmethod
    def pending_rating(state):
        state = model.transition(state, "start", state["k"], 1800)
        return model.transition(state, "stop", state["k"], 1845)

    async def test_every_mutation_reads_back_before_publishing_success(self):
        for name in ("show", "start", "stop", "Strong", "end", "movement",
                     "reminders_on", "reminders_off", "edit", "settings", "tick"):
            with self.subTest(operation=name):
                tracker = self.tracker(self.initial(name))
                if name == "tick":
                    self.now = 6000
                await self.operation(tracker, name)
                self.assertEqual(len(self.writes), 1)
                self.assertEqual(tracker._state, self.disk)
                saved_at = self.events.index("save")
                self.assertEqual(self.events[saved_at:saved_at + 2], ["save", "readback"])
                self.assertIn("publish", self.events[saved_at + 2:])
                if "notify" in self.events:
                    self.assertGreater(self.events.index("notify"), self.events.index("readback"))
                self.assertFalse(tracker.view()["persistence_uncertain"])

    async def test_all_write_paths_latch_uncertainty_on_every_ambiguous_failure(self):
        for name in ("show", "start", "stop", "Strong", "end", "movement",
                     "reminders_on", "reminders_off", "edit", "settings", "tick"):
            for failure in ("raise", "silent", "different", "read_error", "read_none",
                            "cancel_save", "cancel_read"):
                with self.subTest(operation=name, failure=failure):
                    tracker = self.tracker(self.initial(name))
                    before = deepcopy(tracker._state)
                    if name == "tick":
                        self.now = 6000
                    real_save, real_read = tracker._save, tracker._readback

                    async def save(candidate):
                        if failure == "raise":
                            raise OSError("synthetic write failure")
                        if failure == "silent":
                            return  # Models HA suppressing a WriteError.
                        await real_save(candidate)
                        if failure == "cancel_save":
                            raise asyncio.CancelledError
                        if failure == "different":
                            self.disk["k"] = "different-but-valid-token"

                    async def readback():
                        if failure == "read_error":
                            raise OSError("synthetic read failure")
                        if failure == "read_none":
                            return None
                        if failure == "cancel_read":
                            raise asyncio.CancelledError
                        return await real_read()

                    tracker._save, tracker._readback = save, readback
                    if failure.startswith("cancel"):
                        with self.assertRaises(asyncio.CancelledError):
                            await self.operation(tracker, name)
                    elif name == "tick":
                        await tracker.tick()  # Background callback records failure, not success.
                    else:
                        with self.assertRaises(manager.PersistenceError):
                            await self.operation(tracker, name)
                    self.assertEqual(tracker._state, before)
                    self.assertTrue(tracker.view()["persistence_uncertain"])
                    self.assertTrue(tracker.view()["persistence_failed"])
                    self.assertEqual(self.pushes, [])
                    writes, alerts = len(self.writes), len(self.alerts)
                    for command in ("show", "start", "stop", "end", "movement",
                                    "reminders_on", "reminders_off", "intensity", "notify"):
                        with self.assertRaises(model.InvalidCommand):
                            await tracker.command(command)
                    with self.assertRaises(model.InvalidCommand):
                        await tracker.configure_guidance(before["guidance"]["k"], "home", 300)
                    with self.assertRaises(model.InvalidCommand):
                        await tracker.edit("any", "any", 1, 2, "Mild")
                    with self.assertRaises(model.InvalidCommand):
                        await tracker.import_legacy({})
                    with self.assertRaises(model.InvalidCommand):
                        tracker.history()
                    await tracker.tick()
                    await tracker.refresh_location()
                    self.assertEqual(len(self.writes), writes)
                    self.assertEqual(len(self.alerts), alerts)
                    self.assertEqual(self.pushes, [])

    async def test_pending_readback_never_publishes_or_notifies_candidate(self):
        tracker = self.tracker(records())
        before = deepcopy(tracker._state)
        entered, release = asyncio.Event(), asyncio.Event()
        real_read = tracker._readback

        async def readback():
            entered.set()
            await release.wait()
            return await real_read()

        tracker._readback = readback
        task = asyncio.create_task(tracker.command("start", before["k"]))
        await entered.wait()
        self.assertEqual(tracker._state, before)
        self.assertEqual(self.events, ["save"])
        self.assertEqual(self.pushes, [])
        release.set()
        await task
        self.assertEqual(tracker.view()["p"], "active")

    async def test_queued_action_cannot_write_after_unverified_predecessor(self):
        tracker = self.tracker(records())
        entered, release = asyncio.Event(), asyncio.Event()
        attempts = []

        async def save(candidate):
            attempts.append(candidate)
            entered.set()
            await release.wait()
            # Suppressed write failure: independent disk remains unchanged.

        tracker._save = save
        first = asyncio.create_task(tracker.command("start", tracker.view()["k"]))
        await entered.wait()
        second = asyncio.create_task(tracker.command("movement", tracker.view()["movement"]["k"]))
        release.set()
        outcomes = await asyncio.gather(first, second, return_exceptions=True)
        self.assertIsInstance(outcomes[0], manager.PersistenceError)
        self.assertIsInstance(outcomes[1], model.InvalidCommand)
        self.assertEqual(len(attempts), 1)

    async def test_reload_reads_successful_but_unconfirmed_disk_without_retrying(self):
        tracker = self.tracker(records())
        real_save = tracker._save

        async def save(candidate):
            await real_save(candidate)
            raise OSError("write completed but caller failed")

        tracker._save = save
        with self.assertRaises(manager.PersistenceError):
            await tracker.command("start", tracker.view()["k"])
        saved = deepcopy(self.disk)
        self.assertEqual(saved["p"], "active")
        restored = manager.Tracker(saved, real_save, tracker._notify, lambda: self.now,
                                   readback=tracker._readback)
        self.assertFalse(restored.view()["persistence_uncertain"])
        self.assertTrue(restored.restored)
        await restored.command("notify")
        self.assertEqual(len(self.writes), 1)
        self.assertEqual(restored._state, saved)

    async def test_missing_reader_refuses_write_without_claiming_an_uncertain_write(self):
        tracker = self.tracker(records())
        tracker._readback = None
        with self.assertRaises(manager.PersistenceError):
            await tracker.command("start", tracker.view()["k"])
        self.assertEqual(self.writes, [])
        self.assertFalse(tracker.persistence_uncertain)

    async def test_schema_upgrade_cannot_be_verified_by_normalizing_old_disk_data(self):
        current = records()
        old = deepcopy(current)
        old["schema"] = 4
        old.pop("migration")
        for row in old["records"]:
            row.pop("legacy")

        async def suppressed_save(candidate):
            pass

        async def readback():
            return deepcopy(old)

        self.assertEqual(model.load_state(old), current)
        with self.assertRaises(manager.PersistenceError):
            await manager.verified_save(current, suppressed_save, readback)

    async def test_readback_includes_history_originals_audits_and_settings_not_just_phase(self):
        tracker = self.tracker(records())
        real_save = tracker._save
        async def save(candidate):
            await real_save(candidate)
            self.disk["records"][0]["original"]["intensity"] = "Strong"
        tracker._save = save
        with self.assertRaises(manager.PersistenceError):
            await tracker.command("start", tracker.view()["k"])
        self.assertTrue(tracker.persistence_uncertain)
