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
Fresh CI results for these changes are pending; no warning filters or dependency
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
