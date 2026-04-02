"""
Pytest configuration and shared fixtures.
"""
from __future__ import annotations

import pytest
import asyncio


@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
