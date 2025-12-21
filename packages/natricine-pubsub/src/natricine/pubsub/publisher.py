"""Publisher protocol."""

from typing import Protocol, runtime_checkable

from natricine.pubsub.message import Message


@runtime_checkable
class Publisher(Protocol):
    """Protocol for publishing messages to topics."""

    async def publish(self, topic: str, *messages: Message) -> None: ...

    async def close(self) -> None: ...

    async def __aenter__(self) -> "Publisher": ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None: ...
