import { test } from "node:test";
import assert from "node:assert/strict";
import { hourly, parseLegacy } from "../../custom_components/contraction_tracker/frontend/transport.js";

test("hourly average/count uses every eligible record, never a six-row sample", () => {
  const rows = Array.from({ length: 20 }, (_, i) => ({
    start: 1000 + i * 100, end: 1040 + i * 100, duration: 40 + i,
    interval: i ? 100 : 0, rest: 60, intensity: "Mild",
  }));
  const result = hourly(rows, { p: "rest" }, 3000);
  assert.equal(result.count, 20);
  assert.equal(result.duration, 50);
  assert.equal(result.interval, 100);
});
test("intervals crossing the hour boundary are excluded and active starts count", () => {
  const rows = [{ start: 3500, duration: 45, interval: 500 },
    { start: 3800, duration: 55, interval: 300 }];
  const result = hourly(rows, { p: "active", s: 3950, i: 150 }, 7000);
  assert.equal(result.count, 3);
  assert.equal(result.duration, 50);
  assert.equal(result.interval, 225);
});
test("legacy records parse offsets, corrections and stable to-do IDs", () => {
  const description = "Start: 2026-10-25 01:10:00 GMT\nEnd: 2026-10-25 01:11:00 GMT\nIntensity: Mild.\nCT_META:" +
    JSON.stringify({ audit: [{ at: 10 }], original: { start: 1 } });
  const rows = parseLegacy([{ uid: "stable-id", summary: "Contraction #1", description }]);
  assert.equal(rows[0].id, "stable-id");
  assert.equal(rows[0].duration, 60);
  assert.equal(rows[0].start, Date.parse("2026-10-25T01:10:00Z") / 1000);
  assert.equal(rows[0].audit.length, 1);
  assert.equal(rows[0].revision, description);
});
test("legacy sessions never create a false interval across recording sessions", () => {
  const item = (id, number, minute) => ({ uid: id, summary: `Contraction #${number}`,
    description: `Start: 2026-11-23 10:${minute}:00 GMT\nEnd: 2026-11-23 10:${minute}:45 GMT\nIntensity: Mild.` });
  const rows = parseLegacy([item("a", 1, "00"), item("b", 2, "10"), item("c", 1, "20")]);
  assert.equal(rows[1].interval, 600);
  assert.equal(rows[2].interval, 0);
});
