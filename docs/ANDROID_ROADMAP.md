# Standalone Android product roadmap

## Agreed boundary

- The Home Assistant integration is public and MIT-licensed, maintained through
  `DaFern/ha-contraction-tracker`, with HACS/Marketplace distribution intended.
  Public catalog inclusion still requires the relevant checks and approval.
- The future standalone Android application is a separate, proprietary product.
  Keep app-only source, signing keys, store credentials and unreleased commercial
  assets in a separate private repository, never in this repository or its CI.
- MIT permits reuse and redistribution of the integration. Publishing the
  integration cannot reserve exclusive rights over the MIT-covered portions.
  Retain the MIT notice wherever substantial covered material is reused.
- App-specific additions can remain proprietary. Audit third-party dependency,
  asset and SDK licences before choosing them or shipping the application.
- No Android project, cloud service, account system or app-store submission has
  been created by this documentation step.

## First milestone: a private design and test specification

Use the integration as a working reference, not as the Android runtime.
Document and test these portable contracts before choosing an implementation:

1. Start, stop, intensity and session lifecycle; duplicate/stale action handling.
2. Complete local ledger, stable IDs, originals/correction audits and dependent
   interval calculations; never silently drop records.
3. Rolling-hour metrics independent from the latest-six-row editing display.
4. Independent movement/settings concurrency so movement cannot invalidate Stop.
5. Explicit persistence confirmation and honest uncertain-save recovery.
6. Contact prompts that describe recorded patterns, never labour stage, dilation
   or fetal wellbeing. Reminder wording never substitutes for care-team advice.
7. Opt-in location with manual override and conservative uncertain-location
   handling. Do not silently enable background location or collect location history.

Only synthetic fixtures belong in source control. Do not seed app tests with
the owner's Home Assistant records, migration bundles or backup files.

## Second milestone: an offline-first Android prototype

Plan a standalone local database and transactional writes, independent of Home
Assistant connectivity. Evaluate native Kotlin/Jetpack components rather than
assuming browser/Python code can be copied directly into an Android application.

Specify timer anchors and clock-change/reboot behavior explicitly: monotonic
elapsed time and wall-clock record timestamps have different roles. A phone
must not report a successfully saved event merely because a button was tapped.
Test process death, interrupted writes, reboot, notification action races,
time-zone/DST changes and loss of network connectivity.

Provide explicit export, backup/import, retention and deletion behavior suitable
for sensitive personal data. Do not add analytics, advertising SDKs, cloud sync
or account requirements by default. Each requires its own product/privacy review.

## Optional later milestone: Home Assistant interoperability

Keep any HA link opt-in. Define versioned schemas, stable IDs, conflict rules,
authority over records and explicit consent before designing synchronization.
Never run two independent writers against the same logical timer without a
reviewed reconciliation protocol. The Android product should work without HA.

## Before a commercial/store release

- Establish private app repository ownership and proprietary licence/EULA terms.
- Review health-data privacy, Android permissions, notification behavior and
  background-execution requirements for supported Android versions.
- Review Google Play health-app/data-safety requirements and claims with qualified
  advice where needed. Calling software a logging aid does not by itself settle
  its regulatory classification.
- Independently test usability, accessibility, storage recovery and export/delete
  workflows. A working owner deployment is not clinical validation.
- Keep signing/release approval and store publication separate from integration
  repository changes. No live Home Assistant migration is implicit.
