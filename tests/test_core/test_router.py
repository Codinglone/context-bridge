"""Tests for the router/dispatcher."""

import asyncio

import pytest

from context_bridge.connectors.base import BaseConnector
from context_bridge.router import Router


class AddConnector(BaseConnector):
    name = "math"

    async def initialize(self) -> None:
        pass

    async def shutdown(self) -> None:
        pass

    def get_tools(self) -> list:
        return [
            {
                "name": "math.add",
                "description": "Add two numbers",
                "parameters": {},
            }
        ]

    async def call_tool(self, tool_name: str, arguments: dict) -> int:
        return arguments["a"] + arguments["b"]


@pytest.mark.asyncio
async def test_router_registers_and_calls_tool() -> None:
    router = Router()
    router.register_connector(AddConnector({}))
    await router.initialize_all()

    tools = router.list_tools()
    assert len(tools) == 1
    assert tools[0]["name"] == "math.add"

    result = await router.call_tool("math.add", {"a": 2, "b": 3})
    assert result == 5

    await router.shutdown_all()


def test_router_unknown_tool() -> None:
    router = Router()
    with pytest.raises(ValueError, match="Unknown tool"):
        asyncio.run(router.call_tool("nope", {}))
