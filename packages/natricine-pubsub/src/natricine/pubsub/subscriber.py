"""Subscriber protocol."""

from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

from natricine.pubsub.message import Message


@runtime_checkable
class Subscriber(Protocol):
    """Protocol for subscribing to topics."""

    def subscribe(self, topic: str) -> AsyncIterator[Message]: ...

    async def close(self) -> None: ...

    async def __aenter__(self) -> "Subscriber": ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None: ...
