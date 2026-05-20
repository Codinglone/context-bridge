"""Integration tests for Docker, PostgreSQL, SSH — skip when services unavailable."""

import os
from pathlib import Path

import pytest


def _docker_available() -> bool:
    try:
        import docker

        client = docker.DockerClient(base_url="unix:///var/run/docker.sock")
        client.ping()
        client.close()
        return True
    except Exception:
        return False


def _postgres_available() -> bool:
    try:
        import psycopg

        dsn = os.environ.get("TEST_POSTGRES_URL", "postgresql://postgres:postgres@localhost:5432/postgres")
        psycopg.connect(dsn).close()
        return True
    except Exception:
        return False


def _ssh_available() -> bool:
    import subprocess

    result = subprocess.run(
        ["ssh", "-o", "ConnectTimeout=2", "-o", "BatchMode=yes", "localhost", "exit"],
        capture_output=True,
    )
    return result.returncode == 0


# ---------------------------------------------------------------------------
# Docker
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not _docker_available(), reason="Docker not available")
def test_docker_list_containers_real() -> None:
    from context_bridge.connectors.docker import DockerConnector
    from context_bridge.config import DockerConfig

    cfg = DockerConfig(socket="unix:///var/run/docker.sock")
    conn = DockerConnector(cfg)
    import asyncio

    asyncio.run(conn.initialize())
    containers = conn._list_containers(all_=False)
    assert isinstance(containers, list)
    asyncio.run(conn.shutdown())


# ---------------------------------------------------------------------------
# PostgreSQL
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not _postgres_available(), reason="PostgreSQL not available")
def test_postgres_list_tables_real() -> None:
    from context_bridge.connectors.postgresql import PostgreSQLConnector
    from context_bridge.config import PostgreSQLSource

    # Assumes a local PostgreSQL with default credentials for testing
    # Override with TEST_POSTGRES_URL env var
    dsn = os.environ.get("TEST_POSTGRES_URL", "postgresql://postgres:postgres@localhost:5432/postgres")
    sources = [PostgreSQLSource(name="test", connection_string=dsn, schemas=["public"])]
    conn = PostgreSQLConnector(sources)
    tables = conn._list_tables("test", "public")
    assert isinstance(tables, list)


@pytest.mark.skipif(not _postgres_available(), reason="PostgreSQL not available")
def test_postgres_run_query_real() -> None:
    from context_bridge.connectors.postgresql import PostgreSQLConnector
    from context_bridge.config import PostgreSQLSource

    dsn = os.environ.get("TEST_POSTGRES_URL", "postgresql://postgres:postgres@localhost:5432/postgres")
    sources = [PostgreSQLSource(name="test", connection_string=dsn, schemas=["public"])]
    conn = PostgreSQLConnector(sources)
    result = conn._run_query("test", "SELECT 1 AS one, 'hello' AS msg", 10)
    assert len(result) == 1
    assert result[0]["one"] == 1
    assert result[0]["msg"] == "hello"


@pytest.mark.skipif(not _postgres_available(), reason="PostgreSQL not available")
def test_postgres_rejects_write_real() -> None:
    from context_bridge.connectors.postgresql import PostgreSQLConnector
    from context_bridge.config import PostgreSQLSource

    dsn = os.environ.get("TEST_POSTGRES_URL", "postgresql://postgres:postgres@localhost:5432/postgres")
    sources = [PostgreSQLSource(name="test", connection_string=dsn, schemas=["public"])]
    conn = PostgreSQLConnector(sources)
    with pytest.raises(ValueError, match="Only SELECT"):
        conn._run_query("test", "CREATE TABLE _temp_test (id INT)", 10)


# ---------------------------------------------------------------------------
# SSH
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not _ssh_available(), reason="SSH not available")
def test_ssh_run_command_localhost() -> None:
    from context_bridge.connectors.ssh import SSHConnector
    from context_bridge.config import SSHHost

    hosts = [SSHHost(host="localhost", user=os.environ.get("USER", "root"))]
    conn = SSHConnector(hosts)
    result = conn._run_command("localhost", "echo hello", "")
    assert "hello" in result["stdout"]
    assert result["exit_code"] == 0


@pytest.mark.skipif(not _ssh_available(), reason="SSH not available")
def test_ssh_read_file_localhost() -> None:
    from context_bridge.connectors.ssh import SSHConnector
    from context_bridge.config import SSHHost

    hosts = [SSHHost(host="localhost", user=os.environ.get("USER", "root"))]
    conn = SSHConnector(hosts)
    result = conn._read_file("localhost", "/etc/hostname")
    assert len(result) > 0
