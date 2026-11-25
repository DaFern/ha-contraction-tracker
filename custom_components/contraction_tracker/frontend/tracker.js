const assetQuery = new URL(import.meta.url).search;
const { average, duration, escapeHTML: esc, findEntity, longContractionWarning, longTimerWarning, ratings,
  readCurrent, recentRows, time, trends } =
  await import(new URL(`./state.js${assetQuery}`, import.meta.url).href);
const { hourly, localDateTime, loadRecords, sendCommand, saveCorrection, saveGuidance } =
  await import(new URL(`./transport.js${assetQuery}`, import.meta.url).href);

const icons = {
  menu: '<path d="M3 6h18M3 12h18M3 18h18"/>',
  notification: '<path d="M15 12V9a5 5 0 0 0-10 0v4l-2 3h9M8 19a2 2 0 0 0 3 0M21 14v4h-4M21 18a4 4 0 1 0-1 3"/>',
  baby: '<circle cx="12" cy="13" r="8"/><path d="M12 5c-3 0-2-4 1-3M8 12h.01M16 12h.01M9 16q3 3 6 0"/>',
  coffee: '<path d="M4 8h12v7a5 5 0 0 1-5 5H9a5 5 0 0 1-5-5V8ZM16 9h2a3 3 0 0 1 0 6h-2M8 3v2M12 3v2M3 22h16"/>',
};
const icon = (name) => `<svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">${icons[name]}</svg>`;
const styleURL = new URL(`./tracker.css${assetQuery}`, import.meta.url).href;
const expectedPhase = { show: "rest", start: "active", stop: "rate", end: "off",
  Mild: "rest", Moderate: "rest", Strong: "rest" };

export class ContractionTrackerAppCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._open = new Set();
    this._recordOpen = new Set();
    this._configRevision = 0;
    this._records = [];
    this._error = "";
    this.shadowRoot.addEventListener("click", (event) => {
      if (event.target.closest?.("[data-menu]")) {
        this.dispatchEvent(new CustomEvent("hass-toggle-menu", {
          bubbles: true, composed: true, detail: {},
        }));
        return;
      }
      const button = event.target.closest?.("[data-command]");
      if (button) this._send(button.dataset.command);
      if (event.target.closest?.("[data-refresh]")) this._loadHistory();
      if (event.target.closest?.("[data-save-guidance]")) this._saveGuidance();
      const edit = event.target.closest?.("[data-edit]");
      if (edit) this._openEditor(edit.dataset.edit);
      if (event.target.closest?.("[data-cancel-edit]") && !this._editBusy) {
        this._editor = null; this._render();
      }
    });
    this.shadowRoot.addEventListener("keydown", (event) => {
      const row = event.target.closest?.("[data-edit]");
      if (row && ["Enter", " "].includes(event.key)) { event.preventDefault(); this._openEditor(row.dataset.edit); }
    });
    this.shadowRoot.addEventListener("input", (event) => {
      if (this._editor && event.target.name) this._editor[event.target.name] = event.target.value;
      this._updateGuidance(event);
    });
    this.shadowRoot.addEventListener("change", (event) => {
      if (this._editor && event.target.name) this._editor[event.target.name] = event.target.value;
      this._updateGuidance(event);
    });
    this.shadowRoot.addEventListener("submit", (event) => { event.preventDefault(); this._saveEditor(); });
    this.shadowRoot.addEventListener("cancel", (event) => {
      if (this._editBusy) event.preventDefault(); else this._editor = null;
    }, true);
    this.shadowRoot.addEventListener("toggle", (event) => {
      const record = event.target.dataset?.record;
      if (record) {
        if (event.target.open) this._recordOpen.add(record); else this._recordOpen.delete(record);
        return;
      }
      const section = event.target.dataset?.section;
      if (!section) return;
      if (event.target.open) this._open.add(section); else this._open.delete(section);
      if (section === "history" && event.target.open && !this._historyLoaded) this._loadHistory();
    }, true);
  }
  setConfig(config) {
    this._configRevision++;
    clearTimeout(this._watchdog);
    this._pending = null;
    this._records = [];
    this._recordOpen.clear();
    this._historyLoaded = false;
    this._historyError = "";
    this._loading = false;
    this._config = { ...config };
    this._editor = null;
    this._guidanceDraft = null;
    this._guidanceStatus = "";
    this._signature = "";
    this._render();
    if (this._open.has("history")) this._loadHistory();
  }
  static getStubConfig(hass) {
    const choices = Object.values(hass.states).filter((s) => s.attributes.contraction_tracker === true);
    return choices.length === 1 ? { entity: choices[0].entity_id } : {};
  }
  getCardSize() { return 10; }
  getGridOptions() { return { columns: 12, rows: "auto" }; }
  connectedCallback() {
    clearInterval(this._clock);
    this._clock = setInterval(() => this._tick(), 1000);
    this._render();
    if (this._hass) this._loadHistory();
  }
  disconnectedCallback() {
    clearInterval(this._clock);
    clearTimeout(this._watchdog);
    this._pending = null;
    if (this._editWait) this._editWait.reject(new Error("Page disconnected; save status is uncertain."));
    clearTimeout(this._editTimer);
    this._editWait = null;
  }
  _entity() {
    if (this._config?.legacy) return this._hass?.states[this._config.legacy.entity] || null;
    return findEntity(this._hass, this._config || {});
  }
  _current() {
    if (!this._config?.legacy) return readCurrent(this._entity());
    try {
      const current = JSON.parse(this._entity()?.state || "null");
      if (!current || !["off", "rest", "active", "rate"].includes(current.p)) return null;
      let movement = {}, recent = [], guidance = {}, location = {};
      try { movement = JSON.parse(this._hass?.states[this._config.legacy.movement_entity]?.state || "{}"); } catch {}
      try { recent = JSON.parse(this._hass?.states[this._config.legacy.recent_entity]?.state || "[]"); } catch {}
      try { guidance = JSON.parse(this._hass?.states[this._config.legacy.guidance_entity]?.state || "{}"); } catch {}
      guidance = { mode: "manual", person: "", home: "", hospitals: [], ...guidance };
      try { location = JSON.parse(this._hass?.states[this._config.legacy.location_entity]?.state || "{}"); } catch {}
      return { ...current, movement, recent, guidance, location };
    } catch { return null; }
  }
  _connected() { return this._hass?.connection?.connected === true; }
  set hass(value) {
    const previous = this._current();
    this._hass = value;
    const current = this._current();
    if (this._editWait && this._config?.legacy) {
      try {
        const result = JSON.parse(value.states[this._config.legacy.result_entity]?.state || "{}");
        if (result.request === this._editWait.request) {
          const waiting = this._editWait;
          this._editWait = null;
          clearTimeout(this._editTimer);
          if (result.ok) waiting.resolve(result); else waiting.reject(new Error(result.error || "Correction rejected."));
        }
      } catch { /* A missing helper is not a successful correction. */ }
    }
    if (this._pending && current &&
      ((["movement", "reminders_on", "reminders_off"].includes(this._pending.command)
        ? current.movement?.k !== this._pending.token : current.k !== this._pending.token)
       || current.p !== this._pending.phase)) {
      const wanted = this._pending.command;
      if (wanted !== "notify") {
        const movementCommand = ["movement", "reminders_on", "reminders_off"].includes(wanted);
        this._error = (movementCommand || current.p === expectedPhase[wanted]) &&
          (!ratings.includes(wanted) || current.v === wanted)
          ? "" : "The tracker changed elsewhere. Check the current state before trying again.";
        this._pending = null;
        clearTimeout(this._watchdog);
      }
    }
    const signature = JSON.stringify([current, this._entity()?.attributes,
      this._config?.legacy && value.states[this._config.legacy.result_entity]?.state, this._connected()]);
    if (signature !== this._signature) {
      this._signature = signature;
      this._render();
      if (this.isConnected && (current?.k !== previous?.k || !this._historyLoaded)) this._loadHistory();
    }
  }
  _tick() {
    const minute = Math.floor(Date.now() / 60000);
    if (this._minute !== minute) {
      this._minute = minute;
      this._render(); // Also expires recent samples without waiting for a new contraction.
      if (this.isConnected && !this.preview) this._loadHistory();
    }
    const c = this._current();
    if (longTimerWarning(c) !== !!this._showLongWarning) {
      this._render(); // Cross the warning threshold without waiting for a server update.
      return;
    }
    const target = this.shadowRoot.querySelector("[data-timer]");
    if (!target || !c) return;
    const anchor = c.p === "active" ? c.s : c.e;
    target.textContent = anchor > 0 && c.p !== "off"
      ? duration(Math.max(0, Date.now() / 1000 - anchor)) : "00:00";
  }
  _saveUncertain() {
    const c = this._current();
    return !!(c?.import_uncertain || c?.persistence_uncertain);
  }
  async _send(command) {
    if (this._pending || this.preview) return;
    const c = this._current(), entity = this._entity();
    if (this._saveUncertain()) {
      this._error = "Save is unverified. Use your backup timer. Reload the integration and inspect saved history and settings before retrying.";
      this._render(); return;
    }
    if (!c || !this._connected()) {
      this._error = "Home Assistant is unavailable. Use your backup timer.";
      this._render(); return;
    }
    const movementCommand = ["movement", "reminders_on", "reminders_off"].includes(command);
    const allowed = { off: ["show", "notify", "movement", "reminders_off"],
      rest: ["start", "end", "notify", "movement", "reminders_on", "reminders_off"],
      active: ["stop", "notify", "movement", "reminders_on", "reminders_off"],
      rate: ["Mild", "Moderate", "Strong", "notify", "movement", "reminders_on", "reminders_off"] };
    if (!allowed[c.p]?.includes(command)) return;
    const token = movementCommand ? c.movement?.k : c.k;
    if (!token) { this._error = "Controls are not ready. Refresh the tracker."; this._render(); return; }
    this._pending = { command, token, phase: c.p };
    const generation = this._configRevision;
    this._error = "";
    this._render();
    this._watchdog = setTimeout(() => {
      if (!this._pending) return;
      this._pending = null;
      this._error = "Could not confirm the action. Check the notification before trying again.";
      this._render();
    }, 8000);
    try {
      await sendCommand(this._hass, this._config, entity, command, token);
      if (generation !== this._configRevision) return;
      if (command === "notify") {
        this._pending = null;
        clearTimeout(this._watchdog);
        this._render();
      }
    } catch {
      if (generation !== this._configRevision) return;
      this._pending = null;
      clearTimeout(this._watchdog);
      this._error = "The action could not be confirmed. Check the current timer; do not assume it was saved.";
      this._render();
    }
  }
  async _loadHistory() {
    const entity = this._entity();
    if (this._loading || !this._connected() || !entity || this._saveUncertain()) return;
    const entry = entity.attributes.entry_id;
    const generation = this._configRevision;
    this._loading = true;
    this._historyError = "";
    this._render();
    try {
      const records = await loadRecords(this._hass, this._config, entity);
      if (generation !== this._configRevision || this._entity()?.attributes.entry_id !== entry || this._saveUncertain()) return;
      this._records = records.slice().sort((a, b) => a.start - b.start);
      this._historyLoaded = true;
    } catch {
      if (generation !== this._configRevision) return;
      this._historyError = "Records could not be loaded. Saved records have not been changed.";
    } finally {
      if (generation === this._configRevision) {
        this._loading = false;
        this._render();
      }
    }
  }
  _section(id, title, badge, body) {
    return `<details data-section="${id}" ${this._open.has(id) ? "open" : ""}>
      <summary>${title}<span class="badge">${badge}</span></summary><div class="body">${body}</div></details>`;
  }
  _openEditor(id) {
    const row = this._records.find((record) => record.id === id);
    if (!row || !this._connected() || this.preview || this._editBusy || this._guidanceBusy || this._saveUncertain()) return;
    this._editor = { id, revision: row.revision, start_text: localDateTime(row.start),
      end_text: localDateTime(row.end), intensity: row.intensity };
    this._editError = "";
    this._render();
  }
  _waitResult(request) {
    return new Promise((resolve, reject) => {
      this._editWait = { request, resolve, reject };
      this._editTimer = setTimeout(() => {
        this._editWait = null;
        reject(new Error("Save could not be confirmed. Reopen the record before trying again."));
      }, 15000);
    });
  }
  async _saveEditor() {
    if (!this._editor || this._editBusy || this._guidanceBusy || !this._connected() || this.preview || this._saveUncertain()) return;
    const draft = { ...this._editor, start: Date.parse(this._editor.start_text) / 1000,
      end: Date.parse(this._editor.end_text) / 1000 };
    if (![draft.start, draft.end].every(Number.isFinite) || draft.start > draft.end || draft.end > Date.now() / 1000) {
      this._editError = "Choose valid start/end times; the end cannot be in the future.";
      this._render(); return;
    }
    this._editBusy = true; this._editError = ""; this._render();
    try {
      await saveCorrection(this._hass, this._config, this._entity(), draft,
        (request) => this._waitResult(request));
      this._editor = null;
      await this._loadHistory();
    } catch (error) {
      this._editError = error.message || "The correction could not be confirmed.";
    } finally {
      clearTimeout(this._editTimer); this._editWait = null;
      this._editBusy = false; this._render();
    }
  }
  _updateGuidance(event) {
    const key = event.target.dataset?.guidance;
    if (!key) return;
    if (!this._guidanceDraft) this._guidanceDraft = {
      mode: "manual", person: "", home: "", hospitals: [], ...this._current()?.guidance };
    this._guidanceDraft[key] = key === "hospitals" ? Array.from(event.target.selectedOptions).map((o) => o.value)
      : key === "interval" ? Number(event.target.value) * 60 : event.target.value;
    this._guidanceStatus = "";
    if (key === "mode" && event.type === "change") this._render();
  }
  async _saveGuidance() {
    if (this._guidanceBusy || this._editBusy || this._editor || !this._connected() || this.preview || this._saveUncertain()) return;
    const draft = { mode: "manual", person: "", home: "", hospitals: [],
      ...(this._guidanceDraft || this._current()?.guidance) };
    if (!draft.k || !["unspecified", "home", "hospital"].includes(draft.location)
        || !Number.isInteger(draft.interval) || draft.interval < 60 || draft.interval > 600 || draft.interval % 60) {
      this._guidanceStatus = "Choose a location and a whole-minute interval from 1 to 10.";
      this._render(); return;
    }
    if (!["manual", "automatic"].includes(draft.mode) || !Array.isArray(draft.hospitals)
        || draft.hospitals.length > 3 || new Set(draft.hospitals).size !== draft.hospitals.length
        || draft.hospitals.includes(draft.home) || (draft.mode === "automatic" &&
          (!/^person\.[a-z0-9_]+$/.test(draft.person) || !/^zone\.[a-z0-9_]+$/.test(draft.home)
            || !draft.hospitals.length || draft.hospitals.some((id) => !/^zone\.[a-z0-9_]+$/.test(id))))) {
      this._guidanceStatus = "Select the tracked person, a home zone and 1–3 different hospital zones.";
      this._render(); return;
    }
    this._guidanceBusy = true; this._guidanceStatus = ""; this._render();
    const generation = this._configRevision;
    try {
      await saveGuidance(this._hass, this._config, this._entity(),
        { token: draft.k, location: draft.location, interval: draft.interval,
          mode: draft.mode, person: draft.person, home: draft.home, hospitals: draft.hospitals },
        (request) => this._waitResult(request));
      if (generation !== this._configRevision) return;
      this._guidanceDraft = null;
      this._guidanceStatus = "Settings saved.";
    } catch (error) {
      if (generation !== this._configRevision) return;
      this._guidanceStatus = `${error.message || "Save could not be confirmed."} Reopen settings before retrying.`;
      this._guidanceDraft = null;
    } finally {
      clearTimeout(this._editTimer); this._editWait = null;
      this._guidanceBusy = false; this._render();
    }
  }
  _render() {
    if (!this._config || !this._hass) return;
    const entity = this._entity(), c = this._current();
    if (this._saveUncertain()) {
      this._records = [];
      this._historyLoaded = false;
      this._editor = null;
    }
    const hourData = this._config.legacy
      ? this._historyLoaded ? hourly(this._records, c) : { count: null, duration: null, interval: null }
      : c?.hourly || { count: null, duration: null, interval: null };
    const rows = this._historyLoaded ? this._records.slice(-6).map((row) =>
      [row.start, row.duration, row.interval, ratings.indexOf(row.intensity)]) : (c?.recent || []).slice(-6);
    const trendRows = recentRows(rows);
    const last = trendRows;
    const avgLength = hourData.duration, avgGap = hourData.interval;
    const offline = !this._connected(), disabled = this._pending || offline || !c || this.preview || this._saveUncertain();
    const attrs = disabled ? "disabled" : "";
    const active = c?.p === "active", rate = c?.p === "rate", off = c?.p === "off";
    this._showLongWarning = longTimerWarning(c);
    const phase = !c ? "Select an available tracker" : active ? "Contraction in progress"
      : rate ? "Contraction recorded" : off ? (c?.idle_ended ? "Recording ended after inactivity" : "Session paused")
        : c.e ? "Rest between contractions" : "Ready when you are";
    const caption = active ? `Contraction ${c.n} · started ${time(c.s)}`
      : rate ? `Lasted ${duration(c.d)} · timer shows rest`
        : c?.e && !off ? "Time since the last contraction ended" : "One contraction at a time";
    const main = rate
      ? `<p class="rate-title">How strong did it feel?</p><div class="rating-row">${ratings.slice(1).map((value) =>
        `<button class="rating" data-command="${value}" ${attrs}>${value}</button>`).join("")}</div>`
      : `<button class="main ${active ? "stop" : ""}" data-command="${off ? "show" : active ? "stop" : "start"}" ${attrs}>${this._pending ? "Waiting for confirmation…" : off ? "Start recording" : active ? "Stop contraction" : "Start contraction"}</button>`;
    const pattern = `<p>Average duration <strong>${duration(avgLength)}</strong> · average start-to-start <strong>${duration(avgGap)}</strong>.</p>
      <ul>${trends(trendRows).map((text) => `<li>${esc(text)}</li>`).join("")}</ul>
      <p class="note">Figures use all eligible starts in the rolling last 60 minutes, not just these six rows. Duration uses completed records; count includes the contraction being timed. Both starts must fall inside the hour for an interval. Descriptive trends are not medical thresholds.</p>`;
    const visible = this._historyLoaded ? this._records.slice(-6).reverse() : [];
    const recent = `<section class="recent-inline"><div class="recent-heading">Latest contractions <span>Tap to correct</span></div>
      <table><thead><tr><th>Start</th><th>Length</th><th>Interval</th><th>Intensity</th></tr></thead><tbody>
      ${Array.from({ length: 6 }, (_, i) => {
        const row = visible[i];
        return row ? `<tr data-edit="${esc(row.id)}" tabindex="0" role="button" aria-label="Edit contraction started ${time(row.start)}"><td>${time(row.start)}</td><td>${duration(row.duration)}</td><td>${row.interval ? duration(row.interval) : "—"}</td><td>${esc(row.intensity)} <span class="edit-mark">✎</span></td></tr>`
          : '<tr class="placeholder"><td>—</td><td>—</td><td>—</td><td>—</td></tr>';
      }).join("")}</tbody></table></section>`;
    const history = `${this._historyError ? `<p>${esc(this._historyError)}</p>` : ""}
      ${this._loading ? '<p class="empty" role="status">Loading saved records…</p>' : ""}
      ${this._records.slice(-50).reverse().map((row) => `<details class="record" data-record="${esc(row.id)}" ${this._recordOpen.has(row.id) ? "open" : ""}><summary>${esc(new Date(row.start * 1000).toLocaleDateString())} ${time(row.start)} · ${duration(row.duration)} · ${esc(row.intensity)}</summary><pre>${esc(`Started: ${time(row.start)}\nEnded: ${time(row.end)}\nDuration: ${duration(row.duration)}\nIntensity: ${row.intensity}\nStart-to-start: ${row.interval ? duration(row.interval) : "First contraction"}\nRest before: ${row.rest ? duration(row.rest) : "First contraction"}`)}</pre><button class="small" data-edit="${esc(row.id)}">Edit entry</button>
      ${row.audit?.length ? `<details><summary>Correction trail (${row.audit.length})</summary><pre>${esc(JSON.stringify({ original: row.original, corrections: row.audit }, null, 2))}</pre></details>` : ""}
      ${row.legacy ? `<details><summary>Imported source record</summary><pre>${esc(`${row.legacy.item.summary}\nOriginal ID: ${row.legacy.item.uid}\n${row.legacy.item.description}`)}</pre></details>` : ""}</details>`).join("")}
      ${this._historyLoaded && !this._records.length ? '<p class="empty">No saved records yet.</p>' : ""}
      <button class="small" data-refresh ${this._loading || offline ? "disabled" : ""}>Refresh records</button>
      <p class="note">Latest 50 records. Corrections retain the original values. Times use this device’s time zone.</p>`;
    const focused = this.shadowRoot.activeElement?.dataset?.command;
    const movement = c?.movement || {};
    const movementUI = `<section class="movement"><button class="small movement-button" data-command="movement" ${attrs} ${!movement.k ? "disabled" : ""}>${icon("baby")} Movement felt</button>
      <span>${movement.last ? `Last logged ${duration(Math.max(0, Date.now() / 1000 - movement.last))} ago` : "No movement logged yet"}</span></section>`;
    const reminderOptIn = movement.preferred ?? movement.enabled;
    const reminderStatus = movement.enabled ? "On" : reminderOptIn ? "Paused" : "Off";
    const reminder = `<p>Optional logging reminder: <strong>${movement.enabled ? "On · 60 minutes without logged movement" : reminderOptIn ? "Paused · resumes when recording starts" : "Off"}</strong>.</p>
      <button class="small" data-command="${reminderOptIn ? "reminders_off" : "reminders_on"}" ${attrs} ${(off || (!this._config.legacy && !entity?.attributes.notifications_enabled)) && !reminderOptIn ? "disabled" : ""}>${reminderOptIn ? "Turn reminder off" : "Enable hourly logging reminder"}</button>
      <p class="note">Only reminds while recording, after an hour without logged movement. Stopping recording pauses reminders; starting again resumes them if enabled. Turning the reminder off keeps it off.</p>
      <p class="note">No movement logged does not mean no movement occurred. If movements reduce, stop or change, tell your midwife immediately—do not wait for this reminder.</p>`;
    const guidance = { mode: "manual", person: "", home: "", hospitals: [],
      ...(this._guidanceDraft || c?.guidance || {}) };
    const locationNames = { unspecified: "Not specified", home: "At home", hospital: "In hospital / birth centre" };
    const settingsDisabled = offline || !c?.guidance?.k || this.preview || this._guidanceBusy || this._editBusy || this._saveUncertain();
    const automatic = guidance.mode === "automatic";
    const choices = (domain, selected, multiple = false) => {
      const ids = new Set(Object.keys(this._hass.states).filter((id) => id.startsWith(`${domain}.`)));
      for (const id of multiple ? selected : [selected]) if (id) ids.add(id);
      return `${multiple ? "" : '<option value="">Choose…</option>'}${[...ids].sort().map((id) =>
        `<option value="${esc(id)}" ${(multiple ? selected.includes(id) : selected === id) ? "selected" : ""}>${esc(this._hass.states[id]?.attributes.friendly_name || id)}</option>`).join("")}`;
    };
    const detectedLabel = c?.location?.label || (c?.guidance?.mode === "automatic"
      ? "Location uncertain · automatic" : `${locationNames[c?.guidance?.location] || "Not specified"} · manual`);
    const guidanceUI = `<div class="guidance-settings">
      <p role="status">Location: ${esc(detectedLabel)}</p>
      <label>Location mode<select data-guidance="mode" ${settingsDisabled ? "disabled" : ""}>
        <option value="manual" ${!automatic ? "selected" : ""}>Manual override</option>
        <option value="automatic" ${automatic ? "selected" : ""}>Automatic · selected zones</option></select></label>
      <label>Manual location<select data-guidance="location" ${settingsDisabled || automatic ? "disabled" : ""}>
      ${Object.entries(locationNames).map(([value, label]) => `<option value="${value}" ${guidance.location === value ? "selected" : ""}>${label}</option>`).join("")}</select></label>
      ${automatic ? `<label>Person being tracked (not their partner)<select data-guidance="person" ${settingsDisabled ? "disabled" : ""}>${choices("person", guidance.person)}</select></label>
      <label>Home zone<select data-guidance="home" ${settingsDisabled ? "disabled" : ""}>${choices("zone", guidance.home)}</select></label>
      <label>Hospital / birth-centre zones (select 1–3)<select data-guidance="hospitals" multiple size="4" ${settingsDisabled ? "disabled" : ""}>${choices("zone", guidance.hospitals, true)}</select></label>
      <p class="note">Create any missing zones in Settings → Areas, labels & zones. GPS must be reported within 15 minutes, accuracy ≤100 m, and fully inside one selected zone. Boundaries, overlaps and missing/unavailable data mean Location uncertain. Elsewhere is neither home nor hospital. Hospital presence does not mean admission. No geocoding or coordinate history is added.</p>` : ""}
      <label>Care-team contact interval (minutes)<input data-guidance="interval" type="number" min="1" max="10" step="1" value="${Number(guidance.interval || 300) / 60}" ${settingsDisabled ? "disabled" : ""}></label>
      <button class="small" data-save-guidance ${settingsDisabled ? "disabled" : ""}>${this._guidanceBusy ? "Saving…" : "Save settings"}</button>
      <p role="status">${esc(this._guidanceStatus || "")}</p>
      <p class="note">Default: 5 minutes, based on NHS contact guidance. Three consecutive recorded gaps at or below your interval trigger a contact prompt—not proof of regular labour. No hour-long wait is required. Only change this interval to match your care team's advice. Zone detection changes wording only; Manual override wins when selected.</p>
      <p class="note">A recent contraction over 2 minutes or 6 starts in 10 minutes takes priority with an urgent contact prompt. Prompts update on tracker actions/refresh, not continuous monitoring. Missing records can hide a pattern. Never wait for a prompt if worried: contact your team for waters breaking, bleeding, reduced/changed movements or suspected labour before 37 weeks. Strong urge to push and baby coming now: call 999.</p>
      <p class="note">Timings cannot assess dilation. Follow your individual care plan. <a href="https://www.nhs.uk/pregnancy/labour-and-birth/signs-that-labour-has-begun/" target="_blank" rel="noopener noreferrer">NHS guidance</a></p>
      </div>`;
    const editor = this._editor ? `<dialog class="editor"><form><h3>Correct contraction</h3>
      <p class="note">Saved times and dependent intervals will be recalculated. The original is retained.</p>
      <label>Started<input type="datetime-local" step="1" name="start_text" value="${esc(this._editor.start_text)}" required></label>
      <label>Ended<input type="datetime-local" step="1" name="end_text" value="${esc(this._editor.end_text)}" required></label>
      <label>Intensity<select name="intensity">${ratings.map((value) => `<option ${value === this._editor.intensity ? "selected" : ""}>${value}</option>`).join("")}</select></label>
      ${this._editError ? `<p class="error" role="alert">${esc(this._editError)}</p>` : ""}
      <div class="edit-actions"><button class="small" type="button" data-cancel-edit ${this._editBusy ? "disabled" : ""}>Cancel</button><button class="small save" type="submit" ${this._editBusy ? "disabled" : ""}>${this._editBusy ? "Saving…" : "Save correction"}</button></div></form></dialog>` : "";
    const warning = c?.import_uncertain ? "Import could not be verified. Reload the integration and inspect saved history before retrying."
      : c?.persistence_uncertain ? "Save could not be verified. Controls are blocked. Use your backup timer; reload the integration and inspect saved history and settings before retrying."
      : c?.persistence_failed ? "A save was not confirmed. Check storage before retrying."
      : c?.restored ? "Restored after Home Assistant restarted. Check timings; actions made offline may be missing."
        : c?.notification_failed ? "Notification delivery failed. Timings remain saved; refresh the phone notification to retry." : "";
    this.shadowRoot.innerHTML = `<link rel="stylesheet" href="${styleURL}">
      <article class="app ${active ? "active" : ""} ${offline ? "offline" : ""}">
      <header><button class="icon" type="button" data-menu aria-label="Open sidebar">${icon("menu")}</button>
      <div class="brand"><span>${icon("baby")}Contractions</span></div>
      <button class="icon" data-command="notify" aria-label="Refresh notification" ${attrs} ${off || (!this._config.legacy && !entity?.attributes.notifications_enabled) ? "disabled" : ""}>${icon("notification")}</button></header>
      ${this._showLongWarning ? `<div class="error timer-warning" role="alert">${esc(longContractionWarning)}</div>` : ""}
      ${this._error || warning ? `<div class="error" role="alert">${esc(this._saveUncertain() ? warning : this._error || warning)}</div>` : ""}
      ${offline ? '<div class="error" role="status">Offline · last known state. Controls are disabled.</div>' : ""}
      <section class="hero"><div class="status"><span class="dot"></span>${phase}</div>
      <div class="timer" data-timer aria-label="${active ? "Contraction duration" : "Rest duration"}">00:00</div>
      <div class="caption">${caption}</div>${main}</section>
      <div class="sync" role="status">${this._pending ? "Confirming with Home Assistant…" : "One shared timer · local records"}</div>
      <div class="metrics-caption">Rolling last 60 minutes</div>
      <section class="metrics"><div class="metric"><strong>${duration(avgLength)}</strong><span>Avg length</span></div>
      <div class="metric"><strong>${duration(avgGap)}</strong><span>Avg interval</span></div>
      <div class="metric"><strong>${hourData.count ?? "—"}</strong><span>Contractions</span></div></section>
      ${recent}
      ${movementUI}
      ${this._section("trends", "Patterns & averages", `${last.length} recent`, pattern)}
      ${this._section("movement", "Movement logging reminder", reminderStatus, reminder)}
      ${this._section("guidance", "Contact prompts & location", c?.guidance?.mode === "automatic" ? "Automatic" : locationNames[c?.guidance?.location] || "Not specified", guidanceUI)}
      ${this._section("history", "Detailed history", "Saved", history)}
      ${this._section("about", "About these timings", "", "<p>Requires Home Assistant and a working connection. Times use when the server receives controls, not the exact phone tap time.</p><p>Contractions alone cannot determine labour stage, dilation or when birth will occur. Follow your maternity team’s advice.</p><p>This is not a medical device. Keep a backup timer.</p>")}
      <footer><div class="footer"><span>${offline ? "Disconnected" : "Connected to Home Assistant"}</span>
      ${c?.p === "rest" ? `<button class="text-button" data-command="end" ${attrs}>Stop recording</button>` : '<span class="text-button">Logging aid only</span>'}</div>
      <section class="support" aria-label="Support development">
        <div class="support-copy"><p>© 2026 Daniel Fern</p>
        <p>If this project helps you, you can support its development.</p></div>
        <a class="support-link" href="https://buymeacoffee.com/Badger182" target="_blank" rel="noopener noreferrer" referrerpolicy="no-referrer">${icon("coffee")}<span>Buy me a coffee</span></a>
      </section></footer></article>${editor}`;
    this._minute = Math.floor(Date.now() / 60000);
    this._tick();
    const dialog = this.shadowRoot.querySelector("dialog");
    if (dialog && !dialog.open) dialog.showModal();
    if (focused) this.shadowRoot.querySelector(`[data-command="${focused}"]`)?.focus({ preventScroll: true });
  }
}

export class ContractionTrackerPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this.shadowRoot.innerHTML = '<style>:host{display:block;height:100%;overflow:auto}.page{max-width:560px;margin:auto;padding:12px 8px max(16px,env(safe-area-inset-bottom))}</style><div class="page"></div>';
    this._card = new ContractionTrackerAppCard();
    this.shadowRoot.querySelector(".page").append(this._card);
  }
  set panel(value) {
    const id = value?.config?.entry_id;
    if (id !== this._entryID) {
      this._entryID = id;
      this._card.setConfig({ entry_id: id });
    }
    if (this._hass) this._card.hass = this._hass;
  }
  set hass(value) { this._hass = value; if (this._entryID) this._card.hass = value; }
}
if (!customElements.get("contraction-tracker-app-card")) {
  customElements.define("contraction-tracker-app-card", ContractionTrackerAppCard);
}
if (!customElements.get("contraction-tracker-panel")) {
  customElements.define("contraction-tracker-panel", ContractionTrackerPanel);
}
window.customCards = window.customCards || [];
if (!window.customCards.some((item) => item.type === "contraction-tracker-app-card")) {
  window.customCards.push({ type: "contraction-tracker-app-card", name: "Contraction Tracker",
    description: "Local shared timer with actionable Android notifications and saved history." });
}
