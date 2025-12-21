"""Tests for Message class."""

import pytest

from natricine_pubsub import Message

pytestmark = pytest.mark.anyio


class TestMessage:
    def test_payload_required(self) -> None:
        msg = Message(payload=b"hello")
        assert msg.payload == b"hello"

    def test_metadata_defaults_empty(self) -> None:
        msg = Message(payload=b"test")
        assert msg.metadata == {}

    def test_uuid_generated(self) -> None:
        msg1 = Message(payload=b"a")
        msg2 = Message(payload=b"b")
        assert msg1.uuid != msg2.uuid

    def test_initial_state_not_acked_or_nacked(self) -> None:
        msg = Message(payload=b"test")
        assert not msg.acked
        assert not msg.nacked


class TestMessageAck:
    async def test_ack_sets_state(self) -> None:
        msg = Message(payload=b"test")
        await msg.ack()
        assert msg.acked
        assert not msg.nacked

    async def test_ack_calls_callback(self) -> None:
        called = False

        async def on_ack() -> None:
            nonlocal called
            called = True

        msg = Message(payload=b"test", _ack_func=on_ack)
        await msg.ack()
        assert called

    async def test_double_ack_raises(self) -> None:
        msg = Message(payload=b"test")
        await msg.ack()
        with pytest.raises(ValueError, match="already acked"):
            await msg.ack()

    async def test_ack_after_nack_raises(self) -> None:
        msg = Message(payload=b"test")
        await msg.nack()
        with pytest.raises(ValueError, match="has been nacked"):
            await msg.ack()


class TestMessageNack:
    async def test_nack_sets_state(self) -> None:
        msg = Message(payload=b"test")
        await msg.nack()
        assert msg.nacked
        assert not msg.acked

    async def test_nack_calls_callback(self) -> None:
        called = False

        async def on_nack() -> None:
            nonlocal called
            called = True

        msg = Message(payload=b"test", _nack_func=on_nack)
        await msg.nack()
        assert called

    async def test_double_nack_raises(self) -> None:
        msg = Message(payload=b"test")
        await msg.nack()
        with pytest.raises(ValueError, match="already nacked"):
            await msg.nack()

    async def test_nack_after_ack_raises(self) -> None:
        msg = Message(payload=b"test")
        await msg.ack()
        with pytest.raises(ValueError, match="has been acked"):
            await msg.nack()
