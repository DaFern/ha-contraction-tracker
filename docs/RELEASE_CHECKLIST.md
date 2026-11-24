# Public beta and catalog release checklist

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
- [ ] Run Home Assistant hassfest and the appropriate HACS/Marketplace validator.
      HACS passed with no ignored checks in
      [run 45301147034](https://github.com/DaFern/ha-contraction-tracker/actions/runs/45301147034).
      Approved manifest ordering and config-entry-only schema fixes are in the
      source repository; a fresh hassfest/CI result is pending.
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
