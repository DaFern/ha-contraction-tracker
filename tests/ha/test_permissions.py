"""Adapter permission branches against native HA types; full lifecycle remains QA."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from homeassistant.auth.permissions.const import POLICY_CONTROL, POLICY_READ
from homeassistant.exceptions import Unauthorized
import pytest

from custom_components.contraction_tracker import authorize
from custom_components.contraction_tracker.websocket import history


async def test_control_checks_the_native_entity_permission(hass):
    permissions = Mock()
    permissions.check_entity.return_value = True
    user = SimpleNamespace(is_active=True, permissions=permissions)
    runtime = SimpleNamespace(tracker=SimpleNamespace(entity_id="sensor.test_tracker"))
    with patch.object(hass.auth, "async_get_user", new=AsyncMock(return_value=user)):
        await authorize(hass, "test-user", runtime)
    permissions.check_entity.assert_called_once_with("sensor.test_tracker", POLICY_CONTROL)


async def test_inactive_user_is_denied(hass):
    user = SimpleNamespace(is_active=False, permissions=Mock())
    runtime = SimpleNamespace(tracker=SimpleNamespace(entity_id="sensor.test_tracker"))
    with patch.object(hass.auth, "async_get_user", new=AsyncMock(return_value=user)):
        with pytest.raises(Unauthorized):
            await authorize(hass, "test-user", runtime, POLICY_READ)
    user.permissions.check_entity.assert_not_called()


async def test_unauthorized_history_is_denied_before_reading_records(hass):
    runtime = SimpleNamespace(tracker=Mock())
    connection = SimpleNamespace(user=SimpleNamespace(id="test-user"), send_error=Mock(), send_result=Mock())
    with (
        patch("custom_components.contraction_tracker.get_runtime", return_value=runtime),
        patch("custom_components.contraction_tracker.authorize", new=AsyncMock(side_effect=Unauthorized)),
    ):
        await history.__wrapped__(hass, connection, {"id": 1, "entry_id": "test-entry", "limit": 50})
    runtime.tracker.history.assert_not_called()
    connection.send_error.assert_called_once_with(1, "unauthorized", "History access is not permitted.")
    connection.send_result.assert_not_called()
