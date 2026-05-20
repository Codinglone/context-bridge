"""Tests for the PostgreSQL connector."""

from unittest.mock import MagicMock, patch

import pytest

from context_bridge.connectors.postgresql import PostgreSQLConnector
from context_bridge.config import PostgreSQLSource


@pytest.fixture
def connector() -> PostgreSQLConnector:
    sources = [
        PostgreSQLSource(
            name="local-dev",
            connection_string="postgresql://user:pass@localhost/db",
            schemas=["public"],
            query_timeout=30,
        )
    ]
    return PostgreSQLConnector(sources)


def test_resolve_source(connector: PostgreSQLConnector) -> None:
    src = connector._resolve_source("local-dev")
    assert src.name == "local-dev"


def test_resolve_source_unknown(connector: PostgreSQLConnector) -> None:
    with pytest.raises(ValueError, match="Unknown connection"):
        connector._resolve_source("missing")


@patch("context_bridge.connectors.postgresql.psycopg.connect")
def test_list_tables(mock_connect, connector: PostgreSQLConnector) -> None:
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = [
        {"table_name": "users"},
        {"table_name": "orders"},
    ]
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mock_connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
    mock_connect.return_value.__exit__ = MagicMock(return_value=False)

    result = connector._list_tables("local-dev", "public")
    assert len(result) == 2
    assert result[0]["name"] == "users"
    assert result[1]["name"] == "orders"


@patch("context_bridge.connectors.postgresql.psycopg.connect")
def test_get_schema(mock_connect, connector: PostgreSQLConnector) -> None:
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = [
        {
            "column_name": "id",
            "data_type": "integer",
            "is_nullable": "NO",
            "column_default": "nextval('users_id_seq')",
        },
        {
            "column_name": "email",
            "data_type": "character varying",
            "is_nullable": "YES",
            "column_default": None,
        },
    ]
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mock_connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
    mock_connect.return_value.__exit__ = MagicMock(return_value=False)

    result = connector._get_schema("local-dev", "public", "users")
    assert result[0]["column"] == "id"
    assert result[0]["nullable"] is False
    assert result[1]["column"] == "email"
    assert result[1]["nullable"] is True


@patch("context_bridge.connectors.postgresql.psycopg.connect")
def test_get_indexes(mock_connect, connector: PostgreSQLConnector) -> None:
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = [
        {"indexname": "users_pkey", "indexdef": "CREATE UNIQUE INDEX users_pkey ON users USING btree (id)"},
    ]
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mock_connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
    mock_connect.return_value.__exit__ = MagicMock(return_value=False)

    result = connector._get_indexes("local-dev", "public", "users")
    assert result[0]["name"] == "users_pkey"


@patch("context_bridge.connectors.postgresql.psycopg.connect")
def test_get_foreign_keys(mock_connect, connector: PostgreSQLConnector) -> None:
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = [
        {
            "column_name": "user_id",
            "foreign_table": "users",
            "foreign_column": "id",
        },
    ]
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mock_connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
    mock_connect.return_value.__exit__ = MagicMock(return_value=False)

    result = connector._get_foreign_keys("local-dev", "public", "orders")
    assert result[0]["column"] == "user_id"
    assert result[0]["references_table"] == "users"


@patch("context_bridge.connectors.postgresql.psycopg.connect")
def test_run_query(mock_connect, connector: PostgreSQLConnector) -> None:
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = [
        {"id": 1, "email": "alice@example.com"},
    ]
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mock_connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
    mock_connect.return_value.__exit__ = MagicMock(return_value=False)

    result = connector._run_query("local-dev", "SELECT * FROM users", 10)
    assert len(result) == 1
    assert result[0]["email"] == "alice@example.com"


def test_run_query_rejects_non_select(connector: PostgreSQLConnector) -> None:
    with pytest.raises(ValueError, match="Only SELECT"):
        connector._run_query("local-dev", "DROP TABLE users", 10)


def test_run_query_rejects_insert(connector: PostgreSQLConnector) -> None:
    with pytest.raises(ValueError, match="Only SELECT"):
        connector._run_query("local-dev", "INSERT INTO users VALUES (1)", 10)


@patch("context_bridge.connectors.postgresql.psycopg.connect")
def test_run_query_appends_limit(mock_connect, connector: PostgreSQLConnector) -> None:
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = []
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mock_connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
    mock_connect.return_value.__exit__ = MagicMock(return_value=False)

    connector._run_query("local-dev", "SELECT * FROM users", 50)
    executed_sql = mock_cur.execute.call_args[0][0]
    assert "LIMIT 50" in executed_sql
