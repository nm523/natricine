"""SQL Publisher implementation."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from natricine.pubsub import Message
from natricine.sql.config import SQLConfig
from natricine.sql.dialect import Dialect, DialectQueries

if TYPE_CHECKING:
    from collections.abc import Sequence


@runtime_checkable
class SQLConnection(Protocol):
    """Protocol for async SQL connections.

    Supports both aiosqlite and asyncpg patterns.
    """

    async def execute(self, query: str, *args: Any, **kwargs: Any) -> Any:
        """Execute a query."""
        ...


class SQLPublisher:
    """Publisher that writes messages to SQL tables."""

    def __init__(
        self,
        connection: Any,
        dialect: Dialect,
        config: SQLConfig | None = None,
    ) -> None:
        """Initialize the SQL publisher.

        Args:
            connection: Async database connection or pool.
                For SQLite: aiosqlite.Connection
                For Postgres: asyncpg.Pool or asyncpg.Connection
            dialect: SQL dialect for query generation.
            config: Publisher configuration.
        """
        self._connection = connection
        self._dialect = dialect
        self._config = config or SQLConfig()
        self._closed = False
        self._queries_cache: dict[str, DialectQueries] = {}
        self._tables_created: set[str] = set()

    def _get_queries(self, topic: str) -> DialectQueries:
        """Get or create queries for a topic."""
        table_name = f"{self._config.table_prefix}{topic}"
        if table_name not in self._queries_cache:
            self._queries_cache[table_name] = self._dialect.queries_for_topic(
                table_name
            )
        return self._queries_cache[table_name]

    def _table_name(self, topic: str) -> str:
        """Get the table name for a topic."""
        return f"{self._config.table_prefix}{topic}"

    async def _ensure_table(self, topic: str) -> None:
        """Create table if auto_create_tables is enabled."""
        table_name = self._table_name(topic)
        if not self._config.auto_create_tables or table_name in self._tables_created:
            return

        queries = self._get_queries(topic)
        await self._execute(queries.create_table)
        try:
            await self._execute(queries.create_index)
        except Exception:
            # Index may already exist, that's fine
            pass
        await self._commit_if_needed()
        self._tables_created.add(table_name)

    async def _execute(
        self, query: str, params: Sequence[Any] = ()
    ) -> Any:
        """Execute a query, handling dialect differences."""
        conn = self._connection
        # Detect aiosqlite vs asyncpg by checking method signatures
        if hasattr(conn, "cursor"):
            # aiosqlite style: execute(sql, params)
            return await conn.execute(query, params)
        # asyncpg style: execute(sql, *args)
        return await conn.execute(query, *params)

    async def _commit_if_needed(self) -> None:
        """Commit if using a connection that requires explicit commits."""
        if hasattr(self._connection, "commit"):
            await self._connection.commit()

    async def publish(self, topic: str, *messages: Message) -> None:
        """Publish messages to a SQL table."""
        if self._closed:
            msg = "Publisher is closed"
            raise RuntimeError(msg)

        await self._ensure_table(topic)
        queries = self._get_queries(topic)

        for message in messages:
            metadata_json = json.dumps(message.metadata)
            params = (
                str(message.uuid),
                message.payload,
                metadata_json,
                self._config.consumer_group,
            )
            await self._execute(queries.insert, params)

        await self._commit_if_needed()

    async def close(self) -> None:
        """Close the publisher."""
        self._closed = True

    async def __aenter__(self) -> SQLPublisher:
        """Enter async context."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        """Exit async context."""
        await self.close()
