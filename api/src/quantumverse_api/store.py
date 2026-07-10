"""SQLite metadata + on-disk content-addressed blobs.

Layout under the data directory:
    registry.db                       artifacts, versions, capsules
    blobs/sha256/<first2>/<rest>      immutable blobs keyed by digest
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Optional

from quantumverse.canonical import digest_bytes, is_digest

_SCHEMA = """
CREATE TABLE IF NOT EXISTS artifacts (
    id        INTEGER PRIMARY KEY,
    namespace TEXT NOT NULL,
    name      TEXT NOT NULL,
    type      TEXT NOT NULL,
    UNIQUE (namespace, name)
);
CREATE TABLE IF NOT EXISTS versions (
    id          INTEGER PRIMARY KEY,
    artifact_id INTEGER NOT NULL REFERENCES artifacts(id),
    version     TEXT NOT NULL,
    files       TEXT NOT NULL,   -- JSON {path: digest}
    card        TEXT,            -- JSON card or null
    created     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    UNIQUE (artifact_id, version)
);
CREATE TABLE IF NOT EXISTS capsules (
    hexid   TEXT PRIMARY KEY,
    files   TEXT NOT NULL,       -- JSON {path: digest}
    title   TEXT,
    created TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
"""


class StoreError(ValueError):
    """Raised for conflicts and malformed store operations."""


class NotFound(StoreError):
    """Raised when a record does not exist."""


class Conflict(StoreError):
    """Raised when immutability or uniqueness would be violated."""


class Store:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._db_path = self.root / "registry.db"
        self._lock = threading.Lock()
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    # -- blobs ---------------------------------------------------------------

    def _blob_path(self, digest: str) -> Path:
        hexpart = digest.split(":", 1)[1]
        return self.root / "blobs" / "sha256" / hexpart[:2] / hexpart[2:]

    def put_blob(self, data: bytes) -> str:
        digest = digest_bytes(data)
        path = self._blob_path(digest)
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_bytes(data)
            tmp.replace(path)
        return digest

    def get_blob(self, digest: str) -> bytes:
        if not is_digest(digest):
            raise StoreError(f"malformed digest {digest!r}")
        path = self._blob_path(digest)
        if not path.exists():
            raise NotFound(f"blob {digest} not found")
        data = path.read_bytes()
        if digest_bytes(data) != digest:
            raise StoreError(f"blob {digest} is corrupt on disk")
        return data

    # -- artifacts -------------------------------------------------------------

    def create_artifact(self, namespace: str, name: str, type: str) -> dict:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT type FROM artifacts WHERE namespace=? AND name=?",
                (namespace, name),
            ).fetchone()
            if row is not None:
                if row["type"] != type:
                    raise Conflict(
                        f"artifact {namespace}/{name} already exists with type "
                        f"{row['type']!r}, not {type!r}"
                    )
                return {"namespace": namespace, "name": name, "type": type, "created": False}
            conn.execute(
                "INSERT INTO artifacts (namespace, name, type) VALUES (?, ?, ?)",
                (namespace, name, type),
            )
        return {"namespace": namespace, "name": name, "type": type, "created": True}

    def get_artifact(self, namespace: str, name: str) -> dict:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, type FROM artifacts WHERE namespace=? AND name=?",
                (namespace, name),
            ).fetchone()
            if row is None:
                raise NotFound(f"artifact {namespace}/{name} not found")
            versions = [
                r["version"]
                for r in conn.execute(
                    "SELECT version FROM versions WHERE artifact_id=? ORDER BY created, id",
                    (row["id"],),
                )
            ]
        return {
            "namespace": namespace,
            "name": name,
            "type": row["type"],
            "versions": sorted(versions),
        }

    def publish_version(
        self,
        namespace: str,
        name: str,
        version: str,
        files: dict[str, bytes],
        card: Optional[dict],
    ) -> dict:
        file_digests = {path: self.put_blob(data) for path, data in files.items()}
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT id FROM artifacts WHERE namespace=? AND name=?",
                (namespace, name),
            ).fetchone()
            if row is None:
                raise NotFound(f"artifact {namespace}/{name} not found (create it first)")
            exists = conn.execute(
                "SELECT 1 FROM versions WHERE artifact_id=? AND version=?",
                (row["id"], version),
            ).fetchone()
            if exists:
                raise Conflict(
                    f"{namespace}/{name}@{version} is already published; "
                    "published versions are immutable (RFC-0003)"
                )
            conn.execute(
                "INSERT INTO versions (artifact_id, version, files, card) VALUES (?, ?, ?, ?)",
                (
                    row["id"],
                    version,
                    json.dumps(file_digests, sort_keys=True),
                    json.dumps(card, sort_keys=True) if card is not None else None,
                ),
            )
        return {
            "namespace": namespace,
            "name": name,
            "version": version,
            "files": file_digests,
        }

    def get_version(self, namespace: str, name: str, version: str) -> dict:
        with self._connect() as conn:
            row = conn.execute(
                """SELECT a.type, v.version, v.files, v.card
                   FROM artifacts a JOIN versions v ON v.artifact_id = a.id
                   WHERE a.namespace=? AND a.name=? AND v.version=?""",
                (namespace, name, version),
            ).fetchone()
        if row is None:
            raise NotFound(f"{namespace}/{name}@{version} not found")
        return {
            "namespace": namespace,
            "name": name,
            "type": row["type"],
            "version": row["version"],
            "files": json.loads(row["files"]),
            "card": json.loads(row["card"]) if row["card"] else None,
        }

    def list_artifacts(self, type: Optional[str] = None) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, namespace, name, type FROM artifacts ORDER BY namespace, name"
            ).fetchall()
            out = []
            for row in rows:
                if type is not None and row["type"] != type:
                    continue
                vrows = conn.execute(
                    "SELECT version, card FROM versions WHERE artifact_id=?", (row["id"],)
                ).fetchall()
                out.append(
                    {
                        "namespace": row["namespace"],
                        "name": row["name"],
                        "type": row["type"],
                        "versions": sorted(r["version"] for r in vrows),
                        "cards": {
                            r["version"]: json.loads(r["card"]) for r in vrows if r["card"]
                        },
                    }
                )
        return out

    # -- capsules ---------------------------------------------------------------

    def put_capsule(self, capsule_id: str, files: dict[str, bytes], title: str) -> str:
        hexid = capsule_id.split(":", 1)[1]
        file_digests = {path: self.put_blob(data) for path, data in files.items()}
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO capsules (hexid, files, title) VALUES (?, ?, ?)",
                (hexid, json.dumps(file_digests, sort_keys=True), title),
            )
        return capsule_id

    def get_capsule(self, hexid_prefix: str) -> dict:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT hexid, files, title, created FROM capsules WHERE hexid LIKE ?",
                (hexid_prefix + "%",),
            ).fetchall()
        if not rows:
            raise NotFound(f"no capsule with id prefix {hexid_prefix!r}")
        if len(rows) > 1:
            raise Conflict(
                f"capsule id prefix {hexid_prefix!r} is ambiguous ({len(rows)} matches); extend it"
            )
        row = rows[0]
        return {
            "id": f"sha256:{row['hexid']}",
            "files": json.loads(row["files"]),
            "title": row["title"],
            "created": row["created"],
        }

    def list_capsules(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT hexid, title, created FROM capsules ORDER BY created DESC, hexid"
            ).fetchall()
        return [
            {"id": f"sha256:{r['hexid']}", "title": r["title"], "created": r["created"]}
            for r in rows
        ]
