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

Consult the matrix workflow for the specific commit: adding targets is not a
passing result, and queued/failed jobs must not be described as passed. Native
tests remain distinct from the 92 dependency-free tests and the owner's live
acceptance. The new targets' results are reported after both complete; release
notes are updated only after both pass. The beta's published tag and artifacts
remain unchanged.

Still required for catalog submission and stronger compatibility claims:

- Native automated results on the declared minimum and current supported HA
  versions, not just whichever version the test plugin selects.
- Isolated clean installation without legacy resources, full lifecycle and
  restart/offline recovery, multi-entry leases and end-to-end entity permissions.
- Physical-device coverage beyond the owner's accepted Android workflow.
- Passing hassfest and HACS/Marketplace validation and a separately approved
  catalog submission.
- Continued review of privacy, record-deletion/export limitations and safety
  wording. No labour-stage, dilation or fetal-wellbeing determination is made.

See [TESTING.md](TESTING.md) and [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md).
