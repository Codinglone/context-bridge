"""Tests for the HTTP transport."""

import pytest
from httpx import ASGITransport, AsyncClient

from context_bridge.config import ContextBridgeConfig
from context_bridge.router import Router
from context_bridge.server import ContextBridgeServer
from context_bridge.transport_http import ContextBridgeHTTPTransport


@pytest.fixture
def http_client():
    """Create an async HTTP client against the test app."""
    config = ContextBridgeConfig()
    server = ContextBridgeServer(config)
    transport = ContextBridgeHTTPTransport(config, server.router)
    client = AsyncClient(
        transport=ASGITransport(app=transport._app),
        base_url="http://test",
    )
    return client


@pytest.mark.asyncio
async def test_index_page(http_client: AsyncClient) -> None:
    resp = await http_client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "Context Bridge" in resp.text


@pytest.mark.asyncio
async def test_list_tools(http_client: AsyncClient) -> None:
    resp = await http_client.get("/mcp/v1/tools")
    assert resp.status_code == 200
    data = resp.json()
    assert "tools" in data


@pytest.mark.asyncio
async def test_health(http_client: AsyncClient) -> None:
    resp = await http_client.get("/mcp/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"


@pytest.mark.asyncio
async def test_cors_headers(http_client: AsyncClient) -> None:
    resp = await http_client.get("/mcp/v1/tools", headers={"Origin": "https://chat.openai.com"})
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == "*"


@pytest.mark.asyncio
async def test_call_tool_unknown(http_client: AsyncClient) -> None:
    resp = await http_client.post("/mcp/v1/tools/nope", json={})
    assert resp.status_code == 500
    data = resp.json()
    assert "error" in data
