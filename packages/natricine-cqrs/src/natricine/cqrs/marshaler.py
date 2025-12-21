"""Marshaler protocol and implementations."""

from typing import Any, Protocol, TypeVar

T = TypeVar("T")


class Marshaler(Protocol):
    """Protocol for serializing/deserializing commands and events."""

    def marshal(self, obj: Any) -> bytes:
        """Serialize a command or event to bytes."""
        ...

    def unmarshal(self, data: bytes, target_type: type[T]) -> T:
        """Deserialize bytes to the target type."""
        ...

    def name(self, obj_or_type: type | Any) -> str:
        """Get type name for topic routing."""
        ...


class PydanticMarshaler:
    """Marshaler for Pydantic BaseModel using JSON serialization."""

    def __init__(self) -> None:
        try:
            from pydantic import BaseModel  # noqa: PLC0415

            self._base_model = BaseModel
        except ImportError as e:
            msg = (
                "PydanticMarshaler requires pydantic. "
                "Install with: pip install natricine-cqrs[pydantic]"
            )
            raise ImportError(msg) from e

    def marshal(self, obj: Any) -> bytes:
        """Serialize a Pydantic model to JSON bytes."""
        if not isinstance(obj, self._base_model):
            msg = f"Expected BaseModel instance, got {type(obj).__name__}"
            raise TypeError(msg)
        return obj.model_dump_json().encode()

    def unmarshal(self, data: bytes, target_type: type[T]) -> T:
        """Deserialize JSON bytes to a Pydantic model."""
        if not issubclass(target_type, self._base_model):
            msg = f"Expected BaseModel subclass, got {target_type.__name__}"
            raise TypeError(msg)
        return target_type.model_validate_json(data)  # type: ignore[return-value]

    def name(self, obj_or_type: type | Any) -> str:
        """Get the class name for topic routing."""
        if isinstance(obj_or_type, type):
            return obj_or_type.__name__
        return type(obj_or_type).__name__
