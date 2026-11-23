import assert from "node:assert/strict";
import { test } from "node:test";
import { average, duration, escapeHTML, findEntity, homePath, readCurrent, recentRows, trends }
  from "../../custom_components/contraction_tracker/frontend/state.js";

const registry = new Map();
globalThis.window = { customCards: [] };
globalThis.customElements = {
  get: (name) => registry.get(name), define: (name, value) => registry.set(name, value),
};
globalThis.HTMLElement = class {
  attachShadow() {
    this.shadowRoot = { innerHTML: "", activeElement: null, addEventListener() {},
      querySelector() { return null; } };
  }
};
const { ContractionTrackerAppCard } =
  await import("../../custom_components/contraction_tracker/frontend/tracker.js");
const state = { p: "rest", s: 1000, e: 1045, n: 1, d: 45, i: 0, r: 0,
  v: "Mild", k: "revision-a", recent: [] };
const entity = (current = state, entry = "entry-a") => ({
  entity_id: `sensor.${entry}_session`, state: current.p,
  attributes: { contraction_tracker: true, entry_id: entry, current,
    home_path: "/lovelace/0", notifications_enabled: true },
});
const hass = (current = state, connected = true, calls = []) => ({
  states: { "sensor.entry-a_session": entity(current) }, connection: { connected },
  callService: async (...args) => { calls.push(args); },
});
const card = (current = state, connected = true, calls = []) => {
  const result = new ContractionTrackerAppCard();
  result.setConfig({ entry_id: "entry-a" });
  result.hass = hass(current, connected, calls);
  return result;
};

test("formats zero, minutes, hours and invalid values", () => {
  assert.equal(duration(0), "00:00");
  assert.equal(duration(85), "01:25");
  assert.equal(duration(3670), "1:01:10");
  assert.equal(duration(null), "—");
  assert.equal(duration(-1), "—");
  assert.equal(average([]), null);
});
test("selects only the explicit tracker and refuses ambiguous discovery", () => {
  const value = hass();
  value.states["sensor.entry-b_session"] = entity(state, "entry-b");
  assert.equal(findEntity(value, {}), null);
  assert.equal(findEntity(value, { entry_id: "entry-a" }).attributes.entry_id, "entry-a");
  assert.equal(findEntity(value, { entity: "sensor.entry-a_session", entry_id: "entry-b" }), null);
});
test("rejects missing and malformed session attributes", () => {
  assert.equal(readCurrent(null), null);
  assert.equal(readCurrent(entity({ ...state, s: -1 })), null);
  assert.equal(readCurrent(entity({ ...state, p: "unknown" })), null);
});
test("home navigation cannot leave this Home Assistant origin", () => {
  for (const path of ["https://example.org", "//example.org", "/\\example.org", "javascript:bad()"]) {
    assert.equal(homePath(path), "/lovelace/0");
  }
  assert.equal(homePath("/dashboard-home/main"), "/dashboard-home/main");
});
test("recent samples reject stale, future and invalid rows", () => {
  assert.equal(recentRows([[1000, 45, 0, 1], [9000, 45, 0, 1],
    [1000, 45, 0, 99], [1, 1, 0, 1]], 4000).length, 1);
});
test("descriptive patterns do not assign a medical stage", () => {
  const rows = Array.from({ length: 6 }, (_, i) =>
    [1000 + i * 200, i < 3 ? 30 : 60, i < 3 ? 300 : 180, i < 3 ? 1 : 3]);
  const result = trends(rows).join(" ");
  assert.match(result, /closer together/);
  assert.match(result, /longer/);
  assert.match(result, /higher/);
  assert.doesNotMatch(result, /transition|dilated|active labour/i);
});
test("compact main controls and initially collapsed accordions render", () => {
  const html = card().shadowRoot.innerHTML;
  assert.match(html, /Start contraction/);
  assert.equal((html.match(/<details data-section=/g) || []).length, 5);
  assert.doesNotMatch(html, /data-section="history" open/);
});
test("active and rating phases have the correct controls", () => {
  assert.match(card({ ...state, p: "active" }).shadowRoot.innerHTML, /data-command="stop"/);
  const html = card({ ...state, p: "rate" }).shadowRoot.innerHTML;
  for (const rating of ["Mild", "Moderate", "Strong"]) assert.match(html, new RegExp(`data-command="${rating}"`));
  assert.doesNotMatch(html, /data-command="start"/);
});
test("offline and card-editor preview cannot issue commands", async () => {
  const calls = [];
  await card(state, false, calls)._send("start");
  const preview = card(state, true, calls);
  preview.preview = true;
  await preview._send("start");
  assert.equal(calls.length, 0);
});
test("double taps submit once and require observed state confirmation", async () => {
  const calls = [], view = card(state, true, calls);
  await view._send("start");
  await view._send("start");
  assert.equal(calls.length, 1);
  assert.deepEqual(calls[0], ["contraction_tracker", "command", {
    entry_id: "entry-a", command: "start", token: "revision-a" }]);
  assert.ok(view._pending);
  view.hass = hass({ ...state, p: "active", k: "revision-b" });
  assert.equal(view._pending, null);
  assert.equal(view._error, "");
});
test("unexpected parallel changes are not claimed as success", async () => {
  const view = card();
  await view._send("start");
  view.hass = hass({ ...state, p: "off", k: "revision-b" });
  assert.match(view._error, /changed elsewhere/);
});
test("wrong-phase controls are ignored before any API call", async () => {
  const calls = [], view = card(state, true, calls);
  await view._send("stop");
  await view._send("Strong");
  assert.equal(calls.length, 0);
});
test("API failures are explicit and not automatically retried", async () => {
  const view = card();
  let calls = 0;
  view._hass.callService = async () => { calls++; throw new Error("synthetic failure"); };
  await view._send("start");
  assert.equal(calls, 1);
  assert.equal(view._pending, null);
  assert.match(view._error, /could not be confirmed/);
});
test("notification refresh does not create a new contraction", async () => {
  const calls = [], view = card(state, true, calls);
  await view._send("notify");
  assert.equal(calls[0][2].command, "notify");
  assert.equal(view._current().n, 1);
  assert.equal(view._pending, null);
});
test("read-only history is scoped and text is safely escaped", async () => {
  const view = card(), requests = [];
  view._hass.callWS = async (request) => {
    requests.push(request);
    return { items: [{ start: 1000, end: 1045, duration: 45, interval: 0, rest: 0,
      intensity: '<img src=x onerror="bad()">' }] };
  };
  view._open.add("history");
  await view._loadHistory();
  assert.deepEqual(requests[0], { type: "contraction_tracker/history", entry_id: "entry-a", limit: 500 });
  assert.match(view.shadowRoot.innerHTML, /&lt;img/);
  assert.doesNotMatch(view.shadowRoot.innerHTML, /<img src=x/);
  assert.match(view.shadowRoot.innerHTML, /data-section="history" open/);
  assert.equal(escapeHTML('<"&\'>'), "&lt;&quot;&amp;&#39;&gt;");
});
test("reconfiguring a card cannot show another tracker's cached or in-flight history", async () => {
  const view = card();
  let resolve;
  view._hass.callWS = () => new Promise((done) => { resolve = done; });
  const loading = view._loadHistory();
  view.setConfig({ entry_id: "entry-b" });
  view.hass = { ...hass(), states: { "sensor.entry-b_session": entity(state, "entry-b") } };
  resolve({ items: [{ start: 1000, end: 1045, duration: 45, interval: 0, rest: 0, intensity: "Mild" }] });
  await loading;
  assert.deepEqual(view._records, []);
  assert.equal(view._historyLoaded, false);
  assert.equal(view._entity().attributes.entry_id, "entry-b");
});
test("restart and delivery failures are visible, not silently hidden", () => {
  assert.match(card({ ...state, restored: true }).shadowRoot.innerHTML, /Restored after/);
  assert.match(card({ ...state, notification_failed: true }).shadowRoot.innerHTML, /delivery failed/);
  assert.match(card({ ...state, persistence_failed: true }).shadowRoot.innerHTML, /save was not confirmed/);
});
test("disconnect clears ticking and confirmation state", () => {
  const view = card();
  view.connectedCallback();
  assert.ok(view._clock);
  view.disconnectedCallback();
  assert.equal(view._pending, null);
});

test("location/contact settings are manual, scoped and independent of timer controls", async () => {
  const current = { ...state, guidance: { location: "unspecified", interval: 300, k: "settings-a" } };
  const view = card(current), requests = [];
  assert.match(view.shadowRoot.innerHTML, /Contact prompts &amp; location|Contact prompts & location/);
  assert.match(view.shadowRoot.innerHTML, /value="unspecified" selected/);
  assert.match(view.shadowRoot.innerHTML, /Manual override wins/);
  view._guidanceDraft = { location: "hospital", interval: 240, k: "settings-a" };
  view._hass.callWS = async (request) => { requests.push(request); return { response: {} }; };
  await view._saveGuidance();
  assert.deepEqual(requests, [{ type: "call_service", domain: "contraction_tracker",
    service: "configure_guidance", service_data: {
      entry_id: "entry-a", token: "settings-a", location: "hospital", interval: 240,
      mode: "manual", person: "", home: "", hospitals: [],
    }, return_response: true }]);
  assert.equal(view._current().k, "revision-a");
  assert.equal(view._guidanceStatus, "Settings saved.");
});
test("settings refuse invalid intervals and cannot save offline or in preview", async () => {
  const current = { ...state, guidance: { location: "home", interval: 300, k: "settings-a" } };
  const view = card(current);
  let calls = 0;
  view._hass.callWS = async () => { calls++; };
  view._guidanceDraft = { location: "home", interval: 301, k: "settings-a" };
  await view._saveGuidance();
  assert.equal(calls, 0);
  view._guidanceDraft.interval = 300;
  view.preview = true;
  await view._saveGuidance();
  view.preview = false;
  view._hass.connection.connected = false;
  await view._saveGuidance();
  assert.equal(calls, 0);
});
test("settings failure is not silently retried or reported as saved", async () => {
  const view = card({ ...state, guidance: { location: "home", interval: 300, k: "settings-a" } });
  let calls = 0;
  view._hass.callWS = async () => { calls++; throw new Error("synthetic stale settings"); };
  await view._saveGuidance();
  assert.equal(calls, 1);
  assert.match(view._guidanceStatus, /Reopen settings/);
  assert.doesNotMatch(view._guidanceStatus, /Settings saved/);
  assert.equal(view._guidanceBusy, false);
});

test("automatic mode requires explicit person and distinct home/hospital selections", async () => {
  const view = card({ ...state, guidance: { location: "hospital", interval: 300, k: "settings-a",
    mode: "automatic", person: "", home: "", hospitals: [] } });
  let calls = 0;
  view._hass.callWS = async () => { calls++; return { response: {} }; };
  assert.match(view.shadowRoot.innerHTML, /Person being tracked \(not their partner\)/);
  assert.match(view.shadowRoot.innerHTML, /Location uncertain · automatic/);
  assert.match(view.shadowRoot.innerHTML, /Hospital presence does not mean admission/);
  await view._saveGuidance();
  assert.equal(calls, 0);
  view._guidanceDraft = { ...view._current().guidance, person: "person.patient",
    home: "zone.home", hospitals: ["zone.home"] };
  await view._saveGuidance();
  assert.equal(calls, 0);
  view._guidanceDraft.hospitals = ["zone.hospital"];
  await view._saveGuidance();
  assert.equal(calls, 1);
});
test("zone multi-select and mode changes retain an independent settings draft", () => {
  const view = card({ ...state, guidance: { location: "home", interval: 300, k: "settings-a",
    mode: "manual", person: "", home: "", hospitals: [] } });
  view._updateGuidance({ type: "change", target: { dataset: { guidance: "mode" }, value: "automatic" } });
  view._updateGuidance({ type: "change", target: { dataset: { guidance: "hospitals" },
    selectedOptions: [{ value: "zone.a" }, { value: "zone.b" }] } });
  assert.deepEqual(view._guidanceDraft.hospitals, ["zone.a", "zone.b"]);
  assert.equal(view._guidanceDraft.k, "settings-a");
  assert.equal(view._current().k, "revision-a");
  assert.equal(view._current().guidance.mode, "manual");
});

test("unverified imports display a warning and cannot issue timer/settings commands", async () => {
  const calls = [], view = card({ ...state, import_uncertain: true }, true, calls);
  assert.match(view.shadowRoot.innerHTML, /Import could not be verified/);
  await view._send("start");
  await view._saveGuidance();
  assert.equal(calls.length, 0);
});
test("unverified ordinary saves block every control and hide cached editable history", async () => {
  const calls = [], view = card({ ...state, persistence_uncertain: true }, true, calls);
  view._records = [{ id: "cached", start: 1000, end: 1045, revision: "old" }];
  view._historyLoaded = true;
  view._render();
  assert.match(view.shadowRoot.innerHTML, /Save could not be verified/);
  assert.match(view.shadowRoot.innerHTML, /backup timer/);
  assert.deepEqual(view._records, []);
  assert.equal(view._historyLoaded, false);
  for (const command of ["start", "stop", "movement", "end", "notify", "reminders_on"]) {
    await view._send(command);
  }
  await view._saveGuidance();
  view._openEditor("cached");
  assert.equal(view._editor, null);
  let reads = 0;
  view._hass.callWS = async () => { reads++; return { items: [] }; };
  await view._loadHistory();
  assert.equal(reads, 0);
  assert.equal(calls.length, 0);
});
test("history arriving after a save becomes uncertain cannot repopulate the cache", async () => {
  const view = card();
  let resolve;
  view._hass.callWS = () => new Promise((done) => { resolve = done; });
  const pending = view._loadHistory();
  view.hass = { ...view._hass, ...hass({ ...state, persistence_uncertain: true }) };
  resolve({ items: [{ id: "stale", start: 1000, end: 1045 }] });
  await pending;
  assert.deepEqual(view._records, []);
  assert.equal(view._historyLoaded, false);
});
test("imported original notes are shown as escaped text, not executable markup", async () => {
  const view = card();
  view._hass.callWS = async () => ({ items: [{ id: "original-id", start: 1000, end: 1045,
    duration: 45, interval: 0, rest: 0, intensity: "Mild", revision: "rev",
    legacy: { item: { uid: "original-id", summary: "Original summary",
      description: '<img src=x onerror="bad()"> Original notes' } } }] });
  await view._loadHistory();
  const html = view.shadowRoot.innerHTML;
  assert.match(html, /Imported source record/);
  assert.match(html, /Original ID: original-id/);
  assert.match(html, /&lt;img/);
  assert.doesNotMatch(html, /<img src=x/);
});
