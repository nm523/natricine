"""HTTP message marshaling utilities."""

from collections.abc import Mapping
from uuid import UUID, uuid4

# Header prefixes
UUID_HEADER = "X-Natricine-UUID"
META_PREFIX = "X-Natricine-Meta-"


def extract_metadata(headers: Mapping[str, str]) -> dict[str, str]:
    """Extract natricine metadata from HTTP headers.

    Headers with prefix X-Natricine-Meta- are converted to metadata entries.
    """
    result: dict[str, str] = {}
    for key, value in headers.items():
        # Case-insensitive prefix match
        if key.lower().startswith(META_PREFIX.lower()):
            meta_key = key[len(META_PREFIX) :]
            result[meta_key] = value
    return result


def extract_uuid(headers: Mapping[str, str]) -> UUID:
    """Extract message UUID from HTTP headers.

    Falls back to generating a new UUID if not present.
    """
    for key, value in headers.items():
        if key.lower() == UUID_HEADER.lower():
            return UUID(value)
    return uuid4()


def metadata_to_headers(metadata: dict[str, str]) -> dict[str, str]:
    """Convert metadata dict to HTTP headers."""
    return {f"{META_PREFIX}{k}": v for k, v in metadata.items()}
