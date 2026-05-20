"""SSH integration tests against a real SSH server container."""

import os
from pathlib import Path

import pytest

from context_bridge.connectors.ssh import SSHConnector
from context_bridge.config import SSHHost


SSH_HOST = os.environ.get("TEST_SSH_HOST", "localhost")
SSH_PORT = int(os.environ.get("TEST_SSH_PORT", "10022"))
SSH_USER = os.environ.get("TEST_SSH_USER", "testuser")
SSH_KEY = os.environ.get("TEST_SSH_KEY", "/tmp/cb-ssh-test/id_ed25519")


def _ssh_available() -> bool:
    import subprocess

    result = subprocess.run(
        [
            "ssh",
            "-o", "ConnectTimeout=2",
            "-o", "BatchMode=yes",
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "-p", str(SSH_PORT),
            "-i", SSH_KEY,
            f"{SSH_USER}@{SSH_HOST}",
            "exit",
        ],
        capture_output=True,
    )
    return result.returncode == 0


@pytest.fixture
def ssh_connector() -> SSHConnector:
    hosts = [
        SSHHost(
            host=SSH_HOST,
            user=SSH_USER,
            port=SSH_PORT,
            key=Path(SSH_KEY) if os.path.exists(SSH_KEY) else None,
        )
    ]
    return SSHConnector(hosts)


@pytest.mark.skipif(not _ssh_available(), reason="SSH server not available")
def test_run_command(ssh_connector: SSHConnector) -> None:
    result = ssh_connector._run_command(SSH_HOST, "echo hello", "")
    assert result["exit_code"] == 0
    assert "hello" in result["stdout"]
    assert result["stderr"] == ""


@pytest.mark.skipif(not _ssh_available(), reason="SSH server not available")
def test_run_command_with_cwd(ssh_connector: SSHConnector) -> None:
    result = ssh_connector._run_command(SSH_HOST, "pwd", "/tmp")
    assert result["exit_code"] == 0
    assert "/tmp" in result["stdout"]


@pytest.mark.skipif(not _ssh_available(), reason="SSH server not available")
def test_run_command_failure(ssh_connector: SSHConnector) -> None:
    result = ssh_connector._run_command(SSH_HOST, "exit 42", "")
    assert result["exit_code"] == 42


@pytest.mark.skipif(not _ssh_available(), reason="SSH server not available")
def test_read_file(ssh_connector: SSHConnector) -> None:
    content = ssh_connector._read_file(SSH_HOST, "/etc/hostname")
    assert len(content) > 0
    # Container hostname
    assert content.strip() != ""


@pytest.mark.skipif(not _ssh_available(), reason="SSH server not available")
def test_list_dir(ssh_connector: SSHConnector) -> None:
    entries = ssh_connector._list_dir(SSH_HOST, "/tmp")
    assert isinstance(entries, list)
    # /tmp might be empty but should still return a list


@pytest.mark.skipif(not _ssh_available(), reason="SSH server not available")
def test_connection_pooling(ssh_connector: SSHConnector) -> None:
    """Run multiple commands and verify they reuse the same SSH connection."""
    r1 = ssh_connector._run_command(SSH_HOST, "echo first", "")
    r2 = ssh_connector._run_command(SSH_HOST, "echo second", "")
    assert r1["exit_code"] == 0
    assert r2["exit_code"] == 0
    # Pool should have one connection
    assert len(ssh_connector._pool._clients) == 1
