"""Message - the fundamental unit of data in natricine."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from uuid import UUID, uuid4

AckFunc = Callable[[], Awaitable[None]]


@dataclass
class Message:
    """The fundamental unit of data flowing through the system."""

    payload: bytes
    metadata: dict[str, str] = field(default_factory=dict)
    uuid: UUID = field(default_factory=uuid4)

    _ack_func: AckFunc | None = field(default=None, repr=False, compare=False)
    _nack_func: AckFunc | None = field(default=None, repr=False, compare=False)
    _acked: bool = field(default=False, repr=False, compare=False)
    _nacked: bool = field(default=False, repr=False, compare=False)

    async def ack(self) -> None:
        """Acknowledge the message was processed successfully."""
        if self._acked:
            msg = "Message already acked"
            raise ValueError(msg)
        if self._nacked:
            msg = "Cannot ack a message that has been nacked"
            raise ValueError(msg)
        self._acked = True
        if self._ack_func:
            await self._ack_func()

    async def nack(self) -> None:
        """Negative acknowledge - message processing failed."""
        if self._nacked:
            msg = "Message already nacked"
            raise ValueError(msg)
        if self._acked:
            msg = "Cannot nack a message that has been acked"
            raise ValueError(msg)
        self._nacked = True
        if self._nack_func:
            await self._nack_func()

    @property
    def acked(self) -> bool:
        return self._acked

    @property
    def nacked(self) -> bool:
        return self._nacked

    def copy(self) -> "Message":
        """Create a copy with same uuid/payload/metadata but fresh ack state."""
        return Message(
            payload=self.payload,
            metadata=self.metadata.copy(),
            uuid=self.uuid,
        )
