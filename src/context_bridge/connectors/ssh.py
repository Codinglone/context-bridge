"""SSH connector — execute commands and read files on remote servers."""

from typing import Any

import paramiko

from context_bridge.cache import CacheManager
from context_bridge.config import SSHHost
from context_bridge.connectors.base import BaseConnector


class _SSHPool:
    """Simple SSH connection pool keyed by host."""

    def __init__(self) -> None:
        self._clients: dict[str, paramiko.SSHClient] = {}

    def get(
        self,
        host: str,
        port: int,
        user: str,
        key_path: str | None = None,
    ) -> paramiko.SSHClient:
        key = f"{user}@{host}:{port}"
        if key in self._clients:
            transport = self._clients[key].get_transport()
            if transport and transport.is_active():
                return self._clients[key]
            # stale connection
            self._clients[key].close()

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        connect_kwargs: dict[str, Any] = {
            "hostname": host,
            "port": port,
            "username": user,
            "timeout": 10,
            "allow_agent": True,
            "look_for_keys": True,
        }
        if key_path:
            connect_kwargs["key_filename"] = key_path

        client.connect(**connect_kwargs)
        self._clients[key] = client
        return client

    def close_all(self) -> None:
        for client in self._clients.values():
            client.close()
        self._clients.clear()


class SSHConnector(BaseConnector):
    """Execute commands and read files on remote VMs/servers."""

    name = "ssh"
    description = "Remote SSH access"

    def __init__(self, config: list[SSHHost]) -> None:
        super().__init__(config)
        self._hosts: list[SSHHost] = config
        self._pool = _SSHPool()
        self._cache = CacheManager()

    async def initialize(self) -> None:
        self._initialized = True

    async def shutdown(self) -> None:
        self._pool.close_all()
        self._initialized = False

    def get_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "ssh.run_command",
                "description": "Run a command on a remote host via SSH",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "host": {"type": "string", "description": "Host alias or hostname"},
                        "command": {"type": "string", "description": "Shell command to execute"},
                        "cwd": {
                            "type": "string",
                            "default": "",
                            "description": "Working directory",
                        },
                    },
                    "required": ["host", "command"],
                },
            },
            {
                "name": "ssh.read_file",
                "description": "Read a file on a remote host",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "host": {"type": "string", "description": "Host alias or hostname"},
                        "path": {"type": "string", "description": "Absolute file path"},
                    },
                    "required": ["host", "path"],
                },
            },
            {
                "name": "ssh.list_dir",
                "description": "List a directory on a remote host",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "host": {"type": "string", "description": "Host alias or hostname"},
                        "path": {"type": "string", "description": "Absolute directory path"},
                    },
                    "required": ["host", "path"],
                },
            },
        ]

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        if tool_name == "run_command":
            return self._run_command(
                arguments["host"],
                arguments["command"],
                arguments.get("cwd", ""),
            )
        if tool_name == "read_file":
            return self._read_file(arguments["host"], arguments["path"])
        if tool_name == "list_dir":
            return self._list_dir(arguments["host"], arguments["path"])
        raise ValueError(f"Unknown tool: {tool_name}")

    def _resolve_host(self, alias: str) -> SSHHost:
        """Find host config by alias or exact hostname match."""
        for h in self._hosts:
            if h.host == alias:
                return h
        raise ValueError(f"Unknown host: {alias}")

    def _run_command(self, alias: str, command: str, cwd: str) -> dict[str, Any]:
        host = self._resolve_host(alias)
        key = str(host.key) if host.key else None
        client = self._pool.get(host.host, host.port, host.user, key)

        full_cmd = command
        if cwd:
            full_cmd = f"cd {cwd} && {command}"

        stdin, stdout, stderr = client.exec_command(full_cmd)
        exit_code = stdout.channel.recv_exit_status()
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")

        return {
            "stdout": out,
            "stderr": err,
            "exit_code": exit_code,
        }

    def _read_file(self, alias: str, path: str) -> str:
        host = self._resolve_host(alias)
        key = str(host.key) if host.key else None
        client = self._pool.get(host.host, host.port, host.user, key)

        sftp = client.open_sftp()
        try:
            with sftp.file(path, "r") as f:
                data: bytes = f.read()
                return data.decode("utf-8", errors="replace")
        finally:
            sftp.close()

    def _list_dir(self, alias: str, path: str) -> list[dict[str, Any]]:
        host = self._resolve_host(alias)
        key = str(host.key) if host.key else None
        client = self._pool.get(host.host, host.port, host.user, key)

        sftp = client.open_sftp()
        try:
            entries = []
            for entry in sftp.listdir_attr(path):
                entries.append({
                    "name": entry.filename,
                    "size": entry.st_size,
                    "type": "directory" if entry.st_mode & 0o40000 else "file",
                    "modified": entry.st_mtime,
                })
            return sorted(entries, key=lambda e: e["name"])
        finally:
            sftp.close()
