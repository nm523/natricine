"""SQL dialect abstraction for different databases."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class DialectQueries:
    """Pre-generated SQL queries for a specific topic table."""

    create_table: str
    create_index: str
    insert: str
    select_pending: str
    claim_message: str
    ack_message: str
    nack_message: str


class Dialect(Protocol):
    """Protocol for SQL dialect differences."""

    def queries_for_topic(self, table_name: str) -> DialectQueries:
        """Generate all queries for a given topic/table."""
        ...


class SQLiteDialect:
    """SQLite dialect using aiosqlite.

    Note: SQLite does not support FOR UPDATE SKIP LOCKED.
    Uses single-connection serialization for testing.
    Not recommended for production competing consumers.
    """

    def _quote(self, name: str) -> str:
        """Quote identifier for SQLite."""
        # Double any existing double quotes and wrap in double quotes
        return '"' + name.replace('"', '""') + '"'

    def queries_for_topic(self, table_name: str) -> DialectQueries:
        """Generate SQLite queries for a topic table."""
        t = self._quote(table_name)
        idx = self._quote(f"idx_{table_name}_pending")
        return DialectQueries(
            create_table=f"""
                CREATE TABLE IF NOT EXISTS {t} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    uuid TEXT NOT NULL,
                    payload BLOB NOT NULL,
                    metadata TEXT NOT NULL DEFAULT '{{}}',
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    consumer_group TEXT NOT NULL,
                    claimed_at TEXT,
                    acked_at TEXT,
                    delivery_count INTEGER NOT NULL DEFAULT 0,
                    next_delivery_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
            """,
            create_index=f"""
                CREATE INDEX IF NOT EXISTS {idx}
                ON {t} (consumer_group, next_delivery_at)
                WHERE acked_at IS NULL
            """,
            insert=f"""
                INSERT INTO {t}
                    (uuid, payload, metadata, consumer_group, next_delivery_at)
                VALUES (?, ?, ?, ?, datetime('now'))
            """,
            # SQLite: no SKIP LOCKED, use claimed_at IS NULL as workaround
            select_pending=f"""
                SELECT id, uuid, payload, metadata, delivery_count
                FROM {t}
                WHERE consumer_group = ?
                  AND datetime(next_delivery_at) <= datetime('now')
                  AND acked_at IS NULL
                  AND claimed_at IS NULL
                ORDER BY next_delivery_at, id
                LIMIT ?
            """,
            claim_message=f"""
                UPDATE {t}
                SET claimed_at = datetime('now'),
                    next_delivery_at = datetime('now', '+' || ? || ' seconds'),
                    delivery_count = delivery_count + 1
                WHERE id = ?
            """,
            ack_message=f"""
                UPDATE {t}
                SET acked_at = datetime('now')
                WHERE id = ?
            """,
            nack_message=f"""
                UPDATE {t}
                SET next_delivery_at = datetime('now'),
                    claimed_at = NULL
                WHERE id = ?
            """,
        )


class PostgresDialect:
    """PostgreSQL dialect using asyncpg.

    Uses FOR UPDATE SKIP LOCKED for competing consumers.
    """

    def _quote(self, name: str) -> str:
        """Quote identifier for PostgreSQL."""
        # Double any existing double quotes and wrap in double quotes
        return '"' + name.replace('"', '""') + '"'

    def queries_for_topic(self, table_name: str) -> DialectQueries:
        """Generate PostgreSQL queries for a topic table."""
        t = self._quote(table_name)
        idx = self._quote(f"idx_{table_name}_pending")
        return DialectQueries(
            create_table=f"""
                CREATE TABLE IF NOT EXISTS {t} (
                    id BIGSERIAL PRIMARY KEY,
                    uuid UUID NOT NULL,
                    payload BYTEA NOT NULL,
                    metadata JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    consumer_group VARCHAR(255) NOT NULL,
                    claimed_at TIMESTAMPTZ,
                    acked_at TIMESTAMPTZ,
                    delivery_count INTEGER NOT NULL DEFAULT 0,
                    next_delivery_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """,
            create_index=f"""
                CREATE INDEX IF NOT EXISTS {idx}
                ON {t} (consumer_group, next_delivery_at)
                WHERE acked_at IS NULL
            """,
            insert=f"""
                INSERT INTO {t}
                    (uuid, payload, metadata, consumer_group, next_delivery_at)
                VALUES ($1, $2, $3, $4, NOW())
            """,
            select_pending=f"""
                SELECT id, uuid, payload, metadata, delivery_count
                FROM {t}
                WHERE consumer_group = $1
                  AND next_delivery_at <= NOW()
                  AND acked_at IS NULL
                ORDER BY next_delivery_at, id
                LIMIT $2
                FOR UPDATE SKIP LOCKED
            """,
            claim_message=f"""
                UPDATE {t}
                SET claimed_at = NOW(),
                    next_delivery_at = NOW() + INTERVAL '1 second' * $1,
                    delivery_count = delivery_count + 1
                WHERE id = $2
            """,
            ack_message=f"""
                UPDATE {t}
                SET acked_at = NOW()
                WHERE id = $1
            """,
            nack_message=f"""
                UPDATE {t}
                SET next_delivery_at = NOW(),
                    claimed_at = NULL
                WHERE id = $1
            """,
        )
