"""Message marshaling between natricine Message and SQS/SNS formats.

Compatible with watermill-aws marshaling format.
"""

import base64
import json
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from natricine.pubsub import Message

if TYPE_CHECKING:
    from types_aiobotocore_sqs.type_defs import (
        MessageAttributeValueTypeDef,
        MessageTypeDef,
    )

# Attribute keys - matches watermill-aws
UUID_ATTR = "UUID"

# FIFO queue special metadata keys
MESSAGE_DEDUPLICATION_ID = "MessageDeduplicationId"
MESSAGE_GROUP_ID = "MessageGroupId"


def encode_message_body(payload: bytes) -> str:
    """Encode payload for SQS/SNS message body.

    Attempts UTF-8 decode first, falls back to base64 encoding.
    """
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError:
        return base64.b64encode(payload).decode("ascii")


def decode_message_body(body: str, is_base64: bool = False) -> bytes:
    """Decode SQS/SNS message body to payload bytes."""
    if is_base64:
        return base64.b64decode(body)
    # Try to detect base64 by checking if it decodes cleanly
    # and re-encodes to the same value
    try:
        decoded = base64.b64decode(body, validate=True)
        if base64.b64encode(decoded).decode("ascii") == body:
            return decoded
    except Exception:
        pass
    return body.encode("utf-8")


def to_message_attributes(
    message: Message,
) -> tuple[dict[str, "MessageAttributeValueTypeDef"], str | None, str | None]:
    """Convert natricine Message to SQS message attributes.

    Returns (attributes, deduplication_id, group_id).
    Deduplication/group IDs are extracted for FIFO queue support.
    """
    attrs: dict[str, MessageAttributeValueTypeDef] = {
        UUID_ATTR: {
            "DataType": "String",
            "StringValue": str(message.uuid),
        },
    }

    deduplication_id: str | None = None
    group_id: str | None = None

    # Each metadata key becomes a separate attribute (watermill-compatible)
    for key, value in message.metadata.items():
        if key == MESSAGE_DEDUPLICATION_ID:
            deduplication_id = value
            continue
        if key == MESSAGE_GROUP_ID:
            group_id = value
            continue
        attr: MessageAttributeValueTypeDef = {
            "DataType": "String",
            "StringValue": value,
        }
        attrs[key] = attr

    return attrs, deduplication_id, group_id


def from_sqs_message(
    sqs_msg: "MessageTypeDef",
    ack_func: Any = None,
    nack_func: Any = None,
) -> Message:
    """Convert SQS message to natricine Message."""
    body = sqs_msg.get("Body", "")
    attrs = sqs_msg.get("MessageAttributes", {})

    # Extract UUID
    uuid_attr = attrs.get(UUID_ATTR, {})
    uuid_str = uuid_attr.get("StringValue")
    msg_uuid = UUID(uuid_str) if uuid_str else uuid4()

    # Extract metadata from all other attributes (watermill-compatible)
    metadata: dict[str, str] = {}
    for key, value in attrs.items():
        if key == UUID_ATTR:
            continue
        str_value = value.get("StringValue")
        if str_value is not None:
            metadata[key] = str_value

    # Decode body
    payload = decode_message_body(body)

    return Message(
        payload=payload,
        metadata=metadata,
        uuid=msg_uuid,
        _ack_func=ack_func,
        _nack_func=nack_func,
    )


def unwrap_sns_envelope(body: str) -> tuple[str, dict[str, Any]]:
    """Unwrap SNS envelope from SQS message body.

    When SNS delivers to SQS, it wraps the message in a JSON envelope.
    Returns (original_message, sns_message_attributes).
    """
    try:
        envelope = json.loads(body)
        if envelope.get("Type") == "Notification":
            return envelope.get("Message", ""), envelope.get("MessageAttributes", {})
    except (json.JSONDecodeError, TypeError):
        pass
    return body, {}


def from_sns_sqs_message(
    sqs_msg: "MessageTypeDef",
    ack_func: Any = None,
    nack_func: Any = None,
) -> Message:
    """Convert SNS-wrapped SQS message to natricine Message.

    SNS wraps messages in a JSON envelope when delivering to SQS.
    This function unwraps that envelope.
    """
    body = sqs_msg.get("Body", "")

    # Unwrap SNS envelope
    inner_body, sns_attrs = unwrap_sns_envelope(body)

    # Extract UUID from SNS attributes
    uuid_attr = sns_attrs.get(UUID_ATTR, {})
    uuid_str = uuid_attr.get("Value")
    msg_uuid = UUID(uuid_str) if uuid_str else uuid4()

    # Extract metadata from all other SNS attributes (watermill-compatible)
    metadata: dict[str, str] = {}
    for key, value in sns_attrs.items():
        if key == UUID_ATTR:
            continue
        str_value = value.get("Value")
        if str_value is not None:
            metadata[key] = str_value

    # Decode body
    payload = decode_message_body(inner_body)

    return Message(
        payload=payload,
        metadata=metadata,
        uuid=msg_uuid,
        _ack_func=ack_func,
        _nack_func=nack_func,
    )
