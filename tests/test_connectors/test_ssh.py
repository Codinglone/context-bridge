"""Tests for the SSH connector."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from context_bridge.connectors.ssh import SSHConnector
from context_bridge.config import SSHHost


@pytest.fixture
def connector() -> SSHConnector:
    hosts = [SSHHost(host="prod.example.com", user="deploy", key=Path("/tmp/fake_key"))]
    return SSHConnector(hosts)


def test_resolve_host(connector: SSHConnector) -> None:
    h = connector._resolve_host("prod.example.com")
    assert h.user == "deploy"


def test_resolve_host_unknown(connector: SSHConnector) -> None:
    with pytest.raises(ValueError, match="Unknown host"):
        connector._resolve_host("nope")


@patch("paramiko.SSHClient")
def test_run_command(mock_ssh, connector: SSHConnector) -> None:
    mock_client = MagicMock()
    mock_transport = MagicMock()
    mock_transport.is_active.return_value = True
    mock_client.get_transport.return_value = mock_transport

    mock_stdout = MagicMock()
    mock_stdout.channel.recv_exit_status.return_value = 0
    mock_stdout.read.return_value = b"hello output"
    mock_stderr = MagicMock()
    mock_stderr.read.return_value = b""

    mock_client.exec_command.return_value = (None, mock_stdout, mock_stderr)
    mock_ssh.return_value = mock_client

    connector._pool._clients = {"deploy@prod.example.com:22": mock_client}
    result = connector._run_command("prod.example.com", "echo hello", "")

    assert result["stdout"] == "hello output"
    assert result["exit_code"] == 0
    mock_client.exec_command.assert_called_with("echo hello")


@patch("paramiko.SSHClient")
def test_run_command_with_cwd(mock_ssh, connector: SSHConnector) -> None:
    mock_client = MagicMock()
    mock_transport = MagicMock()
    mock_transport.is_active.return_value = True
    mock_client.get_transport.return_value = mock_transport

    mock_stdout = MagicMock()
    mock_stdout.channel.recv_exit_status.return_value = 0
    mock_stdout.read.return_value = b"output"
    mock_stderr = MagicMock()
    mock_stderr.read.return_value = b""

    mock_client.exec_command.return_value = (None, mock_stdout, mock_stderr)
    mock_ssh.return_value = mock_client

    connector._pool._clients = {"deploy@prod.example.com:22": mock_client}
    connector._run_command("prod.example.com", "ls", "/var/log")

    mock_client.exec_command.assert_called_with("cd /var/log && ls")


@patch("paramiko.SSHClient")
def test_read_file(mock_ssh, connector: SSHConnector) -> None:
    mock_client = MagicMock()
    mock_transport = MagicMock()
    mock_transport.is_active.return_value = True
    mock_client.get_transport.return_value = mock_transport

    mock_sftp = MagicMock()
    mock_file = MagicMock()
    mock_file.read.return_value = b"file contents"
    mock_sftp.file.return_value.__enter__ = MagicMock(return_value=mock_file)
    mock_sftp.file.return_value.__exit__ = MagicMock(return_value=False)
    mock_client.open_sftp.return_value = mock_sftp

    connector._pool._clients = {"deploy@prod.example.com:22": mock_client}
    result = connector._read_file("prod.example.com", "/etc/config.yaml")

    assert result == "file contents"
    mock_sftp.file.assert_called_with("/etc/config.yaml", "r")


@patch("paramiko.SSHClient")
def test_list_dir(mock_ssh, connector: SSHConnector) -> None:
    mock_client = MagicMock()
    mock_transport = MagicMock()
    mock_transport.is_active.return_value = True
    mock_client.get_transport.return_value = mock_transport

    mock_entry = MagicMock()
    mock_entry.filename = "alpha.txt"
    mock_entry.st_size = 1024
    mock_entry.st_mode = 0o100644
    mock_entry.st_mtime = 1700000000

    mock_entry2 = MagicMock()
    mock_entry2.filename = "beta"
    mock_entry2.st_size = 4096
    mock_entry2.st_mode = 0o40755
    mock_entry2.st_mtime = 1700000001

    mock_sftp = MagicMock()
    mock_sftp.listdir_attr.return_value = [mock_entry2, mock_entry]
    mock_client.open_sftp.return_value = mock_sftp

    connector._pool._clients = {"deploy@prod.example.com:22": mock_client}
    result = connector._list_dir("prod.example.com", "/var/log")

    assert len(result) == 2
    assert result[0]["name"] == "alpha.txt"
    assert result[0]["type"] == "file"
    assert result[1]["name"] == "beta"
    assert result[1]["type"] == "directory"
