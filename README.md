# Contraction Tracker

A calm, phone-first contraction logger for Home Assistant: one shared timer,
actionable Android notifications and a compact app-style card with expandable
patterns and history.

**0.5.0b2 · development candidate.** Published beta: **0.5.0b1**.

This integration is offered for public testing, with HACS/Marketplace distribution intended.
Its directory layout is compatible with those tools; catalog inclusion has not
been granted. The owner accepted the live dashboard and Android notification
workflow. That is manual acceptance, not a claim that all automated native HA
tests or isolated fresh-install checks have passed.

> A logging aid, not a medical device. Contraction timing and reported intensity
> cannot determine labour stage, dilation, fetal wellbeing or when birth will
> occur. Follow your maternity team's advice, not this tracker. Keep a backup
> timer. This integration requires Home Assistant and a working connection.

## What is included

- UI configuration; optional Android Companion notification action.
- An independent tracker per config entry, with its own local history.
- A bundled sidebar app and custom card; JavaScript registers automatically.
- An icon-only menu button opens Home Assistant's sidebar without leaving the
  tracker. Its accessible name is available to screen readers, not shown as text.
- The title is centred between the menu and icon-only bell-refresh notification
  control; refreshing a notification does not start or stop a contraction.
- Start → Stop → Mild / Moderate / Strong; both interfaces use the same state.
- A visible warning when an active timer passes two minutes, plus one phone
  alert attempt per contraction if notifications are configured. It asks you to
  contact maternity urgently if the contraction is still continuing, or stop and
  correct a timer left running accidentally. It never automatically stops the
  timer, changes a record or diagnoses a complication. See
  [the warning rules and limitations](docs/CONTACT_PROMPTS.md#timed-long-contraction-warning).
- True rolling-hour average duration, average start-to-start interval and start
  count (including an active contraction), calculated from the full history.
- The last six completed contractions always visible, even across recording
  sessions or when older than an hour; tap a row to correct it.
- Corrections to start/end/intensity with original values, audit trails,
  optimistic revision checks, overlap rejection and dependent interval updates.
- Movement logging on the card and Android notification, independent of the
  contraction timer.
- Plain-text phone notifications: last length, hourly average interval and
  average length on separate lines, followed by short bullets. The phone-only
  **Close** button still stops recording; the card keeps **Stop recording**.
- After 60 minutes since the last contraction ended, an idle session closes
  automatically without changing its records. The persistent phone notification
  stays available: **Start** starts a contraction in a fresh session, with no
  interval carried across the gap; **Close** dismisses it. Movement logging stays
  independent and does not prolong a contraction session.
  An unselected intensity remains **Not rated**. An actively running contraction
  is never automatically stopped or assigned a fabricated end time.
- Manual location (**Not specified**, **At home**, **In hospital / birth centre**)
  or opt-in **Automatic · selected zones**, plus an editable whole-minute
  care-team contact interval under **Contact prompts & location**. Defaults:
  manual/not specified, five minutes.
- Automatic mode requires an explicitly chosen person, home zone and 1–3 hospital
  zones. Fresh, accurate GPS wholly within one selected zone is required;
  uncertainty never means home, and hospital presence never means admission.
  Manual override is always available. No external geocoding or extra coordinate
  history is added; [location rules](docs/LOCATION.md) explain the limits.
- Recorded-pattern contact prompts, not labour-stage or hospital-travel decisions.
  See [contact-prompt rules](docs/CONTACT_PROMPTS.md) before using these.
- Preview-first, administrator-only legacy importer with source/destination
  revision guards, preserved source notes/IDs and verified native storage
  read-back. A migration and live handoff were completed and accepted on the
  owner's installation; every other installation still needs its own backup,
  preview and verification. See [IMPORT.md](docs/IMPORT.md).
- Ordinary recording, corrections, movement and contact-setting writes also
  require independent storage read-back before success. Uncertain saves block
  controls until reload and inspection; see [storage safety](docs/ARCHITECTURE.md#verified-persistence).
- An optional **60-minute no-movement-logged reminder**, off by default, with a
  switch. Once enabled, the opt-in is remembered: stopping recording or an idle
  timeout pauses it, and a new recording session resumes it. Explicitly turning
  it off keeps it off. Only reminds while recording, after at least an hour
  without logged movement and at most once an hour. Movement logged while paused
  also resets that clock; recording starts do not reset it. An overdue reminder
  may appear soon after resuming. First enabling waits at least an hour.
  This is not a recommended clinical interval or a fetal-movement monitor.
  When upgrading, an existing Off remains Off until enabled once.
- Compact stats, live on-screen timer and collapsed detail/history accordions.
- Revision guards against double taps and stale notifications.
- Saved transitions before publication; notification failure never rolls back
  recorded timings. Failed or unconfirmed saves are surfaced explicitly.
- Private lock-screen content by default, with an explicit public-content option.
- Local brand assets: no external image host, analytics, AI or cloud inference.

The native integration does **not** create household helper entities, editor automations,
to-do lists or write to existing dashboards. A sidebar app is provided instead.
No existing personal history was copied into this project.

## Requirements and limitations

- Home Assistant **2026.11 or later** (uses the native `probatio` schemas).
- Android Companion app for the intended persistent actionable notification
  experience. iOS notification behaviour is not supported/tested in this beta.
- Samsung/Android controls lock-screen cards, content visibility and whether a
  notification can be swiped away. The integration cannot override phone settings.
- Actions are timestamped at **server receipt**, not the precise phone tap time.
  A delayed network message can therefore affect measurements. The browser's
  clock can affect the displayed live counter; saved times come from the server.
- The two-minute banner uses the live browser timer and available server state.
  The separate phone check needs Home Assistant running and normal Android
  notification delivery; it cannot bypass offline status, notification settings
  or Do Not Disturb. No alert, or no alert yet, is never reassurance to wait.
- After an outage, restored timing is explicitly flagged. Events made offline
  can be missing; this is not an offline phone app.
- Idle closure is checked every minute while HA runs, before timer commands and
  on integration startup after downtime. A stale button may need a refresh.
  The timeout is session housekeeping, not a clinical assessment that contractions
  have stopped. Existing saved intervals are never retrospectively rewritten.
- There is no universal safe interval for baby movements. NHS guidance says to
  contact the midwife/maternity unit immediately if movements reduce, stop or
  change. **Do not wait for the optional logging reminder.** See
  [NHS baby-movement guidance](https://www.nhs.uk/pregnancy/keeping-well/your-babys-movements/).
- Up to 10,000 completed records per entry. At the limit a new contraction cannot
  start; existing records are never silently discarded. History UI shows the
  latest 50; the authenticated API supports up to 500 per request. Bulk export
  and a separately confirmed history-clear workflow are not in this beta.
- This is **household-shared data**, not a private medical chart. Native entity
  permissions are enforced for authenticated commands/history. Other authorised
  Home Assistant users, administrators, Recorder and backups may retain data.
  Hiding a sidebar entry does not make its records private.
- This beta is English-only. Localization structure is supplied.

## Installation — beta testing

The approved repository is
[`DaFern/ha-contraction-tracker`](https://github.com/DaFern/ha-contraction-tracker).
Release preparation and catalog submission are separate steps. Follow the
[release checklist](docs/RELEASE_CHECKLIST.md) for the remaining checks.

For a test installation:

1. Back up Home Assistant.
2. Download the beta source or release archive and copy only
   `custom_components/contraction_tracker` into the instance's `custom_components`
   directory. Do not copy the project root. Release ZIPs contain that full path.
3. **Restart Home Assistant** to load new integration code.
4. Add **Contraction Tracker** in Settings → Devices & services.
5. Choose a phone notification action or **No phone notifications**, and the
   destination for the small Home button.
6. Read the limitations and leave public lock-screen content off unless wanted.
7. Open the new tracker entry in the sidebar and choose **Start recording**.

There is no manual frontend-resource registration step. Reload the browser after
installation/updates if it has an older module cached. Separate tracker entries
receive separate sidebar routes and notification tags.

For an existing dashboard, after installation:

```yaml
type: custom:contraction-tracker-app-card
entity: sensor.your_tracker_session
```

Choose the actual session entity from the entity registry. The card refuses to
guess between multiple trackers when no entity/entry is selected.

### Android lock-screen display

Select notification **Cards**, enable **Show content** for the app if appropriate,
and ensure quiet notifications are not excluded from the lock screen. Names vary
by phone/Android version. Public lock-screen content is visible to bystanders.

## Data lifecycle

Records are written through Home Assistant's supported `Store` helper, not a
public static file. Reloading/disabling an entry retains history and removes its
sidebar/module lease. Notification cleanup on unload is best-effort.

**Removing an integration entry deletes that entry's local tracker store.**
Recorder and backup copies are managed by Home Assistant and are not erased by
this integration. Back up any records you want to retain before removing an entry.
Corrupt/future-format data causes setup to fail rather than being reset.

See [architecture](docs/ARCHITECTURE.md), [privacy](docs/PRIVACY.md),
[migration boundaries](docs/MIGRATION.md), [testing](docs/TESTING.md) and the
[release checklist](docs/RELEASE_CHECKLIST.md).

## Development checks

```sh
python3 tools/build_assets.py
python3 -m unittest discover -s tests/unit -v
npm test
python3 tools/check_release.py
python3 tools/build_release.py
```

There are no JavaScript dependencies. Core/domain tests use the Python standard
library. Native Home Assistant tests require a **separate compatible development
environment**; see `docs/TESTING.md`. Component tests are not phone acceptance tests.

The package has a HACS/Marketplace-compatible directory structure. That is not
approval, a listing or a public release. `tools/check_release.py --publish`
checks repository, maintainer and licence metadata; it is not a substitute for
native HA tests, distribution validators or phone acceptance.

## Licence and product boundary

The Home Assistant integration, its project documentation and bundled original
assets are available under the [MIT licence](LICENSE), copyright 2026 Badger182.
MIT permits redistribution and commercial reuse; those permissions are
intentional for this integration.

A future standalone Android app is a separate product, intended to remain in a
private repository under proprietary terms. It is not included or licensed by
this repository. Reusing MIT-covered material requires retaining the applicable
notice; proprietary app additions do not have to be published merely because
they use MIT code. Third-party dependencies keep their own licences.

See the [Android roadmap and repository boundary](docs/ANDROID_ROADMAP.md).
