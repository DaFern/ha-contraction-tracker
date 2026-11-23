"""Contact prompts based on recorded patterns, never stage or travel decisions."""

import secrets
from .location import entity_id, manual, uncertain

LOCATIONS = ("unspecified", "home", "hospital")


def defaults():
    return {"location": "unspecified", "interval": 300, "k": secrets.token_hex(16),
            "mode": "manual", "person": "", "home": "", "hospitals": []}


def valid(settings):
    return (isinstance(settings, dict) and set(settings) == set(defaults())
            and settings["location"] in LOCATIONS
            and type(settings["interval"]) is int and 60 <= settings["interval"] <= 600
            and settings["interval"] % 60 == 0
            and isinstance(settings["k"], str) and len(settings["k"]) == 32
            and all(c in "0123456789abcdef" for c in settings["k"])
            and settings["mode"] in ("manual", "automatic")
            and (settings["person"] == "" or entity_id(settings["person"], "person"))
            and (settings["home"] == "" or entity_id(settings["home"], "zone"))
            and isinstance(settings["hospitals"], list) and len(settings["hospitals"]) <= 3
            and all(entity_id(zone, "zone") for zone in settings["hospitals"])
            and len(set(settings["hospitals"])) == len(settings["hospitals"])
            and settings["home"] not in settings["hospitals"]
            and (settings["mode"] == "manual" or
                 bool(settings["person"] and settings["home"] and settings["hospitals"])))


def recommendation(state, now, location=None):
    """Three consecutive gaps are a UI trigger, not a clinical regularity test.

    Check current-session starts only, with both ends of each gap inside 30 min.
    No one-hour hold requirement; silence is never permission to wait.
    Urgent contact checks are separate and cannot be weakened by custom settings.
    Called on actions/refresh, not a continuous medical monitoring service.
    """
    settings = state["guidance"]
    location = location or (manual(settings) if settings["mode"] == "manual" else uncertain())
    hospital = location["location"] == "hospital" and location["source"] == "manual"
    contact = "Tell your midwife" if hospital else (
        "Contact your maternity unit" if location["location"] == "home"
        else "Contact your maternity care team")
    if state["p"] == "off":
        return {"level": "paused", "text": "Follow your care plan; contact your maternity team if unsure."}
    records = sorted((r for r in state["records"] if r["session_id"] == state["session_id"]
                      and r["start"] <= now), key=lambda r: r["start"])
    starts = [r["start"] for r in records if r["start"] >= now - 1800]
    if state["p"] == "active" and now - 1800 <= state["s"] <= now:
        starts.append(state["s"])
    long = (any(r["duration"] > 120 and now - 600 <= r["end"] <= now for r in records)
            or state["p"] == "active" and now - state["s"] > 120)
    dense = sum(now - 600 < start <= now for start in starts) >= 6
    if long or dense:
        reason = "contraction over 2 min" if long else "6+ starts in 10 min"
        return {"level": "urgent", "text": f"{contact} urgently: recorded {reason}."}
    latest = starts[-4:]
    gaps = [b - a for a, b in zip(latest, latest[1:])]
    if (len(gaps) == 3 and now - latest[-1] <= settings["interval"] * 2
            and all(0 < gap <= settings["interval"] for gap in gaps)):
        return {"level": "contact", "text": f"{contact} about these frequent contractions."}
    text = ("Keep your midwife updated; ask if you need support." if hospital else
            "Keep your bag and notes ready; contact maternity if unsure."
            if location["location"] == "home" else
            "Follow your care plan; contact your maternity team if unsure.")
    return {"level": "routine", "text": text}
