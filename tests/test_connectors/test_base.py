"""Tests for the base connector ABC."""

import pytest

from context_bridge.connectors.base import BaseConnector


class DummyConnector(BaseConnector):
    name = "dummy"

    async def initialize(self) -> None:
        self._initialized = True

    async def shutdown(self) -> None:
        self._initialized = False

    def get_tools(self) -> list:
        return []

    async def call_tool(self, tool_name: str, arguments: dict) -> str:
        return "ok"


@pytest.mark.asyncio
async def test_connector_lifecycle() -> None:
    conn = DummyConnector({})
    assert not conn._initialized
    await conn.initialize()
    assert conn._initialized
    await conn.shutdown()
    assert not conn._initialized


def test_connector_health() -> None:
    conn = DummyConnector({})
    assert conn.health() == {"status": "not_initialized"}
