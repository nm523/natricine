"""SQL Subscriber implementation with polling."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Sequence
from typing import Any
from uuid import UUID

import anyio

from natricine.pubsub import Message
from natricine.sql.config import SQLConfig
from natricine.sql.dialect import Dialect, DialectQueries


class SQLSubscriber:
    """Subscriber that polls messages from SQL tables."""

    def __init__(
        self,
        connection: Any,
        dialect: Dialect,
        config: SQLConfig | None = None,
    ) -> None:
        """Initialize the SQL subscriber.

        Args:
            connection: Async database connection or pool.
                For SQLite: aiosqlite.Connection
                For Postgres: asyncpg.Pool or asyncpg.Connection
            dialect: SQL dialect for query generation.
            config: Subscriber configuration.
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
            # Index may already exist
            pass
        await self._commit_if_needed()
        self._tables_created.add(table_name)

    async def _execute(self, query: str, params: Sequence[Any] = ()) -> Any:
        """Execute a query, handling dialect differences."""
        conn = self._connection
        if hasattr(conn, "cursor"):
            # aiosqlite style
            return await conn.execute(query, params)
        # asyncpg style
        return await conn.execute(query, *params)

    async def _fetch_all(self, query: str, params: Sequence[Any] = ()) -> list[Any]:
        """Fetch all rows from a query."""
        conn = self._connection
        if hasattr(conn, "cursor"):
            # aiosqlite style
            cursor = await conn.execute(query, params)
            return await cursor.fetchall()
        # asyncpg style
        return await conn.fetch(query, *params)

    async def _commit_if_needed(self) -> None:
        """Commit if using a connection that requires explicit commits."""
        if hasattr(self._connection, "commit"):
            await self._connection.commit()

    def subscribe(self, topic: str) -> AsyncIterator[Message]:
        """Subscribe to a SQL table.

        Returns an async iterator that yields messages as they become available.
        Messages must be acknowledged with ack() or rejected with nack().
        """
        if self._closed:
            msg = "Subscriber is closed"
            raise RuntimeError(msg)
        return self._subscribe_iter(topic)

    async def _subscribe_iter(self, topic: str) -> AsyncIterator[Message]:
        """Poll messages from the table."""
        await self._ensure_table(topic)
        queries = self._get_queries(topic)

        while not self._closed:
            # Fetch pending messages
            rows = await self._fetch_all(
                queries.select_pending,
                (self._config.consumer_group, self._config.batch_size),
            )

            if not rows:
                # No messages, wait before polling again
                await anyio.sleep(self._config.poll_interval)
                continue

            for row in rows:
                # Parse row (id, uuid, payload, metadata, delivery_count)
                msg_id = row[0]
                uuid_str = row[1]
                payload = row[2]
                metadata_json = row[3]
                # row[4] is delivery_count, available if needed for DLQ middleware

                # Claim the message (set visibility timeout)
                # For SQLite: params are (ack_deadline, msg_id)
                # For Postgres: params are (ack_deadline, msg_id) - same order
                await self._execute(
                    queries.claim_message,
                    (self._config.ack_deadline, msg_id),
                )
                await self._commit_if_needed()

                # Create ack/nack closures bound to this message
                async def make_ack(mid: Any = msg_id) -> None:
                    await self._execute(queries.ack_message, (mid,))
                    await self._commit_if_needed()

                async def make_nack(mid: Any = msg_id) -> None:
                    await self._execute(queries.nack_message, (mid,))
                    await self._commit_if_needed()

                # Parse metadata
                metadata = json.loads(metadata_json) if metadata_json else {}

                # Ensure payload is bytes
                if isinstance(payload, str):
                    payload = payload.encode()

                # Create and yield message
                message = Message(
                    payload=payload,
                    metadata=metadata,
                    uuid=UUID(uuid_str) if uuid_str else None,
                    _ack_func=make_ack,
                    _nack_func=make_nack,
                )
                yield message

    async def close(self) -> None:
        """Close the subscriber."""
        self._closed = True

    async def __aenter__(self) -> SQLSubscriber:
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
