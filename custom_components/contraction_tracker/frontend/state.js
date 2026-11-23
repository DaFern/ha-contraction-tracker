// Pure presentation helpers. No network, storage or household-specific settings.
export const escapeHTML = (value) => String(value ?? "").replace(/[&<>"']/g,
  (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]));
export const ratings = ["Not rated", "Mild", "Moderate", "Strong"];
export const average = (values) => values.length
  ? Math.round(values.reduce((sum, value) => sum + value, 0) / values.length) : null;

export function duration(value) {
  if (!Number.isFinite(value) || value < 0) return "—";
  const seconds = Math.floor(value), minutes = Math.floor(seconds / 60);
  return minutes >= 60
    ? `${Math.floor(minutes / 60)}:${String(minutes % 60).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`
    : `${String(minutes).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
}
export const time = (stamp) => stamp > 0
  ? new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" })
    .format(new Date(stamp * 1000)) : "—";

export function readCurrent(entity) {
  const value = entity?.attributes?.current;
  if (!value || !["off", "rest", "active", "rate"].includes(value.p) ||
    typeof value.k !== "string" || !["s", "e", "n", "d", "i", "r"].every((key) =>
      Number.isFinite(value[key]) && value[key] >= 0)) return null;
  return value;
}
export function findEntity(hass, config) {
  if (!hass) return null;
  if (config.entity) {
    const entity = hass.states[config.entity];
    return entity?.attributes?.contraction_tracker === true &&
      (!config.entry_id || entity.attributes.entry_id === config.entry_id) ? entity : null;
  }
  const choices = Object.values(hass.states).filter((entity) =>
    entity.attributes.contraction_tracker === true &&
    (!config.entry_id || entity.attributes.entry_id === config.entry_id));
  return choices.length === 1 ? choices[0] : null; // Never guess between people.
}
export function recentRows(raw, now = Date.now() / 1000) {
  if (!Array.isArray(raw)) return [];
  return raw.filter((row) => Array.isArray(row) && row.length === 4 &&
    row.every(Number.isFinite) && row[0] >= now - 3600 && row[0] <= now &&
    row[1] >= 0 && row[2] >= 0 && [0, 1, 2, 3].includes(row[3]))
    .sort((a, b) => a[0] - b[0]).slice(-6);
}
export function homePath(value) {
  return typeof value === "string" && value.startsWith("/") && !value.startsWith("//") &&
    !/[\\\r\n\t]/.test(value) ? value : "/lovelace/0";
}
const sum = (rows, column) => rows.reduce((total, row) => total + row[column], 0);
export function trends(rows) {
  if (rows.length < 6) return ["More completed records are needed to compare recent patterns."];
  const before = rows.slice(0, 3), after = rows.slice(-3), result = [];
  if ([...before, ...after].every((row) => row[2] > 0)) {
    if (sum(after, 2) <= sum(before, 2) * 0.8) result.push("Recent starts are closer together.");
    else if (sum(after, 2) >= sum(before, 2) * 1.2) result.push("Recent starts are further apart.");
  }
  if (sum(before, 1) > 0) {
    if (sum(after, 1) >= sum(before, 1) * 1.2) result.push("Recent durations are longer.");
    else if (sum(after, 1) <= sum(before, 1) * 0.8) result.push("Recent durations are shorter.");
  }
  if ([...before, ...after].every((row) => row[3] > 0)) {
    if (sum(after, 3) >= sum(before, 3) + 2) result.push("Recent intensity ratings are higher.");
    else if (sum(after, 3) <= sum(before, 3) - 2) result.push("Recent intensity ratings are lower.");
  }
  return result.length ? [...result, "Share the changing pattern with your midwife."]
    : ["No clear change in these small samples."];
}
