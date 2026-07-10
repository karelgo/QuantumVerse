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
from .devices import calibration_summary, validate_record
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
            index = json.loads(self._index_path.read_text(encoding="utf-8"))
        else:
            index = {}
        index.setdefault("artifacts", {})
        index.setdefault("capsules", {})
        index.setdefault("devices", {})
        index.setdefault("boards", {})
        return index

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
        self._link_capsule_calibration(index, capsule_id, files)
        self._save_index(index)
        return capsule_id

    def _link_capsule_calibration(
        self, index: dict, capsule_id: str, files: dict[str, bytes]
    ) -> None:
        """RFC-0004 rule 1: matching capsules feed the device's timeline."""
        raw = files.get("device.json")
        if raw is None:
            return
        try:
            device_doc = json.loads(raw.decode("utf-8"))
            backend = device_doc.get("backend") or {}
            identity = (backend.get("provider"), backend.get("name"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return
        for entry in index["devices"].values():
            record_backend = entry["record"]["backend"]
            if (record_backend["provider"], record_backend["name"]) != identity:
                continue
            if any(c.get("capsule") == capsule_id for c in entry["calibrations"]):
                return
            entry["calibrations"].append(
                {
                    "captured": device_doc.get("captured", ""),
                    "snapshot": self.put_blob(raw),
                    "capsule": capsule_id,
                    "summary": calibration_summary(device_doc),
                }
            )
            return

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

    # -- devices (RFC-0004) ---------------------------------------------------------

    def register_device(self, namespace: str, name: str, record: dict) -> dict:
        validate_record(record)
        index = self._load_index()
        key = f"{namespace}/{name}"
        if key in index["devices"]:
            raise RegistryError(f"device {key} is already registered")
        identity = (record["backend"]["provider"], record["backend"]["name"])
        for other_key, entry in index["devices"].items():
            other = entry["record"]["backend"]
            if (other["provider"], other["name"]) == identity:
                raise RegistryError(
                    f"backend identity {identity[0]}/{identity[1]} is already claimed "
                    f"by device {other_key}"
                )
        index["devices"][key] = {"record": record, "calibrations": []}
        self._save_index(index)
        return self.get_device(namespace, name)

    def _device_entry(self, index: dict, namespace: str, name: str) -> dict:
        entry = index["devices"].get(f"{namespace}/{name}")
        if entry is None:
            raise RegistryError(f"device {namespace}/{name} not found in {self.root}")
        return entry

    def get_device(self, namespace: str, name: str) -> dict:
        index = self._load_index()
        entry = self._device_entry(index, namespace, name)
        calibrations = sorted(entry["calibrations"], key=lambda c: c.get("captured", ""))
        latest = calibrations[-1] if calibrations else None
        certificates = entry.get("certificates") or []
        return {
            "ref": f"qv:device/{namespace}/{name}",
            "namespace": namespace,
            "name": name,
            "record": entry["record"],
            "calibration_count": len(calibrations),
            "capsule_count": sum(1 for c in calibrations if c.get("capsule")),
            "latest_calibration": (
                {"captured": latest["captured"], "summary": latest["summary"]}
                if latest
                else None
            ),
            "certificate": certificates[-1] if certificates else None,
        }

    def list_devices(self) -> list[dict]:
        index = self._load_index()
        return [
            self.get_device(*key.split("/", 1)) for key in sorted(index["devices"])
        ]

    def device_calibrations(self, namespace: str, name: str, limit: int = 100) -> list[dict]:
        index = self._load_index()
        entry = self._device_entry(index, namespace, name)
        ordered = sorted(
            entry["calibrations"], key=lambda c: c.get("captured", ""), reverse=True
        )
        return ordered[:limit]

    def submit_certificate(
        self, namespace: str, name: str, capsule_ids: list[str]
    ) -> dict:
        """Recompute and store a birth certificate from capsules (RFC-0005)."""
        from .certify import evaluate_capsule_files

        index = self._load_index()
        entry = self._device_entry(index, namespace, name)
        capsules = []
        for ref in capsule_ids:
            hexid = ref.split(":", 1)[1] if ref.startswith("sha256:") else ref
            record = self.get_capsule(hexid)
            files = {
                path: self.get_blob(digest) for path, digest in record["files"].items()
            }
            capsules.append((record["id"], files))
        certificate = evaluate_capsule_files(
            capsules, expected_backend=entry["record"]["backend"]
        )
        entry.setdefault("certificates", []).append(certificate)
        self._save_index(index)
        return certificate

    def get_certificate(self, namespace: str, name: str) -> dict:
        index = self._load_index()
        entry = self._device_entry(index, namespace, name)
        certificates = entry.get("certificates") or []
        if not certificates:
            raise RegistryError(f"device {namespace}/{name} has no birth certificate")
        return certificates[-1]

    # -- leaderboards (RFC-0006) -------------------------------------------------------

    def _resolve_instance(self, ref: str) -> dict:
        from .uris import parse_uri

        uri = parse_uri(ref)
        resolved = self.resolve(uri.namespace, uri.name, uri.version)
        if resolved["type"] != "instance":
            raise RegistryError(
                f"leaderboard instance {ref} is a {resolved['type']!r} artifact, not an instance"
            )
        digest = resolved["files"].get("instance.json")
        if digest is None:
            raise RegistryError(f"{ref} has no instance.json payload")
        return json.loads(self.get_blob(digest).decode("utf-8"))

    def create_board(self, board: dict) -> dict:
        from .leaderboard import validate_board

        validate_board(board)
        self._resolve_instance(board["instance"])  # pin must resolve here
        index = self._load_index()
        if board["name"] in index["boards"]:
            raise RegistryError(f"leaderboard {board['name']!r} already exists")
        index["boards"][board["name"]] = {"definition": board, "entries": []}
        self._save_index(index)
        return board

    def list_boards(self) -> list[dict]:
        index = self._load_index()
        return [
            {**record["definition"], "entry_count": len(record["entries"])}
            for _, record in sorted(index["boards"].items())
        ]

    def get_board(self, name: str) -> dict:
        from .leaderboard import rank_entries

        index = self._load_index()
        record = index["boards"].get(name)
        if record is None:
            raise RegistryError(f"leaderboard {name!r} not found")
        definition = record["definition"]
        return {
            **definition,
            "entries": rank_entries(record["entries"], definition["higher_is_better"]),
        }

    def submit_entry(self, name: str, capsule_ref: str) -> dict:
        from .leaderboard import LeaderboardError, score_capsule_files
        from .signing import trust_level

        index = self._load_index()
        record = index["boards"].get(name)
        if record is None:
            raise RegistryError(f"leaderboard {name!r} not found")
        definition = record["definition"]
        instance = self._resolve_instance(definition["instance"])

        hexid = capsule_ref.split(":", 1)[1] if capsule_ref.startswith("sha256:") else capsule_ref
        capsule_record = self.get_capsule(hexid)
        files = {
            path: self.get_blob(digest) for path, digest in capsule_record["files"].items()
        }
        entry = score_capsule_files(definition, instance, capsule_record["id"], files)
        min_shots = definition.get("min_shots")
        if min_shots and (entry["shots"] or 0) < min_shots:
            raise LeaderboardError(
                f"board {name!r} requires at least {min_shots} shots, capsule has {entry['shots']}"
            )
        entry["trust"] = trust_level(files, capsule_record["id"])[0]
        entry["submitted"] = _utc_now()

        entries = [e for e in record["entries"] if e["capsule"] != entry["capsule"]]
        entries.append(entry)
        record["entries"] = entries
        self._save_index(index)
        return entry


def _utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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

    # -- devices (RFC-0004) -----------------------------------------------------------

    def register_device(self, namespace: str, name: str, record: dict) -> dict:
        validate_record(record)
        return self._request(
            "POST", f"/api/v1/devices/{namespace}/{name}", json={"record": record}
        ).json()

    def get_device(self, namespace: str, name: str) -> dict:
        return self._request("GET", f"/api/v1/devices/{namespace}/{name}").json()

    def list_devices(self) -> list[dict]:
        return self._request("GET", "/api/v1/devices").json()["devices"]

    def device_calibrations(self, namespace: str, name: str, limit: int = 100) -> list[dict]:
        return self._request(
            "GET",
            f"/api/v1/devices/{namespace}/{name}/calibrations",
            params={"limit": limit},
        ).json()["calibrations"]

    def submit_certificate(
        self, namespace: str, name: str, capsule_ids: list[str]
    ) -> dict:
        return self._request(
            "POST",
            f"/api/v1/devices/{namespace}/{name}/certificate",
            json={"capsules": list(capsule_ids)},
        ).json()

    def get_certificate(self, namespace: str, name: str) -> dict:
        return self._request(
            "GET", f"/api/v1/devices/{namespace}/{name}/certificate"
        ).json()

    # -- leaderboards (RFC-0006) ---------------------------------------------------------

    def create_board(self, board: dict) -> dict:
        from .leaderboard import validate_board

        validate_board(board)
        return self._request("POST", "/api/v1/leaderboards", json=board).json()

    def list_boards(self) -> list[dict]:
        return self._request("GET", "/api/v1/leaderboards").json()["leaderboards"]

    def get_board(self, name: str) -> dict:
        return self._request("GET", f"/api/v1/leaderboards/{name}").json()

    def submit_entry(self, name: str, capsule_ref: str) -> dict:
        return self._request(
            "POST", f"/api/v1/leaderboards/{name}/entries", json={"capsule": capsule_ref}
        ).json()


Registry = Union[LocalRegistry, RemoteRegistry]


def get_registry(registry: Optional[Union[str, Registry]] = None) -> Registry:
    """Pick a registry: explicit argument > ``QV_REGISTRY_URL`` env > local."""
    if registry is None:
        url = os.environ.get("QV_REGISTRY_URL")
        return RemoteRegistry(url) if url else LocalRegistry()
    if isinstance(registry, str):
        return RemoteRegistry(registry)
    return registry
