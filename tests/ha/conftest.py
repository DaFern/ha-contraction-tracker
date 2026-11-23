"""These tests require the real Home Assistant test plugin, not local shims."""

from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture(autouse=True)
def enable_integration(enable_custom_integrations):
    yield


@pytest.fixture
def mock_entry_setup():
    # Configuration-form tests deliberately do not deploy a running tracker.
    with (
        patch("custom_components.contraction_tracker.async_setup", new=AsyncMock(return_value=True)),
        patch("custom_components.contraction_tracker.async_setup_entry", new=AsyncMock(return_value=True)) as setup,
    ):
        yield setup
