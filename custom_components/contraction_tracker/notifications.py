"""Android-first notification presentation. No external image hosts."""

from .const import STATIC_URL


def build_notification(view, entry_id, path, public=False, title="Contraction Tracker"):
    tag = f"contraction_tracker_{entry_id}"
    if view["p"] == "off":
        return {"message": "clear_notification", "data": {"tag": tag}}
    def action(command, label=None):
        return {"action": f"CT|{entry_id}|{command}|{view['k']}", "title": label or command}
    move = {"action": f"CT|{entry_id}|movement|{view['movement']['k']}", "title": "Movement"}
    phase = view["p"]
    if phase == "active":
        actions = [action("stop", "Stop"), move]
    elif phase == "rate":
        actions = [action("intensity", "Intensity"), move]
    else:
        actions = [action("start", "Start"), move, action("end", "Close")]
    def clock(value):
        return f"{int(value) // 60}:{int(value) % 60:02d}" if value is not None else "—"
    hour = view.get("hourly", {})
    last = view.get("last_record")
    lines = [f"Last length: {clock(last['duration'] if last else None)}",
             f"Avg interval: {clock(hour.get('interval'))}",
             f"Avg length: {clock(hour.get('duration'))}", "",
             f"• {hour.get('count', 0)} contractions · past hour"]
    if last:
        lines.append(f"• Intensity: {last['intensity']}")
    if view.get("location", {}).get("source") == "automatic":
        lines.append(f"• {view['location']['label']}")
    summary = view.get("summary", {})
    descriptions = {"More completed records are needed to compare recent patterns.": "Too few records for trends.",
                    "No clear change in these small samples.": "No clear pattern change."}
    patterns = [descriptions.get(text, text) for text in summary.get("trends", [])
                if text != "Share the changing pattern with your midwife."]
    lines.append("• " + " · ".join(patterns or ["Awaiting completed records."]))
    prompt = view.get("recommendation", {}).get("text", "Contact your maternity team if unsure.")
    lines.append(f"• {prompt}")
    if view.get("restored"):
        lines.append("• Restored after restart: check timings with your maternity team.")
    if view.get("persistence_failed"):
        lines.insert(0, "SAVE NOT CONFIRMED. Check the tracker before retrying.")
    payload = {"title": title, "message": "\n".join(lines), "data": {
        "tag": tag, "channel": f"Contraction Tracker {entry_id[:8]}",
        "importance": "low", "priority": "high", "ttl": 0, "persistent": True,
        "sticky": True, "alert_once": True, "notification_icon": "mdi:baby-face-outline",
        "icon_url": f"{STATIC_URL}/icon.png", "clickAction": path,
        "visibility": "public" if public else "private",
        "chronometer": phase == "active" or view["e"] > 0,
        "when": view["s"] if phase == "active" else view["e"],
        "actions": actions,
    }}
    if not payload["data"]["when"]:
        payload["data"].pop("when")
    return payload


def build_rating(view, entry_id, path):
    return {"title": "Choose contraction intensity", "message": "How strong did it feel?",
            "data": {"tag": f"contraction_tracker_rating_{entry_id}", "clickAction": path,
                     "channel": f"Contraction Tracker {entry_id[:8]}",
                     "actions": [{"action": f"CT|{entry_id}|{rating}|{view['k']}", "title": rating}
                                 for rating in ("Mild", "Moderate", "Strong")]}}


def build_warning(view, entry_id, path, public=False):
    return {"title": "Movement logging reminder",
            "message": "No movement has been logged for at least an hour. This does not tell us whether the baby moved. "
                       "If movements reduce, stop or change, contact your midwife immediately; do not wait for a reminder.",
            "data": {"tag": f"contraction_tracker_movement_{entry_id}",
                     "channel": "Movement logging reminder", "visibility": "public" if public else "private",
                     "clickAction": path, "priority": "high", "ttl": 0}}
