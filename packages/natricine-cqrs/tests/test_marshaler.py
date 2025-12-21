"""Tests for Marshaler implementations."""

import pytest
from pydantic import BaseModel

from natricine_cqrs import PydanticMarshaler

TEST_USER_ID = 456


class SampleCommand(BaseModel):
    user_id: int
    name: str


class TestPydanticMarshaler:
    def test_marshal_basemodel(self) -> None:
        marshaler = PydanticMarshaler()
        cmd = SampleCommand(user_id=123, name="Alice")

        data = marshaler.marshal(cmd)

        assert isinstance(data, bytes)
        assert b'"user_id":123' in data
        assert b'"name":"Alice"' in data

    def test_marshal_non_basemodel_raises(self) -> None:
        marshaler = PydanticMarshaler()

        with pytest.raises(TypeError, match="Expected BaseModel"):
            marshaler.marshal({"user_id": 123})

    def test_unmarshal_to_basemodel(self) -> None:
        marshaler = PydanticMarshaler()
        data = f'{{"user_id": {TEST_USER_ID}, "name": "Bob"}}'.encode()

        result = marshaler.unmarshal(data, SampleCommand)

        assert isinstance(result, SampleCommand)
        assert result.user_id == TEST_USER_ID
        assert result.name == "Bob"

    def test_unmarshal_non_basemodel_raises(self) -> None:
        marshaler = PydanticMarshaler()

        with pytest.raises(TypeError, match="Expected BaseModel subclass"):
            marshaler.unmarshal(b"{}", dict)

    def test_name_from_instance(self) -> None:
        marshaler = PydanticMarshaler()
        cmd = SampleCommand(user_id=1, name="Test")

        assert marshaler.name(cmd) == "SampleCommand"

    def test_name_from_type(self) -> None:
        marshaler = PydanticMarshaler()

        assert marshaler.name(SampleCommand) == "SampleCommand"

    def test_roundtrip(self) -> None:
        marshaler = PydanticMarshaler()
        original = SampleCommand(user_id=789, name="Charlie")

        data = marshaler.marshal(original)
        restored = marshaler.unmarshal(data, SampleCommand)

        assert restored == original
