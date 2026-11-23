"""Native HA config-flow tests, intentionally separate from standalone tests."""

from homeassistant.config_entries import SOURCE_USER
from homeassistant.data_entry_flow import FlowResultType

from custom_components.contraction_tracker.const import DOMAIN


def inputs(**changes):
    return {"name": "Test tracker", "notification_service": "none",
            "home_path": "/lovelace/0", "public_lock_screen": False,
            "acknowledge_limitations": True, **changes}


async def test_shows_setup_form(hass):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"


async def test_medical_and_privacy_acknowledgement_is_required(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}, data=inputs(acknowledge_limitations=False))
    assert result["errors"]["acknowledge_limitations"] == "acknowledgement_required"


async def test_external_home_destination_is_rejected(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}, data=inputs(home_path="//example.org"))
    assert result["errors"]["home_path"] == "invalid_path"


async def test_entry_defaults_are_private_and_phone_optional(hass, mock_entry_setup):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}, data=inputs())
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["public_lock_screen"] is False
    assert result["data"]["notification_service"] == "none"
    assert "acknowledge_limitations" not in result["data"]


async def test_missing_phone_service_is_not_silently_accepted(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER},
        data=inputs(notification_service="notify.mobile_app_missing_test_phone"))
    assert result["errors"]["notification_service"] == "notification_unavailable"
