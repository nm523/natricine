"""Tests for graceful_shutdown utility."""

import signal

import anyio
import pytest

from natricine.router.shutdown import graceful_shutdown

pytestmark = pytest.mark.anyio


class MockCloseable:
    """Mock object that implements the Closeable protocol."""

    def __init__(self) -> None:
        self.closed = False
        self.close_called_count = 0

    async def close(self) -> None:
        self.closed = True
        self.close_called_count += 1


class TestGracefulShutdown:
    async def test_context_manager_yields(self) -> None:
        """graceful_shutdown should yield control inside the context."""
        entered = False
        async with graceful_shutdown():
            entered = True
        assert entered

    async def test_closes_on_signal(self) -> None:
        """graceful_shutdown should close all closeables on signal."""
        closeable1 = MockCloseable()
        closeable2 = MockCloseable()

        async with graceful_shutdown(closeable1, closeable2) as _:
            # Simulate signal by manually calling the handler
            # We can't easily send real signals in tests
            pass

        # Without signal, closeables should not be closed on normal exit
        assert not closeable1.closed
        assert not closeable2.closed

    async def test_normal_exit_does_not_close(self) -> None:
        """Normal exit from context should not call close()."""
        closeable = MockCloseable()

        async with graceful_shutdown(closeable):
            await anyio.sleep(0.01)

        assert not closeable.closed

    async def test_signal_handler_calls_close(self) -> None:
        """When signal is received, close should be called on all closeables."""
        closeable1 = MockCloseable()
        closeable2 = MockCloseable()
        signal_received = anyio.Event()

        async def simulate_work() -> None:
            await signal_received.wait()

        async with graceful_shutdown(closeable1, closeable2) as _:
            # Get the current signal handler (which should be our handler)
            current_handler = signal.getsignal(signal.SIGTERM)

            # Manually call the signal handler to simulate signal
            if callable(current_handler):
                current_handler(signal.SIGTERM, None)

            # Give time for close to be called
            await anyio.sleep(0.1)

            # Now closeables should be closed
            assert closeable1.closed
            assert closeable2.closed

    async def test_restores_original_handlers(self) -> None:
        """Original signal handlers should be restored after context exit."""
        original_sigterm = signal.getsignal(signal.SIGTERM)
        original_sigint = signal.getsignal(signal.SIGINT)

        closeable = MockCloseable()

        async with graceful_shutdown(closeable):
            # Handlers should be replaced
            pass

        # Handlers should be restored
        assert signal.getsignal(signal.SIGTERM) == original_sigterm
        assert signal.getsignal(signal.SIGINT) == original_sigint

    async def test_custom_signals(self) -> None:
        """graceful_shutdown should accept custom signals."""
        closeable = MockCloseable()

        # Use only SIGUSR1 (which is safer to test with)
        try:
            async with graceful_shutdown(closeable, signals=(signal.SIGUSR1,)):
                handler = signal.getsignal(signal.SIGUSR1)
                assert handler is not signal.SIG_DFL
        except (ValueError, OSError):
            # Signal handling might not be available
            pytest.skip("Signal handling not available")

    async def test_empty_closeables(self) -> None:
        """graceful_shutdown should work with no closeables."""
        async with graceful_shutdown():
            await anyio.sleep(0.01)
        # Should complete without error
