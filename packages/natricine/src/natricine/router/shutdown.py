"""Graceful shutdown utilities for signal handling."""

from __future__ import annotations

import signal
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Protocol

import anyio


class Closeable(Protocol):
    """Protocol for objects that can be closed."""

    async def close(self) -> None:
        """Close the object gracefully."""
        ...


@asynccontextmanager
async def graceful_shutdown(
    *closeables: Closeable,
    signals: tuple[signal.Signals, ...] = (signal.SIGTERM, signal.SIGINT),
) -> AsyncIterator[None]:
    """Context manager that handles shutdown signals gracefully.

    Sets up signal handlers for the specified signals (default: SIGTERM, SIGINT).
    When a signal is received, calls close() on all provided closeables.

    Usage:
        async with graceful_shutdown(router, command_bus, event_bus):
            async with anyio.create_task_group() as tg:
                tg.start_soon(router.run)
                tg.start_soon(command_bus.run)
                tg.start_soon(event_bus.run)

    Args:
        *closeables: Objects with a close() method to call on shutdown.
        signals: Signals to handle (default: SIGTERM, SIGINT).
    """
    shutdown_event = anyio.Event()
    original_handlers: dict[signal.Signals, object] = {}

    def handle_signal(signum: int, frame: object) -> None:
        shutdown_event.set()

    # Install signal handlers
    for sig in signals:
        try:
            original_handlers[sig] = signal.signal(sig, handle_signal)
        except (ValueError, OSError):
            # Signal handling not supported (e.g., not main thread, Windows)
            pass

    async def shutdown_watcher() -> None:
        await shutdown_event.wait()
        for closeable in closeables:
            await closeable.close()

    try:
        async with anyio.create_task_group() as tg:
            tg.start_soon(shutdown_watcher)
            yield
            # Normal exit - cancel the watcher
            tg.cancel_scope.cancel()
    finally:
        # Restore original signal handlers
        for sig, handler in original_handlers.items():
            try:
                signal.signal(sig, handler)  # type: ignore[arg-type]
            except (ValueError, OSError):
                pass
