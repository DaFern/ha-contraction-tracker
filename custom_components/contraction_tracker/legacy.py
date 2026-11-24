"""Strict, loss-preserving legacy conversion. Never writes files or HA state."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
import secrets

from .const import MAX_RECORDS, RATINGS
from .guidance import defaults as guidance_defaults, valid as valid_guidance
from .model import InvalidCommand, InvalidStorage, load_state, new_state

ENTITY_DOMAINS = {"records": "todo", "state": "input_text", "movement": "input_text",
                  "guidance": "input_text", "automation": "automation"}


def digest(value):
    """Canonical source/target guard; non-JSON or nonfinite values are refused."""
    try:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    except (TypeError, ValueError) as err:
        raise InvalidCommand("Migration input is not valid finite JSON.") from err
    if len(encoded) > 16 * 1024 * 1024:
        raise InvalidCommand("Migration input exceeds 16 MiB; nothing was truncated.")
    return hashlib.sha256(encoded).hexdigest()


def source_digest(bundle):
    candidate = deepcopy(bundle)
    if isinstance(candidate, dict) and isinstance(candidate.get("items"), list):
        candidate["items"] = sorted(candidate["items"], key=lambda row: str(row.get("uid", "")) if isinstance(row, dict) else "")
    return digest(candidate)


def _integer(value, name):
    if type(value) is not int or value < 0:
        raise InvalidCommand(f"Invalid legacy {name}; expected a nonnegative integer.")
    return value


def _one(pattern, text, name):
    matches = re.findall(pattern, text, flags=re.MULTILINE)
    if len(matches) != 1:
        raise InvalidCommand(f"Legacy record has missing or ambiguous {name}. Nothing was skipped.")
    return matches[0]


def _stamp(label, text):
    stamp, zone = _one(rf"^{label}: (\d{{4}}-\d{{2}}-\d{{2}} \d{{2}}:\d{{2}}:\d{{2}}) (GMT|BST)\s*$", text, label)
    try:
        offset = timezone(timedelta(hours=1 if zone == "BST" else 0))
        value = int(datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S").replace(tzinfo=offset).timestamp())
        return _integer(value, label)
    except (ValueError, OverflowError) as err:
        raise InvalidCommand("Invalid legacy timestamp.") from err


def _seconds(label, text, first=False):
    value = _one(rf"^{label}: ([^\r\n]+)", text, label).strip()
    if first and value in ("First contraction of this session.", "Not available for the first contraction."):
        return 0
    match = re.fullmatch(r"(\d+)m (\d+)s\.", value)
    if not match or len(match[1]) > 12 or len(match[2]) > 2 or int(match[2]) >= 60:
        raise InvalidCommand(f"Invalid legacy {label}.")
    return int(match[1]) * 60 + int(match[2])


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate metadata field")
        result[key] = value
    return result


def _parse(item, now):
    if (not isinstance(item, dict) or not isinstance(item.get("uid"), str)
            or not 1 <= len(item["uid"]) <= 128 or not isinstance(item.get("summary"), str)
            or not isinstance(item.get("description"), str)
            or item.get("status") not in ("needs_action", "completed")):
        raise InvalidCommand("Unsupported legacy record shape/status. Nothing was skipped.")
    raw = item["description"]
    if len(raw.encode()) > 256 * 1024:
        raise InvalidCommand("Legacy description exceeds 256 KiB; nothing was truncated.")
    visible, marker, metadata = raw.partition("\nCT_META:")
    try:
        meta = json.loads(metadata, object_pairs_hook=_unique_object) if marker else {}
    except (ValueError, TypeError) as err:
        raise InvalidCommand("Invalid or ambiguous legacy correction metadata.") from err
    if not isinstance(meta, dict):
        raise InvalidCommand("Invalid legacy correction metadata.")
    start, end = _stamp("Start", visible), _stamp("End", visible)
    number_text = _one(r"Contraction #([0-9]+)", item["summary"], "contraction number")
    if len(number_text) > 6:
        raise InvalidCommand("Invalid legacy contraction number.")
    number = int(number_text)
    intensity = _one(r"^Intensity: (Mild|Moderate|Strong|Not rated)\.\s*$", visible, "intensity")
    if number < 1 or start > end or end > now or _seconds("Duration", visible) != end - start:
        raise InvalidCommand("Legacy duration, order or future timestamp is inconsistent.")
    original = meta.get("original", {"start": start, "end": end, "intensity": intensity})
    if not isinstance(original, dict) or not all(key in original for key in ("start", "end", "intensity")):
        raise InvalidCommand("Legacy original values are incomplete.")
    # Extra original/source fields, notes and all original JSON stay in legacy.item.
    original = {key: deepcopy(original[key]) for key in ("start", "end", "intensity")}
    audit = deepcopy(meta.get("audit", []))
    if not isinstance(audit, list) or len(audit) > 100:
        raise InvalidCommand("Unsupported legacy correction trail; nothing was discarded.")
    return {"id": item["uid"], "number": number, "start": start, "end": end,
            "duration": end - start, "intensity": intensity, "original": original,
            "audit": audit, "revision": secrets.token_hex(16), "_meta": meta,
            "_gap": _seconds("Start-to-start interval", visible, first=number == 1),
            "_rest": _seconds("Rest before this contraction", visible, first=number == 1)}


def _session(source, first):
    return "legacy-" + hashlib.sha256((source + "\0" + first).encode()).hexdigest()[:32]


def convert(bundle, now):
    """Build and validate a complete candidate; never skip, merge or clear rows."""
    _integer(now, "receipt time")
    if not isinstance(bundle, dict) or set(bundle) != {"entities", "items", "state", "movement", "guidance"}:
        raise InvalidCommand("Incomplete legacy source snapshot.")
    entities = bundle["entities"]
    if (not isinstance(entities, dict) or set(entities) != set(ENTITY_DOMAINS)
            or any(not isinstance(entities[key], str) or not re.fullmatch(domain + r"\.[a-z0-9_]+", entities[key])
                   for key, domain in ENTITY_DOMAINS.items())):
        raise InvalidCommand("Choose explicit legacy source entities in the expected domains.")
    source_hash = source_digest(bundle)
    items = bundle["items"]
    if not isinstance(items, list) or len(items) > MAX_RECORDS:
        raise InvalidCommand("Invalid legacy history size; nothing was truncated.")
    if len({item.get("uid") for item in items if isinstance(item, dict) and isinstance(item.get("uid"), str)}) != len(items):
        raise InvalidCommand("Duplicate or invalid legacy record IDs.")
    parsed = sorted((_parse(item, now) for item in items), key=lambda row: (row["start"], row["id"]))
    source_items = {item["uid"]: item for item in items}
    rows, previous, session_ids, explicit_ids = [], None, set(), {}
    for row in parsed:
        if previous and row["start"] < previous["end"]:
            raise InvalidCommand("Legacy contractions overlap; review source records first.")
        new_session = row["number"] == 1
        if not new_session and (previous is None or row["number"] != previous["number"] + 1):
            raise InvalidCommand("Legacy session numbering is incomplete or ambiguous.")
        session_id = _session(entities["records"], row["id"]) if new_session else previous["session_id"]
        session_ids.add(session_id)
        meta_session = row["_meta"].get("session_id")
        if meta_session:
            if not isinstance(meta_session, str):
                raise InvalidCommand("Invalid legacy session metadata.")
            if meta_session in explicit_ids and explicit_ids[meta_session] != session_id:
                raise InvalidCommand("Conflicting legacy session metadata.")
            explicit_ids[meta_session] = session_id
            if any(sid != meta_session and mapped == session_id for sid, mapped in explicit_ids.items()):
                raise InvalidCommand("Conflicting legacy session metadata.")
        gap = row["start"] - previous["start"] if not new_session else 0
        rest = row["start"] - previous["end"] if not new_session else 0
        if row.pop("_gap") != gap or row.pop("_rest") != rest:
            raise InvalidCommand("Legacy interval/rest text disagrees with recorded timestamps.")
        row.pop("_meta")
        row.update(session_id=session_id, interval=gap, rest=rest,
                   legacy={"source_entity": entities["records"], "item": deepcopy(source_items[row["id"]])})
        rows.append(row)
        previous = row
    old = bundle["state"]
    required = {"p", "s", "e", "i", "r", "n", "d", "v", "k"}
    if not isinstance(old, dict) or not required <= set(old) or set(old) - required - {"u"}:
        raise InvalidCommand("Unsupported legacy current-state fields.")
    if old["p"] not in ("off", "rest", "rate", "active") or old["v"] not in (*RATINGS, "Not rated"):
        raise InvalidCommand("Invalid legacy phase or intensity.")
    if not isinstance(old["k"], str) or not old["k"]:
        raise InvalidCommand("Legacy tracker revision is missing.")
    for key in ("s", "e", "i", "r", "n", "d"):
        _integer(old[key], key)
    if old["s"] > now or old["e"] > now:
        raise InvalidCommand("Legacy current timestamps are in the future.")
    result = new_state()
    result.update({key: old[key] for key in ("p", "s", "e", "i", "r", "n", "d", "v")})
    result["records"] = rows
    if old["p"] == "active":
        if old["n"] < 1 or old["d"] != 0 or old["v"] != "Not rated":
            raise InvalidCommand("Legacy active timer is inconsistent.")
        prior = previous if old["n"] > 1 else None
        if prior and (prior["number"] != old["n"] - 1 or old["s"] < prior["end"]):
            raise InvalidCommand("Legacy active timer does not follow its saved session.")
        if old["n"] > 1 and prior is None:
            raise InvalidCommand("Legacy active timer is missing its preceding records.")
        if old["n"] == 1 and previous and old["s"] < previous["end"]:
            raise InvalidCommand("Legacy active timer overlaps saved history.")
        expected = (old["s"] - prior["start"], old["s"] - prior["end"], prior["end"]) if prior else (0, 0, 0)
        if (old["i"], old["r"], old["e"]) != expected:
            raise InvalidCommand("Legacy active interval/rest/end is inconsistent.")
        result["session_id"] = prior["session_id"] if prior else _session(entities["records"], f"active:{old['s']}:{old['k']}")
        session_ids.add(result["session_id"])
    elif old["n"]:
        if not previous or any(old[key] != previous[column] for key, column in
                               (("n", "number"), ("s", "start"), ("e", "end"), ("d", "duration"),
                                ("v", "intensity"), ("i", "interval"), ("r", "rest"))):
            raise InvalidCommand("Legacy current state disagrees with its latest saved record.")
        if old.get("u") and old["u"] != previous["id"]:
            raise InvalidCommand("Legacy current record ID disagrees with saved history.")
        result["session_id"] = previous["session_id"]
    else:
        if old["p"] == "rate" or any(old[key] for key in ("s", "e", "i", "r", "d")) or old["v"] != "Not rated":
            raise InvalidCommand("Legacy empty current session is inconsistent.")
        result["session_id"] = _session(entities["records"], "empty:" + old["k"]) if old["p"] != "off" else ""
    movement = bundle["movement"]
    if not isinstance(movement, dict) or set(movement) != set(result["movement"]) - {"preferred"}:
        raise InvalidCommand("Incomplete legacy movement settings.")
    if type(movement["enabled"]) is not bool or not isinstance(movement["k"], str) or not movement["k"]:
        raise InvalidCommand("Invalid legacy movement controls.")
    for key in ("last", "enabled_at", "last_alert", "count"):
        _integer(movement[key], "movement " + key)
        if key != "count" and movement[key] > now:
            raise InvalidCommand("Legacy movement timestamp is in the future.")
    if bool(movement["last"]) != bool(movement["count"]) or (movement["enabled"] and (not movement["enabled_at"] or old["p"] == "off")):
        raise InvalidCommand("Legacy movement logging/reminder state is inconsistent.")
    result["movement"].update({key: movement[key] for key in movement if key != "k"})
    result["movement"]["preferred"] = movement["enabled"]
    raw_guidance = bundle["guidance"]
    if not isinstance(raw_guidance, dict) or not {"location", "interval", "k"} <= set(raw_guidance):
        raise InvalidCommand("Incomplete legacy contact settings.")
    settings = {**guidance_defaults(), **deepcopy(raw_guidance), "k": secrets.token_hex(16)}
    if not valid_guidance(settings):
        raise InvalidCommand("Invalid legacy contact/location settings.")
    result["guidance"] = settings
    result["migration"] = {"source_sha256": source_hash, "source_entities": deepcopy(entities),
                           "source_helpers": {key: deepcopy(bundle[key]) for key in ("state", "movement", "guidance")},
                           "imported_at": now, "records": len(rows), "sessions": len(session_ids)}
    try:
        return load_state(result)
    except InvalidStorage as err:
        raise InvalidCommand("Legacy candidate failed native storage validation. Nothing was imported.") from err


def require_pristine(state):
    if (state["migration"] is not None or state["records"] or state["p"] != "off" or state["session_id"]
            or any(state[key] for key in ("s", "e", "i", "r", "n", "d"))
            or state["v"] != "Not rated"
            or any(state["movement"][key] for key in ("last", "enabled", "enabled_at", "last_alert", "count"))):
        raise InvalidCommand("Import requires an unused, paused tracker. Existing data will not be merged or overwritten.")


def summary(candidate):
    return {"records": len(candidate["records"]), "sessions": candidate["migration"]["sessions"],
            "phase": candidate["p"], "session_number": candidate["n"],
            "movement_count": candidate["movement"]["count"],
            "reminder_enabled": candidate["movement"]["enabled"],
            "location_mode": candidate["guidance"]["mode"],
            "location": candidate["guidance"]["location"],
            "contact_interval": candidate["guidance"]["interval"]}
