"""High-level hub API: ``load(ref)`` and ``push(path, ref, ...)``."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, Union

from .canonical import digest_bytes
from .cards import build_card
from .registry import Registry, RegistryError, get_registry, _decode_file
from .uris import QvUriError, format_uri, parse_uri

__all__ = ["LoadedArtifact", "load", "push", "PAYLOAD_FILES", "ARTIFACT_TYPES"]

# artifact type -> canonical payload filename (RFC-0003 object kinds)
PAYLOAD_FILES = {
    "circuit": "circuit.qasm",
    "parameters": "params.json",
    "instance": "instance.json",
    "noise-model": "noise.json",
}
ARTIFACT_TYPES = tuple(PAYLOAD_FILES)


class LoadedArtifact:
    """Files and metadata for one resolved artifact or capsule."""

    def __init__(self, ref: str, files: dict[str, bytes], meta: dict):
        self.ref = ref
        self.files = files
        self.meta = meta

    def text(self, path: Optional[str] = None) -> str:
        """Decode one file as UTF-8. With no *path*, picks the primary payload."""
        if path is None:
            if "circuit.qasm" in self.files:
                path = "circuit.qasm"
            elif len(self.files) == 1:
                path = next(iter(self.files))
            else:
                raise KeyError(
                    f"multiple files in {self.ref}; specify one of: {sorted(self.files)}"
                )
        if path not in self.files:
            raise KeyError(f"{path!r} not in {self.ref} (has: {sorted(self.files)})")
        return self.files[path].decode("utf-8")

    def json(self, path: Optional[str] = None):
        return json.loads(self.text(path))

    def qiskit(self):
        """Load ``circuit.qasm`` as a Qiskit ``QuantumCircuit`` (requires qiskit)."""
        try:
            from qiskit import qasm3  # type: ignore[import-not-found]
        except ImportError as exc:
            raise ImportError(
                "qiskit is required for .qiskit(); install it with "
                "'pip install quantumverse[qiskit]' or 'pip install qiskit'"
            ) from exc
        return qasm3.loads(self.text("circuit.qasm"))

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"LoadedArtifact({self.ref!r}, files={sorted(self.files)})"


def _fetch_files(registry: Registry, file_map: dict) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    for path, entry in file_map.items():
        if isinstance(entry, str):  # a content digest -> fetch the blob
            data = registry.get_blob(entry)
            if digest_bytes(data) != entry:
                raise RegistryError(f"{path}: content digest mismatch for {entry}")
            files[path] = data
        else:  # inline {"text": ...} / {"b64": ...}
            files[path] = _decode_file(entry)
    return files


def load(ref: str, registry: Optional[Union[str, Registry]] = None) -> LoadedArtifact:
    """Resolve a qv: reference and fetch its files.

    Supports artifact refs (``ns/name[@version]``) and capsule refs
    (``capsule/<hexid>``). Registry selection: explicit > ``QV_REGISTRY_URL``
    env > local ``~/.qv``.
    """
    uri = parse_uri(ref)
    reg = get_registry(registry)

    if uri.kind == "capsule":
        record = reg.get_capsule(uri.name)
        files = _fetch_files(reg, record.get("files", {}))
        meta = {"kind": "capsule", "id": record.get("id")}
        return LoadedArtifact(format_uri(uri), files, meta)

    if uri.kind != "artifact":
        raise QvUriError(f"cannot load {ref!r}: only artifacts and capsules are loadable")

    resolved = reg.resolve(uri.namespace, uri.name, uri.version)
    files = _fetch_files(reg, resolved.get("files", {}))
    meta = {
        "kind": "artifact",
        "namespace": uri.namespace,
        "name": uri.name,
        "type": resolved.get("type"),
        "version": resolved.get("version"),
        "card": resolved.get("card"),
    }
    ref_out = f"qv:{uri.namespace}/{uri.name}@{resolved.get('version')}"
    return LoadedArtifact(ref_out, files, meta)


def push(
    path_or_dir: Union[str, Path],
    ref: str,
    type: str,
    version: Optional[str] = None,
    summary: Optional[str] = None,
    description: Optional[str] = None,
    tags: Optional[list[str]] = None,
    license: str = "CC-BY-4.0",
    authors: Optional[list[str]] = None,
    registry: Optional[Union[str, Registry]] = None,
) -> str:
    """Validate and publish an artifact version; returns the canonical ref.

    For ``circuit`` artifacts the payload is ``circuit.qasm`` (a Circuit Card
    is auto-built and attached); ``parameters`` -> ``params.json``,
    ``instance`` -> ``instance.json``, ``noise-model`` -> ``noise.json``
    (all must be valid JSON).
    """
    if type not in PAYLOAD_FILES:
        raise ValueError(
            f"unknown artifact type {type!r}; expected one of {', '.join(ARTIFACT_TYPES)}"
        )
    uri = parse_uri(ref)
    if uri.kind != "artifact":
        raise QvUriError(f"push target must be an artifact reference, got {uri.kind}: {ref!r}")
    version = version or uri.version
    if not version or version == "latest":
        raise ValueError("an explicit semantic version is required to push (e.g. 1.0.0)")

    payload_name = PAYLOAD_FILES[type]
    src = Path(path_or_dir)
    if src.is_dir():
        payload_path = src / payload_name
        if not payload_path.is_file():
            raise FileNotFoundError(
                f"{src} does not contain the {type} payload file {payload_name!r}"
            )
    elif src.is_file():
        payload_path = src
    else:
        raise FileNotFoundError(f"no such file or directory: {src}")
    data = payload_path.read_bytes()

    card_fields: dict = {}
    if type == "circuit":
        qasm_text = data.decode("utf-8")
        card_fields = build_card(
            qasm_text,
            name=uri.name,
            summary=summary or f"Circuit artifact {uri.namespace}/{uri.name}",
            description=description,
            tags=tags,
            provenance={"license": license, **({"authors": authors} if authors else {})},
        )
    else:
        try:
            json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"{payload_path} must be valid JSON for type {type!r}: {exc}") from exc
        card_fields = {"name": uri.name, "summary": summary or f"{type} artifact"}
        if description:
            card_fields["description"] = description
        if tags:
            card_fields["tags"] = tags

    reg = get_registry(registry)
    reg.create_artifact(uri.namespace, uri.name, type)
    reg.publish_version(
        uri.namespace, uri.name, version, {payload_name: data}, card_fields=card_fields
    )
    return f"qv:{uri.namespace}/{uri.name}@{version}"
