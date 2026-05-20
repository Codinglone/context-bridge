"""Base connector abstract class for all data source connectors."""

from abc import ABC, abstractmethod
from typing import Any


class BaseConnector(ABC):
    """Abstract base class for all Context Bridge connectors.

    Each connector represents a single data source (filesystem, GitHub, SSH, etc.)
    and exposes a set of capabilities as callable tools.
    """

    name: str = ""
    description: str = ""

    def __init__(self, config: Any) -> None:
        """Initialize the connector with validated configuration."""
        self.config = config
        self._initialized = False

    @abstractmethod
    async def initialize(self) -> None:
        """Set up connections, file watchers, or API clients.

        Called once at server startup. Raise an exception if the
        connector cannot start (e.g., bad credentials, unreachable host).
        """

    @abstractmethod
    async def shutdown(self) -> None:
        """Clean up resources (close sockets, stop watchers, etc.)."""

    @abstractmethod
    def get_tools(self) -> list[dict[str, Any]]:
        """Return a list of MCP tool definitions exposed by this connector.

        Each tool is a dict with keys:
            - name: str          # fully-qualified tool name (e.g. "fs.read_file")
            - description: str   # human-readable description
            - parameters: dict   # JSON Schema for arguments
        """

    @abstractmethod
    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        """Execute a tool and return its result.

        Args:
            tool_name: Short tool name (without connector prefix).
            arguments: Validated arguments matching the tool's JSON Schema.

        Returns:
            Arbitrary JSON-serializable result.
        """

    def health(self) -> dict[str, Any]:
        """Return connector health status. Override for richer diagnostics."""
        return {"status": "healthy" if self._initialized else "not_initialized"}
