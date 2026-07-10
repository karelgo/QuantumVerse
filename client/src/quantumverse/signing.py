"""Ed25519 capsule signing and verification (RFC-0001 trust levels).

Signatures cover the ASCII bytes of the capsule id, so one signature endorses
the entire content-addressed capsule. Signature files (``author.sig``,
``receipt.sig``) are never content-addressed themselves: a capsule's identity
is its contents, not its endorsements.

Keys live under ``$QV_HOME/keys/`` (default ``~/.qv/keys``), one JSON file per
key, private file mode 0600.
"""

from __future__ import annotations

import base64
import json
import os
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from ._schema import schema_errors
from .canonical import canonical_bytes, digest_bytes

__all__ = [
    "SigningError",
    "generate_keypair",
    "load_key",
    "key_info",
    "make_signature",
    "sign_files",
    "check_signature",
    "trust_level",
]

SIGNATURE_FILES = ("author.sig", "receipt.sig")


class SigningError(ValueError):
    """Raised for key-store and signing failures."""


def _keys_dir(home: Optional[str] = None) -> Path:
    root = Path(home) if home else Path(os.environ.get("QV_HOME") or (Path.home() / ".qv"))
    return root / "keys"


def _key_path(name: str, home: Optional[str] = None) -> Path:
    if not name.replace("-", "").replace("_", "").isalnum():
        raise SigningError(f"invalid key name {name!r}")
    return _keys_dir(home) / f"{name}.json"


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def generate_keypair(name: str = "default", home: Optional[str] = None) -> dict:
    """Generate and store an Ed25519 keypair; returns its public info."""
    path = _key_path(name, home)
    if path.exists():
        raise SigningError(f"key {name!r} already exists at {path}")
    private = Ed25519PrivateKey.generate()
    public_raw = private.public_key().public_bytes_raw()
    record = {
        "algorithm": "ed25519",
        "name": name,
        "created": _utc_now(),
        "private_key": _b64(private.private_bytes_raw()),
        "public_key": _b64(public_raw),
        "key_id": digest_bytes(public_raw),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    return key_info(name, home)


def load_key(name: str = "default", home: Optional[str] = None) -> tuple[Ed25519PrivateKey, dict]:
    path = _key_path(name, home)
    if not path.exists():
        raise SigningError(f"no key named {name!r} — run 'qv key generate' first")
    record = json.loads(path.read_text(encoding="utf-8"))
    private = Ed25519PrivateKey.from_private_bytes(base64.b64decode(record["private_key"]))
    return private, record


def key_info(name: str = "default", home: Optional[str] = None) -> dict:
    """Public info for a stored key: name, key_id, public_key, created."""
    _, record = load_key(name, home)
    return {k: record[k] for k in ("name", "key_id", "public_key", "created", "algorithm")}


def make_signature(
    capsule_id: str,
    key_name: str = "default",
    signer: Optional[str] = None,
    home: Optional[str] = None,
) -> dict:
    """Build a signature document over *capsule_id* (RFC-0001 signature format)."""
    if not capsule_id.startswith("sha256:"):
        raise SigningError(f"cannot sign malformed capsule id {capsule_id!r}")
    private, record = load_key(key_name, home)
    doc = {
        "algorithm": "ed25519",
        "key_id": record["key_id"],
        "public_key": record["public_key"],
        "signature": _b64(private.sign(capsule_id.encode("ascii"))),
        "signed": _utc_now(),
    }
    if signer:
        doc["signer"] = signer
    return doc


def sign_files(
    files: dict[str, bytes],
    capsule_id: str,
    key_name: str = "default",
    signer: Optional[str] = None,
    home: Optional[str] = None,
) -> dict[str, bytes]:
    """Return a copy of capsule *files* with ``author.sig`` attached."""
    doc = make_signature(capsule_id, key_name=key_name, signer=signer, home=home)
    signed = dict(files)
    signed["author.sig"] = canonical_bytes(doc)
    return signed


def check_signature(sig_doc: dict, capsule_id: str) -> Optional[str]:
    """Verify one signature document against *capsule_id*.

    Returns ``None`` when valid, otherwise a human-readable reason.
    Schema, key-id binding, and the Ed25519 signature are all checked.
    """
    errors = schema_errors("signature", sig_doc)
    if errors:
        return "signature file malformed: " + "; ".join(errors)
    try:
        public_raw = base64.b64decode(sig_doc["public_key"])
        signature = base64.b64decode(sig_doc["signature"])
    except Exception as exc:
        return f"signature file carries invalid base64: {exc}"
    if digest_bytes(public_raw) != sig_doc["key_id"]:
        return "key_id does not match the embedded public key"
    try:
        Ed25519PublicKey.from_public_bytes(public_raw).verify(
            signature, capsule_id.encode("ascii")
        )
    except InvalidSignature:
        return "Ed25519 signature does not verify over the capsule id"
    except ValueError as exc:
        return f"invalid public key: {exc}"
    return None


def trust_level(files: dict[str, bytes], capsule_id: str) -> tuple[int, str]:
    """RFC-0001 trust level of a capsule's signature set.

    Level 2 remains a *candidate* until a provider key registry exists
    (RFC-0001 Open Questions §5) — the signature is checked for internal
    validity, but the key is not yet bound to a known provider.
    """
    def _doc(name: str) -> Optional[dict]:
        raw = files.get(name)
        if raw is None:
            return None
        try:
            doc = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        return doc if isinstance(doc, dict) else None

    receipt = _doc("receipt.sig")
    if receipt is not None and check_signature(receipt, capsule_id) is None:
        return 2, (
            "level 2 candidate (provider receipt verifies; provider key "
            "registry not yet established)"
        )
    author = _doc("author.sig")
    if author is not None and check_signature(author, capsule_id) is None:
        who = author.get("signer")
        detail = f", signer claim: {who}" if who else ""
        return 1, f"level 1 (author-signed, key {author.get('key_id', '?')[:20]}…{detail})"
    return 0, "level 0 (unsigned)"
