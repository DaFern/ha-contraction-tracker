import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import importlib
import json
import unittest
from unittest.mock import patch

from tests.support import model, manager

legacy = importlib.import_module(f"{model.__package__}.legacy")


def item(uid, number, start, end, previous=None, intensity="Moderate", status="needs_action"):
    stamp = lambda value: datetime.fromtimestamp(value, timezone.utc).strftime("%Y-%m-%d %H:%M:%S GMT")
    clock = lambda value: f"{value // 60}m {value % 60}s."
    gap = "First contraction of this session." if previous is None else clock(start - previous[0])
    rest = "Not available for the first contraction." if previous is None else clock(start - previous[1])
    return {"uid": uid, "summary": f"Example | {end-start}s | Contraction #{number}", "status": status,
            "description": f"Start: {stamp(start)}\nEnd: {stamp(end)}\nDuration: {clock(end-start)}\n"
                           f"Intensity: {intensity}.\nStart-to-start interval: {gap}\n"
                           f"Rest before this contraction: {rest}\nOriginal notes retained."}


def bundle(count=3):
    rows, previous = [], None
    for index in range(count):
        start, end = 1000 + index * 300, 1045 + index * 300
        rows.append(item(f"source-{index+1}", index+1, start, end, previous))
        previous = (start, end)
    return {
        "entities": {"records": "todo.source_records", "state": "input_text.source_state",
                     "movement": "input_text.source_movement", "guidance": "input_text.source_guidance",
                     "automation": "automation.source_tracker"},
        "items": rows,
        "state": {"p": "rest", "s": previous[0] if previous else 0, "e": previous[1] if previous else 0,
                  "d": 45 if rows else 0, "i": 300 if count > 1 else 0,
                  "r": 255 if count > 1 else 0, "n": count, "v": "Moderate" if rows else "Not rated",
                  "k": "old-revision", **({"u": rows[-1]["uid"]} if rows else {})},
        "movement": {"last": 1500, "count": 1, "enabled": False,
                     "enabled_at": 0, "last_alert": 0, "k": "old-movement-revision"},
        "guidance": {"location": "hospital", "interval": 300, "k": "old-guidance-revision"},
    }


class LegacyConversionTests(unittest.TestCase):
    def test_all_fifteen_rows_ids_text_and_current_rest_state_are_preserved(self):
        source = bundle(15)
        before = deepcopy(source)
        result = legacy.convert(source, 10000)
        self.assertEqual(len(result["records"]), 15)
        for original, row in zip(source["items"], result["records"]):
            self.assertEqual(row["id"], original["uid"])
            self.assertEqual(row["legacy"]["item"], original)
        self.assertEqual({k: result[k] for k in ("p", "s", "e", "d", "n", "i", "r", "v")},
                         {k: source["state"][k] for k in ("p", "s", "e", "d", "n", "i", "r", "v")})
        self.assertEqual(result["movement"]["last"], source["movement"]["last"])
        self.assertEqual(result["movement"]["count"], 1)
        self.assertFalse(result["movement"]["enabled"])
        self.assertEqual(result["guidance"]["location"], "hospital")
        self.assertEqual(result["guidance"]["mode"], "manual")
        self.assertEqual(result["migration"]["sessions"], 1)
        self.assertNotEqual(result["k"], source["state"]["k"])
        self.assertNotIn("migration", model.snapshot(result, 10000))
        self.assertEqual(model.snapshot(result, 10000)["import_receipt"]["records"], 15)
        self.assertNotIn("old-revision", json.dumps(model.snapshot(result, 10000)))
        self.assertEqual(source, before)
        model.load_state(result)

    def test_source_order_does_not_change_hash_sessions_or_record_order(self):
        source = bundle()
        result = legacy.convert(source, 10000)
        source["items"].reverse()
        other = legacy.convert(source, 10000)
        self.assertEqual(result["migration"]["source_sha256"], other["migration"]["source_sha256"])
        self.assertEqual([r["id"] for r in result["records"]], [r["id"] for r in other["records"]])
        self.assertEqual(result["session_id"], other["session_id"])

    def test_session_resets_are_preserved_without_false_intervals(self):
        source = bundle(2)
        source["items"].append(item("second-session", 1, 1800, 1840, status="completed"))
        source["state"].update(n=1, s=1800, e=1840, d=40, i=0, r=0, u="second-session")
        result = legacy.convert(source, 2000)
        self.assertEqual(result["migration"]["sessions"], 2)
        self.assertNotEqual(result["records"][0]["session_id"], result["records"][-1]["session_id"])
        self.assertEqual(result["records"][-1]["interval"], 0)
        self.assertEqual(result["records"][-1]["legacy"]["item"]["status"], "completed")

    def test_gmt_bst_offsets_disambiguate_repeated_clock_times(self):
        source = bundle(2)
        first = int(datetime(2026, 10, 25, 0, 10, tzinfo=timezone.utc).timestamp())
        second = first + 3600
        source["items"] = [item("bst", 1, first, first+60), item("gmt", 2, second, second+60, (first, first+60))]
        source["items"][0]["description"] = source["items"][0]["description"].replace(
            "00:10:00 GMT", "01:10:00 BST").replace("00:11:00 GMT", "01:11:00 BST")
        source["state"].update(n=2, s=second, e=second+60, d=60, i=3600, r=3540, u="gmt")
        result = legacy.convert(source, second+100)
        self.assertEqual(result["records"][0]["start"], first)
        self.assertEqual(result["records"][1]["interval"], 3600)

    def test_audits_originals_extra_metadata_and_full_source_notes_survive(self):
        source = bundle()
        row = source["items"][-1]
        original = dict(start=1590, end=1635, intensity="Mild", source_text="Full original text")
        audit = [{"at": 1800, "before": {k: original[k] for k in ("start", "end", "intensity")},
                  "after": dict(start=1600, end=1645, intensity="Moderate")}]
        row["description"] += "\nCT_META:" + json.dumps({"original": original, "audit": audit, "custom": "kept"})
        row["extra"] = {"note": "Also kept"}
        result = legacy.convert(source, 2000)
        imported = result["records"][-1]
        self.assertEqual(imported["audit"], audit)
        self.assertEqual(imported["original"]["start"], 1590)
        self.assertEqual(imported["legacy"]["item"], row)
        corrected = model.correct(result, imported["id"], imported["revision"], 1601, 1646, "Strong", 2000)
        self.assertEqual(corrected["records"][-1]["legacy"]["item"], row)
        self.assertEqual(len(corrected["records"][-1]["audit"]), 2)

    def test_active_timer_first_or_later_and_empty_sessions_are_not_restarted(self):
        for count in (0, 3):
            source = bundle(count)
            start = source["state"]["s"] + 300 if count else 1700
            source["state"].update(p="active", s=start, d=0, v="Not rated", n=count+1)
            source["state"].pop("u", None)
            result = legacy.convert(source, 2000)
            self.assertEqual(result["p"], "active")
            self.assertEqual(result["s"], start)
            self.assertEqual(len(result["records"]), count)
        source = bundle(0)
        result = legacy.convert(source, 2000)
        self.assertEqual(result["p"], "rest")
        self.assertEqual(result["n"], 0)
        self.assertTrue(result["session_id"])

    def test_off_state_and_enabled_movement_reminders_preserve_intent(self):
        source = bundle()
        source["state"]["p"] = "off"
        self.assertEqual(legacy.convert(source, 2000)["p"], "off")
        source["state"]["p"] = "rest"
        source["movement"].update(enabled=True, enabled_at=1700, last_alert=1800)
        result = legacy.convert(source, 2000)
        self.assertTrue(result["movement"]["enabled"])
        self.assertEqual(result["movement"]["last_alert"], 1800)
        source["state"]["p"] = "off"
        with self.assertRaises(model.InvalidCommand):
            legacy.convert(source, 2000)

    def test_inconsistent_duplicate_missing_future_or_ambiguous_data_is_not_skipped(self):
        cases = []
        source = bundle(); source["items"][1]["uid"] = source["items"][0]["uid"]; cases.append(source)
        source = bundle(); source["items"].pop(1); cases.append(source)
        source = bundle(); source["items"][0]["description"] = "Unknown format"; cases.append(source)
        source = bundle(); source["items"][0]["description"] += "\nStart: 1970-01-01 00:16:40 GMT"; cases.append(source)
        source = bundle(); source["state"]["d"] = 999; cases.append(source)
        source = bundle(); source["state"]["u"] = "wrong"; cases.append(source)
        source = bundle(); source["state"]["n"] = True; cases.append(source)
        source = bundle(); source["movement"]["count"] = 0; cases.append(source)
        source = bundle(); source["movement"]["last"] = 3000; cases.append(source)
        source = bundle(); source["items"][0]["description"] = source["items"][0]["description"].replace("0m 45s.", "0m 46s."); cases.append(source)
        source = bundle(); source["guidance"]["interval"] = 301; cases.append(source)
        source = bundle(); source["items"][0]["description"] += '\nCT_META:{"audit":[],"audit":[]}'; cases.append(source)
        source = bundle(); source["entities"]["records"] = "sensor.wrong_domain"; cases.append(source)
        for index, source in enumerate(cases):
            with self.subTest(case=index), self.assertRaises(model.InvalidCommand):
                legacy.convert(source, 2000)
        with self.assertRaises(model.InvalidCommand):
            legacy.convert(bundle(), 1500)

    def test_rating_an_imported_pending_record_does_not_rewrite_source_originals(self):
        source = bundle(1)
        source["items"][0]["description"] = source["items"][0]["description"].replace("Intensity: Moderate.", "Intensity: Not rated.")
        source["state"].update(p="rate", v="Not rated")
        imported = legacy.convert(source, 2000)
        rated = model.transition(imported, "Strong", imported["k"], 2000)
        self.assertEqual(rated["records"][0]["original"]["intensity"], "Not rated")
        self.assertEqual(rated["records"][0]["legacy"], imported["records"][0]["legacy"])

    def test_schema_four_migration_adds_empty_provenance_without_changing_history(self):
        source = legacy.convert(bundle(), 2000)
        source["migration"] = None
        old = deepcopy(source); old["schema"] = 4; old.pop("migration")
        for row in old["records"]:
            row.pop("legacy")
        result = model.load_state(old)
        self.assertEqual(result["schema"], 8)
        self.assertIsNone(result["migration"])
        self.assertTrue(all(row["legacy"] is None for row in result["records"]))


class LegacyImportTests(unittest.IsolatedAsyncioTestCase):
    def setup_tracker(self):
        self.disk = None
        self.saves, self.pushes = [], []
        async def save(value):
            self.disk = deepcopy(value); self.saves.append(value)
        async def readback():
            return deepcopy(self.disk)
        async def notify(view):
            self.pushes.append(view)
        return manager.Tracker(None, save, notify, lambda: 10000, readback=readback)

    async def test_preview_is_read_only_and_apply_is_verified_without_notifications(self):
        tracker = self.setup_tracker(); source = bundle()
        before = deepcopy(tracker._state)
        preview = await tracker.import_legacy(source)
        self.assertEqual(preview["status"], "preview")
        self.assertFalse(preview["saved"])
        self.assertEqual(tracker._state, before)
        self.assertEqual(self.saves, [])
        async def fresh():
            return source
        applied = await tracker.import_legacy(source, apply=True, expected_source=preview["source_sha256"],
                                              expected_target=preview["target_sha256"], source_check=fresh)
        self.assertTrue(applied["verified"])
        self.assertEqual(len(self.saves), 1)
        self.assertEqual(self.pushes, [])
        self.assertEqual(tracker.view()["s"], source["state"]["s"])
        self.assertNotIn("migration", tracker.view())
        self.assertEqual(tracker.view()["import_receipt"]["source_sha256"], preview["source_sha256"])
        with self.assertRaises(model.InvalidCommand):
            await tracker.import_legacy(source)
        self.assertEqual(len(self.saves), 1)

    async def test_stale_source_target_or_final_source_check_prevents_all_import_writes(self):
        for variant in ("source", "target", "final_read"):
            tracker = self.setup_tracker(); source = bundle()
            preview = await tracker.import_legacy(source)
            modified = deepcopy(source); modified["items"][0]["description"] += "\nA new note."
            passed = modified if variant == "source" else source
            if variant == "target":
                tracker._state["guidance"]["interval"] = 240
            async def fresh():
                return modified if variant == "final_read" else passed
            with self.subTest(variant=variant), self.assertRaises(model.InvalidCommand):
                await tracker.import_legacy(passed, apply=True, expected_source=preview["source_sha256"],
                                             expected_target=preview["target_sha256"], source_check=fresh)
            self.assertEqual(self.saves, [])

    async def test_existing_target_data_or_active_destination_is_never_overwritten(self):
        tracker = self.setup_tracker()
        await tracker.command("show")
        with self.assertRaises(model.InvalidCommand):
            await tracker.import_legacy(bundle())

    async def test_candidate_size_failure_happens_before_any_save(self):
        tracker = self.setup_tracker()
        real_digest = manager.digest
        def limited(value):
            if value.get("migration") is not None:
                raise model.InvalidCommand("Candidate exceeds its size limit.")
            return real_digest(value)
        with patch.object(manager, "digest", side_effect=limited), self.assertRaises(model.InvalidCommand):
            await tracker.import_legacy(bundle())
        self.assertEqual(self.saves, [])
        self.assertFalse(tracker.import_uncertain)

    async def test_save_readback_failure_or_silent_failed_save_blocks_further_writes(self):
        for variant in ("raise", "silent", "readback", "cancel"):
            tracker = self.setup_tracker(); source = bundle()
            preview = await tracker.import_legacy(source)
            async def fresh():
                return source
            async def fail(value):
                if variant == "cancel":
                    self.disk = value
                    raise asyncio.CancelledError
                raise OSError("synthetic write failure")
            async def no_write(value):
                pass
            async def unreadable():
                raise OSError("synthetic read-back failure")
            if variant in ("raise", "cancel"):
                tracker._save = fail
            elif variant == "silent":
                tracker._save = no_write
            else:
                tracker._readback = unreadable
            expected = asyncio.CancelledError if variant == "cancel" else manager.PersistenceError
            with self.subTest(variant=variant), self.assertRaises(expected):
                await tracker.import_legacy(source, apply=True, expected_source=preview["source_sha256"],
                                             expected_target=preview["target_sha256"], source_check=fresh)
            self.assertTrue(tracker.import_uncertain)
            self.assertEqual(tracker._state["records"], [])
            with self.assertRaises(model.InvalidCommand):
                await tracker.command("show")
            with self.assertRaises(model.InvalidCommand):
                await tracker.configure_guidance(tracker._state["guidance"]["k"], "home", 300)
            self.assertEqual(self.pushes, [])
