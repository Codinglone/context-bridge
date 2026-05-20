"""Tests for the Docker connector."""

from unittest.mock import MagicMock, patch

import pytest

from context_bridge.connectors.docker import DockerConnector
from context_bridge.config import DockerConfig


@pytest.fixture
def connector() -> DockerConnector:
    cfg = DockerConfig(socket="unix:///var/run/docker.sock", include_stopped=False, max_log_lines=500)
    return DockerConnector(cfg)


@patch("docker.DockerClient")
def test_list_containers(mock_client, connector: DockerConnector) -> None:
    c1 = MagicMock()
    c1.id = "abc123def456"
    c1.name = "web"
    c1.image.tags = ["nginx:latest"]
    c1.status = "running"
    c1.ports = {"80/tcp": [{"HostIp": "0.0.0.0", "HostPort": "8080"}]}
    c1.attrs = {"Created": "2024-01-01T00:00:00Z"}

    mock_instance = MagicMock()
    mock_instance.containers.list.return_value = [c1]
    mock_client.return_value = mock_instance

    connector._client = mock_instance
    result = connector._list_containers(all_=False)

    assert len(result) == 1
    assert result[0]["name"] == "web"
    assert result[0]["status"] == "running"
    assert result[0]["id"] == "abc123def456"


@patch("docker.DockerClient")
def test_get_logs(mock_client, connector: DockerConnector) -> None:
    c1 = MagicMock()
    c1.logs.return_value = b"log line 1\nlog line 2"

    mock_instance = MagicMock()
    mock_instance.containers.get.return_value = c1
    mock_client.return_value = mock_instance

    connector._client = mock_instance
    result = connector._get_logs("web", 10)

    assert "log line 1" in result
    c1.logs.assert_called_with(tail=10, timestamps=False)


@patch("docker.DockerClient")
def test_get_logs_respects_max(mock_client, connector: DockerConnector) -> None:
    c1 = MagicMock()
    c1.logs.return_value = b"logs"

    mock_instance = MagicMock()
    mock_instance.containers.get.return_value = c1
    mock_client.return_value = mock_instance

    connector._client = mock_instance
    connector._get_logs("web", 1000)

    # max_log_lines is 500, so tail should be 500 not 1000
    c1.logs.assert_called_with(tail=500, timestamps=False)


@patch("docker.DockerClient")
def test_inspect(mock_client, connector: DockerConnector) -> None:
    c1 = MagicMock()
    c1.attrs = {
        "Id": "abc123",
        "Name": "/web",
        "Config": {"Image": "nginx", "Cmd": ["nginx", "-g", "daemon off;"], "Env": ["FOO=bar"], "ExposedPorts": {"80/tcp": {}}},
        "HostConfig": {"Mounts": [{"Destination": "/data"}]},
        "State": {"Status": "running", "Health": {"Status": "healthy"}, "StartedAt": "2024-01-01", "FinishedAt": "0001-01-01"},
        "NetworkSettings": {"Ports": {"80/tcp": [{"HostIp": "0.0.0.0", "HostPort": "8080"}]}},
    }

    mock_instance = MagicMock()
    mock_instance.containers.get.return_value = c1
    mock_client.return_value = mock_instance

    connector._client = mock_instance
    result = connector._inspect("web")

    assert result["name"] == "web"
    assert result["status"] == "running"
    assert result["health"] == "healthy"
    assert "/data" in result["mounts"]


@patch("docker.DockerClient")
def test_list_services(mock_client, connector: DockerConnector) -> None:
    c1 = MagicMock()
    c1.name = "project_web_1"
    c1.status = "running"
    c1.labels = {"com.docker.compose.project": "myproject", "com.docker.compose.service": "web"}

    c2 = MagicMock()
    c2.name = "project_db_1"
    c2.status = "running"
    c2.labels = {"com.docker.compose.project": "myproject", "com.docker.compose.service": "db"}

    mock_instance = MagicMock()
    mock_instance.containers.list.return_value = [c1, c2]
    mock_client.return_value = mock_instance

    connector._client = mock_instance
    result = connector._list_services()

    assert len(result) == 1
    assert result[0]["project"] == "myproject"
    assert len(result[0]["services"]) == 2
    service_names = {s["service"] for s in result[0]["services"]}
    assert service_names == {"web", "db"}


@patch("docker.DockerClient")
def test_list_services_no_compose(mock_client, connector: DockerConnector) -> None:
    c1 = MagicMock()
    c1.labels = {}

    mock_instance = MagicMock()
    mock_instance.containers.list.return_value = [c1]
    mock_client.return_value = mock_instance

    connector._client = mock_instance
    result = connector._list_services()

    assert result == []
