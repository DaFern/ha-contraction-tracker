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
public-Store verification/failure behavior, not complete runtime lifecycle.

Full setup/unload/reload, HTTP static-path serving, actual sidebar registration,
sensor naming/renaming, multi-entry leases, broader storage recovery and mobile-event
delivery must additionally be exercised in a native HA instance before release.
Compilation or mocked component tests do not establish these behaviours.

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
