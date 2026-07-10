"""Canonical JSON serialization (RFC 8785) and content digests (RFC-0001).

Every JSON document on QuantumVerse is hashed over its RFC 8785 canonical
form; text files are hashed as raw UTF-8 bytes with ``\\n`` line endings.
Digests are always lowercase-hex SHA-256 with a ``sha256:`` prefix.
"""

from __future__ import annotations

import hashlib
from typing import Any

import rfc8785

DIGEST_PREFIX = "sha256:"


def canonical_bytes(obj: Any) -> bytes:
    """Serialize *obj* to RFC 8785 (JCS) canonical JSON bytes."""
    return rfc8785.dumps(obj)


def digest_bytes(data: bytes) -> str:
    """Return the ``sha256:<hex>`` digest of raw bytes."""
    return DIGEST_PREFIX + hashlib.sha256(data).hexdigest()


def digest_json(obj: Any) -> str:
    """Return the ``sha256:<hex>`` digest of the canonical form of *obj*."""
    return digest_bytes(canonical_bytes(obj))


def is_digest(value: str) -> bool:
    """True if *value* is a well-formed ``sha256:<64 lowercase hex>`` digest."""
    if not isinstance(value, str) or not value.startswith(DIGEST_PREFIX):
        return False
    hexpart = value[len(DIGEST_PREFIX):]
    return len(hexpart) == 64 and all(c in "0123456789abcdef" for c in hexpart)
