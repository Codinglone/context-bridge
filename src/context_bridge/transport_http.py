"""HTTP/SSE MCP server using Starlette and sse-starlette."""

import json
import logging

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from context_bridge.config import ContextBridgeConfig
from context_bridge.router import Router

logger = logging.getLogger(__name__)


class MCPHTTPTransport:
    """MCP over HTTP/SSE — the new Streamable HTTP transport standard.

    This allows web-based clients (browsers, web apps) to connect to
    Context Bridge without needing stdio pipes.
    """

    def __init__(self, config: ContextBridgeConfig, router: Router) -> None:
        self.config = config
        self.router = router
        self._app: Starlette | None = None

    def build_app(self) -> Starlette:
        """Build the ASGI app with MCP endpoints."""
        middleware = [
            Middleware(
                CORSMiddleware,
                allow_origins=["*"],
                allow_methods=["*"],
                allow_headers=["*"],
            )
        ]

        routes = [
            Route("/mcp/v1/tools", endpoint=self._list_tools, methods=["GET"]),
            Route("/mcp/v1/tools/{tool_name:path}", endpoint=self._call_tool, methods=["POST"]),
            Route("/mcp/v1/health", endpoint=self._health, methods=["GET"]),
            Route("/", endpoint=self._index, methods=["GET"]),
        ]

        self._app = Starlette(
            debug=False,
            routes=routes,
            middleware=middleware,
        )
        return self._app

    async def _index(self, request: Request) -> Response:
        """Simple landing page with available tools."""
        tools = self.router.list_tools()
        html = """<!DOCTYPE html>
<html>
<head>
    <title>Context Bridge</title>
    <style>
        body {
            font-family: -apple-system, sans-serif;
            max-width: 800px;
            margin: 40px auto;
            padding: 0 20px;
        }
        h1 { color: #333; }
        .tool {
            border: 1px solid #e0e0e0;
            border-radius: 8px;
            padding: 16px;
            margin: 12px 0;
        }
        .tool-name {
            font-weight: bold;
            color: #0066cc;
            font-size: 1.1em;
        }
        .tool-desc { color: #666; margin-top: 4px; }
        .endpoint {
            background: #f5f5f5;
            padding: 8px 12px;
            border-radius: 4px;
            font-family: monospace;
            margin-top: 8px;
            font-size: 0.9em;
        }
        code {
            background: #f5f5f5;
            padding: 2px 6px;
            border-radius: 3px;
        }
    </style>
</head>
<body>
    <h1>Context Bridge</h1>
    <p>Local context server running on <code>localhost:8080</code></p>
    <p>Connected connectors: """ + str(len(self.router._connectors)) + """</p>

    <h2>Available Tools</h2>
"""
        for tool in tools:
            name = tool.get("name", "unknown")
            desc = tool.get("description", "")
            html += f"""
    <div class="tool">
        <div class="tool-name">{name}</div>
        <div class="tool-desc">{desc}</div>
        <div class="endpoint">POST /mcp/v1/tools/{name}</div>
    </div>
"""

        html += """
    <h2>Usage</h2>
    <p>For web-based chatbots, copy relevant context and paste into the chat:</p>
    <pre><code>curl http://localhost:8080/mcp/v1/tools/fs.read_file \
  -X POST \
  -H "Content-Type: application/json" \
  -d '{"path": "src/main.py"}'</code></pre>

    <p>Or open this page in your browser to browse available context.</p>
</body>
</html>"""
        return Response(html, media_type="text/html")

    async def _list_tools(self, request: Request) -> JSONResponse:
        """Return the full catalog of available tools."""
        tools = self.router.list_tools()
        return JSONResponse({"tools": tools})

    async def _call_tool(self, request: Request) -> JSONResponse:
        """Execute a tool call via HTTP POST."""
        tool_name = request.path_params["tool_name"]
        try:
            body = await request.json()
        except json.JSONDecodeError:
            return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

        try:
            result = await self.router.call_tool(tool_name, body)
            return JSONResponse({"result": result})
        except Exception as exc:
            logger.exception("Tool call failed")
            return JSONResponse({"error": str(exc)}, status_code=500)

    async def _health(self, request: Request) -> JSONResponse:
        """Health check endpoint."""
        health = self.router.health()
        return JSONResponse({
            "status": "healthy",
            "connectors": health,
        })


class ContextBridgeHTTPTransport:
    """Wrapper that runs the HTTP app via uvicorn."""

    def __init__(self, config: ContextBridgeConfig, router: Router) -> None:
        self.config = config
        self.router = router
        self._transport = MCPHTTPTransport(config, router)
        self._app = self._transport.build_app()

    async def start(self, host: str, port: int) -> None:
        import uvicorn

        config = uvicorn.Config(
            self._app,
            host=host,
            port=port,
            log_level="info",
            loop="asyncio",
        )
        server = uvicorn.Server(config)
        await server.serve()
