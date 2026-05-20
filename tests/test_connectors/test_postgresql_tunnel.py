"""Tests for PostgreSQL connector SSH tunnel helpers."""

import pytest

from context_bridge.connectors.postgresql import PostgreSQLConnector
from context_bridge.config import PostgreSQLSource, SSHHost


def test_parse_host_port_key_value() -> None:
    conn_str = "host=myhost port=5433 dbname=mydb"
    host, port = PostgreSQLConnector._parse_host_port(conn_str)
    assert host == "myhost"
    assert port == 5433


def test_parse_host_port_url() -> None:
    conn_str = "postgresql://user:pass@myhost:5433/mydb"
    host, port = PostgreSQLConnector._parse_host_port(conn_str)
    assert host == "myhost"
    assert port == 5433


def test_parse_host_port_defaults() -> None:
    conn_str = "dbname=mydb"
    host, port = PostgreSQLConnector._parse_host_port(conn_str)
    assert host == "localhost"
    assert port == 5432


def test_rewrite_port_key_value() -> None:
    conn_str = "host=myhost port=5433 dbname=mydb"
    rewritten = PostgreSQLConnector._rewrite_port(conn_str, 9000)
    assert "host=127.0.0.1" in rewritten
    assert "port=9000" in rewritten


def test_rewrite_port_url() -> None:
    conn_str = "postgresql://user:pass@myhost:5433/mydb"
    rewritten = PostgreSQLConnector._rewrite_port(conn_str, 9000)
    assert "127.0.0.1:9000" in rewritten
    assert "myhost" not in rewritten


def test_connector_with_ssh_hosts() -> None:
    sources = [
        PostgreSQLSource(
            name="remote-db",
            connection_string="host=db.internal port=5432 dbname=app",
            ssh_tunnel="bastion",
        )
    ]
    ssh_hosts = [SSHHost(host="bastion.example.com", user="admin", port=22)]
    conn = PostgreSQLConnector(sources, ssh_hosts)
    assert conn._ssh_hosts == ssh_hosts


def test_resolve_ssh_host() -> None:
    ssh_hosts = [
        SSHHost(host="bastion1", user="admin"),
        SSHHost(host="bastion2", user="root"),
    ]
    conn = PostgreSQLConnector([], ssh_hosts)
    h = conn._resolve_ssh_host("bastion2")
    assert h.user == "root"


def test_resolve_ssh_host_unknown() -> None:
    conn = PostgreSQLConnector([], [SSHHost(host="bastion", user="admin")])
    with pytest.raises(ValueError, match="Unknown SSH host"):
        conn._resolve_ssh_host("missing")
