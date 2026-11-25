# Contact prompts — 0.3.0a1

The user selects **Not specified**, **At home**, or **In hospital / birth centre**
under **Contact prompts & location**, then saves. These remain manual overrides.
Version 0.4.0a1 also offers opt-in selected-person/zone detection; see
[LOCATION.md](LOCATION.md). Automatic hospital presence uses generic maternity-team
contact wording and never assumes admission.
An independent settings revision ensures changing this cannot invalidate Stop,
reset a timer, start recording, erase records or change movement settings.
Native saves use the same serialized persistence boundary as contractions.
The live prototype queues settings through its automation and confirms read-back.
An uncertain save is never automatically retried.

## What changes in the notification

Last completed length, rolling-hour average start-to-start interval and average
length each have their own plain-text line. Count, intensity, descriptive changes
and one action prompt follow as short bullets. No HTML, spacing-based columns,
button instructions or generic medical disclaimer is used in the primary
notification. Save/restart warnings remain visible when applicable.
**Close** is only the phone label for stopping recording; its action is unchanged.

## Pattern rules

- Default contact interval: **300 seconds** (five minutes). Whole-minute values
  from 1–10 minutes can match a maternity team's instructions. This does not
  change the urgent checks below. Do not change it to justify waiting.
- A contact prompt needs **three consecutive positive start-to-start gaps**, each
  at or below the selected interval, using four recent starts in the current
  recording session. All four starts must be within 30 minutes. An active
  contraction may supply the fourth start.
- The last start must be no more than twice the selected interval ago. Old
  qualifying records never supply a current contact prompt.
- This repeated-gap UI criterion is **not a validated clinical regularity test**.
  No average can substitute for individual gaps; no one-hour wait, minimum
  contraction duration, intensity rating or cervical-dilation threshold is imposed.
- Urgent wording takes priority for a recorded contraction lasting **over 120
  seconds** and ending in the last ten minutes (or currently timed over 120
  seconds), or **six or more starts in the rolling last ten minutes**.
- Incomplete logs and network delays can hide or distort patterns. These are
  presentation checks on actions/refresh, not continuous medical monitoring.
  Expired evidence returns to a neutral contact/support prompt, never “safe to
  wait”, “not in labour” or “stay home”.

## Timed long-contraction warning

The native tracker additionally shows a prominent live banner when an active
timer passes two minutes. The browser checks its displayed timer each second;
the server schedules a separate check for 121 seconds after its recorded start
(strictly over 120 seconds), without requiring another tap or a minute refresh.
Scheduling and phone delivery can be delayed; this is not medical monitoring.

The warning says:

> Timer over 2 minutes. If this contraction is still continuing, contact your
> midwife or maternity unit urgently. If it ended earlier, stop the timer and
> correct the record.

If a phone notification action is configured, the integration makes one alert
attempt per contraction, using a separate ordinary Android high-importance
channel. Lock-screen privacy follows the user's existing setting. Stop remains
available on the tracker and alert; only the user's Stop records an end time.
Nothing classifies the contraction, invents an end or changes its saved timing.

The attempt marker is independently verified in storage before sending. It
does not change the Stop or movement tokens. Reload/restart cannot re-send an
already claimed attempt; an overdue active timer not yet claimed gets one
attempt after setup. A stopped or unloaded tracker rejects stale callbacks.
An uncertain save blocks actionable alerts and controls, as with other writes.
An uncertain or failed phone delivery is not retried automatically: a warning
can consequently be missed. This is intentional duplicate prevention, not
evidence of successful delivery. The banner remains independent of that marker.

### Warning cleanup and delayed delivery

The source follow-up gives each contraction a stable, opaque warning tag derived
from its session, number and recorded start. It is not an authentication token.
Ordinary active updates and refreshes do not send warning-clear messages, before
or after the threshold. Cleanup requires a claimed attempt and a verified
completed record for that contraction; a temporary off presentation during
active-timer unload/reload is not completion. An old contraction's delayed clear
cannot remove a later contraction's newly tagged warning.

Existing pre-upgrade warning Stop buttons retain their legacy tag handling, but
still require native user authorization and the valid current Stop token.
Both warning-tag forms allow only Stop; stale per-contraction tags and stale
tokens are rejected. After completion, cleanup also retires the old entry-wide
warning tag. No storage migration, timing edits or extra automatic alert attempts
are introduced.

This addresses an ordering race in warning cleanup; it does **not** guarantee
FCM ordering, immediate arrival or reliable lock-screen/sound behavior. A
main-notification snapshot can still arrive late. A warning could also arrive
after its own end/clear, or be missed; those transport limits are not eliminated
by isolating tags. Stale controls must not affect a subsequent contraction.
Phone history showing a warning and clear messages in one delayed batch supports
investigating this race, but without each message's tag it does not prove which
clear removed a particular visible warning.

The follow-up is included in beta 0.5.0b2. The owner accepted the deployed phone
fix after restart; automated queue simulation is not exhaustive physical-phone
delivery acceptance.

The app cannot distinguish a genuinely continuing contraction from a timer left
running, diagnose hyperstimulation, assess fetal wellbeing or guarantee alerts
through outages or phone notification restrictions. Never wait for an alert if
worried. NHS advice is to contact maternity urgently for any contraction lasting
longer than two minutes; call 111 if the maternity team cannot be reached.
Individual care-team advice to call sooner still applies.

Sources checked 25 November 2026:

- [NHS — signs that labour has begun](https://www.nhs.uk/pregnancy/labour-and-birth/signs-that-labour-has-begun/):
  urgent contact for any contraction lasting longer than two minutes.
- [NICE NG207 — hyperstimulation](https://www.nice.org.uk/guidance/ng207/chapter/recommendations#hyperstimulation):
  describes prolonged contractions in the specific context of induction.
  A manual home timer must not infer this clinical diagnosis.

## Location wording

| Selection | Repeated-gap contact prompt |
| --- | --- |
| Not specified | Contact your maternity care team about these frequent contractions. |
| At home | Contact your maternity unit about these frequent contractions. |
| In hospital / birth centre | Tell your midwife about these frequent contractions. |

Routine text suggests following the care plan/asking for support, or keeping bag
and notes ready at home. Urgent text identifies the recorded reason and asks for
urgent contact; it does not diagnose labour or instruct travel.

## Guidance that timings cannot assess

Follow your maternity team's individual advice, including any instruction to
call sooner. Contact them promptly if worried or needing support, regardless of
what is recorded. Waters breaking, vaginal bleeding, reduced or changed movements,
or suspected labour before 37 weeks require immediate contact. If baby seems to
be coming now with a strong urge to push, call 999.

The tracker does not know cervical dilation, gestation, risk factors, waters,
bleeding, true movement patterns, distance to care or clinical assessment.
Location alone supplies none of that. A movement log is not a wellbeing test.

Source: [NHS — signs that labour has begun](https://www.nhs.uk/pregnancy/labour-and-birth/signs-that-labour-has-begun/),
checked 23 November 2026. NHS says to contact maternity for regular contractions
every five minutes or more often, or if labour is suspected/there is concern.
It does not require waiting for a 5‑1‑1 pattern for an hour.
