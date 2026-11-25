# Public beta and catalog release checklist

## Beta 0.5.0b2 preparation

The owner approved preparation and publication as a **prerelease**. Beta-1's tag
and downloads must remain unchanged. Marketplace submission is not approved.

- [x] Runtime manifest/constants `0.5.0b2`; npm `0.5.0-beta.2`.
- [x] Runtime source `79357fe` passed all five jobs in
      [CI 45708091239](https://github.com/DaFern/ha-contraction-tracker/actions/runs/45708091239):
      148 Python, 42 frontend and 66 native cases per exact HA target.
- [x] Approved owner deployment/restart recovered; owner confirmed the phone fix.
- [x] Reviewed tracked paths and scanned source for private records, identifiers,
      snapshots and credential-shaped values. Reviewed scanner matches: the
      browser runner's generic cache-path fallback and the release validator's
      forbidden household-reference literals are tooling, not private records.
- [x] ZIP contains only 27 runtime files; each matches release source. Two builds
      produced identical bytes. Checksum and size appear in the release notes.
- [x] Release notes disclose remaining clean-install/offline/device limits.

The publication record is the GitHub prerelease and its immutable target tag;
do not treat this preparation checklist as proof that an upload has completed.
The checklist below retains the historical beta-1 evidence and broader gates.

## Approved product and licensing decisions

- [x] Public Home Assistant integration: `DaFern/ha-contraction-tracker`.
- [x] MIT licence, copyright 2026 Badger182; redistribution is permitted.
- [x] Future standalone Android app stays separate and proprietary.
- [x] Owner approved a public beta based on live dashboard/phone acceptance.

The owner's beta acceptance is not evidence that unrun automated tests passed.
Do not label the product clinically validated, fully tested or catalog-approved.

## Before uploading source and publishing a beta artifact

- [x] Replace both `OWNER` manifest URLs with the approved repository URLs.
- [x] Set `manifest.json` codeowners to `@DaFern`.
- [x] Set runtime manifest/constants to `0.5.0b1` and npm metadata to
      `0.5.0-beta.1`; verify the archive and tag before publication.
- [x] Audit the complete source/export for secrets, private migration snapshots,
      medical records, household identifiers and local operational evidence.
- [x] Keep personal checkpoints, rollback copies, caches and old archives out of Git.
- [x] Update public validation/migration documentation without publishing private
      source records or identifiers.
- [x] Run Python/frontend tests: 92 Python and 31 Node tests passed locally.
      Native remote results remain distinct; see the commit's workflow run.
- [x] Run `python3 tools/check_release.py --publish`.
- [x] Review the generated archive, paths, source matching and checksum;
      two builds produced identical bytes.
- [x] Publish `v0.5.0b1` as a GitHub **prerelease**, not a stable/1.0 readiness claim.
      Its tag/artifacts remain unchanged by follow-up CI-only commits.

Public repository creation and beta publication have been approved. Do not infer
permission to publish any separate Android code, private snapshots or live data.

## Remaining verification and catalog gates

- [x] Run the existing ten native HA tests on the minimum and current stable
      versions in isolated runners. Official-package targets 2026.11.0 and
      2026.11.3 each passed all ten cases, exact-version assertions and `pip check`
      in [run 45292640042](https://github.com/DaFern/ha-contraction-tracker/actions/runs/45292640042).
      This does not complete the broader lifecycle/clean-install checklist.
- [ ] Complete isolated clean-install, browser, restart/offline and physical
      Android acceptance; distinguish these from the accepted owner deployment.
      The fixture-based setup/lifecycle suite passed on both HA targets:
      23 native tests each in [run 45301704031](https://github.com/DaFern/ha-contraction-tracker/actions/runs/45301704031).
      This is not a substitute for real browser,
      complete process-reboot or physical-device/offline acceptance.
- [ ] Review auth boundaries, storage validation, unload/reload and record deletion.
- [ ] Review compatibility with the intended HACS/Marketplace version.
- [x] Run Home Assistant hassfest and the appropriate HACS/Marketplace validator.
      Both passed on source commit `b64c8d4` in
      [run 45397920045](https://github.com/DaFern/ha-contraction-tracker/actions/runs/45397920045),
      with no ignored HACS checks. All 23 native tests passed on each HA target;
      standalone tests/build passed. Non-blocking categories and action-version
      warnings remain visible. The published beta tag/assets remain unchanged.
      Follow-up categories and Node 24 action upgrades passed all five jobs in
      [run 45404659668](https://github.com/DaFern/ha-contraction-tracker/actions/runs/45404659668)
      on `265fd82`; categories/Node 20/punycode warnings are absent. Upstream
      HA/backoff Python warnings are documented separately in
      [VALIDATION.md](VALIDATION.md), not suppressed.
- [x] Initial beta CI passed on the published commit, but its native tests ran
      on HA 2026.10.4. Do not treat that as minimum/current-version validation.
- [x] Confirm the official-package minimum/current matrix passes on pushed
      follow-up commit `9a8046b`; record the results in validation evidence.
      The beta notes link that follow-up evidence without moving the release tag.
- [ ] Submit to the catalog only after the required checks pass and submission is
      separately approved. A public repository alone does not create a listing.

## Already prepared

- Single `custom_components/contraction_tracker` runtime directory.
- UI setup/options, versioned manifest, service metadata and English translation.
- Bundled card, CSS, original PNG brand assets and notification image.
- Documentation and local test/build tooling.
- Reproducible local alpha ZIP build.

The brand marks are original project assets, not third-party emoji.
HACS-compatible structure is **not** a listing, endorsement or medical validation.

The installed integration is a separate copy from this development project.
Release preparation must not overwrite it, restart HA, operate the live timer or
alter real records. Runtime deployment always needs separate approval.
