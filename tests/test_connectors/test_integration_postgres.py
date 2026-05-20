"""Deep PostgreSQL integration test against the running container."""

import os

import pytest

from context_bridge.connectors.postgresql import PostgreSQLConnector
from context_bridge.config import PostgreSQLSource


DSN = os.environ.get("TEST_POSTGRES_URL", "")


@pytest.fixture
def pg_connector() -> PostgreSQLConnector:
    sources = [PostgreSQLSource(name="test", connection_string=DSN, schemas=["public"])]
    return PostgreSQLConnector(sources)


@pytest.mark.skipif(not DSN, reason="TEST_POSTGRES_URL not set")
def test_full_introspection(pg_connector: PostgreSQLConnector) -> None:
    """End-to-end: list tables, get schema, get indexes, get FKs, run query."""
    # List tables
    tables = pg_connector._list_tables("test", "public")
    table_names = {t["name"] for t in tables}
    assert "users" in table_names
    assert "orders" in table_names

    # Get users schema
    users_schema = pg_connector._get_schema("test", "public", "users")
    columns = {c["column"]: c for c in users_schema}
    assert "id" in columns
    assert columns["id"]["type"] == "integer"
    assert columns["id"]["nullable"] is False
    assert "email" in columns
    assert columns["email"]["nullable"] is False  # defined as NOT NULL
    assert "created_at" in columns
    assert columns["created_at"]["nullable"] is True  # has DEFAULT, so nullable

    # Get orders schema
    orders_schema = pg_connector._get_schema("test", "public", "orders")
    columns = {c["column"]: c for c in orders_schema}
    assert "user_id" in columns
    assert "total" in columns
    assert "status" in columns

    # Get indexes for orders
    indexes = pg_connector._get_indexes("test", "public", "orders")
    idx_names = {i["name"] for i in indexes}
    assert "orders_pkey" in idx_names
    assert "idx_orders_status" in idx_names

    # Get foreign keys for orders
    fks = pg_connector._get_foreign_keys("test", "public", "orders")
    assert len(fks) == 1
    assert fks[0]["column"] == "user_id"
    assert fks[0]["references_table"] == "users"
    assert fks[0]["references_column"] == "id"

    # Run a real query
    result = pg_connector._run_query("test", "SELECT * FROM users ORDER BY id", 10)
    assert len(result) == 2
    assert result[0]["email"] == "alice@example.com"
    assert result[1]["email"] == "bob@example.com"

    # Run a JOIN query
    result = pg_connector._run_query(
        "test",
        """
        SELECT u.email, o.total, o.status
        FROM users u
        JOIN orders o ON u.id = o.user_id
        ORDER BY u.id
        """,
        10,
    )
    assert len(result) == 2
    assert result[0]["status"] == "pending"
    assert result[1]["status"] == "shipped"


@pytest.mark.skipif(not DSN, reason="TEST_POSTGRES_URL not set")
def test_query_with_limit_appended(pg_connector: PostgreSQLConnector) -> None:
    """Verify LIMIT is auto-appended when not present."""
    result = pg_connector._run_query("test", "SELECT * FROM orders", 1)
    assert len(result) == 1


@pytest.mark.skipif(not DSN, reason="TEST_POSTGRES_URL not set")
def test_write_rejected(pg_connector: PostgreSQLConnector) -> None:
    """Verify INSERT/UPDATE/DELETE are all rejected."""
    with pytest.raises(ValueError, match="Only SELECT"):
        pg_connector._run_query("test", "INSERT INTO users (email) VALUES ('test')", 10)

    with pytest.raises(ValueError, match="Only SELECT"):
        pg_connector._run_query("test", "UPDATE users SET email = 'x' WHERE id = 1", 10)

    with pytest.raises(ValueError, match="Only SELECT"):
        pg_connector._run_query("test", "DELETE FROM users WHERE id = 1", 10)


@pytest.mark.skipif(not DSN, reason="TEST_POSTGRES_URL not set")
def test_caching(pg_connector: PostgreSQLConnector) -> None:
    """Verify repeated calls use cache."""
    r1 = pg_connector._list_tables("test", "public")
    r2 = pg_connector._list_tables("test", "public")
    assert r1 == r2
    # Cache hit should be instant
