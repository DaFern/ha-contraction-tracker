"""HA adapter for explicit admin-only, read-only source snapshots."""

import json
import re

from .legacy import ENTITY_DOMAINS, _unique_object
from .model import InvalidCommand


def require_stopped(hass, entity_id):
    source = hass.states.get(entity_id)
    if source is None or source.state != "off" or source.attributes.get("current", 0) != 0:
        raise InvalidCommand("Disable the legacy tracker and wait for its queue to finish before applying an import.")


async def read_source(hass, entities, context, *, stopped=False):
    """Read supported APIs, bracketing the to-do read with helper-state checks."""
    if set(entities) != set(ENTITY_DOMAINS) or any(
        not isinstance(entities[key], str) or not re.fullmatch(domain + r"\.[a-z0-9_]+", entities[key])
        for key, domain in ENTITY_DOMAINS.items()
    ):
        raise InvalidCommand("Invalid legacy source entity domains.")
    if stopped:
        require_stopped(hass, entities["automation"])

    def helpers():
        result = {}
        for key in ("state", "movement", "guidance"):
            value = hass.states.get(entities[key])
            if value is None or value.state in ("unknown", "unavailable", ""):
                raise InvalidCommand("A legacy source helper is unavailable.")
            result[key] = value.state
        return result

    before = helpers()
    response = await hass.services.async_call(
        "todo", "get_items", target={"entity_id": entities["records"]},
        blocking=True, return_response=True, context=context,
    )
    if helpers() != before:
        raise InvalidCommand("Legacy controls changed during the source read. Take a fresh preview.")
    if stopped:
        require_stopped(hass, entities["automation"])
    try:
        items = response[entities["records"]]["items"]
        parsed = {key: json.loads(value, object_pairs_hook=_unique_object) for key, value in before.items()}
    except (KeyError, TypeError, ValueError) as err:
        raise InvalidCommand("Legacy source response or helper JSON is invalid.") from err
    return {"entities": dict(entities), "items": items, **parsed}
