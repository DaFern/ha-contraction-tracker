"""Authenticated read-only history endpoint; never served as a public file."""

import probatio as vol

from homeassistant.auth.permissions.const import POLICY_READ
from homeassistant.components import websocket_api
from homeassistant.exceptions import ServiceValidationError, Unauthorized

from .const import DOMAIN


def async_register(hass):
    websocket_api.async_register_command(hass, history)


@websocket_api.websocket_command({
    "type": f"{DOMAIN}/history",
    vol.Required("entry_id"): str,
    vol.Optional("limit", default=50): vol.All(int, vol.Range(min=1, max=500)),
})
@websocket_api.async_response
async def history(hass, connection, msg):
    from . import authorize, get_runtime
    try:
        runtime = get_runtime(hass, msg["entry_id"])
        await authorize(hass, connection.user.id, runtime, POLICY_READ)
    except Unauthorized:
        connection.send_error(msg["id"], "unauthorized", "History access is not permitted.")
        return
    except ServiceValidationError:
        connection.send_error(msg["id"], "not_loaded", "This tracker is not loaded.")
        return
    if runtime.tracker.import_uncertain or runtime.tracker.persistence_uncertain:
        connection.send_error(msg["id"], "persistence_uncertain", "Reload and inspect saved history before retrying.")
        return
    connection.send_result(msg["id"], {
        "items": runtime.tracker.history(msg["limit"]),
        "total": runtime.tracker.view()["records_count"],
    })
