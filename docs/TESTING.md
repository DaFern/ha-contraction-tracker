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

Use a disposable compatible environment, not the live instance:

```sh
python -m pip install -r requirements-ha-test.txt
pytest tests/ha -v
```

The HA test plugin chooses its compatible Home Assistant version. Record that
version when reporting results. The minimum supported target is HA 2026.11;
before a release, also run with a plugin/core pair matching that minimum.
The fixture tests cover setup forms and authorization adapter branches.

Full setup/unload/reload, HTTP static-path serving, actual sidebar registration,
sensor naming/renaming, multi-entry leases, store I/O failure and mobile-event
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
