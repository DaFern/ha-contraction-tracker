import asyncio
import unittest
from copy import deepcopy

from tests.support import manager, model


class ManagerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.saved = []
        self.pushed = []
        self.now = 1000
        async def save(data):
            self.saved.append(data)
        async def notify(view):
            self.pushed.append(view)
        async def readback():
            return deepcopy(self.saved[-1])
        self.tracker = manager.Tracker(None, save, notify, lambda: self.now, readback=readback)
        await self.tracker.command("show")

    async def test_durable_commit_precedes_publication_and_notification(self):
        observed = []
        self.tracker.subscribe(lambda: observed.append(len(self.saved)))
        await self.tracker.command("start", self.tracker.view()["k"])
        self.assertTrue(all(count == 2 for count in observed))
        self.assertEqual(self.pushed[-1]["p"], "active")

    async def test_save_failure_never_promotes_candidate_to_current_state(self):
        before = self.tracker.view()
        async def fail(data):
            raise OSError("synthetic disk failure")
        self.tracker._save = fail
        with self.assertRaises(manager.PersistenceError):
            await self.tracker.command("start", before["k"])
        self.assertEqual(self.tracker.view()["p"], "rest")
        self.assertEqual(self.tracker.view()["k"], before["k"])
        self.assertTrue(self.tracker.view()["persistence_failed"])

    async def test_notification_failure_preserves_saved_transition(self):
        async def fail(view):
            raise RuntimeError("synthetic delivery failure")
        self.tracker._notify = fail
        await self.tracker.command("start", self.tracker.view()["k"])
        self.assertEqual(self.tracker.view()["p"], "active")
        self.assertEqual(self.saved[-1]["p"], "active")
        self.assertTrue(self.tracker.view()["notification_failed"])

    async def test_duplicate_concurrent_start_is_applied_once(self):
        token = self.tracker.view()["k"]
        results = await asyncio.gather(self.tracker.command("start", token),
                                       self.tracker.command("start", token), return_exceptions=True)
        self.assertEqual(sum(isinstance(result, model.InvalidCommand) for result in results), 1)
        self.assertEqual(self.tracker.view()["n"], 1)

    async def test_queued_stop_uses_receipt_time_not_push_completion_time(self):
        entered, release = asyncio.Event(), asyncio.Event()
        async def notify(view):
            if view["p"] == "active":
                entered.set()
                await release.wait()
        self.tracker._notify = notify
        start = asyncio.create_task(self.tracker.command("start", self.tracker.view()["k"]))
        await entered.wait()
        self.now = 1005
        stop = asyncio.create_task(self.tracker.command("stop", self.tracker.view()["k"]))
        await asyncio.sleep(0)
        self.now = 5000
        release.set()
        await asyncio.gather(start, stop)
        self.assertEqual(self.tracker.view()["d"], 5)

    async def test_phone_event_receipt_timestamp_can_be_preserved(self):
        await self.tracker.command("start", self.tracker.view()["k"], received=1000)
        self.now = 2000
        await self.tracker.command("stop", self.tracker.view()["k"], received=1045)
        self.assertEqual(self.tracker.view()["d"], 45)

    async def test_restored_state_is_flagged_until_a_new_durable_transition(self):
        async def noop(value):
            pass
        disk = [deepcopy(self.saved[-1])]
        async def save(value):
            disk[0] = deepcopy(value)
        async def readback():
            return deepcopy(disk[0])
        restored = manager.Tracker(disk[0], save, noop, lambda: 1200, readback=readback)
        self.assertTrue(restored.view()["restored"])
        await restored.command("notify")
        self.assertTrue(restored.view()["restored"])
        await restored.command("start", restored.view()["k"])
        self.assertFalse(restored.view()["restored"])

    async def test_history_returns_copies_with_explicit_bounded_limit(self):
        await self.tracker.command("start", self.tracker.view()["k"])
        self.now = 1045
        await self.tracker.command("stop", self.tracker.view()["k"])
        history = self.tracker.history()
        history[0]["duration"] = 999
        self.assertEqual(self.tracker.history()[0]["duration"], 45)
        for limit in (0, 501, True, 1.5):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                self.tracker.history(limit)

    async def test_listener_failure_does_not_undo_a_commit(self):
        def fail():
            raise RuntimeError("synthetic UI failure")
        self.tracker.subscribe(fail)
        await self.tracker.command("start", self.tracker.view()["k"])
        self.assertEqual(self.tracker.view()["p"], "active")

    async def test_shutdown_clears_notification_but_retains_stored_state(self):
        before = self.tracker.view()
        await self.tracker.shutdown()
        self.assertEqual(self.pushed[-1]["p"], "off")
        self.assertEqual(self.tracker.view()["p"], before["p"])
        with self.assertRaises(model.InvalidCommand):
            await self.tracker.command("show")

    async def test_trackers_do_not_share_records_or_revision_tokens(self):
        async def noop(value):
            pass
        other = manager.Tracker(None, noop, noop, lambda: 1000)
        self.assertNotEqual(self.tracker.view()["k"], other.view()["k"])
        await self.tracker.command("start", self.tracker.view()["k"])
        self.assertEqual(other.view()["n"], 0)
