"""Shared constants. This project is independent of any household configuration."""

DOMAIN = "contraction_tracker"
VERSION = "0.5.0b2"
STORAGE_VERSION = 1
MAX_RECORDS = 10000
COMMANDS = ("show", "start", "stop", "Mild", "Moderate", "Strong", "end", "notify",
            "movement", "reminders_on", "reminders_off", "intensity")
RATINGS = ("Mild", "Moderate", "Strong")
STATIC_URL = "/contraction_tracker_static"
MODULE_URL = f"{STATIC_URL}/tracker.js?v={VERSION}&ui=support-footer1"
LONG_CONTRACTION_SECONDS = 120
LONG_CONTRACTION_WARNING = (
    "Timer over 2 minutes. If this contraction is still continuing, contact your "
    "midwife or maternity unit urgently. If it ended earlier, stop the timer "
    "and correct the record."
)
SERVICE_COMMAND = "command"
CONF_NOTIFY = "notification_service"
CONF_HOME_PATH = "home_path"
CONF_PUBLIC = "public_lock_screen"
CONF_WARNING = "acknowledge_limitations"
