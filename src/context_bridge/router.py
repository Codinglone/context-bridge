"""Request router / dispatcher for MCP tool calls."""

from typing import Any

from context_bridge.cache import CacheManager
from context_bridge.connectors.base import BaseConnector


class Router:
    """Central dispatcher for MCP tool calls.

    Routes incoming tool calls to the appropriate connector,
    applies caching, and formats responses.
    """

    def __init__(self, cache: CacheManager | None = None) -> None:
        self._connectors: dict[str, BaseConnector] = {}
        self._tool_index: dict[str, tuple[str, str]] = {}
        self.cache = cache or CacheManager()

    def register_connector(self, connector: BaseConnector) -> None:
        """Add a connector and index its tools."""
        if not connector.name:
            raise ValueError("Connector must have a 'name' attribute")

        self._connectors[connector.name] = connector
        for tool in connector.get_tools():
            full_name = tool["name"]
            if "." not in full_name:
                full_name = f"{connector.name}.{full_name}"
            short_name = full_name.split(".", 1)[-1]
            self._tool_index[full_name] = (connector.name, short_name)

    async def initialize_all(self) -> None:
        """Initialize every registered connector."""
        for connector in self._connectors.values():
            await connector.initialize()
            connector._initialized = True

    async def shutdown_all(self) -> None:
        """Shut down every registered connector."""
        for connector in self._connectors.values():
            await connector.shutdown()
            connector._initialized = False

    def list_tools(self) -> list[dict[str, Any]]:
        """Return the full catalog of available tools."""
        tools: list[dict[str, Any]] = []
        for connector in self._connectors.values():
            tools.extend(connector.get_tools())
        return tools

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        """Dispatch a tool call to the correct connector."""
        if tool_name not in self._tool_index:
            raise ValueError(f"Unknown tool: {tool_name}")

        connector_name, short_name = self._tool_index[tool_name]
        connector = self._connectors[connector_name]
        return await connector.call_tool(short_name, arguments)

    def health(self) -> dict[str, Any]:
        """Health check for all connectors."""
        return {
            name: conn.health()
            for name, conn in self._connectors.items()
        }
