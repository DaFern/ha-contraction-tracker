# Native entities and opt-in automations

This source candidate adds native sensors, binary sensors, one Activity event
entity and three optional blueprints. Nothing is installed or enabled in the
household by developing these sources. Existing Session identity, discovery
marker, authorization, commands, tokens, history API and storage schema 8 are
unchanged. Published beta 0.5.0b1 does not contain these additions.

## Entity reference

All 22 entities (including the existing Session) belong to the same tracker
device. Unique IDs are `<config_entry_id>_<key>`; actual entity IDs are managed
by HA and can be renamed. Only Session retains `contraction_tracker: true` for
card discovery and native authorization. All are enabled by default; you can
disable unused entities independently from the device page. Disabled activity
entities do not queue/replay missed events when enabled again.

| Key | Name | Type / unit |
| --- | --- | --- |
| `session` | Session (existing) | Enum: off/rest/active/rate |
| `session_recording` | Session recording | Binary, on except off |
| `contraction_active` | Contraction active | Binary, on only in active |
| `awaiting_rating` | Awaiting rating | Binary, on only in rate |
| `timer_over_two_minutes` | Timer over two minutes | Binary, active and elapsed >120 seconds |
| `session_count` | Session contraction count | Starts in latest session |
| `hourly_starts` | Starts in last hour | Rolling count including active |
| `hourly_completed` | Completed contractions in last hour | Duration sample count |
| `last_duration` | Last contraction duration | Duration / seconds |
| `last_interval` | Last start-to-start interval | Duration / seconds |
| `last_rest` | Last rest period | Duration / seconds |
| `hourly_duration` | Average duration in last hour | Duration / seconds |
| `hourly_interval` | Average start-to-start interval in last hour | Duration / seconds |
| `hourly_interval_samples` | Interval sample count in last hour | Interval sample count |
| `current_start` | Current contraction started | Timestamp, unknown outside active |
| `last_end` | Last contraction ended | Timestamp, latest completed record |
| `last_movement` | Last movement logged | Timestamp, unknown until logged |
| `last_intensity` | Last recorded intensity | Enum: Not rated/Mild/Moderate/Strong |
| `resolved_location` | Resolved location | Enum: unspecified/home/hospital/elsewhere/uncertain |
| `save_uncertain` | Save outcome uncertain | Diagnostic binary |
| `notification_failed` | Notification delivery failed | Diagnostic binary |
| `activity` | Activity | Native EventEntity, seven types below |

Timestamps are timezone-aware and HA displays them in your time zone. Resolved
location exposes only the coarse location and `source` (manual/automatic);
uncertain/elsewhere are not home or hospital and imply no wellbeing assessment.
No state class opts these health-related rolling/session values into long-term
statistics. Normal Recorder retention still applies.

Measurements become unavailable on an uncertain save/import rather than claiming
unverified recording success. Diagnostics remain available to expose the failure.
The existing Session retains its compatibility payload and explicit failure flags.
Activity retains its last *verified* event; that does not confirm a later write.

## Shared bounded facts

`Tracker.view()` caches the model snapshot by committed state identity, integer
server second and resolved location. Every caller gets an independent deep copy.
Runtime failure/restoration flags are overlaid fresh, not cached. Location is
resolved on each read so a same-second location change invalidates the cache.
Ticks and clock rollback recalculate time-dependent values. No elapsed values
are persisted and no second statistics algorithm is introduced.

Existing `hourly` values keep their definitions: starts include an active start;
completed duration samples include all completed records starting in the
inclusive rolling hour, across sessions. `interval_samples` counts exactly the
positive intervals contributing to `hourly.interval`, including an eligible
active interval whose preceding start is in the hour. Missing averages are
`None`; empty counts are zero. Existing rounding remains unchanged.

`last_record` still includes duration/intensity and now adds bounded record ID,
session ID, number, start, end, interval and rest. It describes the latest
completed record across sessions, not an active timer. A first record's interval
and rest are unknown (`None`); genuine zero duration/rest/known interval remains
zero. Legacy zero intervals still do not contribute to the hourly average.
Corrections update these facts. They remain available while paused/off and while
a new session has no completed records. Session count `n` retains the latest
session's start count while off; a fresh session resets it.

## Verified-operation activity hooks

`subscribe_activity(callback)` returns an unsubscribe function. Callbacks are
synchronous adapter handoffs, **not** arbitrary automation actions. The native
adapter writes Activity only from this channel and adds `entry_id`. Subscribers
receive independent bounded dictionaries:

| `event_type` | Additional attributes |
| --- | --- |
| `session_started` | none |
| `session_ended` | `reason`: `manual` or `inactivity` |
| `contraction_started` | `number`, `start` |
| `contraction_completed` | `record_id`, `number`, `start`, `end`, `duration`, `intensity` |
| `contraction_rated` | same completed-record fields |
| `record_corrected` | same fields, identifying the corrected record's session |
| `movement_logged` | `logged_at`, `count` |

Every payload has `session_id` and `occurred_at` (server Unix seconds).
Completion happens on Stop, with intensity `Not rated`; rating is a separate
operation. Equal successive measurements still emit distinct record IDs.
Correction emits only correction activity, even when dependent intervals change.
Session starts use the real session ID, not a rate-to-rest transition.
Starting directly from inactivity closure emits session start then contraction
start. Dismissing an already closed session does not emit another end.

Metadata is queued only after independent storage read-back succeeds. Updated
state subscribers run before activity callbacks; activity is handed off after
the persistence lock is released, in operation order. Subscriber exceptions are
isolated without exposing payloads in logs. A later error in the same request
does not erase activity for an earlier independently verified inactivity closure.
Notification delivery failures do not erase successful recording activity.

Refreshes, ordinary ticks, settings changes, reminder/warning attempt markers,
rejected/stale controls, failed/unverified writes and imports generate no
activity. Constructing/restoring a tracker does not replay history. An overdue
inactivity closure reconciled after restart is a new verified `session_ended`
operation, timestamped when reconciled, not a replay of prior contractions.
Shutdown removes subscribers. Subscriptions are local to each tracker.

There is no persisted event outbox or exactly-once guarantee: a crash after save
and before callback can lose delivery; reload does not retry it. Record/session
IDs help consumers correlate operations but do not promise deduplication of all
future transport behavior. Activity's native state is HA's event-delivery
timestamp, not the occurrence time. Delivery follows the existing notification
attempt (which may take up to its timeout). Use `occurred_at` for the operation's
server timestamp. HA makes successive event timestamps distinct even when
measurements or wall time are equal.

EventEntity restores its last event timestamp/attributes without firing a new
operation. Automations must reject entity addition (`from_state` is absent),
unavailable/restored transitions and unchanged event timestamps. The supplied
blueprints include these guards while allowing the first real unknown-to-event
transition. A downtime inactivity closure is buffered after verified storage
reconciliation and emitted only after the native measurement platforms are ready.
This is new closure activity, not a replay of a historical contraction.

## Timer evaluation without a phone

The scheduled deadline now updates the binary timer state with notifications
set to none. It does not save or claim a phone attempt in that case. The model's
existing whole-second server clock is preserved: >120 seconds becomes true at
recorded start +121 seconds. No per-second persisted elapsed sensor is added.
Minute ticks age rolling metrics; timer deadlines are scheduled separately.

Stop, stale identities and unload cancel/ignore old checks. Reload already
overdue exposes the true derived state without replaying activity. Clock rollback
can rearm state evaluation without a second phone alert. With a phone, the same
verified one-attempt persisted marker and existing Stop token are preserved.
These convenience states do not determine whether it is safe to wait, and no
automation overrides the built-in warning or ends a contraction automatically.

## Visual editor examples (no nested Session templates)

After installing the candidate separately on a test instance:

- **Breathing support:** choose a state trigger for **Contraction active**,
  off → on, and a user-selected script/light action. Use on → off in a separate
  automation for explicit end actions.
- **Rating reminder:** choose **Awaiting rating**, off → on, with a user-selected
  duration in the trigger. Add your reminder action. HA's `for` duration does
  not survive automation reload/restart.
- **Custom recorded pattern:** use a numeric-state trigger for **Starts in last
  hour** and numeric-state conditions for **Average start-to-start interval in
  last hour**, **Average duration in last hour** and both sample-count sensors.
  Choose your own thresholds/minimum samples and cooldown; this is not clinical
  guidance. A threshold trigger reacts on crossing, not every qualifying record.
- **Technical fallback:** choose **Save outcome uncertain**, off → on, then your
  private fallback action. Notification failure is a different diagnostic and
  does not mean saved timings failed.

Use Activity for per-operation triggers, especially equal-duration records:
watch its **state**, then select/filter the `event_type` attribute. Filtering
only on an attribute change misses repeated events of the same type. For simple
session/partner/timer use cases the blueprints below supply the guards for you.

## Three optional starter blueprints

The sources live under `blueprints/automation/` in this repository. They are not
copied into HA's blueprint directory or included as enabled automations by the
integration. The integration ZIP contains component code only.

1. **Calming session** (`calming_session.yaml`): choose one tracker's Activity,
   start actions and explicit end actions. A new session is distinct from a
   contraction start or rating. Manual/inactivity ends both run the chosen end
   actions. Actions are queued in order (maximum 10 waiting/running runs).
   There is no automatic scene snapshot restoration that might overwrite your
   subsequent changes. Keep chosen actions short and idempotent.
2. **Partner update** (`partner_update.yaml`): choose Activity and completion
   **or** rating, your recipient/message/actions and a cooldown. Completion has
   `Not rated`; choosing rating waits for a rating that may never arrive.
   Corrections, refreshes and history imports do not send partner updates.
   A single in-memory run holds the cooldown after the selected action attempt;
   events during it are dropped, not delayed or replayed, and do not extend it.
   Action failure is not retried automatically. Reload/restart resets cooldown.
3. **Timer reminder** (`timer_reminder.yaml`): choose **Current contraction
   started**, seconds and your reminder action. It reminds once for a newly
   observed active start, rechecks that exact timestamp, and cancels on Stop,
   unavailability or another start. Reload/restart cancels pending waits; it
   does not catch up existing active timers. Selecting another timestamp sensor
   would give different/incorrect behavior: choose the named current-start entity.

For import after these files are committed/pushed, use Settings → Automations &
scenes → Blueprints → Import blueprint with:

- `https://github.com/DaFern/ha-contraction-tracker/blob/main/blueprints/automation/calming_session.yaml`
- `https://github.com/DaFern/ha-contraction-tracker/blob/main/blueprints/automation/partner_update.yaml`
- `https://github.com/DaFern/ha-contraction-tracker/blob/main/blueprints/automation/timer_reminder.yaml`

Uncommitted sources are not available at those URLs yet. For an isolated local
test installation, explicitly copy a selected file into that instance's
`blueprints/automation/contraction_tracker/` directory instead. Then create an
automation from it, choose entities from **one tracker device**, choose actions
and save only when ready to enable them. Import alone does not create an
automation. No household entity ID, recipient or medical threshold is hardcoded.

The action editor is available for all three blueprints. Partner/calming actions
may optionally use `activity` (bounded trigger attributes, including record/
session IDs), but no health data is inserted into a message by default. There
is no exactly-once execution promise across crashes or chosen user actions.

## Privacy and activation boundaries

Payloads exclude concurrency/revision tokens, full history, correction audits,
original/import source data, coordinates and phone details. IDs and timestamps
are still sensitive health-related metadata. Native entities/events may
be recorded by Recorder, automation traces or selected outbound actions under
HA's normal permissions; users must choose destinations and retention carefully.

New measurements/events can increase recorded state. Review Recorder entity
exclusions and retention through HA's supported configuration controls if that
is inappropriate; this code does not change your retention policy. Review
automation traces and outbound destinations as well as lock-screen privacy.
Session-based native control/history authorization remains unchanged.

Nothing is automatically deployed, restarted or enabled by this source work.
Loading changed integration code would require a separately approved restart.
Blueprints require a separate explicit import and user-configured automation.

## Local validation

The preceding first-slice source passed 142 dependency-free Python unit tests (including
16 automation-foundation tests), 39 frontend tests, `check_release.py --publish`,
the local release archive build and `git diff --check`. The `--publish` flag
validates public-release requirements; it does not publish anything.
These results are not a fresh native HA matrix, hassfest/HACS run or physical
acceptance. Native tests added with this slice exercise actual blueprint
expansion/schema validation and automation execution on disposable synthetic
trackers, entity registry/device membership, ordering, corrections, restore
filtering, cooldown, cancellation and no-phone timer deadlines. Their results
must be obtained in the exact official HA matrix before deployment.

For the combined native-entity/blueprint source candidate, local checks passed
143 Python unit tests, all 39 frontend tests, release validation, Python AST
parsing and the local integration archive build. All three blueprint sources
have clean YAML language-server diagnostics against an authenticated HA 2026.11.1
connection. This checks source YAML, not native blueprint expansion/execution.
The generic safe-write checker mentions `value_template` as a legacy-template
sensor hint; these uses are valid automation conditions, not template sensors.
The exact HA 2026.11.0/2026.11.3 native suites, hassfest and HACS were **not rerun**
for this uncommitted candidate. No live tracker records or automation actions
were used for validation.
