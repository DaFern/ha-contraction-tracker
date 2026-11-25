"""Android-first notification presentation. No external image hosts."""

from hashlib import sha256
import json

from .const import LONG_CONTRACTION_WARNING, STATIC_URL


def build_notification(view, entry_id, path, public=False, title="Contraction Tracker"):
    tag = f"contraction_tracker_{entry_id}"
    idle = view.get("idle_ended", False)
    if view["p"] == "off" and not idle:
        return {"message": "clear_notification", "data": {"tag": tag}}
    def action(command, label=None):
        return {"action": f"CT|{entry_id}|{command}|{view['k']}", "title": label or command}
    move = {"action": f"CT|{entry_id}|movement|{view['movement']['k']}", "title": "Movement"}
    phase = view["p"]
    if idle:
        actions = [action("start", "Start"), move, action("end", "Close")]
    elif phase == "active":
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
    if idle:
        lines.insert(0, "Recording ended after inactivity. Start begins a new session.")
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
        "chronometer": not idle and (phase == "active" or view["e"] > 0),
        "when": 0 if idle else view["s"] if phase == "active" else view["e"],
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


def long_warning_tag(view, entry_id):
    """Stable per-contraction identity, not an authentication/concurrency token."""
    identity = json.dumps([view["session_id"], view["n"], view["s"]], separators=(",", ":"))
    suffix = sha256(identity.encode()).hexdigest()[:32]
    return f"contraction_tracker_long_{entry_id}_{suffix}"


def long_warning_cleanup_tags(view, entry_id):
    """Clear only a claimed warning whose contraction has actually completed.

    Never enqueue a pre-threshold clear for the current warning. Shutdown uses
    an off presentation even for an active timer, so require a completed record,
    not just the presentation phase. Old clears cannot target later contractions.
    """
    last = view.get("last_record")
    if (view["p"] == "active" or not view.get("long_warning_attempted") or not last
            or any(last.get(key) != value for key, value in (
                ("session_id", view["session_id"]), ("number", view["n"]), ("start", view["s"])))):
        return []
    # Retire the pre-upgrade entry-wide warning only after completion too.
    return [long_warning_tag(view, entry_id), f"contraction_tracker_long_{entry_id}"]


def build_long_warning(view, entry_id, path, public=False):
    """A timer check, not a diagnosis; normal Android delivery restrictions apply."""
    return {
        "title": "Contraction timer over 2 minutes",
        "message": LONG_CONTRACTION_WARNING,
        "data": {
            "tag": long_warning_tag(view, entry_id),
            "channel": "Contraction timer warnings",
            "importance": "high", "priority": "high", "ttl": 0,
            "visibility": "public" if public else "private",
            "clickAction": path,
            "actions": [{"action": f"CT|{entry_id}|stop|{view['k']}", "title": "Stop"}],
        },
    }
