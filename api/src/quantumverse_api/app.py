"""FastAPI application exposing the RFC-0003 HTTP mapping.

Trust model: the server re-derives everything derivable. Circuit Cards are
rebuilt server-side from the uploaded QASM (RFC-0002: resources are computed,
not claimed); capsules are fully re-validated before acceptance; blobs are
stored and served by content digest.
"""

from __future__ import annotations

import base64
import os
import re
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field

from quantumverse._schema import schema_errors
from quantumverse.capsule import Capsule
from quantumverse.cards import CardError, build_card
from quantumverse.hub import ARTIFACT_TYPES, PAYLOAD_FILES
from quantumverse.uris import QvUriError, VersionError, parse_uri, resolve_version

from .store import Conflict, NotFound, Store, StoreError

_SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?"
    r"(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$"
)
_HEXID_RE = re.compile(r"^[0-9a-f]{6,64}$")


class FileEntry(BaseModel):
    text: Optional[str] = None
    b64: Optional[str] = None

    def to_bytes(self) -> bytes:
        if self.text is not None:
            return self.text.encode("utf-8")
        if self.b64 is not None:
            try:
                return base64.b64decode(self.b64, validate=True)
            except Exception as exc:
                raise HTTPException(400, f"invalid base64 payload: {exc}") from exc
        raise HTTPException(400, "file entry must carry 'text' or 'b64'")


class CreateArtifact(BaseModel):
    type: str


class PublishVersion(BaseModel):
    version: str
    files: dict[str, FileEntry]
    card_fields: dict = Field(default_factory=dict)


class CapsuleUpload(BaseModel):
    files: dict[str, FileEntry]


class DeviceRegistration(BaseModel):
    record: dict


class CertificateSubmission(BaseModel):
    capsules: list[str] = Field(min_length=1)


def _check_ref(namespace: str, name: str) -> None:
    try:
        uri = parse_uri(f"{namespace}/{name}")
    except QvUriError as exc:
        raise HTTPException(400, str(exc)) from exc
    if uri.kind != "artifact":
        raise HTTPException(400, f"{namespace}/{name} is not an artifact reference")


def create_app(data_dir: Optional[str] = None, web_dir: Optional[str] = None) -> FastAPI:
    data_dir = data_dir or os.environ.get("QV_DATA_DIR") or "data"
    store = Store(data_dir)

    app = FastAPI(
        title="QuantumVerse registry",
        version="0.1.0",
        description="Reference registry for QuantumVerse artifacts, capsules, and blobs.",
    )
    app.state.store = store
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(NotFound)
    async def _not_found(_req: Request, exc: NotFound):
        return Response(
            content=f'{{"detail": {exc.args[0]!r}}}'.replace("'", '"'),
            status_code=404,
            media_type="application/json",
        )

    @app.get("/healthz")
    def healthz() -> dict:
        return {"status": "ok", "service": "quantumverse-registry"}

    # -- artifacts -----------------------------------------------------------

    @app.post("/api/v1/artifacts/{namespace}/{name}", status_code=201)
    def create_artifact(namespace: str, name: str, body: CreateArtifact) -> dict:
        _check_ref(namespace, name)
        if body.type not in ARTIFACT_TYPES:
            raise HTTPException(
                400,
                f"unknown artifact type {body.type!r}; expected one of {', '.join(ARTIFACT_TYPES)}",
            )
        try:
            return store.create_artifact(namespace, name, body.type)
        except Conflict as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.get("/api/v1/artifacts")
    def list_artifacts(type: Optional[str] = Query(default=None)) -> dict:
        return {"artifacts": store.list_artifacts(type=type)}

    @app.get("/api/v1/artifacts/{namespace}/{name}")
    def get_artifact(namespace: str, name: str) -> dict:
        try:
            record = store.get_artifact(namespace, name)
        except NotFound as exc:
            raise HTTPException(404, str(exc)) from exc
        try:
            record["latest"] = resolve_version("latest", record["versions"])
        except VersionError:
            record["latest"] = None
        return record

    @app.post("/api/v1/artifacts/{namespace}/{name}/versions", status_code=201)
    def publish_version(namespace: str, name: str, body: PublishVersion) -> dict:
        _check_ref(namespace, name)
        if not _SEMVER_RE.match(body.version):
            raise HTTPException(400, f"{body.version!r} is not a semantic version (RFC-0003)")
        try:
            record = store.get_artifact(namespace, name)
        except NotFound as exc:
            raise HTTPException(404, str(exc)) from exc

        files = {path: entry.to_bytes() for path, entry in body.files.items()}
        payload_name = PAYLOAD_FILES.get(record["type"])
        if payload_name and payload_name not in files:
            raise HTTPException(
                422,
                f"{record['type']} artifacts must include the payload file {payload_name!r}",
            )

        card = dict(body.card_fields or {})
        if record["type"] == "circuit" and "circuit.qasm" in files:
            # RFC-0002: resources are computed, not claimed — rebuild the card
            # server-side and overwrite whatever the client sent.
            try:
                qasm_text = files["circuit.qasm"].decode("utf-8")
                card = build_card(
                    qasm_text,
                    name=card.get("name") or name,
                    summary=card.get("summary") or f"Circuit artifact {namespace}/{name}",
                    description=card.get("description"),
                    tags=card.get("tags"),
                    provenance=card.get("provenance") or {"license": "CC-BY-4.0"},
                )
            except (UnicodeDecodeError, CardError, ValueError) as exc:
                raise HTTPException(
                    422, f"circuit.qasm rejected by the registry: {exc}"
                ) from exc

        try:
            return store.publish_version(namespace, name, body.version, files, card or None)
        except Conflict as exc:
            raise HTTPException(409, str(exc)) from exc
        except NotFound as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.get("/api/v1/artifacts/{namespace}/{name}/resolve")
    def resolve(namespace: str, name: str, version: str = Query(default="latest")) -> dict:
        try:
            record = store.get_artifact(namespace, name)
        except NotFound as exc:
            raise HTTPException(404, str(exc)) from exc
        try:
            resolved = resolve_version(version, record["versions"])
        except VersionError as exc:
            raise HTTPException(404, str(exc)) from exc
        return store.get_version(namespace, name, resolved)

    # -- blobs ----------------------------------------------------------------

    @app.get("/api/v1/blobs/{digest}")
    def get_blob(digest: str) -> Response:
        try:
            data = store.get_blob(digest)
        except NotFound as exc:
            raise HTTPException(404, str(exc)) from exc
        except StoreError as exc:
            raise HTTPException(400, str(exc)) from exc
        return Response(content=data, media_type="application/octet-stream")

    # -- capsules --------------------------------------------------------------

    @app.post("/api/v1/capsules", status_code=201)
    def push_capsule(body: CapsuleUpload) -> dict:
        from quantumverse.signing import trust_level

        files = {path: entry.to_bytes() for path, entry in body.files.items()}
        capsule = Capsule(files)
        findings = capsule.validate()
        errors = [str(f) for f in findings if f.severity == "error"]
        if errors:
            raise HTTPException(422, {"detail": "capsule is invalid", "errors": errors})
        manifest = capsule.manifest
        level, trust_detail = trust_level(files, capsule.id)
        store.put_capsule(capsule.id, files, title=manifest.get("title", ""), trust=level)
        return {
            "id": capsule.id,
            "short_id": capsule.short_id,
            "trust": level,
            "trust_detail": trust_detail,
            "warnings": [str(f) for f in findings if f.severity == "warning"],
        }

    @app.get("/api/v1/capsules")
    def list_capsules() -> dict:
        return {"capsules": store.list_capsules()}

    @app.get("/api/v1/capsules/{hexid}")
    def get_capsule(hexid: str) -> dict:
        hexid = hexid.lower()
        if hexid.startswith("sha256:"):
            hexid = hexid.split(":", 1)[1]
        if not _HEXID_RE.match(hexid):
            raise HTTPException(400, f"malformed capsule id {hexid!r} (want 6-64 hex chars)")
        try:
            return store.get_capsule(hexid)
        except NotFound as exc:
            raise HTTPException(404, str(exc)) from exc
        except Conflict as exc:
            raise HTTPException(409, str(exc)) from exc

    # -- devices (RFC-0004) ---------------------------------------------------------

    def _check_device_ref(owner: str, name: str) -> None:
        try:
            parse_uri(f"device/{owner}/{name}")
        except QvUriError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/v1/devices/{owner}/{name}", status_code=201)
    def register_device(owner: str, name: str, body: DeviceRegistration) -> dict:
        _check_device_ref(owner, name)
        errors = schema_errors("device-record", body.record)
        if errors:
            raise HTTPException(
                422, {"detail": "device record is invalid", "errors": errors}
            )
        try:
            return store.register_device(owner, name, body.record)
        except Conflict as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.get("/api/v1/devices")
    def list_devices() -> dict:
        return {"devices": store.list_devices()}

    @app.get("/api/v1/devices/{owner}/{name}")
    def get_device(owner: str, name: str) -> dict:
        try:
            return store.get_device(owner, name)
        except NotFound as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.post("/api/v1/devices/{owner}/{name}/calibrations", status_code=201)
    def add_calibration(owner: str, name: str, body: dict) -> dict:
        errors = schema_errors("device", body)
        if errors:
            raise HTTPException(
                422, {"detail": "calibration snapshot is invalid device.json", "errors": errors}
            )
        from quantumverse.canonical import canonical_bytes

        try:
            return store.add_calibration(owner, name, body, canonical_bytes(body))
        except NotFound as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.get("/api/v1/devices/{owner}/{name}/calibrations")
    def device_calibrations(
        owner: str, name: str, limit: int = Query(default=100, ge=1, le=1000)
    ) -> dict:
        try:
            return {"calibrations": store.device_calibrations(owner, name, limit=limit)}
        except NotFound as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.get("/api/v1/devices/{owner}/{name}/capsules")
    def device_capsules(owner: str, name: str) -> dict:
        try:
            return {"capsules": store.device_capsules(owner, name)}
        except NotFound as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.post("/api/v1/devices/{owner}/{name}/certificate", status_code=201)
    def submit_certificate(owner: str, name: str, body: CertificateSubmission) -> dict:
        from quantumverse.certify import CertifyError

        try:
            return store.submit_certificate(owner, name, body.capsules)
        except NotFound as exc:
            raise HTTPException(404, str(exc)) from exc
        except (CertifyError, Conflict) as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get("/api/v1/devices/{owner}/{name}/certificate")
    def get_certificate(owner: str, name: str) -> dict:
        try:
            return store.get_certificate(owner, name)
        except NotFound as exc:
            raise HTTPException(404, str(exc)) from exc

    # -- search ------------------------------------------------------------------

    @app.get("/api/v1/search")
    def search(q: str = Query(default=""), type: Optional[str] = Query(default=None)) -> dict:
        query = q.lower()
        results = []
        for record in store.list_artifacts(type=type):
            haystack = [f"{record['namespace']}/{record['name']}", record["type"]]
            for card in record["cards"].values():
                haystack.append(str(card.get("name", "")))
                haystack.append(str(card.get("summary", "")))
                haystack.extend(str(t) for t in card.get("tags") or [])
            if query and not any(query in h.lower() for h in haystack):
                continue
            try:
                latest = resolve_version("latest", record["versions"])
            except VersionError:
                latest = None
            latest_card = record["cards"].get(latest, {}) if latest else {}
            results.append(
                {
                    "namespace": record["namespace"],
                    "name": record["name"],
                    "type": record["type"],
                    "latest": latest,
                    "summary": latest_card.get("summary", ""),
                    "tags": latest_card.get("tags", []),
                }
            )
        return {"results": results}

    # -- static playground (optional) ----------------------------------------------

    web_dir = web_dir or os.environ.get("QV_WEB_DIR")
    if web_dir and Path(web_dir).is_dir():
        from fastapi.staticfiles import StaticFiles

        app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")

    return app
