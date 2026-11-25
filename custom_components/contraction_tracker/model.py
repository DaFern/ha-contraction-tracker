"""Dependency-free, copy-on-write contraction state machine.

Tokens are concurrency guards, not authentication. Authorization belongs to the
Home Assistant adapter. No stage, dilation or birth-time prediction is made.
"""

from copy import deepcopy
from math import isfinite
import json
import secrets
from uuid import uuid4

from .const import LONG_CONTRACTION_SECONDS, MAX_RECORDS, RATINGS
from .guidance import defaults as guidance_defaults, recommendation, valid as valid_guidance
from .location import manual as manual_location, uncertain as uncertain_location


class InvalidCommand(ValueError):
    """An invalid, stale or out-of-phase request."""


class InvalidStorage(ValueError):
    """Stored data cannot safely be interpreted. Never silently reset it."""


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value) and value >= 0


def new_state():
    """Return an independent empty tracker, not a running session."""
    return {
        "schema": 8, "p": "off", "k": secrets.token_hex(16), "session_id": "",
        "idle_ended": False,
        "long_warning_attempted": False,
        "s": 0, "e": 0, "i": 0, "r": 0, "n": 0, "d": 0, "v": "Not rated",
        "records": [],
        "migration": None,
        "guidance": guidance_defaults(),
        "movement": {"last": 0, "enabled": False, "preferred": False, "enabled_at": 0, "last_alert": 0,
                     "k": secrets.token_hex(16), "count": 0},
    }


def load_state(data):
    """Validate the storage boundary before accepting records."""
    if data is None:
        return new_state()
    data = deepcopy(data)
    if isinstance(data, dict) and type(data.get("schema")) is int and data["schema"] == 1:
        # Explicit backwards-compatible migration of the unpublished first alpha.
        data["schema"] = 2
        data["movement"] = new_state()["movement"]
        for row in data.get("records", []):
            row.update(revision=secrets.token_hex(16), audit=[],
                       original={key: row[key] for key in ("start", "end", "intensity")})
    if isinstance(data, dict) and type(data.get("schema")) is int and data["schema"] == 2:
        data["schema"] = 3
        data["guidance"] = guidance_defaults()
    if isinstance(data, dict) and type(data.get("schema")) is int and data["schema"] == 3:
        if not isinstance(data.get("guidance"), dict):
            raise InvalidStorage("Invalid contact-prompt settings.")
        data["schema"] = 4
        data["guidance"] = {**guidance_defaults(), **data.get("guidance", {})}
    if isinstance(data, dict) and type(data.get("schema")) is int and data["schema"] == 4:
        if not isinstance(data.get("records"), list):
            raise InvalidStorage("Invalid stored records.")
        data["schema"] = 5
        data["migration"] = None
        for row in data["records"]:
            if not isinstance(row, dict):
                raise InvalidStorage("Invalid stored record.")
            row["legacy"] = None
    if isinstance(data, dict) and type(data.get("schema")) is int and data["schema"] == 5:
        data["schema"] = 6
        data["idle_ended"] = False
    if isinstance(data, dict) and type(data.get("schema")) is int and data["schema"] == 6:
        if not isinstance(data.get("movement"), dict):
            raise InvalidStorage("Invalid movement logging settings.")
        data["schema"] = 7
        # Old Off cannot distinguish a deliberate opt-out from an automatic pause.
        data["movement"]["preferred"] = data["movement"].get("enabled")
    if isinstance(data, dict) and type(data.get("schema")) is int and data["schema"] == 7:
        data["schema"] = 8
        data["long_warning_attempted"] = False
    expected = set(new_state())
    if not isinstance(data, dict) or set(data) != expected or type(data.get("schema")) is not int or data["schema"] != 8:
        raise InvalidStorage("Unsupported or incomplete storage; restore a backup.")
    if type(data["long_warning_attempted"]) is not bool:
        raise InvalidStorage("Invalid contraction warning state.")
    if type(data["idle_ended"]) is not bool or (data["idle_ended"] and (
            data["p"] != "off" or not data["n"])):
        raise InvalidStorage("Invalid idle-session state.")
    if not valid_guidance(data["guidance"]):
        raise InvalidStorage("Invalid contact-prompt settings.")
    if data["p"] not in ("off", "rest", "active", "rate"):
        raise InvalidStorage("Invalid stored phase.")
    if (not isinstance(data["k"], str) or len(data["k"]) != 32
            or any(char not in "0123456789abcdef" for char in data["k"])):
        raise InvalidStorage("Invalid stored revision.")
    if not isinstance(data["session_id"], str):
        raise InvalidStorage("Invalid stored session.")
    if not all(_number(data[key]) for key in ("s", "e", "i", "r", "n", "d")):
        raise InvalidStorage("Invalid stored timestamps or measurements.")
    if not isinstance(data["n"], int) or data["v"] not in (*RATINGS, "Not rated"):
        raise InvalidStorage("Invalid stored count or rating.")
    if not isinstance(data["records"], list) or len(data["records"]) > MAX_RECORDS:
        raise InvalidStorage("Invalid history size.")
    seen = set()
    movement = data["movement"]
    if (not isinstance(movement, dict) or set(movement) != set(new_state()["movement"])
            or type(movement["enabled"]) is not bool or type(movement["preferred"]) is not bool
            or (movement["enabled"] and (not movement["preferred"] or data["p"] == "off"))
            or not isinstance(movement["k"], str)
            or len(movement["k"]) != 32 or any(char not in "0123456789abcdef" for char in movement["k"])
            or not isinstance(movement["count"], int) or isinstance(movement["count"], bool)
            or not all(_number(movement[key]) for key in ("last", "enabled_at", "last_alert", "count"))):
        raise InvalidStorage("Invalid movement logging settings.")
    if data["idle_ended"] and movement["enabled"]:
        raise InvalidStorage("An idle-ended session cannot keep reminders enabled.")
    record_keys = {"id", "session_id", "number", "start", "end", "duration", "interval", "rest", "intensity",
                   "revision", "audit", "original", "legacy"}
    for row in data["records"]:
        if not isinstance(row, dict) or set(row) != record_keys:
            raise InvalidStorage("Invalid record shape.")
        if not all(isinstance(row[key], str) and row[key] for key in ("id", "session_id")):
            raise InvalidStorage("Invalid record identifier.")
        if row["id"] in seen:
            raise InvalidStorage("Duplicate record identifier.")
        seen.add(row["id"])
        if not all(_number(row[key]) for key in ("number", "start", "end", "duration", "interval", "rest")):
            raise InvalidStorage("Invalid record measurements.")
        if not isinstance(row["number"], int) or row["number"] < 1:
            raise InvalidStorage("Invalid record number.")
        if row["end"] < row["start"] or row["duration"] != row["end"] - row["start"]:
            raise InvalidStorage("Inconsistent record duration.")
        if row["intensity"] not in (*RATINGS, "Not rated"):
            raise InvalidStorage("Invalid recorded intensity.")
        if (not isinstance(row["revision"], str) or not isinstance(row["audit"], list)
                or len(row["revision"]) != 32 or not row["revision"].isascii()
                or not isinstance(row["original"], dict) or len(row["audit"]) > 100):
            raise InvalidStorage("Invalid correction history.")
        snapshots = [row["original"]]
        for correction in row["audit"]:
            if (not isinstance(correction, dict) or set(correction) != {"at", "before", "after"}
                    or not _number(correction["at"])):
                raise InvalidStorage("Invalid correction audit event.")
            snapshots.extend((correction["before"], correction["after"]))
        for original in snapshots:
            if (not isinstance(original, dict) or set(original) != {"start", "end", "intensity"}
                    or not _number(original["start"]) or not _number(original["end"])
                    or original["end"] < original["start"] or original["intensity"] not in (*RATINGS, "Not rated")):
                raise InvalidStorage("Invalid original or corrected values.")
        provenance = row["legacy"]
        if provenance is not None:
            if (not isinstance(provenance, dict) or set(provenance) != {"source_entity", "item"}
                    or not isinstance(provenance["source_entity"], str) or not provenance["source_entity"].startswith("todo.")
                    or not isinstance(provenance["item"], dict)
                    or provenance["item"].get("uid") != row["id"]
                    or not isinstance(provenance["item"].get("summary"), str)
                    or not isinstance(provenance["item"].get("description"), str)
                    or provenance["item"].get("status") not in ("needs_action", "completed")):
                raise InvalidStorage("Invalid imported provenance.")
    migration = data["migration"]
    if migration is not None:
        if (not isinstance(migration, dict) or set(migration) != {
                "source_sha256", "source_entities", "source_helpers", "imported_at", "records", "sessions"}
                or not isinstance(migration["source_sha256"], str) or len(migration["source_sha256"]) != 64
                or any(char not in "0123456789abcdef" for char in migration["source_sha256"])
                or not isinstance(migration["source_entities"], dict)
                or set(migration["source_entities"]) != {"records", "state", "movement", "guidance", "automation"}
                or not all(isinstance(value, str) and value for value in migration["source_entities"].values())
                or not isinstance(migration["source_helpers"], dict)
                or set(migration["source_helpers"]) != {"state", "movement", "guidance"}
                or not all(isinstance(value, dict) for value in migration["source_helpers"].values())
                or not _number(migration["imported_at"])
                or type(migration["records"]) is not int
                or migration["records"] != sum(row["legacy"] is not None for row in data["records"])
                or type(migration["sessions"]) is not int or not 0 <= migration["sessions"] <= migration["records"] + 1):
            raise InvalidStorage("Invalid import receipt.")
        try:
            json.dumps({"receipt": migration, "provenance": [row["legacy"] for row in data["records"]]},
                       allow_nan=False)
        except (ValueError, TypeError) as err:
            raise InvalidStorage("Imported provenance must be finite JSON.") from err
    elif any(row["legacy"] is not None for row in data["records"]):
        raise InvalidStorage("Imported records have no import receipt.")
    if data["p"] != "off" and not data["session_id"]:
        raise InvalidStorage("Active tracking has no session.")
    if data["p"] == "active" and (data["n"] < 1 or data["s"] < data["e"]):
        raise InvalidStorage("Active contraction timestamps are inconsistent.")
    if data["p"] in ("off", "rest", "rate") and data["n"]:
        if not data["records"]:
            raise InvalidStorage("Current record is missing.")
        last = data["records"][-1]
        if any((last["session_id"] != data["session_id"], last["number"] != data["n"],
                last["start"] != data["s"], last["end"] != data["e"],
                last["duration"] != data["d"], last["intensity"] != data["v"])):
            raise InvalidStorage("Current state and saved record disagree.")
    return deepcopy(data)


def expire_idle(state, now):
    """End only a completed, inactive session; never infer a contraction end."""
    if state["p"] not in ("rest", "rate") or not state["n"] or now - state["e"] < 3600:
        return deepcopy(state)
    result = deepcopy(state)
    result.update(p="off", idle_ended=True, k=secrets.token_hex(16))
    result["movement"].update(enabled=False, k=secrets.token_hex(16))
    return result


def transition(state, command, token, now):
    """Build a candidate; callers must persist it before publishing or notifying."""
    if not _number(now):
        raise InvalidCommand("A valid server timestamp is required.")
    if command in ("movement", "reminders_on", "reminders_off"):
        result = deepcopy(state)
        movement = result["movement"]
        if not isinstance(token, str) or not token.isascii() or not secrets.compare_digest(token, movement["k"]):
            raise InvalidCommand("Movement controls changed. Refresh before retrying.")
        if command == "movement":
            if now < movement["last"]:
                raise InvalidCommand("Server time moved backwards. Check time synchronization.")
            movement.update(last=now, count=movement["count"] + 1, last_alert=0)
        elif command == "reminders_on":
            if state["p"] == "off":
                raise InvalidCommand("Start recording before enabling the logging reminder.")
            movement.update(enabled=True, preferred=True, enabled_at=now, last_alert=0)
        else:
            movement.update(enabled=False, preferred=False, last_alert=0)
        movement["k"] = secrets.token_hex(16)
        return result
    if command == "intensity" and state["p"] == "rate":
        if not isinstance(token, str) or not token.isascii() or not secrets.compare_digest(token, state["k"]):
            raise InvalidCommand("Intensity controls changed. Refresh before retrying.")
        return deepcopy(state)
    if command in ("show", "notify") and (command == "notify" or state["p"] != "off"):
        return deepcopy(state)
    if command != "show" and (not isinstance(token, str) or not token.isascii()
                              or not secrets.compare_digest(token, state["k"])):
        raise InvalidCommand("This control is out of date. Refresh the tracker.")
    result = deepcopy(state)
    if command == "show" and state["p"] == "off":
        result.update(p="rest", idle_ended=False, long_warning_attempted=False, session_id=uuid4().hex,
                      s=0, e=0, i=0, r=0, n=0, d=0, v="Not rated")
    elif command == "start" and (state["p"] == "rest" or state["idle_ended"]):
        if len(state["records"]) >= MAX_RECORDS:
            raise InvalidCommand("History is full. Existing records were not deleted.")
        if now < max(state["s"], state["e"]):
            raise InvalidCommand("Server time moved backwards. Check time synchronization.")
        if state["idle_ended"]:
            result.update(session_id=uuid4().hex, n=0, s=0, e=0)
        result.update(p="active", idle_ended=False, long_warning_attempted=False,
                      s=now, n=result["n"] + 1, d=0, v="Not rated",
                      i=now - state["s"] if result["n"] else 0,
                      r=now - state["e"] if result["n"] else 0)
    elif command == "stop" and state["p"] == "active":
        if now < state["s"]:
            raise InvalidCommand("Server time moved backwards. Check time synchronization.")
        result.update(p="rate", e=now, d=now - state["s"])
        result["records"].append({
            "id": uuid4().hex, "session_id": state["session_id"], "number": state["n"],
            "start": state["s"], "end": now, "duration": now - state["s"],
            "interval": state["i"], "rest": state["r"], "intensity": "Not rated",
            "revision": secrets.token_hex(16), "audit": [],
            "original": {"start": state["s"], "end": now, "intensity": "Not rated"},
            "legacy": None,
        })
    elif command in RATINGS and state["p"] == "rate":
        result.update(p="rest", v=command)
        result["records"][-1]["intensity"] = command
        result["records"][-1]["revision"] = secrets.token_hex(16)
        if result["records"][-1]["legacy"] is None:
            result["records"][-1]["original"]["intensity"] = command
    elif command == "end" and (state["p"] == "rest" or state["idle_ended"]):
        result.update(p="off", idle_ended=False)
        result["movement"].update(enabled=False, k=secrets.token_hex(16))
    else:
        raise InvalidCommand("That action is not available in the current phase.")
    if state["p"] == "off" and result["p"] != "off" and result["movement"]["preferred"]:
        # Resume the existing clock: neither session starts nor Stop reset movement.
        result["movement"].update(enabled=True, k=secrets.token_hex(16))
    result["k"] = secrets.token_hex(16)
    return result


def snapshot(state, now, location=None):
    """Small sensor payload; complete history is fetched through authorized APIs."""
    result = {key: deepcopy(value) for key, value in state.items() if key not in ("schema", "records", "migration")}
    recent = state["records"][-6:]
    result["recent"] = [[row["start"], row["duration"], row["interval"],
                         RATINGS.index(row["intensity"]) + 1 if row["intensity"] in RATINGS else 0]
                        for row in recent]
    result["records_count"] = len(state["records"])
    result["long_contraction"] = (
        state["p"] == "active" and now - state["s"] > LONG_CONTRACTION_SECONDS
    )
    result["import_receipt"] = ({key: state["migration"][key] for key in
                                ("source_sha256", "records", "sessions", "imported_at")}
                               if state["migration"] else None)
    result["location"] = (manual_location(state["guidance"]) if state["guidance"]["mode"] == "manual"
                          else location or uncertain_location())
    result["recommendation"] = recommendation(state, now, result["location"])
    result["last_record"] = ({key: state["records"][-1][key] for key in ("duration", "intensity")}
                             if state["records"] else None)
    hour = [row for row in state["records"] if now - 3600 <= row["start"] <= now]
    starts = len(hour) + int(state["p"] == "active" and now - 3600 <= state["s"] <= now)
    eligible = [row["interval"] for row in hour
                if row["interval"] > 0 and row["start"] - row["interval"] >= now - 3600]
    if state["p"] == "active" and state["i"] > 0 and state["s"] - state["i"] >= now - 3600:
        eligible.append(state["i"])
    mean = lambda values: int(sum(values) / len(values) + .5) if values else None
    result["hourly"] = {"count": starts, "duration": mean([row["duration"] for row in hour]),
                        "interval": mean(eligible), "completed": len(hour)}
    result["summary"] = summarize([[row["start"], row["duration"], row["interval"],
                                   RATINGS.index(row["intensity"]) + 1 if row["intensity"] in RATINGS else 0]
                                  for row in hour[-6:]])
    result["summary"].update(duration=result["hourly"]["duration"], interval=result["hourly"]["interval"],
                             samples=len(hour))
    return result


def configure_guidance(state, token, location, interval, mode="manual", person="", home="", hospitals=None):
    """Independent revision: settings must never invalidate an active Stop."""
    settings = {"location": location, "interval": interval, "k": secrets.token_hex(16),
                "mode": mode, "person": person, "home": home, "hospitals": deepcopy(hospitals) if hospitals is not None else []}
    if not valid_guidance(settings):
        raise InvalidCommand("Check location mode, person, distinct home/hospital zones and a whole-minute interval from 1 to 10.")
    if not isinstance(token, str) or not token.isascii() or not secrets.compare_digest(token, state["guidance"]["k"]):
        raise InvalidCommand("Contact-prompt settings changed. Reopen them before saving.")
    result = deepcopy(state)
    result["guidance"] = settings
    return result


def correct(state, record_id, revision, start, end, intensity, now):
    """Validate one correction and atomically derive every dependent interval."""
    if not all(_number(value) for value in (start, end, now)) or start > end or end > now:
        raise InvalidCommand("Use valid start/end times, with the end no later than now.")
    if intensity not in (*RATINGS, "Not rated"):
        raise InvalidCommand("Choose a valid intensity.")
    result = deepcopy(state)
    rows = result["records"]
    index = next((i for i, row in enumerate(rows) if row["id"] == record_id), None)
    if index is None or rows[index]["revision"] != revision:
        raise InvalidCommand("This record changed. Reopen it before saving.")
    row = rows[index]
    if (index > 0 and start < rows[index - 1]["end"]) or (index + 1 < len(rows) and end > rows[index + 1]["start"]):
        raise InvalidCommand("The corrected contraction overlaps another record.")
    if state["p"] == "active" and index == len(rows) - 1 and end > state["s"]:
        raise InvalidCommand("The corrected record overlaps the contraction being timed.")
    if len(row["audit"]) >= 100:
        raise InvalidCommand("Correction history is full; nothing was discarded.")
    before = {key: row[key] for key in ("start", "end", "intensity")}
    after = {"start": start, "end": end, "intensity": intensity}
    if before == after:
        return result
    row["audit"].append({"at": now, "before": before, "after": after})
    row.update(after)
    for i, record in enumerate(rows):
        previous = rows[i - 1] if i > 0 and rows[i - 1]["session_id"] == record["session_id"] else None
        derived = (record["end"] - record["start"],
                   record["start"] - previous["start"] if previous else 0,
                   record["start"] - previous["end"] if previous else 0)
        if (record["duration"], record["interval"], record["rest"]) != derived or i == index:
            record.update(duration=derived[0], interval=derived[1], rest=derived[2],
                          revision=secrets.token_hex(16))
    current = next((record for record in reversed(rows) if record["session_id"] == state["session_id"]
                    and record["number"] == state["n"]), None)
    if state["p"] != "active" and current:
        result.update(s=current["start"], e=current["end"], d=current["duration"], v=current["intensity"],
                      i=current["interval"], r=current["rest"])
        if state["p"] == "rate" and current["intensity"] != "Not rated":
            result["p"] = "rest"
    elif state["p"] == "active" and rows and rows[-1]["session_id"] == state["session_id"]:
        result.update(i=state["s"] - rows[-1]["start"], r=state["s"] - rows[-1]["end"])
    return result


def reminder_due(state, now):
    """A logging reminder, never a fetal-movement or wellbeing assessment."""
    movement = state["movement"]
    anchor = max(movement["last"], movement["enabled_at"], movement["last_alert"])
    return movement["preferred"] and movement["enabled"] and state["p"] != "off" and now - anchor >= 3600


def summarize(rows):
    """Descriptive UI noise filters only; never clinical thresholds."""
    def mean(values):
        return int(sum(values) / len(values) + .5) if values else None
    last = rows[-5:]
    result = {"samples": len(last), "duration": mean([row[1] for row in last]),
              "interval": mean([row[2] for row in last if row[2] > 0]), "trends": []}
    if len(rows) < 6:
        result["trends"] = ["More completed records are needed to compare recent patterns."]
        return result
    before, after = rows[:3], rows[-3:]
    for column, increase, decrease in (
        (2, "Recent starts are further apart.", "Recent starts are closer together."),
        (1, "Recent durations are longer.", "Recent durations are shorter."),
    ):
        if column == 2 and not all(row[2] > 0 for row in before + after):
            continue
        left, right = sum(row[column] for row in before), sum(row[column] for row in after)
        if left > 0 and right >= left * 1.2:
            result["trends"].append(increase)
        elif left > 0 and right <= left * .8:
            result["trends"].append(decrease)
    if all(row[3] > 0 for row in before + after):
        change = sum(row[3] for row in after) - sum(row[3] for row in before)
        if change >= 2:
            result["trends"].append("Recent intensity ratings are higher.")
        elif change <= -2:
            result["trends"].append("Recent intensity ratings are lower.")
    if result["trends"]:
        result["trends"].append("Share the changing pattern with your midwife.")
    else:
        result["trends"] = ["No clear change in these small samples."]
    return result
