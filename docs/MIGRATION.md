# Migration and deployment boundaries

## New installations

The integration is self-contained under `custom_components/contraction_tracker`.
It creates its own config entries, sensors, sidebar panels and local storage.
It does not create a legacy automation/helper/to-do stack or automatically
rewrite an existing dashboard.

Create one entry per independent tracker. Phone notifications are optional.
The native frontend is registered automatically: a clean installation does not
need a manually registered legacy card resource.

## Existing native storage

Native state schemas 1–4 migrate to schema 5 while preserving recorded history.
New movement/contact/zone/provenance fields are initialized conservatively:
manual location is retained and older records receive no invented legacy source.
Setup-time schema saves must pass independent public-Store read-back.

Invalid or unsupported logical state is refused, not silently pruned. Back up
records before upgrades. Do not manually edit HA's internal storage files.

## Prototype ledger imports

The optional admin-only importer supports the original GMT/BST textual to-do
ledger and its explicit JSON helpers. It is not a general-purpose importer.
See [IMPORT.md](IMPORT.md) for the exact preservation rules, format limits,
preview hashes, pristine-target requirement and controlled cutover.

An owner deployment successfully completed native import, verification and
dashboard/phone handoff. Source records and private rollback copies were kept,
and old automation/helper/frontend resources were retired after acceptance.
Those private records, household configuration and deployment identifiers are
not part of this public repository.

Every other installation needs a fresh source review, backup, preview and
verification. Never reuse another destination's preview hashes. Do not infer
permission to stop recording, import or delete source data from installation or
packaging work. Resolve any legacy/native custom-element resource conflict and
confirm only one recorder is active before accepting a handoff.

## Working on the public project

The development checkout and a user's installed integration are separate
deployment units. A source commit, beta tag or new release archive does not
authorize copying code onto a live HA instance or restarting it.

Keep real contractions, migration bundles, credentials and backup/rollback
artifacts outside the repository. Use synthetic fixtures for development and
isolated HA acceptance tests, not fabricated events in an active real session.
