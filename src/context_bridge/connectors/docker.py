"""Docker connector — inspect containers, stream logs, view services."""

from typing import Any

import docker

from context_bridge.cache import CacheManager
from context_bridge.config import DockerConfig
from context_bridge.connectors.base import BaseConnector


class DockerConnector(BaseConnector):
    """Inspect running containers and read logs."""

    name = "docker"
    description = "Docker container access"

    def __init__(self, config: DockerConfig) -> None:
        super().__init__(config)
        self._socket = config.socket
        self._include_stopped = config.include_stopped
        self._max_log_lines = config.max_log_lines
        self._client: docker.DockerClient | None = None
        self._cache = CacheManager()

    async def initialize(self) -> None:
        self._client = docker.DockerClient(base_url=self._socket)
        # Quick health check
        self._client.ping()
        self._initialized = True

    async def shutdown(self) -> None:
        if self._client:
            self._client.close()
            self._client = None
        self._initialized = False

    def get_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "docker.list_containers",
                "description": "List running (or all) containers",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "all": {"type": "boolean", "default": False},
                    },
                },
            },
            {
                "name": "docker.get_logs",
                "description": "Get recent logs from a container",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "container": {"type": "string", "description": "Container name or ID"},
                        "tail": {"type": "integer", "default": 100},
                    },
                    "required": ["container"],
                },
            },
            {
                "name": "docker.inspect",
                "description": "Inspect a container (image, ports, env, mounts, health)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "container": {"type": "string"},
                    },
                    "required": ["container"],
                },
            },
            {
                "name": "docker.list_services",
                "description": "List Docker Compose services (if using compose)",
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
        ]

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        if not self._client:
            raise RuntimeError("Docker connector not initialized")

        if tool_name == "list_containers":
            return self._list_containers(arguments.get("all", False))
        if tool_name == "get_logs":
            return self._get_logs(arguments["container"], arguments.get("tail", 100))
        if tool_name == "inspect":
            return self._inspect(arguments["container"])
        if tool_name == "list_services":
            return self._list_services()
        raise ValueError(f"Unknown tool: {tool_name}")

    def _list_containers(self, all_: bool) -> list[dict]:
        cache_key = ("containers", all_)
        try:
            return self._cache.get(self.name, *cache_key)
        except KeyError:
            pass

        containers = self._client.containers.list(all=all_)
        result = [
            {
                "id": c.id[:12],
                "name": c.name,
                "image": c.image.tags[0] if c.image.tags else c.image.id[:12],
                "status": c.status,
                "ports": c.ports,
                "created": c.attrs["Created"],
            }
            for c in containers
        ]

        self._cache.set(self.name, *cache_key, value=result, ttl=10)
        return result

    def _get_logs(self, container: str, tail: int) -> str:
        tail = min(tail, self._max_log_lines)
        c = self._client.containers.get(container)
        logs = c.logs(tail=tail, timestamps=False).decode("utf-8", errors="replace")
        return logs

    def _inspect(self, container: str) -> dict:
        cache_key = ("inspect", container)
        try:
            return self._cache.get(self.name, *cache_key)
        except KeyError:
            pass

        c = self._client.containers.get(container)
        attrs = c.attrs
        config = attrs.get("Config", {})
        host_config = attrs.get("HostConfig", {})
        state = attrs.get("State", {})

        result = {
            "id": attrs.get("Id", "")[:12],
            "name": attrs.get("Name", "").lstrip("/"),
            "image": config.get("Image", ""),
            "command": config.get("Cmd", []),
            "env": config.get("Env", []),
            "ports": config.get("ExposedPorts", {}),
            "host_ports": attrs.get("NetworkSettings", {}).get("Ports", {}),
            "mounts": [m.get("Destination") for m in host_config.get("Mounts", [])],
            "status": state.get("Status"),
            "health": state.get("Health", {}).get("Status"),
            "started": state.get("StartedAt"),
            "finished": state.get("FinishedAt"),
        }

        self._cache.set(self.name, *cache_key, value=result, ttl=10)
        return result

    def _list_services(self) -> list[dict]:
        """List Docker Compose projects and services."""
        cache_key = ("services",)
        try:
            return self._cache.get(self.name, *cache_key)
        except KeyError:
            pass

        containers = self._client.containers.list()
        projects: dict[str, list[dict]] = {}
        for c in containers:
            labels = c.labels or {}
            project = labels.get("com.docker.compose.project")
            service = labels.get("com.docker.compose.service")
            if project and service:
                projects.setdefault(project, []).append(
                    {"service": service, "container": c.name, "status": c.status}
                )

        result = [
            {"project": proj, "services": svcs}
            for proj, svcs in sorted(projects.items())
        ]

        self._cache.set(self.name, *cache_key, value=result, ttl=10)
        return result
