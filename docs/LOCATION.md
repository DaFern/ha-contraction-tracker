# Optional zone location — 0.4.0a1

Automatic mode is opt-in. Existing/manual selections survive migration unchanged.
The app does not pick a person, guess a hospital, create zones, or grant location
permissions. It uses location Home Assistant already has for the selected person.

**Deployment status for this development copy:** native integration uninstalled;
the live 0.4.0a1 adapter/UI update was staged but activation was explicitly deferred.
The currently running prototype remains the previous manual-location version.

## Configuration

Open **Contact prompts & location**, choose **Automatic · selected zones**, select
the **person being tracked** (not their partner), a home zone and 1–3 distinct
hospital/birth-centre zones, then save. Create missing zones through Home
Assistant's Zones UI. Coordinates, radius and background location permission must
already be configured appropriately outside this app.

Selecting **Manual override**, choosing a location and saving disables detection.
The manual selection is retained while using automatic mode; switch back whenever
detection is unsuitable. Nothing changes the contraction timer or its revision.

The live helper adapter has a 255-character JSON settings limit. Overlong
selections are refused before saving; use fewer hospital zones if necessary.
This adapter limit is not present in the native integration.

## Conservative resolution

- Read only the selected person's **current source** device tracker. The source
  must be GPS, not router/Bluetooth presence. Do not fall back to another phone.
- Require finite valid coordinates and a reported GPS accuracy from 0–100 metres.
- Use the source's HA `last_reported` time, not how long the person has been in
  the same zone. Require a report no older than 15 minutes and not more than
  30 seconds in the future. Reject restored/missing/unavailable source data.
- Use metre-based spherical distances against explicitly selected zone centres
  and radii; do not infer location from zone occupancy counts or friendly names.
- The complete reported accuracy circle must lie **strictly inside exactly one**
  selected zone. Boundary contact or overlap with another selected zone means
  **Location uncertain · automatic**.
- Valid GPS outside every selected zone means **Elsewhere · automatic**. It never
  means home, hospital or “safe to wait”.
- Bad/missing selected-zone data means uncertain, even if another zone looks valid.
- A person's source can be a router when at home, depending on their HA tracker
  configuration; this deliberately yields uncertain rather than asserting GPS.

These freshness/accuracy rules are conservative UI heuristics, not guarantees
of physical location or clinically validated thresholds. Background permissions,
GPS noise and upstream integrations can still delay or misreport a fix.

## Wording and refresh

The card shows the effective location and **manual/automatic** source. Automatic
mode adds the same short source label to the notification. Automatically detecting
a hospital zone uses **Contact your maternity care team**, never assumes admission,
and does not say “Tell your midwife” as though care has already begun.

Location changes only wording; contraction-contact and urgent timing checks are
unchanged. Native location events and the minute scheduler update changed
locations; the live adapter checks each minute and on tracker/settings actions.
Unchanged locations do not generate another notification. Stale data becomes
uncertain on the next check. Recording paused stays paused; refresh never starts it.

No coordinate trail is added to the tracker store, helpers, sensor attributes,
notification or release package. Only configured entity IDs/settings are persisted;
the live helper stores coarse location/source labels. Existing Home Assistant
tracking/recorder history remains governed by that installation.

Native setting changes require tracker control permission and read permission
for the selected person, zones and current source tracker. Native lifecycle,
permissions and real-phone background tracking still need test-instance acceptance.
