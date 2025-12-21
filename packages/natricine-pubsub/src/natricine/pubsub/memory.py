"""In-memory pub/sub implementation for testing."""

from collections.abc import AsyncIterator
from dataclasses import dataclass, field

import anyio
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream

from natricine.pubsub.message import Message


@dataclass
class _TopicState:
    """Internal state for a topic."""

    subscribers: list[MemoryObjectSendStream[Message]] = field(default_factory=list)


class InMemoryPubSub:
    """In-memory pub/sub for testing. Acts as both Publisher and Subscriber."""

    def __init__(self, buffer_size: int = 100) -> None:
        self._buffer_size = buffer_size
        self._topics: dict[str, _TopicState] = {}
        self._closed = False

    async def publish(self, topic: str, *messages: Message) -> None:
        if self._closed:
            msg = "MemoryPubSub is closed"
            raise RuntimeError(msg)

        state = self._topics.get(topic)
        if state is None:
            return  # No subscribers, messages are dropped

        for message in messages:
            for send_stream in state.subscribers:
                # Each subscriber gets its own copy for independent ack/nack
                await send_stream.send(message.copy())

    def subscribe(self, topic: str) -> AsyncIterator[Message]:
        if self._closed:
            msg = "MemoryPubSub is closed"
            raise RuntimeError(msg)

        if topic not in self._topics:
            self._topics[topic] = _TopicState()

        send_stream, receive_stream = anyio.create_memory_object_stream[Message](
            self._buffer_size
        )
        self._topics[topic].subscribers.append(send_stream)

        return self._subscribe_iter(receive_stream, topic, send_stream)

    async def _subscribe_iter(
        self,
        receive_stream: MemoryObjectReceiveStream[Message],
        topic: str,
        send_stream: MemoryObjectSendStream[Message],
    ) -> AsyncIterator[Message]:
        try:
            async for message in receive_stream:
                yield message
        finally:
            # Clean up when iteration stops
            state = self._topics.get(topic)
            if state and send_stream in state.subscribers:
                state.subscribers.remove(send_stream)
            await send_stream.aclose()
            await receive_stream.aclose()

    async def close(self) -> None:
        self._closed = True
        for state in self._topics.values():
            for send_stream in state.subscribers:
                await send_stream.aclose()
        self._topics.clear()

    async def __aenter__(self) -> "InMemoryPubSub":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        await self.close()
