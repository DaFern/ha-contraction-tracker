# Testing and evidence

## Available without Home Assistant

```sh
python3 -m unittest discover -s tests/unit -v
npm test
python3 tools/build_assets.py
python3 tools/check_release.py
python3 tools/build_release.py
```

Domain tests exercise real transition and manager code with injected storage and
notification callbacks. Frontend tests exercise the real JavaScript helpers and
component methods with a minimal DOM stand-in. They are **not browser rendering,
touch interaction, native HA integration or physical-phone tests**.

## Native Home Assistant tests — separate development environment

Use a fresh disposable Python 3.14.2+ environment, not the live instance.
Home Assistant now supplies the official `pytest-homeassistant` package.
Install a release matching the exact Home Assistant version being tested:

```sh
python -m pip install -r requirements-ha-test.txt "pytest-homeassistant==2026.11.0" "homeassistant==2026.11.0"
python -m pip check
pytest tests/ha -v
```

The frontend is an integration dependency that must also be present. CI reads
`homeassistant/components/frontend/manifest.json` from the installed HA package
and installs its exact `home-assistant-frontend==...` requirement. Follow the same
step when reproducing setup-form tests locally; see `.github/workflows/ci.yml`.

CI has independent targets for the declared minimum **2026.11.0** and the current
stable version at matrix review, **2026.11.3**. Both Home Assistant and the official
test package are explicitly pinned per target. The workflow asserts their actual
installed versions and runs `pip check` before tests, so a passing job cannot
silently refer to a different HA version. Review and advance the explicit current
target when supporting newer releases; it is not an automatically floating target.

Do not install the retired `pytest-homeassistant-custom-component` alongside the
official package: they provide overlapping fixtures, and its last published
release pins HA 2026.10.4. The earlier green beta CI therefore did not validate
the declared 2026.11 minimum. Do not force newer HA over that dependency pin.

`pytest.ini` supplies the repository import path, function-scoped asyncio fixtures
and the official package's recommended `-p no:respx` bootstrap setting. Existing
fixture names remain compatible; no tests are skipped or assertions weakened.
The native suite covers setup forms, authorization adapter branches and real
public-Store verification/failure behavior.

## Isolated clean-install and lifecycle suite

`tests/ha/test_lifecycle.py` runs with the official disposable HA fixtures on both
matrix versions. It does not patch the integration's setup/unload functions.
Only the explicit panel-registration failure case injects a failing dependency.
Storage is handled through public Store APIs backed by the official test backend.
All entries, records, users and phone services in these tests are synthetic.

The suite checks:

- Fresh native setup without helper/to-do entities or a legacy frontend resource.
- Actual sensor/service and sidebar-panel registration, and bundled HTTP assets.
- Authorized native WebSocket panel/history access.
- Public-Store preservation and new runtime reconstruction after unload/reload
  in off, rest, active and awaiting-rating phases.
- Options-flow reload with preserved records and private-by-default phone payloads.
- Multiple entries, independent histories, shared module leases and panel cleanup.
- Removal of only the selected entry's store.
- Cleanup after a failed panel registration and refusal to reset invalid logical state.
- Actual phone-event dispatch with anonymous, wrong-tag and stale-action refusal.
- Idle-session reconciliation after downtime, retained notification and authorized
  phone Start/Close after reload, preserving the full synthetic ledger.

`tests/unit/test_idle_session.py` checks the exact 60-minute boundary, unrated
records, active-contraction protection, independent movement, schema-5 upgrade,
new session/zero interval, stale buttons, verified-save failures and notification
restoration/dismissal. Frontend coverage checks the inactivity message and absence
of a running rest caption. These do not establish physical Android delivery.

These are automated fixture-based integration tests, not a fresh OS installation
or rendered-browser/device acceptance. An unload/reload reconstruction is not a
whole Core process reboot. Physical delivery, lock-screen behavior, device
background restrictions, real network loss/reconnect and broader storage recovery
still need separate acceptance. Passing HTML/JS HTTP responses does not prove
browser execution, touch interaction or accessibility.

## Distribution validators

`test_long_contraction.py` checks the strict two-minute boundary, verified
one-attempt persistence, restart/downtime, stale callbacks, independent settings
and movement, queued Stop receipt timing, no selected phone, delivery failure
and unverified saves. Frontend tests cross the threshold without a server update,
show the alert banner and retain enabled Stop, without issuing any command.
Native lifecycle cases exercise the real scheduled callback, unload cancellation,
overdue setup, schema-7 upgrade and authorized Stop from the warning notification.
These native cases must pass in isolated CI before deployment; test definitions
or local stand-ins are not native/physical-phone evidence.

Reminder-preference tests cover manual and idle-session pauses, ordinary and
notification-based session restarts, explicit opt-out while paused, movement
logged in or out of a session, exact hourly boundaries, and schema-6 upgrades.
The native suite checks verified upgrade and pause/reload/resume with full ledger
and movement timestamps preserved. Cooldown is saved and independently read back
before notification delivery; uncertain delivery is not retried every minute.
This deliberately prefers a potentially missed reminder over duplicate alerts.
It is not a fetal-movement monitor.

CI runs the official `home-assistant/actions/hassfest` action and
`hacs/action` with category `integration` and **no ignored checks**. The HACS action
uses the repository/catalog validation code; passing it does not submit or add
the repository to the Marketplace catalog. Its result is tied to the repository,
branch/release and action behavior reported in that run.

Record actual results before marking release gates complete. Do not repair a
runtime defect by skipping a failing lifecycle test or disabling a validator.

## Manual acceptance checklist

- [ ] Install on an isolated supported HA version; no prototype files present.
- [ ] Add entries with notifications off and with an Android phone selected.
- [ ] Check generated sidebar routes and automatically loaded card resources.
- [ ] Start on the card, stop on the phone, rate on either; verify one record.
- [ ] Reverse the direction and repeat; verify start-to-start vs rest.
- [ ] Double taps/stale notifications cannot advance a later contraction.
- [ ] Reload/restart while resting, active and awaiting a rating.
- [ ] Confirm restart warning, restored data and no fabricated missing events.
- [ ] Check network loss, API errors, notification failures and reconnect.
- [ ] Confirm inactive/unauthorized users cannot fetch history or control entries.
- [ ] Check two trackers do not share records, actions, panels or notifications.
- [ ] Check option changes, disabling, re-enabling and explicit removal.
- [ ] Verify small screens, keyboard focus, accordion retention and reduced motion.
- [ ] Verify history fetch failure, long records and no unsafe HTML rendering.
- [ ] Confirm Android lock-screen cards and privacy options on a physical phone.
- [ ] Verify age-out of the recent-hour sample and time-zone presentation.
- [ ] Verify native permission/Recorder/backup disclosures in the documentation.

Do not generate fake contractions in an active real labour session just to test
the new implementation. Use synthetic fixtures in a separate instance.
