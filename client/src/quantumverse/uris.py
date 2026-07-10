"""``qv:`` URI parsing, formatting, and version resolution (RFC-0003)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

__all__ = [
    "QvUri",
    "QvUriError",
    "VersionError",
    "parse_uri",
    "format_uri",
    "resolve_version",
    "is_semver",
    "is_hexid",
    "RESERVED_NAMESPACES",
]

# Namespaces that can never be registered as user or organization handles.
RESERVED_NAMESPACES = frozenset({"users", "device", "capsule", "instances", "spec"})

_SEGMENT_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_HEXID_RE = re.compile(r"^[0-9a-f]{6,64}$")
# A full semantic version: X.Y.Z with optional pre-release and build metadata.
_SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?"
    r"(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$"
)
# Prefix version specs allowed in references: "1" or "1.4".
_PREFIX_RE = re.compile(r"^(0|[1-9]\d*)(?:\.(0|[1-9]\d*))?$")


def is_semver(value: str) -> bool:
    """True if *value* is a full X.Y.Z semantic version (RFC-0003)."""
    return isinstance(value, str) and bool(_SEMVER_RE.match(value))


def is_hexid(value: str) -> bool:
    """True if *value* is a 6–64 char lowercase-hex capsule id prefix (RFC-0003)."""
    return isinstance(value, str) and bool(_HEXID_RE.match(value))


class QvUriError(ValueError):
    """Raised for anything that is not a well-formed qv: reference."""


class VersionError(ValueError):
    """Raised when a version spec cannot be resolved."""


def _check_segment(seg: str, what: str, uri: str) -> None:
    if not _SEGMENT_RE.match(seg):
        raise QvUriError(
            f"invalid {what} {seg!r} in {uri!r}: segments are lowercase ASCII "
            "alphanumerics with single interior hyphens (no leading/trailing/double hyphen)"
        )
    if len(seg) > 64:
        raise QvUriError(f"invalid {what} {seg!r} in {uri!r}: segments are at most 64 characters")


def _check_version_spec(version: str, uri: str) -> None:
    if version == "latest":
        return
    if _SEMVER_RE.match(version) or _PREFIX_RE.match(version):
        return
    raise QvUriError(
        f"invalid version {version!r} in {uri!r}: expected 'latest', a semantic "
        "version (e.g. 1.4.2), or a numeric prefix (e.g. 1 or 1.4)"
    )


@dataclass(frozen=True)
class QvUri:
    """A parsed qv: reference.

    kind: one of ``artifact``, ``user``, ``device``, ``capsule``.
    namespace: artifact/device namespace; ``None`` for users and capsules.
    name: artifact/device name, user handle, or capsule hex id.
    version: version spec for artifacts (``None`` means ``latest``).
    """

    kind: str
    namespace: Optional[str]
    name: str
    version: Optional[str] = None

    def __str__(self) -> str:
        return format_uri(self)


def parse_uri(text: str) -> QvUri:
    """Parse a qv: reference (the ``qv:`` scheme prefix is optional).

    Accepts artifact (``ns/name[@ver]``), user (``users/handle``),
    device (``device/ns/name``), and capsule (``capsule/hexid``) forms.
    Uppercase input is lowered before validation, per RFC-0003.
    """
    if not isinstance(text, str):
        raise QvUriError(f"expected a string qv: reference, got {type(text).__name__}")
    original = text
    text = text.strip()
    if text.lower().startswith("qv://"):
        raise QvUriError(
            f"invalid reference {original!r}: cross-host 'qv://' qualification is not defined; "
            "qv: URIs are host-relative"
        )
    if text.lower().startswith("qv:"):
        text = text[3:]
    text = text.lower()
    if not text:
        raise QvUriError(f"empty qv: reference: {original!r}")

    version: Optional[str] = None
    if "@" in text:
        path, _, version = text.partition("@")
        if not version:
            raise QvUriError(f"invalid reference {original!r}: empty version after '@'")
        if "@" in version:
            raise QvUriError(f"invalid reference {original!r}: more than one '@'")
    else:
        path = text

    segments = path.split("/")
    if any(s == "" for s in segments):
        raise QvUriError(f"invalid reference {original!r}: empty path segment")

    if segments[0] == "users":
        if len(segments) != 2:
            raise QvUriError(f"invalid user reference {original!r}: expected users/<handle>")
        if version is not None:
            raise QvUriError(f"invalid reference {original!r}: user profiles are versionless")
        _check_segment(segments[1], "handle", original)
        return QvUri(kind="user", namespace=None, name=segments[1])

    if segments[0] == "device":
        if len(segments) != 3:
            raise QvUriError(f"invalid device reference {original!r}: expected device/<owner>/<name>")
        if version is not None:
            raise QvUriError(f"invalid reference {original!r}: devices are versionless by address")
        _check_segment(segments[1], "device owner", original)
        _check_segment(segments[2], "device name", original)
        return QvUri(kind="device", namespace=segments[1], name=segments[2])

    if segments[0] == "capsule":
        if len(segments) != 2:
            raise QvUriError(f"invalid capsule reference {original!r}: expected capsule/<hexid>")
        if version is not None:
            raise QvUriError(f"invalid reference {original!r}: capsules are content-addressed, not versioned")
        hexid = segments[1]
        if not _HEXID_RE.match(hexid):
            raise QvUriError(
                f"invalid capsule id {hexid!r} in {original!r}: expected 6-64 lowercase hex digits"
            )
        return QvUri(kind="capsule", namespace=None, name=hexid)

    if len(segments) != 2:
        raise QvUriError(
            f"invalid reference {original!r}: expected <namespace>/<name>, users/<handle>, "
            "device/<owner>/<name>, or capsule/<hexid>"
        )
    _check_segment(segments[0], "namespace", original)
    _check_segment(segments[1], "name", original)
    if version is not None:
        _check_version_spec(version, original)
    return QvUri(kind="artifact", namespace=segments[0], name=segments[1], version=version)


def format_uri(uri: QvUri) -> str:
    """Render a QvUri back to its canonical ``qv:...`` string."""
    if uri.kind == "artifact":
        base = f"qv:{uri.namespace}/{uri.name}"
        if uri.version:
            base += f"@{uri.version}"
        return base
    if uri.kind == "user":
        return f"qv:users/{uri.name}"
    if uri.kind == "device":
        return f"qv:device/{uri.namespace}/{uri.name}"
    if uri.kind == "capsule":
        return f"qv:capsule/{uri.name}"
    raise QvUriError(f"unknown qv URI kind {uri.kind!r}")


def _parse_semver(version: str):
    m = _SEMVER_RE.match(version)
    if not m:
        return None
    major, minor, patch, prerelease, _build = m.groups()
    pre_key = ()
    if prerelease is not None:
        parts = []
        for ident in prerelease.split("."):
            if ident.isdigit():
                parts.append((0, int(ident), ""))
            else:
                parts.append((1, 0, ident))
        pre_key = tuple(parts)
    return (int(major), int(minor), int(patch), prerelease, pre_key)


def _semver_sort_key(parsed):
    major, minor, patch, prerelease, pre_key = parsed
    # A pre-release sorts below the corresponding release.
    return (major, minor, patch, 0 if prerelease is not None else 1, pre_key)


def resolve_version(spec: Optional[str], available: list[str]) -> str:
    """Resolve a version spec against a list of published versions (RFC-0003).

    - ``None`` / ``"latest"``: highest stable version (pre-releases ignored).
    - Exact semver (``1.4.2`` or ``1.0.0-rc.1``): that version, exactly.
    - Prefix ``1.4``: highest stable ``1.4.x``; prefix ``1``: highest stable ``1.x.y``.
    """
    if spec is None:
        spec = "latest"
    parsed_available = []
    for v in available:
        p = _parse_semver(v)
        if p is not None:
            parsed_available.append((v, p))

    if spec == "latest":
        stable = [(v, p) for v, p in parsed_available if p[3] is None]
        if not stable:
            raise VersionError(
                f"no stable version available (versions: {sorted(available) or 'none'})"
            )
        return max(stable, key=lambda vp: _semver_sort_key(vp[1]))[0]

    if _SEMVER_RE.match(spec):
        if spec in available:
            return spec
        raise VersionError(f"version {spec!r} not found (versions: {sorted(available) or 'none'})")

    m = _PREFIX_RE.match(spec)
    if not m:
        raise VersionError(
            f"invalid version spec {spec!r}: expected 'latest', a semantic version, or a prefix"
        )
    major = int(m.group(1))
    minor = int(m.group(2)) if m.group(2) is not None else None
    matching = [
        (v, p)
        for v, p in parsed_available
        if p[3] is None and p[0] == major and (minor is None or p[1] == minor)
    ]
    if not matching:
        raise VersionError(
            f"no version matches {spec!r} (versions: {sorted(available) or 'none'})"
        )
    return max(matching, key=lambda vp: _semver_sort_key(vp[1]))[0]
