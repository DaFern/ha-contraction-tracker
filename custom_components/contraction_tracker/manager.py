"""Transactional application layer; deliberately independent of Home Assistant."""

import asyncio
from contextlib import asynccontextmanager
from copy import deepcopy
import logging
import time

from .model import InvalidCommand, configure_guidance, correct, expire_idle, load_state, reminder_due, snapshot, transition
from .location import uncertain
from .legacy import convert, digest, require_pristine, source_digest, summary as import_summary
from .const import LONG_CONTRACTION_SECONDS
from .activity import operation_activity

_LOGGER = logging.getLogger(__name__)


class PersistenceError(RuntimeError):
    """The save was not verified and must not be presented as recorded."""


async def verified_save(candidate, save, readback):
    """Validate before writing; compare raw independent read-back before migration."""
    if readback is None:
        raise PersistenceError("Independent storage read-back is required.")
    candidate = load_state(candidate)
    expected = digest(candidate)
    await save(deepcopy(candidate))
    stored = await readback()
    # Comparing after load_state could hide an unwritten schema upgrade.
    if digest(stored) != expected:
        raise PersistenceError("Stored data did not match the saved candidate.")
    return load_state(stored)


class Tracker:
    """One serialized entry. Never roll back a saved contraction on push failure."""

    def __init__(self, data, save, notify, clock=time.time, location_provider=None, readback=None):
        self._state = load_state(data)
        self._save = save
        self._readback = readback
        self.import_uncertain = False
        self.persistence_uncertain = False
        self._notify = notify
        self._clock = clock
        self._location_provider = location_provider
        self._last_location = None
        self._lock = asyncio.Lock()
        self._listeners = set()
        self._activity_listeners = set()
        self._pending_activity = []
        self._snapshot_cache = None
        self.notification_failed = False
        self.persistence_failed = False
        self.restored = data is not None and self._state["p"] != "off"
        self.closed = False
        self.entity_id = None
        self.rating_notify = None
        self.warning_notify = None
        self.long_warning_notify = None
        self._long_evaluated = None

    def view(self):
        now = int(self._clock())
        location = None
        if self._state["guidance"]["mode"] == "automatic":
            try:
                location = self._location_provider(self._state["guidance"], now) if self._location_provider else uncertain()
            except Exception:
                location = uncertain()
        cache = self._snapshot_cache
        if cache is None or cache[0] is not self._state or cache[1] != now or cache[2] != location:
            cache = (self._state, now, deepcopy(location), snapshot(self._state, now, location))
            self._snapshot_cache = cache
        result = deepcopy(cache[3])
        result.update(notification_failed=self.notification_failed,
                      persistence_failed=self.persistence_failed, restored=self.restored,
                      import_uncertain=self.import_uncertain,
                      persistence_uncertain=self.persistence_uncertain)
        return result

    def subscribe(self, listener):
        self._listeners.add(listener)
        return lambda: self._listeners.discard(listener)

    def subscribe_activity(self, listener):
        """Subscribe a synchronous adapter callback, not an automation action."""
        self._activity_listeners.add(listener)
        return lambda: self._activity_listeners.discard(listener)

    @asynccontextmanager
    async def _operation(self):
        acquired = False
        try:
            async with self._lock:
                acquired = True
                yield
        finally:
            # No awaits between unlocking and delivery; preserve commit order.
            pending = []
            if acquired:
                pending, self._pending_activity = self._pending_activity, []
            for event in pending:
                for listener in tuple(self._activity_listeners):
                    try:
                        listener(deepcopy(event))
                    except Exception:
                        _LOGGER.warning("A tracker activity subscriber failed")

    def _record_activity(self, before, operation, occurred_at, record_id=None):
        self._pending_activity.extend(operation_activity(
            before, self._state, operation, occurred_at, record_id))

    def _publish(self):
        for listener in tuple(self._listeners):
            try:
                listener()
            except Exception:  # UI subscriber failure must not undo a durable write.
                _LOGGER.warning("A tracker state subscriber failed")

    async def _push(self):
        if self.persistence_uncertain or self.import_uncertain:
            return  # Never send actionable controls based on unverified state.
        try:
            view = self.view()
            async with asyncio.timeout(10):
                await self._notify(view)
            self._last_location = view["location"]
            self.notification_failed = False
        except Exception:  # Do not log private payloads, tokens or service exceptions.
            self.notification_failed = True
            _LOGGER.warning("Notification delivery failed; saved timings were retained")
        self._publish()

    async def command(self, command, token="", received=None):
        received = int(self._clock()) if received is None else received
        async with self._operation():
            self._check_save_outcome()
            if self.closed:
                raise InvalidCommand("This tracker is unloading. Refresh when it reconnects.")
            await self._expire_idle(received)
            candidate = transition(self._state, command, token, received)
            if command == "intensity" and self.rating_notify is not None:
                try:
                    async with asyncio.timeout(10):
                        await self.rating_notify(self.view())
                except Exception:
                    self.notification_failed = True
                    self._publish()
                return self.view()
            if candidate != self._state:
                before = self._state
                await self._commit(candidate)
                self._record_activity(before, command, received)
                if command not in ("movement", "reminders_on", "reminders_off"):
                    self.restored = False
                self._publish()
            await self._push()
            return self.view()

    async def edit(self, record_id, revision, start, end, intensity):
        async with self._operation():
            self._check_save_outcome()
            if self.closed:
                raise InvalidCommand("This tracker is unloading.")
            now = int(self._clock())
            candidate = correct(self._state, record_id, revision, start, end, intensity, now)
            if candidate != self._state:
                before = self._state
                await self._commit(candidate)
                self._record_activity(before, "correct", now, record_id)
                self._publish()
                await self._push()
            return self.view()

    async def configure_guidance(self, token, location, interval, **settings):
        async with self._lock:
            self._check_save_outcome()
            if self.closed:
                raise InvalidCommand("This tracker is unloading.")
            candidate = configure_guidance(self._state, token, location, interval, **settings)
            await self._commit(candidate)
            self._publish()
            await self._push()
            return self.view()

    def _check_save_outcome(self):
        if self.persistence_uncertain or self.import_uncertain:
            raise InvalidCommand("Save outcome is uncertain. Reload the integration and inspect stored history and settings before retrying.")

    async def _commit(self, candidate, *, importing=False):
        """Promote only independently verified state; never retry/roll back a write."""
        # Preflight failures cannot have reached storage and need no uncertainty latch.
        candidate = load_state(candidate)
        digest(candidate)
        if self._readback is None:
            raise PersistenceError("Independent storage read-back is required. Nothing was saved.")
        try:
            verified = await verified_save(candidate, self._save, self._readback)
        except BaseException as err:
            self.persistence_uncertain = True
            self.import_uncertain = importing
            self.persistence_failed = True
            self._publish()
            if not isinstance(err, Exception):
                raise
            raise PersistenceError(
                "Save could not be verified. Controls are blocked; reload the integration "
                "and inspect saved history and settings before retrying."
            ) from err
        self._state = verified
        self.persistence_failed = False

    async def import_legacy(self, bundle, *, apply=False, expected_source="", expected_target="", source_check=None):
        """One-shot import into a pristine entry; never changes or notifies source."""
        async with self._lock:
            self._check_save_outcome()
            if self.closed:
                raise InvalidCommand("This tracker is unloading.")
            require_pristine(self._state)
            candidate = convert(bundle, int(self._clock()))
            source_hash, target_hash = source_digest(bundle), digest(self._state)
            candidate_hash = digest(candidate)  # Refuse oversized candidates before any save.
            result = {"status": "preview", "saved": False, "verified": False,
                      "source_sha256": source_hash, "target_sha256": target_hash, **import_summary(candidate)}
            if not apply:
                return result
            if expected_source != source_hash or expected_target != target_hash:
                raise InvalidCommand("Source or destination changed since preview. Review a fresh preview.")
            if self._readback is None or source_check is None:
                raise InvalidCommand("Import requires a fresh source check and storage read-back.")
            fresh = await source_check()
            if source_digest(fresh) != source_hash:
                raise InvalidCommand("Source changed during import preparation. Nothing was saved.")
            await self._commit(candidate, importing=True)
            self.restored = self._state["p"] != "off"
            self._publish()
            result.update(status="imported", saved=True, verified=True, imported_sha256=candidate_hash)
            return result

    async def refresh_location(self):
        async with self._lock:
            if self.closed or self.persistence_uncertain or self.import_uncertain:
                return
            self._publish()
            if self._state["p"] != "off" and self.view()["location"] != self._last_location:
                await self._push()

    def location_references(self):
        settings = self._state["guidance"]
        return ({settings["person"], settings["home"], *settings["hospitals"]}
                if settings["mode"] == "automatic" else set())

    async def tick(self):
        """Age rolling-hour data without sending a push every minute."""
        async with self._operation():
            if self.closed or self.persistence_uncertain or self.import_uncertain:
                return
            try:
                await self._expire_idle(int(self._clock()))
            except PersistenceError:
                _LOGGER.warning("Idle-session closure could not be verified; controls are blocked")
                return
            self._publish()
            if self._state["guidance"]["mode"] == "automatic" and self._state["p"] != "off":
                if self.view()["location"] != self._last_location:
                    await self._push()
            now = int(self._clock())
            if reminder_due(self._state, now) and self.warning_notify is not None:
                try:
                    candidate = deepcopy(self._state)
                    candidate["movement"]["last_alert"] = now
                    # Claim this hour durably before attempting delivery. An
                    # ambiguous phone response must not cause minute-by-minute repeats.
                    await self._commit(candidate)
                    async with asyncio.timeout(10):
                        await self.warning_notify(self.view())
                except Exception:
                    self.notification_failed = True
                    _LOGGER.warning("Optional movement logging reminder could not be confirmed")
                self._publish()

    async def _expire_idle(self, now):
        """Caller holds the lock; publish/notify only after verified persistence."""
        candidate = expire_idle(self._state, now)
        if candidate != self._state:
            before = self._state
            await self._commit(candidate)
            self._record_activity(before, "inactivity", now)
            self.restored = False
            self._publish()
            await self._push()

    async def refresh_notification(self):
        await self.command("notify")

    def long_warning_schedule(self):
        """Evaluate timer state even without a phone; never a clinical status."""
        if (self.closed or self.persistence_uncertain or self.import_uncertain
                or self._state["p"] != "active"):
            return None
        state = self._state
        identity = (state["session_id"], state["n"], state["s"])
        delay = max(0, state["s"] + LONG_CONTRACTION_SECONDS + 1 - self._clock())
        if delay == 0 and (self._long_evaluated == identity or state["long_warning_attempted"]):
            return None
        # Even an already-attempted warning can need a future state-only
        # evaluation after clock rollback. It must never send a second alert.
        return identity, delay

    async def check_long_contraction(self, identity):
        """One verified alert attempt per active contraction, including after restart."""
        async with self._lock:
            state = self._state
            if (self.closed or self.persistence_uncertain or self.import_uncertain
                    or state["p"] != "active"
                    or identity != (state["session_id"], state["n"], state["s"])
                    or int(self._clock()) - state["s"] <= LONG_CONTRACTION_SECONDS):
                return
            self._long_evaluated = identity
            # Publish derived state without claiming a nonexistent phone attempt.
            self._publish()
            if self.long_warning_notify is None or state["long_warning_attempted"]:
                return
            candidate = deepcopy(state)
            candidate["long_warning_attempted"] = True
            try:
                # Do not rotate the main or movement token: Stop must stay valid.
                # Claim before delivery; an uncertain response must not create repeat alerts.
                await self._commit(candidate)
            except PersistenceError:
                _LOGGER.warning("Contraction timer warning could not be verified; controls are blocked")
                return
            self._publish()
            try:
                async with asyncio.timeout(10):
                    await self.long_warning_notify(self.view())
            except Exception:
                self.notification_failed = True
                _LOGGER.warning("Contraction timer warning delivery could not be confirmed")
                self._publish()

    def history(self, limit=50):
        self._check_save_outcome()
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 500:
            raise ValueError("History limit must be between 1 and 500.")
        return deepcopy(self._state["records"][-limit:])

    async def shutdown(self):
        """Reject new work and wait for any in-flight durable write."""
        self.closed = True
        async with self._lock:
            try:
                async with asyncio.timeout(3):
                    await self._notify({**self.view(), "p": "off", "idle_ended": False})
            except Exception:
                _LOGGER.warning("Notification cleanup could not be confirmed")
            self._listeners.clear()
            self._activity_listeners.clear()
