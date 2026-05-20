"""Configuration loader and Pydantic settings for Context Bridge."""

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, ValidationError
from pydantic_settings import BaseSettings

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "context-bridge" / "config.yaml"


class ServerConfig(BaseModel):
    transport: str = Field(default="stdio", pattern=r"^(stdio|http|sse)$")
    port: int = Field(default=8080, ge=1024, le=65535)
    host: str = "127.0.0.1"


class FilesystemSource(BaseModel):
    path: Path
    name: str | None = None
    exclude: list[str] = Field(default_factory=lambda: ["node_modules", ".git"])
    max_file_size: int = 1_048_576  # 1 MB


class GitHubConfig(BaseModel):
    token: str | None = None
    repos: list[str] = Field(default_factory=list)
    cache_ttl: int = 300  # seconds


class SSHHost(BaseModel):
    host: str
    user: str
    port: int = 22
    key: Path | None = None


class ObsidianConfig(BaseModel):
    vault: Path
    exclude: list[str] = Field(default_factory=lambda: [".git", "attachments"])


class PostgreSQLSource(BaseModel):
    name: str
    connection_string: str
    schemas: list[str] = Field(default_factory=lambda: ["public"])
    include_query_history: bool = False
    query_timeout: int = 30
    ssh_tunnel: str | None = None  # SSH host alias to tunnel through


class DockerConfig(BaseModel):
    socket: str = "unix:///var/run/docker.sock"
    include_stopped: bool = False
    max_log_lines: int = 500


class ConnectorsConfig(BaseModel):
    filesystem: list[FilesystemSource] = Field(default_factory=list)
    github: GitHubConfig | None = None
    ssh: list[SSHHost] = Field(default_factory=list)
    obsidian: ObsidianConfig | None = None
    postgresql: list[PostgreSQLSource] = Field(default_factory=list)
    docker: DockerConfig | None = None


class ContextBridgeConfig(BaseSettings):
    server: ServerConfig = Field(default_factory=ServerConfig)
    connectors: ConnectorsConfig = Field(default_factory=ConnectorsConfig)

    @classmethod
    def from_yaml(cls, path: Path) -> "ContextBridgeConfig":
        """Load configuration from a YAML file."""
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")

        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}

        try:
            return cls.model_validate(raw)
        except ValidationError as exc:
            raise ValueError(f"Invalid configuration in {path}: {exc}") from exc

    def get_connector_config(self, name: str) -> Any:
        """Return the configuration dict for a named connector."""
        return getattr(self.connectors, name, None)
