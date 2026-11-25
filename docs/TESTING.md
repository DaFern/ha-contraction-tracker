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

### Support footer source preview (issue #2)

The source candidate adds one optional support section after the unchanged
connection/recording footer row. The shared card supplies the native panel too.
It uses an original inline SVG cup and the fixed HTTPS creator page with
`target="_blank"`, `rel="noopener noreferrer"` and `referrerpolicy="no-referrer"`.
There is no embedded widget, remote image, payment/account configuration,
state/token query string or donation-related tracker notification. All features
remain available without supporting; no payout/verification status is claimed.
The footer display name does not change the existing MIT licence notice.

The module's existing `ui` query-key convention is advanced to
`support-footer1`; JS imports and the CSS URL inherit that key. The version/tag
and published downloads are not changed by developing these sources.
README and `.github/FUNDING.yml` use the same confirmed `Badger182` page.

With Node supporting built-in WebSocket and a local Chromium installation:

```sh
node tests/browser/support_footer.mjs
```

Set `CHROMIUM` if the binary is not `/usr/bin/chromium`. Optionally set
`SUPPORT_PREVIEW_DIR` to an existing output directory. The runner uses the
OpenCode cache when present, otherwise the system temporary directory.
It serves only the development frontend and a synthetic fixture on loopback;
it never connects to live Home Assistant, reads records or requires credentials.

Local source validation passed **143 Python unit tests**, **42 frontend tests**
(including three support regressions), release validation and the integration
archive build. The Chromium runner passed **48 rendered cases**: 320/430/1280px,
light/dark surrounding themes, card/panel/legacy/editor-preview, online/offline.
It checks one footer, normal flow below controls, no horizontal overflow,
44px minimum link height, at least 4.5:1 text/link contrast against the card's
gradient endpoints, native keyboard activation and no tracker commands.
The tracker retains its existing dark card palette inside both HA theme
surroundings; no unrelated theme conversion was introduced.

No non-loopback page requests were observed. Keyboard activation was intercepted
by the **test fixture only**, before external navigation, so no payment page
was visited and no transaction attempted. The production link has no custom
click handler. These tests verify safe link attributes, not payout status or an
actual payment/referrer exchange with the external site.

320px light and 1280px dark synthetic screenshots were visually reviewed: support
text/link wrapped cleanly, keyboard focus was visible, and the existing
connection status, Stop recording and movement/history controls remained visible.
Screenshot/results artifacts are private local test output, not repository
assets or production screenshots. Installed HA rendering/physical phone
acceptance, fresh native/distribution CI, commit/push and deployment remain
separate pending steps for this uncommitted UI candidate.

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

### Native automation candidate

`tests/ha/test_automation_entities.py` covers all 22 entities on one device,
stable IDs/discovery compatibility, native units/timestamps, verified activity
ordering, equal successive records, corrections, save uncertainty, per-entry
isolation, disabled entities and cleanup. Four fractional offsets exercise the
real deadline with no phone, including reload and unchanged storage. Startup
inactivity closure is distinguished from restored event history.

`tests/ha/test_blueprints.py` expands all three actual source blueprints using
HA's Blueprint/BlueprintInputs and validates the expanded configurations with
the native automation schema. It uses the real automation engine and disposable
tracker services for start/end/rating selection, equal records, restoration
filtering, real downtime closure, cooldown and timer Stop/reload cancellation.
No production automation is created. The files join the existing exact-version
CI matrix automatically via `pytest tests/ha -v`; definitions are not passing
test evidence until that matrix has actually run.

The first automation matrix run, `45608262555` on `5774039`, was cancelled after
both native targets completed the same 18 cases and then stalled at the
cooldown test. This was partial native evidence, not a passing suite. The timed
blueprint tests now dispatch actual tracker services without the lifecycle
helper's full task drain while a script deliberately waits. They observe the
real script's delay/wait phase, advance fixture time, and drain all tasks only
after the wait completes or is explicitly cancelled. All previous behavioral
assertions remain; no HA scheduler, automation execution or blueprint action
is mocked or disabled.

`pytest-timeout==2.4.0` provides a 60-second per-test wall-clock thread watchdog,
including teardown, independent of frozen asyncio time. CI also requests a
30-second faulthandler dump and live captured output, with a 15-minute native-job
cap. A stuck case therefore emits diagnostics and fails rather than silently
consuming hours. The exact official HA/test-package pins and `pip check` remain.
The corrected native run must confirm this test-sequencing diagnosis; it is not
evidence that production cooldown behavior was faulty or has been changed.

### Warning cleanup ordering follow-up

`tests/unit/test_warning_cleanup.py` checks stable bounded per-contraction tags,
no pre-threshold or active warning clears, completed-record-only cleanup,
zero-duration boundary/unload presentations, and every delivery permutation of
a new warning plus the previous contraction's cleanup/legacy retirement.
The visible-notification dictionary models exact-tag replacement/removal only;
it is not an Android/FCM emulator or transport delivery proof.

Native lifecycle coverage captures the real adapter's notification-service
payloads, then delivers early/previous clears after the warnings. It also checks
active reload preservation, one persisted warning attempt, subsequent contraction
isolation, unchanged verified records/tokens, stale/anonymous warning actions
and authorized legacy Stop compatibility. The four existing fractional-deadline
cases use the new tag while retaining the full threshold/reload/phone-Stop checks.

Local checks passed 148 Python unit tests, 42 frontend tests and release
validation. The follow-up native matrix must pass before any deployment.
No live timer, record, notification or installed integration is changed by
these isolated checks; source changes alone do not repair an installed phone
notification. See [warning cleanup limits](CONTACT_PROMPTS.md#warning-cleanup-and-delayed-delivery).

The first follow-up matrix, run `45707721060` on `f9e4cad`, passed standalone
checks, hassfest and HACS but each native target reported **65 passed, 1 failed**.
The updated unload-recovery test tried to read `entry.runtime_data` after HA had
correctly removed it. The test now derives the warning tag from its captured,
verified stored-state snapshot, retaining every unload/overdue/one-attempt
assertion. No additional runtime change was needed for that test correction.
Fresh native results remain pending.

The no-phone unit expectation now requires scheduled **state evaluation**, not
no schedule: the deadline must publish the over-two-minute state with no
notification marker write. Clock rollback tests retain the one-phone-attempt
policy while rearming derived state evaluation.

`test_long_contraction.py` checks the strict two-minute boundary, verified
one-attempt persistence, restart/downtime, stale callbacks, independent settings
and movement, queued Stop receipt timing, no selected phone, delivery failure
and unverified saves. Frontend tests cross the threshold without a server update,
show the alert banner and retain enabled Stop, without issuing any command.
Native lifecycle cases exercise the real scheduled callback, unload cancellation,
overdue setup, schema-7 upgrade and authorized Stop from the warning notification.
These native cases must pass in isolated CI before deployment; test definitions
or local stand-ins are not native/physical-phone evidence.
The two advancing-time tests explicitly inject a clock following the freezer
into the real Tracker, avoiding its import-time default time.time reference.
They do not mock HA's scheduler, integration setup/unload or persistence.

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
