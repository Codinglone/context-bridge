"""PostgreSQL connector — schema introspection and query history with SSH tunnel support."""

import re
import select
import socket
import threading
from typing import Any

import paramiko
import psycopg
from psycopg.rows import dict_row

from context_bridge.cache import CacheManager
from context_bridge.config import PostgreSQLSource, SSHHost
from context_bridge.connectors.base import BaseConnector


class _SSHTunnel:
    """Local port forward through an SSH server to a remote PostgreSQL port."""

    def __init__(
        self,
        ssh_host: str,
        ssh_port: int,
        ssh_user: str,
        ssh_key: str | None,
        remote_host: str,
        remote_port: int,
    ) -> None:
        self.ssh_host = ssh_host
        self.ssh_port = ssh_port
        self.ssh_user = ssh_user
        self.ssh_key = ssh_key
        self.remote_host = remote_host
        self.remote_port = remote_port
        self.local_port: int = 0
        self._client: paramiko.SSHClient | None = None
        self._server: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self) -> int:
        """Open the tunnel and return the local bound port."""
        self._client = paramiko.SSHClient()
        self._client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        kwargs: dict[str, Any] = {
            "hostname": self.ssh_host,
            "port": self.ssh_port,
            "username": self.ssh_user,
            "timeout": 10,
            "allow_agent": True,
            "look_for_keys": True,
        }
        if self.ssh_key:
            kwargs["key_filename"] = self.ssh_key
        self._client.connect(**kwargs)

        self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server.bind(("127.0.0.1", 0))
        self._server.listen(5)
        self.local_port = self._server.getsockname()[1]

        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()
        return self.local_port

    def _serve(self) -> None:
        """Accept local connections and forward through SSH transport."""
        transport = self._client.get_transport() if self._client else None
        if not transport or not self._server:
            return

        while not self._stop.is_set():
            readable, _, _ = select.select([self._server], [], [], 1.0)
            if not readable:
                continue
            try:
                local_sock, _ = self._server.accept()
            except OSError:
                break

            try:
                channel = transport.open_channel(
                    "direct-tcpip",
                    (self.remote_host, self.remote_port),
                    local_sock.getsockname(),
                )
            except Exception:
                local_sock.close()
                continue

            threading.Thread(
                target=self._forward,
                args=(local_sock, channel),
                daemon=True,
            ).start()

    @staticmethod
    def _forward(sock: socket.socket, channel: paramiko.Channel) -> None:
        """Bidirectional forward between a local socket and an SSH channel."""
        while True:
            readable, _, _ = select.select([sock, channel], [], [], 1.0)
            try:
                if sock in readable:
                    data = sock.recv(16384)
                    if not data:
                        break
                    channel.send(data)
                if channel in readable:
                    data = channel.recv(16384)
                    if not data:
                        break
                    sock.send(data)
            except Exception:
                break
        sock.close()
        channel.close()

    def stop(self) -> None:
        self._stop.set()
        if self._server:
            self._server.close()
        if self._client:
            self._client.close()
        if self._thread:
            self._thread.join(timeout=2)


class PostgreSQLConnector(BaseConnector):
    """Introspect PostgreSQL schemas and run read-only queries."""

    name = "pg"
    description = "PostgreSQL database access"

    def __init__(
        self,
        config: list[PostgreSQLSource],
        ssh_hosts: list[SSHHost] | None = None,
    ) -> None:
        super().__init__(config)
        self._sources: list[PostgreSQLSource] = config
        self._ssh_hosts: list[SSHHost] = ssh_hosts or []
        self._cache = CacheManager()
        self._tunnels: dict[str, _SSHTunnel] = {}  # source_name -> tunnel

    async def initialize(self) -> None:
        self._initialized = True

    async def shutdown(self) -> None:
        for tunnel in self._tunnels.values():
            tunnel.stop()
        self._tunnels.clear()
        self._initialized = False

    def get_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "pg.list_tables",
                "description": "List tables in a schema",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Connection name from config"},
                        "schema": {"type": "string", "default": "public"},
                    },
                    "required": ["name"],
                },
            },
            {
                "name": "pg.get_schema",
                "description": "Get column details for a table",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Connection name"},
                        "schema": {"type": "string", "default": "public"},
                        "table": {"type": "string"},
                    },
                    "required": ["name", "table"],
                },
            },
            {
                "name": "pg.get_indexes",
                "description": "List indexes for a table",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Connection name"},
                        "schema": {"type": "string", "default": "public"},
                        "table": {"type": "string"},
                    },
                    "required": ["name", "table"],
                },
            },
            {
                "name": "pg.get_foreign_keys",
                "description": "List foreign key relationships for a table",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Connection name"},
                        "schema": {"type": "string", "default": "public"},
                        "table": {"type": "string"},
                    },
                    "required": ["name", "table"],
                },
            },
            {
                "name": "pg.run_query",
                "description": "Execute a read-only SELECT query",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Connection name"},
                        "sql": {"type": "string"},
                        "limit": {"type": "integer", "default": 100},
                    },
                    "required": ["name", "sql"],
                },
            },
        ]

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        if tool_name == "list_tables":
            return self._list_tables(
                arguments["name"], arguments.get("schema", "public")
            )
        if tool_name == "get_schema":
            return self._get_schema(
                arguments["name"],
                arguments.get("schema", "public"),
                arguments["table"],
            )
        if tool_name == "get_indexes":
            return self._get_indexes(
                arguments["name"],
                arguments.get("schema", "public"),
                arguments["table"],
            )
        if tool_name == "get_foreign_keys":
            return self._get_foreign_keys(
                arguments["name"],
                arguments.get("schema", "public"),
                arguments["table"],
            )
        if tool_name == "run_query":
            return self._run_query(
                arguments["name"],
                arguments["sql"],
                arguments.get("limit", 100),
            )
        raise ValueError(f"Unknown tool: {tool_name}")

    def _resolve_source(self, name: str) -> PostgreSQLSource:
        for src in self._sources:
            if src.name == name:
                return src
        raise ValueError(f"Unknown connection: {name}")

    def _resolve_ssh_host(self, alias: str) -> SSHHost:
        for h in self._ssh_hosts:
            if h.host == alias:
                return h
        raise ValueError(f"Unknown SSH host for tunnel: {alias}")

    def _get_connection_string(self, source: PostgreSQLSource) -> str:
        """Return a connection string, opening an SSH tunnel if configured."""
        if not source.ssh_tunnel:
            return source.connection_string

        # Reuse existing tunnel
        if source.name in self._tunnels:
            tunnel = self._tunnels[source.name]
            return self._rewrite_port(source.connection_string, tunnel.local_port)

        # Open new tunnel
        ssh_cfg = self._resolve_ssh_host(source.ssh_tunnel)
        # Parse connection string to find remote host/port
        remote_host, remote_port = self._parse_host_port(source.connection_string)
        tunnel = _SSHTunnel(
            ssh_host=ssh_cfg.host,
            ssh_port=ssh_cfg.port,
            ssh_user=ssh_cfg.user,
            ssh_key=str(ssh_cfg.key) if ssh_cfg.key else None,
            remote_host=remote_host,
            remote_port=remote_port,
        )
        local_port = tunnel.start()
        self._tunnels[source.name] = tunnel
        return self._rewrite_port(source.connection_string, local_port)

    @staticmethod
    def _parse_host_port(connection_string: str) -> tuple[str, int]:
        """Extract host and port from a psycopg connection string."""
        host = "localhost"
        port = 5432

        # Key=value format
        host_match = re.search(r"\bhost(?:name)?=([^\s&]+)", connection_string)
        port_match = re.search(r"\bport=(\d+)", connection_string)
        if host_match:
            host = host_match.group(1)
        if port_match:
            port = int(port_match.group(1))

        # URL format override: postgresql://user@host:port/db
        url_match = re.search(r"@([^:/]+)(?::(\d+))?/(?:[^\s&?]+)?", connection_string)
        if url_match:
            host = url_match.group(1)
            if url_match.group(2):
                port = int(url_match.group(2))

        return host, port

    @staticmethod
    def _rewrite_port(connection_string: str, local_port: int) -> str:
        """Rewrite connection string to point to localhost:local_port."""
        # URL format: replace host and port in the netloc
        url_pattern = r"(postgresql://[^@]+@)([^:/]+)(?::(\d+))?(/.*)?"
        if re.match(url_pattern, connection_string):
            return re.sub(url_pattern, rf"\g<1>127.0.0.1:{local_port}\g<4>", connection_string)

        # Key=value format
        conn = re.sub(r"\bhost(?:name)?=([^\s&;]+)", "host=127.0.0.1", connection_string)
        if "port=" in conn:
            conn = re.sub(r"\bport=\d+", f"port={local_port}", conn)
        else:
            conn += f" port={local_port}"
        return conn

    def _connect(self, source: PostgreSQLSource) -> psycopg.Connection:
        conn_str = self._get_connection_string(source)
        return psycopg.connect(
            conn_str,
            row_factory=dict_row,
            options=f"-c statement_timeout={source.query_timeout * 1000}",
        )

    def _list_tables(
        self, name: str, schema: str
    ) -> list[dict[str, Any]]:
        cache_key = ("tables", name, schema)
        try:
            return self._cache.get(self.name, *cache_key)
        except KeyError:
            pass

        source = self._resolve_source(name)
        with self._connect(source) as conn, conn.cursor() as cur:
            cur.execute(
                """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = %s
                    ORDER BY table_name
                    """,
                (schema,),
            )
            result = [{"name": r["table_name"]} for r in cur.fetchall()]

        self._cache.set(self.name, *cache_key, value=result, ttl=300)
        return result

    def _get_schema(
        self, name: str, schema: str, table: str
    ) -> list[dict[str, Any]]:
        cache_key = ("schema", name, schema, table)
        try:
            return self._cache.get(self.name, *cache_key)
        except KeyError:
            pass

        source = self._resolve_source(name)
        with self._connect(source) as conn, conn.cursor() as cur:
            cur.execute(
                """
                    SELECT column_name, data_type, is_nullable,
                           column_default
                    FROM information_schema.columns
                    WHERE table_schema = %s AND table_name = %s
                    ORDER BY ordinal_position
                    """,
                (schema, table),
            )
            result = [
                {
                    "column": r["column_name"],
                    "type": r["data_type"],
                    "nullable": r["is_nullable"] == "YES",
                    "default": r["column_default"],
                }
                for r in cur.fetchall()
            ]

        self._cache.set(self.name, *cache_key, value=result, ttl=300)
        return result

    def _get_indexes(
        self, name: str, schema: str, table: str
    ) -> list[dict[str, Any]]:
        cache_key = ("indexes", name, schema, table)
        try:
            return self._cache.get(self.name, *cache_key)
        except KeyError:
            pass

        source = self._resolve_source(name)
        with self._connect(source) as conn, conn.cursor() as cur:
            cur.execute(
                """
                    SELECT indexname, indexdef
                    FROM pg_indexes
                    WHERE schemaname = %s AND tablename = %s
                    """,
                (schema, table),
            )
            result = [
                {
                    "name": r["indexname"],
                    "definition": r["indexdef"],
                }
                for r in cur.fetchall()
            ]

        self._cache.set(self.name, *cache_key, value=result, ttl=300)
        return result

    def _get_foreign_keys(
        self, name: str, schema: str, table: str
    ) -> list[dict[str, Any]]:
        cache_key = ("fks", name, schema, table)
        try:
            return self._cache.get(self.name, *cache_key)
        except KeyError:
            pass

        source = self._resolve_source(name)
        with self._connect(source) as conn, conn.cursor() as cur:
            cur.execute(
                """
                    SELECT
                        kcu.column_name,
                        ccu.table_name AS foreign_table,
                        ccu.column_name AS foreign_column
                    FROM information_schema.table_constraints tc
                    JOIN information_schema.key_column_usage kcu
                        ON tc.constraint_name = kcu.constraint_name
                        AND tc.table_schema = kcu.table_schema
                    JOIN information_schema.constraint_column_usage ccu
                        ON ccu.constraint_name = tc.constraint_name
                        AND ccu.table_schema = tc.table_schema
                    WHERE tc.constraint_type = 'FOREIGN KEY'
                        AND tc.table_schema = %s
                        AND tc.table_name = %s
                    """,
                (schema, table),
            )
            result = [
                {
                    "column": r["column_name"],
                    "references_table": r["foreign_table"],
                    "references_column": r["foreign_column"],
                }
                for r in cur.fetchall()
            ]

        self._cache.set(self.name, *cache_key, value=result, ttl=300)
        return result

    def _run_query(
        self, name: str, sql: str, limit: int
    ) -> list[dict[str, Any]]:
        stripped = sql.strip().lower()
        if not stripped.startswith("select"):
            raise ValueError("Only SELECT queries are allowed")

        cache_key = ("query", name, sql, limit)
        try:
            return self._cache.get(self.name, *cache_key)
        except KeyError:
            pass

        source = self._resolve_source(name)
        if "limit" not in stripped:
            sql = f"{sql.strip()} LIMIT {limit}"

        with self._connect(source) as conn, conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()
            result = [dict(r) for r in rows]

        self._cache.set(self.name, *cache_key, value=result, ttl=30)
        return result
