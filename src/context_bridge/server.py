"""MCP server entrypoint — stdio and HTTP/SSE transports."""

import asyncio
import json
import sys
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server

from context_bridge.cache import CacheManager
from context_bridge.config import ContextBridgeConfig
from context_bridge.router import Router


def _register_connectors(config: ContextBridgeConfig, router: Router) -> None:
    """Auto-register connectors based on loaded configuration."""
    connectors_cfg = config.connectors

    if connectors_cfg.filesystem:
        from context_bridge.connectors.filesystem import FilesystemConnector

        router.register_connector(FilesystemConnector(connectors_cfg.filesystem))

    if connectors_cfg.obsidian:
        from context_bridge.connectors.obsidian import ObsidianConnector

        router.register_connector(ObsidianConnector(connectors_cfg.obsidian))

    if connectors_cfg.github:
        from context_bridge.connectors.github import GitHubConnector

        router.register_connector(GitHubConnector(connectors_cfg.github))

    if connectors_cfg.ssh:
        from context_bridge.connectors.ssh import SSHConnector

        router.register_connector(SSHConnector(connectors_cfg.ssh))

    if connectors_cfg.postgresql:
        from context_bridge.connectors.postgresql import PostgreSQLConnector

        router.register_connector(
            PostgreSQLConnector(connectors_cfg.postgresql, connectors_cfg.ssh)
        )

    if connectors_cfg.docker:
        from context_bridge.connectors.docker import DockerConnector

        router.register_connector(DockerConnector(connectors_cfg.docker))


class ContextBridgeServer:
    """MCP server that exposes connector tools to MCP clients."""

    def __init__(self, config: ContextBridgeConfig, router: Router | None = None) -> None:
        self.config = config
        self.router = router or Router(cache=CacheManager())
        _register_connectors(config, self.router)
        self._mcp = Server("context-bridge")
        self._setup_handlers()

    def _setup_handlers(self) -> None:
        """Register MCP protocol handlers."""

        @self._mcp.list_tools()
        async def list_tools() -> list[Any]:
            return self.router.list_tools()

        @self._mcp.call_tool()
        async def call_tool(name: str, arguments: dict[str, Any]) -> list[Any]:
            try:
                result = await self.router.call_tool(name, arguments)
                return [self._to_content(result)]
            except Exception as exc:
                return [self._error_content(str(exc))]

    def _to_content(self, result: Any) -> dict[str, Any]:
        """Convert a Python result to MCP text content."""
        text = (
            result
            if isinstance(result, str)
            else json.dumps(result, indent=2, default=str)
        )
        return {"type": "text", "text": text}

    def _error_content(self, message: str) -> dict[str, Any]:
        return {"type": "text", "text": f"Error: {message}"}

    async def run_stdio(self) -> None:
        """Start the MCP server over stdio (for Claude Desktop, etc.)."""
        async with stdio_server() as (read_stream, write_stream):
            await self._mcp.run(
                read_stream,
                write_stream,
                self._mcp.create_initialization_options(),
            )

    async def run_http(self, host: str, port: int) -> None:
        """Start an HTTP MCP server for web-based clients."""
        from context_bridge.transport_http import ContextBridgeHTTPTransport

        transport = ContextBridgeHTTPTransport(self.config, self.router)
        await transport.start(host, port)

    async def start(self) -> None:
        """Initialize connectors and start the configured transport."""
        await self.router.initialize_all()
        if self.config.server.transport == "stdio":
            await self.run_stdio()
        elif self.config.server.transport == "http":
            await self.run_http(self.config.server.host, self.config.server.port)
        else:
            raise ValueError(f"Unsupported transport: {self.config.server.transport}")

    async def stop(self) -> None:
        """Shut down connectors cleanly."""
        await self.router.shutdown_all()


def main() -> None:
    """Synchronous entry point for stdio transport."""
    import argparse

    parser = argparse.ArgumentParser(description="Context Bridge MCP Server")
    parser.add_argument(
        "--config",
        type=str,
        default=str(ContextBridgeConfig.model_fields["server"].default),
        help="Path to config YAML",
    )
    parser.parse_args()

    # Build a minimal default config if none provided
    config = ContextBridgeConfig()

    server = ContextBridgeServer(config)
    try:
        asyncio.run(server.start())
    except KeyboardInterrupt:
        asyncio.run(server.stop())
        sys.exit(0)
