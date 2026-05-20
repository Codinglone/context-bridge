"""Tests for configuration module."""

import tempfile
from pathlib import Path

import pytest
import yaml

from context_bridge.config import ContextBridgeConfig


def test_default_config() -> None:
    cfg = ContextBridgeConfig()
    assert cfg.server.transport == "stdio"
    assert cfg.server.port == 8080
    assert cfg.server.host == "127.0.0.1"


def test_load_from_yaml() -> None:
    data = {
        "server": {"transport": "http", "port": 9000},
        "connectors": {"filesystem": [{"path": "/tmp", "name": "tmp"}]},
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(data, f)
        f.flush()
        path = Path(f.name)

    cfg = ContextBridgeConfig.from_yaml(path)
    assert cfg.server.transport == "http"
    assert cfg.server.port == 9000
    assert len(cfg.connectors.filesystem) == 1
    assert cfg.connectors.filesystem[0].path == Path("/tmp")


def test_load_missing_file() -> None:
    with pytest.raises(FileNotFoundError):
        ContextBridgeConfig.from_yaml(Path("/nonexistent/config.yaml"))
