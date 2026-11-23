# Legacy import — 0.5.0b1

This optional importer supports the specific prototype ledger format described
below, not arbitrary to-do lists or medical records. A native migration and
dashboard/phone handoff were accepted on the owner's installation. That does not
prove every source configuration or failure scenario has been tested.

Keep the original recorder configuration and source records until your own
transfer has been verified and accepted. Use backups and a backup timer; an
import is not permission to delete data or start two competing recorders.

## Boundary and preserved data

The supported source is the prototype's GMT/BST textual to-do format plus its
JSON state, movement and contact-settings helpers. Source entity IDs are supplied
explicitly; none are embedded in runtime code.

Conversion preserves:

- Every item, including completed to-do items, original UID, status, summary,
  exact description, extra JSON fields and notes.
- Start/end epochs, duration, intensity, recording session numbering and
  start-to-start/rest intervals (checked against timestamps, never guessed).
- Original correction values and audit trails. Extra metadata remains in the
  complete original source item, visible under **Imported source record**.
- Current off/rest/rating/active phase and timer anchors. A valid active
  contraction is not stopped, completed or restarted by conversion.
- Available movement **last timestamp and count**, and reminder settings. The
  old helper does not contain a full movement-event ledger; none is invented.
- Manual/contact settings, defaulting only newly introduced zone fields to manual
  mode for older source versions.

New native concurrency revisions replace old button tokens. Original helper
snapshots and the full import receipt remain in native storage. Sensor
`current.import_receipt` exposes only source digest, record/session counts and
import time for supported-API verification; it never exposes old helper tokens.
Source records are never edited, marked complete or deleted by the importer.

Unknown/ambiguous formats, missing/duplicate IDs, incomplete session numbering,
overlapping/future records, inconsistent intervals/current state, invalid audit
data or oversized input are refused in full. Nothing is silently skipped or
truncated. Limits: native record capacity, 256 KiB per description and 16 MiB
canonical source snapshot and native candidate.

## Offline check

Keep private snapshots outside this portable repository:

```text
python3 tools/preview_legacy.py --source /private/path/source.json
```

The command prints only a summary and source digest. It has no apply option and
does not write a native candidate or personal data into the project.
An offline memory rehearsal is not native storage acceptance; its temporary
destination hash must never be reused for a real apply.

## Native preview/apply service

`contraction_tracker.import_legacy` is an authenticated **administrator-only**
service returning response data. An anonymous automation/phone event cannot use
it. Supply:

- `entry_id`
- `source_records` — to-do entity
- `source_state`, `source_movement`, `source_guidance` — text-helper entities
- `source_automation` — the old queued tracker automation
- `apply` — defaults to `false`

Preview returns `source_sha256`, `target_sha256`, counts, phase and incoming
settings without writing or notifying. The target must be unused and paused;
existing records or an already imported entry are never merged/overwritten.
Settings can be replaced only as reflected in the reviewed incoming preview.

For apply, provide both unchanged preview hashes as `expected_source` and
`expected_target`. Native phone notifications must be **none**. The old automation
must be off with no running/queued actions, and HA must be fully running.
The adapter brackets source reads with helper-state and stopped-queue checks,
then takes another source snapshot just before saving.

This is best-effort concurrency protection, not a cross-integration atomic CAS:
select the actual recorder that owns these sources and avoid other to-do/helper
writers during the short cutover. The importer cannot prove that an unrelated
automation or external editor will not write after the final source check.

The manager serializes one validated save, then verifies the complete
logical JSON content through a separate public HA `Store` instance. The store
uses private, atomic writes. No direct storage-file/database/registry editing is
used. Success returns `saved=true`, `verified=true` and an imported-state digest;
publishing the native state does **not** send a phone notification.
The independent reader is read-only. The same verification also
protects ordinary recording, corrections, movement/reminder and contact-setting
saves, plus saved-state schema upgrades at setup.

If saving, read-back or cancellation leaves the result uncertain, the manager
blocks further state-changing controls and history presentation. **Do not retry
blindly.** Reload the integration, inspect sensor `current.import_receipt` and
authorized history through supported HA APIs, and
review a fresh preview if the destination is still genuinely unused. No automatic
rollback overwrites a potentially successful import.

## Controlled cutover checklist

1. Confirm current backups, a backup timer and a planned short tracking pause.
2. Install the reviewed integration files and approve the required Core restart
   separately. Restart interrupts other running automations too.
3. Through **Add integration**, create an unused entry with phone notifications
   **none**.
4. Verify native setup/entities/services. Do not operate the new timer before
   import. No source data has moved yet.
5. Resolve the frontend resource handoff before UI acceptance. The old resource
   imports an older copy of the same custom-element tags; loading both versions
   can leave old classes registered. Once native static serving is confirmed,
   a reviewed compatibility shim can import the exact canonical native module
   URL while preserving old-card support. Hard-refresh the browser. Do not point
   the old shim at an unavailable native endpoint.
6. Review a native import preview. At cutover, disable new triggers without
   cancelling running recorder actions (`stop_actions: false`), wait for
   its queue to drain, temporarily avoid tracker/to-do edits, and review a fresh
   preview. Apply once with its two hashes. Verify records, originals, current
   timer anchors, movements and settings through native API read-back.
7. Replace only the existing tracker dashboard card's legacy wiring with the
   native entity/entry. Preserve its dashboard path and Home destination.
8. Configure the chosen native notification target after import is verified.
   Leave public lock-screen content off unless explicitly wanted. Confirm the new
   notification, then clear the old notification tags. Accept actual phone
   controls and confirm only one recorder is active.
9. After user acceptance and fresh dependency checks, request cleanup approval:
   retire old automation/scripts/helpers and obsolete frontend assets. Remove the
    old Lovelace resource entry through the supported UI
   before deleting files it still references. Keep the original to-do list until
   transfer verification and rollback retention are agreed; integration removal
   may require its supported UI.

If any native check fails, leave the source data intact. Rollback is a separately
reviewed re-enable/notification/dashboard operation, not permission to restore
the entire HA backup over unrelated new data.
