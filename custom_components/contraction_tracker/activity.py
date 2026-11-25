"""Bounded metadata for verified operations; no HA dependency or durable outbox."""

from .const import RATINGS

EVENT_TYPES = (
    "session_started", "session_ended", "contraction_started",
    "contraction_completed", "contraction_rated", "record_corrected",
    "movement_logged",
)


def operation_activity(before, after, operation, occurred_at, record_id=None):
    """Called only after independent read-back, never for arbitrary state diffs."""
    events = []

    def add(kind, **fields):
        events.append({"event_type": kind, "session_id": after["session_id"],
                       "occurred_at": occurred_at, **fields})

    if operation in ("show", "start") and before["session_id"] != after["session_id"]:
        add("session_started")
    if operation == "start":
        add("contraction_started", number=after["n"], start=after["s"])
    elif operation in ("stop", *RATINGS, "correct"):
        row = (next(row for row in after["records"] if row["id"] == record_id)
               if operation == "correct" else after["records"][-1])
        kind = ("record_corrected" if operation == "correct" else
                "contraction_completed" if operation == "stop" else "contraction_rated")
        add(kind, record_id=row["id"], number=row["number"], start=row["start"],
            end=row["end"], duration=row["duration"], intensity=row["intensity"])
        # Correcting an older session must identify that record's real session.
        events[-1]["session_id"] = row["session_id"]
    elif operation == "movement":
        add("movement_logged", logged_at=after["movement"]["last"],
            count=after["movement"]["count"])
    elif operation == "inactivity" or (operation == "end" and before["p"] != "off"):
        add("session_ended", reason="inactivity" if operation == "inactivity" else "manual")
    return events
