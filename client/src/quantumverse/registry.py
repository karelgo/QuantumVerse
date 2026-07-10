"""Registries: local content-addressed store and the RFC-0003 HTTP mapping.

- :class:`LocalRegistry` — filesystem registry under ``~/.qv`` (or ``QV_HOME``):
  blobs at ``blobs/sha256/<first2>/<rest>`` plus an ``index.json`` mapping
  ``ns/name`` to versions, files, and cards.
- :class:`RemoteRegistry` — the RFC-0003 HTTP mapping over httpx.
- :func:`get_registry` — explicit argument > ``QV_REGISTRY_URL`` env > local.
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Optional, Union

import httpx

from .canonical import digest_bytes, is_digest
from .uris import resolve_version

__all__ = ["RegistryError", "LocalRegistry", "RemoteRegistry", "get_registry"]


class RegistryError(Exception):
    """Raised for registry lookup, publish, or transport failures."""


def _encode_file(data: bytes) -> dict:
    """Wire encoding for file payloads: UTF-8 text inline, otherwise base64."""
    try:
        text = data.decode("utf-8")
        if "\x00" not in text:
            return {"text": text}
    except UnicodeDecodeError:
        pass
    return {"b64": base64.b64encode(data).decode("ascii")}


def _decode_file(entry) -> bytes:
    if isinstance(entry, dict):
        if "text" in entry:
            return entry["text"].encode("utf-8")
        if "b64" in entry:
            return base64.b64decode(entry["b64"])
    raise RegistryError(f"unrecognized file encoding in registry response: {entry!r}")


class LocalRegistry:
    """Content-addressed local registry (default root ``~/.qv`` or ``$QV_HOME``)."""

    def __init__(self, root: Optional[Union[str, Path]] = None):
        if root is None:
            root = os.environ.get("QV_HOME") or (Path.home() / ".qv")
        self.root = Path(root)
        self._index_path = self.root / "index.json"

    # -- index ------------------------------------------------------------------

    def _load_index(self) -> dict:
        if self._index_path.exists():
            return json.loads(self._index_path.read_text(encoding="utf-8"))
        return {"artifacts": {}, "capsules": {}}

    def _save_index(self, index: dict) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self._index_path.write_text(
            json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    # -- blobs ------------------------------------------------------------------

    def _blob_path(self, digest: str) -> Path:
        hexpart = digest.split(":", 1)[1]
        return self.root / "blobs" / "sha256" / hexpart[:2] / hexpart[2:]

    def put_blob(self, data: bytes) -> str:
        digest = digest_bytes(data)
        path = self._blob_path(digest)
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        return digest

    def get_blob(self, digest: str) -> bytes:
        if not is_digest(digest):
            raise RegistryError(f"malformed digest {digest!r}")
        path = self._blob_path(digest)
        if not path.exists():
            raise RegistryError(f"blob {digest} not found in {self.root}")
        data = path.read_bytes()
        if digest_bytes(data) != digest:
            raise RegistryError(f"blob {digest} is corrupt on disk (digest mismatch)")
        return data

    # -- artifacts -----------------------------------------------------------------

    def create_artifact(self, namespace: str, name: str, type: str) -> dict:
        index = self._load_index()
        key = f"{namespace}/{name}"
        record = index["artifacts"].get(key)
        if record is None:
            record = {"type": type, "versions": {}}
            index["artifacts"][key] = record
            self._save_index(index)
        elif record["type"] != type:
            raise RegistryError(
                f"artifact {key} already exists with type {record['type']!r}, not {type!r}"
            )
        return {"namespace": namespace, "name": name, "type": record["type"]}

    def publish_version(
        self,
        namespace: str,
        name: str,
        version: str,
        files: dict[str, bytes],
        card_fields: Optional[dict] = None,
    ) -> dict:
        index = self._load_index()
        key = f"{namespace}/{name}"
        record = index["artifacts"].get(key)
        if record is None:
            raise RegistryError(f"artifact {key} does not exist (create it first)")
        if version in record["versions"]:
            raise RegistryError(
                f"{key}@{version} is already published; published versions are immutable (RFC-0003)"
            )
        file_digests = {path: self.put_blob(data) for path, data in files.items()}
        record["versions"][version] = {
            "files": file_digests,
            "card": card_fields,
        }
        self._save_index(index)
        return {
            "namespace": namespace,
            "name": name,
            "version": version,
            "files": file_digests,
        }

    def get_artifact(self, namespace: str, name: str) -> dict:
        index = self._load_index()
        key = f"{namespace}/{name}"
        record = index["artifacts"].get(key)
        if record is None:
            raise RegistryError(f"artifact {key} not found in local registry {self.root}")
        return {
            "namespace": namespace,
            "name": name,
            "type": record["type"],
            "versions": sorted(record["versions"]),
        }

    def resolve(self, namespace: str, name: str, version: Optional[str] = None) -> dict:
        index = self._load_index()
        key = f"{namespace}/{name}"
        record = index["artifacts"].get(key)
        if record is None:
            raise RegistryError(f"artifact {key} not found in local registry {self.root}")
        resolved = resolve_version(version, list(record["versions"]))
        entry = record["versions"][resolved]
        return {
            "namespace": namespace,
            "name": name,
            "type": record["type"],
            "version": resolved,
            "files": dict(entry["files"]),
            "card": entry.get("card"),
        }

    def search(self, query: str, type: Optional[str] = None) -> list[dict]:
        index = self._load_index()
        query = (query or "").lower()
        results = []
        for key, record in sorted(index["artifacts"].items()):
            if type is not None and record["type"] != type:
                continue
            haystack = [key]
            for entry in record["versions"].values():
                card = entry.get("card") or {}
                haystack += [str(card.get("name", "")), str(card.get("summary", ""))]
                haystack += [str(t) for t in card.get("tags", []) or []]
            if query and not any(query in h.lower() for h in haystack):
                continue
            ns, _, name = key.partition("/")
            versions = list(record["versions"])
            try:
                latest = resolve_version("latest", versions)
            except Exception:
                latest = max(versions) if versions else None
            results.append(
                {"namespace": ns, "name": name, "type": record["type"], "latest": latest}
            )
        return results

    # -- capsules ---------------------------------------------------------------------

    def push_capsule(self, files: dict[str, bytes]) -> str:
        if "manifest.json" not in files:
            raise RegistryError("capsule upload requires manifest.json")
        try:
            manifest = json.loads(files["manifest.json"].decode("utf-8"))
            capsule_id = manifest["id"]
        except Exception as exc:
            raise RegistryError(f"capsule manifest.json is unreadable: {exc}") from exc
        if not is_digest(capsule_id):
            raise RegistryError(f"capsule manifest has malformed id {capsule_id!r}")
        index = self._load_index()
        hexid = capsule_id.split(":", 1)[1]
        index["capsules"][hexid] = {
            "files": {path: self.put_blob(data) for path, data in files.items()}
        }
        self._save_index(index)
        return capsule_id

    def get_capsule(self, hexid: str) -> dict:
        index = self._load_index()
        matches = [h for h in index["capsules"] if h.startswith(hexid)]
        if not matches:
            raise RegistryError(f"no capsule with id prefix {hexid!r}")
        if len(matches) > 1:
            raise RegistryError(
                f"capsule id prefix {hexid!r} is ambiguous ({len(matches)} matches); extend it"
            )
        full = matches[0]
        entry = index["capsules"][full]
        return {"id": f"sha256:{full}", "files": dict(entry["files"])}


class RemoteRegistry:
    """RFC-0003 HTTP mapping against a QuantumVerse registry server."""

    def __init__(self, base_url: str, client: Optional[httpx.Client] = None):
        self.base_url = base_url.rstrip("/")
        self._client = client or httpx.Client(base_url=self.base_url, timeout=30.0)
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        try:
            resp = self._client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise RegistryError(f"registry request failed: {method} {path}: {exc}") from exc
        if resp.status_code >= 400:
            detail = ""
            try:
                body = resp.json()
                detail = body.get("detail") or body.get("error") or ""
            except Exception:
                detail = resp.text[:200]
            raise RegistryError(
                f"registry returned {resp.status_code} for {method} {path}"
                + (f": {detail}" if detail else "")
            )
        return resp

    # -- artifacts ----------------------------------------------------------------

    def get_artifact(self, namespace: str, name: str) -> dict:
        return self._request("GET", f"/api/v1/artifacts/{namespace}/{name}").json()

    def resolve(self, namespace: str, name: str, version: Optional[str] = None) -> dict:
        params = {"version": version or "latest"}
        return self._request(
            "GET", f"/api/v1/artifacts/{namespace}/{name}/resolve", params=params
        ).json()

    def get_blob(self, digest: str) -> bytes:
        data = self._request("GET", f"/api/v1/blobs/{digest}").content
        if digest_bytes(data) != digest:
            raise RegistryError(f"blob {digest} from registry failed digest verification")
        return data

    def create_artifact(self, namespace: str, name: str, type: str) -> dict:
        try:
            return self._request(
                "POST", f"/api/v1/artifacts/{namespace}/{name}", json={"type": type}
            ).json()
        except RegistryError as exc:
            # already-exists is not an error for idempotent pushes
            if "409" in str(exc):
                return self.get_artifact(namespace, name)
            raise

    def publish_version(
        self,
        namespace: str,
        name: str,
        version: str,
        files: dict[str, bytes],
        card_fields: Optional[dict] = None,
    ) -> dict:
        payload = {
            "version": version,
            "files": {path: _encode_file(data) for path, data in files.items()},
            "card_fields": card_fields or {},
        }
        return self._request(
            "POST", f"/api/v1/artifacts/{namespace}/{name}/versions", json=payload
        ).json()

    def search(self, query: str, type: Optional[str] = None) -> list[dict]:
        params = {"q": query}
        if type is not None:
            params["type"] = type
        body = self._request("GET", "/api/v1/search", params=params).json()
        if isinstance(body, dict) and "results" in body:
            return body["results"]
        if isinstance(body, list):
            return body
        raise RegistryError(f"unexpected search response shape: {type(body).__name__}")

    # -- capsules -------------------------------------------------------------------

    def push_capsule(self, files: dict[str, bytes]) -> str:
        payload = {"files": {path: _encode_file(data) for path, data in files.items()}}
        body = self._request("POST", "/api/v1/capsules", json=payload).json()
        capsule_id = body.get("id")
        if not isinstance(capsule_id, str):
            raise RegistryError(f"capsule upload response missing id: {body!r}")
        return capsule_id

    def get_capsule(self, hexid: str) -> dict:
        return self._request("GET", f"/api/v1/capsules/{hexid}").json()


Registry = Union[LocalRegistry, RemoteRegistry]


def get_registry(registry: Optional[Union[str, Registry]] = None) -> Registry:
    """Pick a registry: explicit argument > ``QV_REGISTRY_URL`` env > local."""
    if registry is None:
        url = os.environ.get("QV_REGISTRY_URL")
        return RemoteRegistry(url) if url else LocalRegistry()
    if isinstance(registry, str):
        return RemoteRegistry(registry)
    return registry
