# Architecture

## Boundaries

`model.py` is a copy-on-write state machine. `manager.py` serializes
commands, persists each changed candidate, publishes the committed snapshot, then
sends the notification. These two modules have no Home Assistant dependency.

The HA adapter owns `Store`, native service registration, entry lifecycle, the
session sensor, authenticated WebSocket history, native entity-permission checks,
and the Android notification listener. Per-entry state is in `entry.runtime_data`.
Only a frontend-module reference count is shared at integration level.

The bundled frontend has no third-party JavaScript dependencies. It reads a
bounded session sensor and an authorized record window for the visible editable
rows/history. Native hourly figures are calculated from the full server ledger,
not this bounded window. The explicitly configured prototype adapter reads its
own to-do ledger to calculate full-hour figures. No record is embedded in a static asset.

## State machine

| Phase | Accepted transitions |
| --- | --- |
| `off` | `show` → fresh session in `rest` |
| `rest` | `start` → `active`; `end` → `off` |
| `active` | `stop` → saved record, `rate` |
| `rate` | `Mild`, `Moderate`, `Strong` → update that same record, `rest` |

`movement`, `reminders_on` and `reminders_off` use a separate revision and never
invalidate a contraction's Stop button. `intensity` opens a secondary rating
notification so Android's three-action limit does not hide Movement.

`notify` refreshes presentation without resetting timings. `show` while already
tracking also refreshes without resetting. These non-mutating actions do not
rotate the revision. Changed candidates receive a new random 128-bit revision.

Other state-changing controls require the exact current revision and phase.
The manager rechecks them inside its lock. A stale/double Stop cannot end a
subsequent contraction, and rating updates the existing record rather than
creating another. Authentication and native permissions remain mandatory:
the revision is a concurrency guard, **not** an access credential.

## Persistence and failure semantics

1. Capture server receipt time before waiting for a busy tracker lock.
2. Validate the revision/phase and create an isolated candidate.
3. Await `Store.async_save` and compare a fresh, independent public-Store read-back.
4. Only after a complete match, publish the verified candidate and update the entity.
5. Attempt a bounded push while preserving ordering.

A push failure never reverts saved timing. An unverified save leaves the
last-verified in-memory state unchanged, surfaces an **unconfirmed save** warning,
and blocks further controls rather than claiming the candidate was recorded.
A disk write whose acknowledgement failed can remain uncertain; restoration
validates whatever was actually stored. See [verified persistence](#verified-persistence).

The serialized store is schema-versioned and validated on load. Corrupt or
future-format data is refused, not silently converted to an empty session.
At the history cap a new Start is rejected rather than pruning personal records.

Clock rollback during an active session is rejected. Durations, intervals and
rest periods are wall-clock server measurements, so server time synchronization
and connection latency remain limitations. No reconstruction of lost offline
events is attempted.

## Native API

- Service: `contraction_tracker.command`
  - `entry_id`, `command`, current `token` for state-changing commands.
  - Optional response containing the current bounded snapshot.
  - Authenticated callers require control permission on the tracker entity.
  - HA's internal automations can have no user context; those are trusted native
    service callers, not anonymous network requests.
- WebSocket: `contraction_tracker/history`
  - `entry_id`, `limit` from 1 to 500; default 50.
  - Requires an authenticated connection and read permission on the entry's entity.
  - Only loaded tracker entries are accessible.
- Mobile actions:
  - Entry-specific notification tag, command and revision.
  - Require the Companion event's HA user context and native control permission.
  - Incoming phone timestamp is not trusted; use event receipt time.

Static code and images are public, as normal HA static resources are. They
contain no records, credentials, phone registration data or per-entry settings.

## Recent patterns

Averages use all completed records starting in the rolling last hour. The count
includes an active contraction. Start-to-start averages include an interval only
when both starts are in the hour and the same recording session.
The latest six completed rows are a separate display, not the statistics sample.
Descriptive trends compare three previous measurements with three recent ones:
at least a 20% change in mean duration/interval, or a two-point change in summed
ordinal ratings. All three ratings must be present in both groups.

These are UI noise filters, **not validated clinical thresholds**. There is no
labour-stage classifier, dilation estimate, urgency score, fetal assessment,
birth prediction or clinical reassurance.

## Corrections and optional movement logging reminders

Schema 3 added independent, manually selected contact-prompt settings. Schema 4
adds opt-in selected-person/zone settings; schema 1–3 stores migrate in memory,
validate, and persist before native runtime
exposure; existing timers, revisions, movements and records are retained.
`guidance.py` computes contact wording from individual current-session starts,
not hourly averages. Settings use their own revision and the same persistence
lock, with entity-control authorization at the HA service boundary.
The generic frontend and live adapter expose the same location/interval form.
See [CONTACT_PROMPTS.md](CONTACT_PROMPTS.md) for trigger definitions and limits.
`location.py` is a dependency-free conservative resolver. The HA adapter injects
current selected entity state without persisting coordinates. Location refresh
uses the manager lock but performs no ledger write or token rotation; only changed
coarse locations refresh notifications. See [LOCATION.md](LOCATION.md).

Schema 5 adds optional per-record legacy provenance and a private import receipt;
only its source digest/count/time summary appears in sensor snapshots.
Schema 1–4 migration adds empty provenance without
changing records. `legacy.py` converts complete generic source snapshots without
I/O; `migration.py` reads supported HA services/helpers with queue/freshness checks.
Admin-only preview/apply uses the manager lock, source/destination hashes and an
independent public Store read-back. Uncertain imports block further writes rather
than overwriting a potentially successful save. See [IMPORT.md](IMPORT.md).

## Verified persistence

HA 2026.11.1 `Store.async_save` can log/suppress write errors or defer a write
while stopping. Awaiting it alone is not proof that a recording reached storage.
Version 0.5.0a2 uses a shared `verified_save` path for every tracker mutation:
start/stop/rating/end, corrections, movement/reminder controls, contact/location
settings, reminder bookkeeping, legacy import and setup-time schema upgrades.

The manager lock spans candidate validation, private atomic public-Store save,
independent read-only public-Store load, raw canonical JSON digest comparison,
and promotion/publication. Read-back must match the entire candidate, including
originals/audits/settings, before notification of success. Raw comparison happens
**before** schema migration so an old on-disk schema cannot normalize into a
false positive for a suppressed upgrade write. Missing verification capability
refuses the write before touching storage.

A write/read-back exception, mismatch or cancellation conservatively latches
`current.persistence_uncertain` and `persistence_failed` (plus `import_uncertain`
for imports). The candidate is not promoted. Commands, edits, settings, imports
and history access are blocked. Background ticks/location refreshes cannot
write, send reminders or send actionable state notifications while uncertain.
The frontend disables controls and hides cached editable history. No automatic
retry or rollback overwrites a possibly successful write. A reminder is delivered
before its bookkeeping write; that already-sent reminder cannot be recalled,
but an unverified bookkeeping save blocks subsequent reminders.

Use a backup timer, let any interrupted storage work settle, then reload and
inspect saved records, current timer and settings through supported APIs before
deciding what to retry. Reload loads storage afresh; it does not prove that the
failed action was saved. These guards are not cross-process CAS or a guarantee
against later corruption/power loss, and do not replace backups. Native Store
and lifecycle tests remain unrun in this shell; see [VALIDATION.md](VALIDATION.md).

Native corrections use an independent per-record revision. They reject future or
overlapping start/end times, append a before/after audit entry and retain the
original values. Dependent durations, intervals, rests and the current snapshot
are recomputed in a single candidate and persisted atomically through the manager.
They never start recording or reset an active contraction's start time.

Movement logging stores the last logged timestamp and a revision/count, not a
clinical assessment or a movement target. The optional reminder is initially off.
When enabled during recording, its baseline is the later of the last log,
enabling time and previous reminder. It can remind after 60 minutes, with a
minute-resolution scheduler. Disabling it or stopping recording cancels it.
It is not a recommendation to wait an hour for reduced movement.

The generic prototype transport is an explicitly configured compatibility adapter;
it contains no household IDs. Its native to-do service has no atomic CAS. The live
prototype serializes corrections, compares the exact record read by the editor,
updates only the corrected and affected neighboring records, and verifies read-back.
Uncertain saves are not automatically retried. The standalone native store path
does not depend on this compatibility adapter.

## Frontend lifecycle

Register static paths using `async_register_static_paths`; register/remove the
bundled module using the frontend's supported extra-module API. Per-entry
sidebar panels use `panel_custom.async_register_panel`. Existing dashboards and
resource registries are not edited.

The portable element is `contraction-tracker-app-card`, deliberately different
from the prototype card's tag so they can coexist during a later approved test.
No importer, migration or live replacement is included in this alpha.
