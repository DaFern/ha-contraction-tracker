// Native integration plus an explicitly configured prototype adapter.
// No household identifiers or credentials are embedded in this module.
export function parseLegacy(items) {
  const rows = [];
  for (const item of items) {
    const text = item.description || "";
    const stamp = (label) => {
      const match = text.match(new RegExp(`${label}: ([0-9-]+) ([0-9:]+) (GMT|BST)`));
      return match ? Date.parse(`${match[1]}T${match[2]}${match[3] === "BST" ? "+01:00" : "Z"}`) / 1000 : NaN;
    };
    const start = stamp("Start"), end = stamp("End");
    const number = Number(item.summary?.match(/Contraction #(\d+)/)?.[1]);
    if (!Number.isFinite(start) || !Number.isFinite(end) || !number) continue;
    let meta = {};
    try { meta = JSON.parse(text.split("\nCT_META:")[1] || "{}"); } catch { /* Preserve text for CAS. */ }
    rows.push({ id: item.uid, start, end, number, duration: end - start,
      intensity: text.match(/Intensity: (Mild|Moderate|Strong|Not rated)\./)?.[1] || "Not rated",
      revision: text, audit: meta.audit || [], original: meta.original,
      session_id: meta.session_id || "", summary: item.summary });
  }
  rows.sort((a, b) => a.start - b.start);
  let session = "";
  rows.forEach((row, index) => {
    const previous = rows[index - 1];
    if (!previous || row.number !== previous.number + 1 || row.number === 1) session = row.id;
    row.session_id = row.session_id || session;
    const same = previous && previous.session_id === row.session_id;
    row.interval = same ? row.start - previous.start : 0;
    row.rest = same ? row.start - previous.end : 0;
  });
  return rows;
}

export function hourly(records, current, now = Date.now() / 1000) {
  const cutoff = now - 3600;
  const hour = records.filter((row) => row.start >= cutoff && row.start <= now);
  const active = current?.p === "active" && current.s >= cutoff && current.s <= now;
  const intervals = hour.filter((row) => row.interval > 0 && row.start - row.interval >= cutoff).map((row) => row.interval);
  if (active && current.i > 0 && current.s - current.i >= cutoff) intervals.push(current.i);
  const mean = (values) => values.length ? Math.round(values.reduce((a, b) => a + b, 0) / values.length) : null;
  return { count: hour.length + Number(Boolean(active)), duration: mean(hour.map((row) => row.duration)),
    interval: mean(intervals), completed: hour.length };
}

export function localDateTime(stamp) {
  const date = new Date(stamp * 1000);
  const pad = (value) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
}

export async function loadRecords(hass, config, entity) {
  if (config.legacy) {
    const result = await hass.callWS({ type: "call_service", domain: "todo", service: "get_items",
      target: { entity_id: config.legacy.records_entity }, return_response: true });
    const items = result.response?.[config.legacy.records_entity]?.items;
    if (!Array.isArray(items)) throw new Error("Missing records response");
    return parseLegacy(items);
  }
  const result = await hass.callWS({ type: "contraction_tracker/history",
    entry_id: entity.attributes.entry_id, limit: 500 });
  if (!Array.isArray(result.items)) throw new Error("Missing records response");
  return result.items;
}

export async function sendCommand(hass, config, entity, command, token) {
  if (config.legacy) {
    const service = config.legacy.control_service;
    if (!/^script\.[a-z0-9_]+$/.test(service)) throw new Error("Invalid adapter service");
    return hass.callService("script", service.slice(7), { command, token });
  }
  return hass.callService("contraction_tracker", "command", {
    entry_id: entity.attributes.entry_id, command, token });
}

export async function saveCorrection(hass, config, entity, draft, waitResult) {
  const data = { record_id: draft.id, revision: draft.revision, start: draft.start,
    end: draft.end, intensity: draft.intensity };
  if (config.legacy) {
    const service = config.legacy.edit_service;
    if (!/^script\.[a-z0-9_]+$/.test(service)) throw new Error("Invalid adapter service");
    const request = crypto.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}`;
    const confirmation = waitResult(request);
    try {
      await hass.callService("script", service.slice(7), { ...data, request_id: request });
      return await confirmation;
    } catch (error) {
      // Attach a rejection handler even if the service failed before confirmation.
      confirmation.catch(() => {});
      throw error;
    }
  }
  return hass.callWS({ type: "call_service", domain: "contraction_tracker", service: "edit",
    service_data: { ...data, entry_id: entity.attributes.entry_id }, return_response: true });
}

export async function saveGuidance(hass, config, entity, settings, waitResult) {
  if (!config.legacy) return hass.callWS({ type: "call_service", domain: "contraction_tracker",
    service: "configure_guidance", service_data: { ...settings, entry_id: entity.attributes.entry_id },
    return_response: true });
  const service = config.legacy.guidance_service;
  if (!/^script\.[a-z0-9_]+$/.test(service)) throw new Error("Invalid settings adapter service");
  const request = crypto.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  const confirmation = waitResult(request);
  try {
    await hass.callService("script", service.slice(7), { ...settings, request_id: request });
    return await confirmation;
  } catch (error) {
    confirmation.catch(() => {});
    throw error;
  }
}
