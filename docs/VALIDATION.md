# Beta validation evidence — 0.5.0b1

This is a public, sanitized engineering summary. Personal record snapshots,
private deployment identifiers, backup locations and household event timelines
are deliberately excluded. All committed test fixtures are synthetic.

## Scope of the beta

The owner accepted the installed integration's dashboard, Android phone
notification workflow and migration handoff. The owner also approved public
beta testing under MIT. This is manual acceptance on one installation, not
clinical validation, catalog approval or a guarantee of behavior on every phone.

Version 0.5.0b1 changes release metadata and public documentation from 0.5.0a2;
it does not change the tracking/storage logic. Release preparation does not
deploy that metadata over the owner's installed copy or operate real records.

## Local automated coverage

The dependency-free suites exercise the actual Python model/manager and
JavaScript UI/transport code with injected storage/notification callbacks and a
minimal DOM stand-in. They do not provide a real browser or HA runtime.

- Python: 92 unit tests passed for 0.5.0b1.
- Node: 31 frontend tests passed for 0.5.0b1.
- Recording/session transitions, duplicate/stale actions and receipt-time anchors.
- Full-ledger rolling-hour metrics independent of the six editable display rows.
- Corrections, original values/audit preservation and overlap/future-time refusal.
- Independent movement and contact-setting revisions.
- Conservative selected-zone resolution, freshness/accuracy/boundary refusal and
  location-appropriate recorded-pattern prompts.
- Strict complete legacy conversion, source/destination hashes, duplicate import
  refusal, source queue/freshness checks and private provenance preservation.
- Eleven mutation paths across seven ambiguous write/read/cancellation fault
  modes, pending read-back ordering and queued-action blocking.
- Full-candidate/raw-schema read-back checks, reload after an unconfirmed write,
  and frontend blocking of unverified saves and late stale history.
- Unsafe imported markup is escaped rather than executed.

Local parsing, runtime structure, English translation equality, bundled-image
signatures and runtime household-isolation checks are included in the release
checker. `--publish` additionally checks public repository/maintainer/licence
metadata; passing it is not hassfest or HACS validation.

The 0.5.0b1 local publish-mode check passed. Python/runtime-YAML parsing and a
source privacy review passed; caches, prior archives and private checkpoints are
excluded from the public source. Intentional rejection-pattern strings inside
the isolation checker are not deployed entities or test-record data.

The reproducible ZIP contains 23 runtime files, 52,688 bytes. Its CRC, scoped
paths, exact source-byte matching and two-build reproducibility were checked.
SHA-256: `38978aca3e3d5514c6bd965722cb6e0ed6a99f84e10c352e0ec0ea8a8dc9cd9a`.

## Manual deployment evidence

- Native UI setup and optional phone-target configuration were exercised.
- A duplicate empty entry was removed through the supported HA UI.
- Preview-first native import returned `saved=true` and `verified=true` after
  complete independent public-Store read-back. The source records were retained.
- Sensor receipt/current state and original source APIs were checked afterwards.
- Existing dashboard wiring was switched to the native entry without changing
  its navigation destination; mobile and desktop screenshots were inspected.
- The owner confirmed native phone display and controls worked.
- Legacy resources were retired only after acceptance. Configuration validation
  passed and unrelated automation/script definitions remained unchanged.

This is not an exhaustive isolated acceptance run. In particular, it does not
prove every service permission branch, storage fault, reload race or Android
background/lock-screen policy on physical hardware.

## CI and remaining gates

The repository workflow runs dependency-free checks and native HA tests in
separate jobs. Native CI now uses official `pytest-homeassistant` packages and
explicit matching HA/test-package targets for **2026.11.0** and **2026.11.3**.
It installs HA's declared frontend dependency, asserts both installed versions
equal the matrix target and runs `pip check` before the tests. No runtime tracking
code or release artifact changes are part of this CI migration.

The beta's original green run passed 10 native tests on HA **2026.10.4**, selected
by the retired third-party test plugin. That result is real but does not validate
the declared 2026.11 minimum. The maintainer directs projects to the official
package; the workflow no longer relies on that older plugin.

The [first exact-version matrix run](https://github.com/DaFern/ha-contraction-tracker/actions/runs/45292640042)
passed on commit `9a8046b7196467a5c24c10efbf0fa15fe5e5985f`:

| Target | Installed HA / official test package | Native results | Dependency check |
| --- | --- | --- | --- |
| Declared minimum | 2026.11.0 / 2026.11.0 | 10 passed | Passed |
| Current stable at matrix review | 2026.11.3 / 2026.11.3 | 10 passed | Passed |

The same run passed all 92 dependency-free Python and 31 Node tests. The native
cases are the same ten tests exercised on two versions, not twenty distinct
test scenarios. Warnings remain visible in the logs; no tests were skipped or
assertions weakened to obtain these results.

The follow-up commit changes only CI configuration, test requirements, pytest
bootstrap settings and documentation. Runtime files are identical to the
published beta. Its tag and downloadable artifacts remain unchanged; the release
notes link the new matrix evidence rather than implying the old tag's original
workflow tested these versions.

Still required for catalog submission and stronger compatibility claims:

- Continue running native tests on the declared minimum and an explicitly
  reviewed current stable version; advance the current target as releases change.
- Isolated clean installation without legacy resources, full lifecycle and
  restart/offline recovery, multi-entry leases and end-to-end entity permissions.
- Physical-device coverage beyond the owner's accepted Android workflow.
- A separately approved catalog submission, retaining passing hassfest and
  HACS/Marketplace validation on the candidate commit.
- Continued review of privacy, record-deletion/export limitations and safety
  wording. No labour-stage, dilation or fetal-wellbeing determination is made.

## Catalog and expanded lifecycle verification

Follow-up CI adds official hassfest and HACS integration validation with no
ignored checks, plus the isolated suite in `tests/ha/test_lifecycle.py` on both HA
targets. It covers real setup/services/panels/assets, authorized history,
unload/reload state recovery, options, multiple entries, scoped removal and
startup/event failure boundaries. The integration's setup/unload functions are
not mocked; test records and phone services are synthetic.

The [initial expanded run](https://github.com/DaFern/ha-contraction-tracker/actions/runs/45301147034)
on commit `588fdf1` produced these actual results:

- HACS/Marketplace integration validation passed with no ignored checks.
- Standalone checks/build passed.
- Hassfest failed on manifest key ordering (`domain`, `name`, then alphabetical).
  It also warned that the config-entry-only integration lacks a `CONFIG_SCHEMA`
  declaration. Neither runtime metadata nor setup code was changed to hide this.
- Each HA target passed 18 native cases, with four failures and one setup error
  in the newly added tests. The unload tests incorrectly expected registered
  sensors to disappear rather than become HA's unavailable registry placeholders;
  the phone test requested a user fixture name absent from the official package.

The test-only correction asserts the unavailable, restored, non-actionable
placeholder and uses the official `hass_admin_user` fixture. Durable phase/history
and timer-anchor assertions remain intact; no cases are skipped. Rerun results
must be recorded separately rather than treating these corrections as a pass.

The [corrected-suite run](https://github.com/DaFern/ha-contraction-tracker/actions/runs/45301704031)
on commit `eea237c636dc7e24ef7bf1a3a67a7869346d4bae` passed **23 native tests
on each of HA 2026.11.0 and 2026.11.3**, including all 13 new lifecycle cases.
Both exact-version assertions and dependency checks passed. Standalone checks,
92 Python unit tests, frontend tests and the release build also passed.
HACS passed again without ignored checks, with a non-blocking missing-categories
warning. Hassfest still failed on manifest ordering and retained its schema
warning; the overall workflow therefore failed. No runtime fix was applied.

With owner approval, the source manifest keys are now ordered `domain`, `name`,
then alphabetically, and `__init__.py` declares
`CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)`, matching its UI-only
setup. The tracking, storage and notification logic is unchanged.

The [post-fix CI run](https://github.com/DaFern/ha-contraction-tracker/actions/runs/45397920045)
on commit `b64c8d48a464eb1467455ee693046947bc1eeb71` passed all five jobs:

- Hassfest passed; the manifest ordering error and schema warning are resolved.
- HACS/Marketplace passed without ignored checks. Its non-blocking missing
  manifest categories warning remains.
- HA 2026.11.0 and 2026.11.3 each passed all 23 native tests, with matching
  official test-package versions and clean `pip check` results.
- All 92 Python unit tests and 31 frontend tests passed, along with asset,
  release-structure and archive-build checks.

Native test warnings and GitHub Actions Node-version deprecation warnings remain
visible in the logs. The earlier failing runs are retained as historical evidence.
These fixes are on the repository branch only: the published beta tag/assets and
installed integration remain unchanged. This green branch run does not validate
a newly published release artifact or authorize deployment/catalog submission.

### Warning cleanup

The approved source follow-up adds manifest categories `helpers` and
`health_wellbeing`, and upgrades GitHub Actions to checkout `v7.0.1`,
setup-python `v7.1.0` and setup-node `v7.1.0`, all using Node 24.
The [warning-cleanup CI run](https://github.com/DaFern/ha-contraction-tracker/actions/runs/45404659668)
on commit `265fd82ca9a7752a4071809aebf158f66e5014d8` passed all five jobs.
The missing-categories, Node 20 and action `punycode` warnings are absent.
Hassfest and HACS passed without ignored checks; both HA targets passed all
23 native tests and dependency checks. All 92 Python and 31 frontend tests,
asset checks and the release build passed. No warning filters or dependency
overrides were added.

The five native Python warnings per target come from upstream code: one
aiohttp application-inheritance deprecation in Home Assistant's HTTP server and
four deprecated `asyncio.iscoroutinefunction` uses in `backoff`. They remain
visible on the exact pinned HA targets. Tracker code does not generate these
warnings, and patching or replacing HA's dependencies would invalidate the
matched-version evidence. The installed tracker and published beta remain unchanged.

Even a green run does not establish a whole Core process reboot, real-browser
rendering/accessibility, actual Android notification delivery or physical-device
offline/reconnect behavior. Those remain separate acceptance work, and a green
HACS action does not itself make a catalog submission.

See [TESTING.md](TESTING.md) and [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md).

## 0.5.0b2 idle-session candidate

The approved follow-up closes a completed session after 60 minutes without
another contraction, retaining a persistent Start/Movement/Close notification.
Start creates a fresh session with no cross-session interval; Close dismisses it.
All existing records, original values, revisions and provenance are preserved.
No active contraction is automatically ended; an unanswered rating remains
Not rated. Movement/settings activity does not extend the contraction deadline.

Stored schema 5 upgrades to 6 by adding `idle_ended: false`; the setup adapter
independently verifies this write before reconciling overdue idle state. Idle
closure itself also requires verified persistence before publishing/notifying.
Existing manually closed sessions do not acquire a notification on upgrade.

The [idle-session CI run](https://github.com/DaFern/ha-contraction-tracker/actions/runs/45407772869)
on commit `f54e463c7cd0e734673054626c350ad68f4c8451` passed all five jobs:
102 Python unit tests, 32 frontend tests, 25 native tests on each of HA
2026.11.0/2026.11.3 with clean dependency checks, hassfest, HACS and release build.
The two added native cases cover downtime reconciliation and authenticated
notification Start/Close while preserving the full synthetic ledger.

After owner approval, the installed copy was backed up, the committed runtime
was deployed and byte-verified, and the configuration check passed. The restart
request returned 502; after the required 60-second grace period, Core reported
RUNNING on HA 2026.11.1 with the integration loaded and Supervisor healthy.
The pre-existing record count and recent-history fingerprint were unchanged.
An authenticated mobile-width screenshot showed the paused tracker and existing
history. No synthetic contractions or phone actions were sent to the live ledger.
Physical-phone timeout/Start/Close acceptance remains unverified.

The published 0.5.0b1 tag/assets remain unchanged; 0.5.0b2 has not been published
as a GitHub release. Deployment is not catalog approval or clinical validation.

### Icon-only sidebar navigation

The approved frontend follow-up replaces the Home link with a hamburger button.
It emits Home Assistant's `hass-toggle-menu` event with bubbling and composed
delivery across shadow roots, without navigation or a tracker command. Only the
icon is visible; `aria-label="Open sidebar"` supplies its screen-reader name.
The frontend module query includes `ui=sidebar1` to avoid stale cached modules.
The release version remains the unpublished 0.5.0b2 candidate.

Two additional frontend tests check the icon-only markup and actual click-handler
dispatch using the DOM stand-in, including no tracker service call or state
change. The [sidebar follow-up CI run](https://github.com/DaFern/ha-contraction-tracker/actions/runs/45418661035)
on commit `e4deec37a8bf82c9b85f83bbe35d5a4b3bcadf44` passed all five jobs:
102 Python tests, 34 frontend tests, 25 native tests on each HA target,
dependency checks, hassfest, HACS and release build.

The two changed runtime files were deployed and the complete installed package
was checked against committed source. Configuration validation passed. The
approved restart returned 502; after the required 60-second wait, Core reported
RUNNING with the integration loaded. The record count and recent-history
fingerprint were unchanged. An authenticated 430-pixel screenshot confirmed the
hamburger icon with no visible label and the retained tracker layout.
This screenshot did not click the live menu; event dispatch is covered by the
frontend test, while physical-phone interaction remains owner acceptance.

### Remembered reminder opt-in and header presentation

The approved follow-up adds stored schema 7 with `movement.preferred`, separate
from the session-active `movement.enabled`. Manual session stop and inactivity
pause reminders without removing consent; new recording sessions resume only a
previous opt-in. Explicit Off removes that preference, including while paused.
Migration copies only the old current Enabled value, never inferring consent
from an old timestamp. Existing Off settings therefore stay Off.

Recording starts preserve movement timestamps and cooldown. A reminder is due
only while recording, after at least one hour since the latest of logged
movement, initial enable and the previous attempt. A recent movement suppresses
it, including a movement logged while recording was paused. A resumed overdue
reminder can be sent on the next scheduler check. The hourly attempt is saved
and independently verified before delivery, preventing minute-by-minute retries
after ambiguous phone delivery; a failed attempt can consequently be missed.
No alert is a clinical assessment of movement or wellbeing.

The header text is centred independently of its decorative icon; the phone icon
is replaced by an icon-only bell/refresh symbol. Screen-reader naming remains.
The [reminder/header CI run](https://github.com/DaFern/ha-contraction-tracker/actions/runs/45464334205)
on commit `06c500f7d076add7d9a1c76a035f67e368f3493a` passed all five jobs:
113 Python tests, 37 frontend tests, 27 native tests on each exact HA target,
dependency checks, hassfest, HACS and release build. Upstream Python warnings
remain visible, not suppressed.

A normal Home Assistant backup completed before the stored-settings upgrade;
no removed code rollback folders were recreated. Seven changed runtime files
were deployed and the complete installed package was verified against source.
Configuration validation passed. Following the approved restart (502 response)
and 60-second grace period, Core reported RUNNING with the integration loaded.
The existing record count and recent-history fingerprint were unchanged, with
no persistence uncertainty. The previously Off reminder remained Off, requiring
one explicit enable to establish future remembered opt-in.

An authenticated 430-pixel screenshot confirmed the centred title, decorative
icon, icon-only bell/refresh button and intact recording controls/history.
The normal restored-session warning remained visible. Synthetic reminder and
session tests were not run against the live ledger; physical-phone reminder
delivery and pause/resume acceptance remain unverified.

### Timed long-contraction warning — repository implementation

The owner approved adding a live two-minute timer warning after review of NHS
and NICE guidance on 25 November 2026. The rule describes the manual timer, not
a diagnosis. A visible banner asks for urgent maternity contact if the
contraction is continuing, or stopping/correcting an accidentally running timer.
Stop remains available; no end time or clinical event is fabricated.

The HA adapter schedules a dedicated callback at 121 seconds after the recorded
start, with stale-identity checks and unload cancellation. The serialized manager
independently verifies one attempt marker before a configured phone alert, never
rotating the Stop token. Schema 7 upgrades to 8 by adding an initially false
marker. Claimed attempts survive restart and are not retried after ambiguous
delivery; an overdue, unclaimed active contraction is checked after setup.
The phone alert preserves existing lock-screen privacy and supports authorized
Stop. The UI warning remains independent of the attempt marker.

Local results: 125 Python unit tests, 39 frontend tests, release-structure checks,
native-test syntax and diff checks passed. Three new native lifecycle cases are
written but **not yet run**; CI and distribution validators for this candidate
are pending. No live synthetic events, deployment, restart, publication or tag
changes were performed during local development. The owner subsequently approved
commit/push, isolated CI and deployment only if every check passes. Those CI and
deployment results remain pending; activation requires restart approval.

Physical-phone alert delivery, timing and real-browser interaction are not
established by these local tests. No alert must be interpreted as reassurance.
See [the warning rules](CONTACT_PROMPTS.md#timed-long-contraction-warning).

The [first warning CI run](https://github.com/DaFern/ha-contraction-tracker/actions/runs/45595584697)
on `a4607d5` passed standalone tests/build, hassfest and HACS. Both exact native
targets reported **28 passed, 2 failed**: the new timer tests froze wall time but
the Tracker's default clock function had been captured at module import.
The test correction explicitly injects a clock that follows the freezer into
the real Tracker, including on reload. HA's scheduler, setup/unload, persistence
and all warning assertions remain unchanged; no runtime code, thresholds or
checks are changed or skipped.

The [corrected-clock CI run](https://github.com/DaFern/ha-contraction-tracker/actions/runs/45596103337)
on commit `d512d681105e130ec556972be41740e1e7e51621` passed all five jobs:
125 Python unit tests, 39 frontend tests, all 30 native tests on each of HA
2026.11.0 and 2026.11.3, exact-version/dependency checks, hassfest, HACS and the
release build. No runtime change was needed to correct the fixture clock.

After this green run and completion of a normal HA backup, the eight changed
runtime files were deployed. All 23 installed runtime files matched the tested
source bytes. Configuration validation passed. The existing record count and
recent-history fingerprint were unchanged. A mobile-width screenshot confirmed
the inactive tracker and retained layout/history; it did not simulate an active
contraction or establish warning delivery. No synthetic live events were sent.

The owner then explicitly approved activation. The restart call returned 502;
after the required 60-second grace period, Core reported RUNNING and Supervisor
healthy. The tracker exposed its new warning-state field with no persistence
uncertainty, confirming the upgraded backend loaded. The pre-existing record
count and recent-history fingerprint were unchanged, and the tracker stayed
inactive. No synthetic contraction or alert was sent to the live installation.
Physical-phone warning delivery and an actual threshold crossing remain
unverified on the live installation. No published release, tag or download
was changed.

### Fractional-second deadline regression

The [activation-evidence run](https://github.com/DaFern/ha-contraction-tracker/actions/runs/45597317787)
on `ef561aa` subsequently failed one threshold test on HA 2026.11.0, despite the
two preceding green runs. Investigation reproduced a real subsecond scheduling
error: calculating the delay from an integer-truncated current clock placed the
callback up to almost one second after the intended recorded-start + 121-second
deadline. This was not solely a fixture issue.

With owner approval, the delay now uses the full-precision current clock.
The recorded start, strict over-120-second guard, attempt policy and Stop token
are unchanged. Unit and native cases cover scheduling offsets 0, 0.2, 0.8 and
0.999 seconds, retaining the no-early-warning and exactly-one-attempt assertions.
Fresh CI results are pending. This correction is source-only; no deployment or
restart is authorized as part of this follow-up.
