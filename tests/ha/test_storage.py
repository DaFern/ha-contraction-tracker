"""Run with the real HA plugin. No direct storage-file reads or writes."""

from copy import deepcopy
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.helpers.storage import Store
from homeassistant.util.file import WriteError

from custom_components.contraction_tracker.manager import PersistenceError, Tracker, verified_save
from custom_components.contraction_tracker.model import new_state, transition


async def test_public_store_save_is_checked_through_an_independent_reader(hass, hass_storage):
    key = "contraction_tracker.test_verified"
    writer = Store(hass, 1, key, private=True, atomic_writes=True)
    async def readback():
        return await Store(hass, 1, key, private=True, atomic_writes=True, read_only=True).async_load()
    candidate = new_state()
    verified = await verified_save(candidate, writer.async_save, readback)
    assert verified == candidate
    assert await readback() == candidate


async def test_real_store_suppressed_write_error_blocks_manager(hass, hass_storage):
    key = "contraction_tracker.test_suppressed"
    writer = Store(hass, 1, key, private=True, atomic_writes=True)
    initial = transition(new_state(), "show", "", 1000)
    await writer.async_save(deepcopy(initial))
    async def readback():
        return await Store(hass, 1, key, read_only=True).async_load()
    notify = AsyncMock()
    tracker = Tracker(initial, writer.async_save, notify, lambda: 1100, readback=readback)
    # Fault injection only: exercise HA's real async_save suppression branch.
    with patch.object(writer, "_async_write_data", new=AsyncMock(side_effect=WriteError("synthetic"))):
        with pytest.raises(PersistenceError):
            await tracker.command("start", initial["k"])
    assert tracker.persistence_uncertain
    assert tracker.view()["p"] == "rest"
    assert await readback() == initial
    notify.assert_not_awaited()
