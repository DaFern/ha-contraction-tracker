"""UI setup; notifications are optional and lock-screen disclosure is opt-in."""

from urllib.parse import urlsplit

import probatio as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import CONF_HOME_PATH, CONF_NOTIFY, CONF_PUBLIC, CONF_WARNING, DOMAIN


def notification_choices(hass):
    names = sorted(name for name in hass.services.async_services().get("notify", {})
                   if name.startswith("mobile_app_"))
    return [{"value": "none", "label": "No phone notifications"}] + [
        {"value": f"notify.{name}", "label": name.removeprefix("mobile_app_").replace("_", " ")}
        for name in names
    ]


def valid_home_path(value):
    parsed = urlsplit(value)
    return (value.startswith("/") and not value.startswith("//") and
            not parsed.scheme and not parsed.netloc and
            not any(char in value for char in ("\\", "\r", "\n", "\t")))


def form_schema(hass, defaults, include_name=False):
    fields = {}
    if include_name:
        fields[vol.Required("name", default="Contraction Tracker")] = selector.TextSelector()
    fields.update({
        vol.Required(CONF_NOTIFY, default=defaults.get(CONF_NOTIFY, "none")):
            selector.SelectSelector(selector.SelectSelectorConfig(options=notification_choices(hass))),
        vol.Required(CONF_HOME_PATH, default=defaults.get(CONF_HOME_PATH, "/lovelace/0")):
            selector.TextSelector(),
        vol.Required(CONF_PUBLIC, default=defaults.get(CONF_PUBLIC, False)):
            selector.BooleanSelector(),
        vol.Required(CONF_WARNING, default=False): selector.BooleanSelector(),
    })
    return vol.Schema(fields)


def validate(hass, data, include_name=False):
    errors = {}
    if include_name and not data.get("name", "").strip():
        errors["name"] = "empty_name"
    if not valid_home_path(data.get(CONF_HOME_PATH, "")):
        errors[CONF_HOME_PATH] = "invalid_path"
    if data.get(CONF_NOTIFY, "none") not in {item["value"] for item in notification_choices(hass)}:
        errors[CONF_NOTIFY] = "notification_unavailable"
    if not data.get(CONF_WARNING):
        errors[CONF_WARNING] = "acknowledgement_required"
    return errors


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            errors = validate(self.hass, user_input, True)
            if not errors:
                data = {key: value for key, value in user_input.items() if key != CONF_WARNING}
                data["name"] = data["name"].strip()
                return self.async_create_entry(title=data["name"], data=data)
        return self.async_show_form(step_id="user",
                                    data_schema=form_schema(self.hass, user_input or {}, True),
                                    errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return OptionsFlow()


class OptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        errors = {}
        if user_input is not None:
            errors = validate(self.hass, user_input)
            if not errors:
                return self.async_create_entry(title="", data={
                    key: value for key, value in user_input.items() if key != CONF_WARNING
                })
        defaults = {**self.config_entry.data, **self.config_entry.options, **(user_input or {})}
        return self.async_show_form(step_id="init", data_schema=form_schema(self.hass, defaults), errors=errors)
