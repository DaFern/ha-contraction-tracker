# Privacy and security

Optional zone detection (0.4.0a1) reads the explicitly selected person's current
GPS source locally. Tracker storage retains selected entity IDs and manual/auto
settings, not coordinates or a GPS trail. Coarse location/source labels are
visible on the tracker sensor/card/notification when enabled; the live adapter
would also retain those labels in a helper. Existing HA recorder/tracking history
is independent. No external geocoding was added. Automatic mode defaults off;
the live adapter update remains staged and has not enabled detection.

- No external analytics, AI service, remote database or image host.
- History stays in the instance through Home Assistant's `Store` helper.
- Android pushes use the user's existing Companion notification delivery path,
  which may involve Google's notification infrastructure. “Local storage” does
  not mean push-message transport is entirely local.
- Lock-screen content is private by default. Enabling public content exposes it
  to bystanders; phone-wide settings still take precedence.
- This integration is not a private patient portal. Standard HA entity read/control
  permissions apply. Administrators, authorised household users, Recorder,
  diagnostic exports of state and backups can include sensitive timings.
- There is no diagnostics endpoint that returns records and no patient data in
  static files. Error logs intentionally omit payloads, records and revision values.
- WebSocket history requires authentication and entity read permission.
- Service and phone commands with user context require entity control permission.
  Native internal automations without user context are trusted HA callers.
- Nonces stop stale commands; they are not intended to protect against an
  authorised household user deliberately issuing controls.
- Correction controls retain original values and before/after audit trails; they
  do not delete historical records. Movement logs and optional reminder settings
  are also stored locally. Reminders are not a fetal-wellbeing assessment.
- Removing a tracker entry deletes its own
  local store. Existing HA backups and Recorder retention are outside its remit.
- No bulk export or destructive history-clear service is shipped in the alpha.

Before publishing an issue, remove any records, phone/user names, entity
identifiers, domains, coordinates, credentials and unredacted screenshots.
Do not attach a complete Home Assistant configuration or storage file.
