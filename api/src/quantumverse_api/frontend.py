"""The Next.js frontend's Hub-API seam (web/lib/api.ts), served by qv-registry.

The product frontend in ``web/`` reads through five routes when ``QV_API_URL``
is set, expecting the TypeScript shapes in ``web/lib/types.ts``. This router
serves exactly those shapes from the live registry store, mounted at
``/api/hub`` — point the frontend at it with:

    QV_API_URL=http://127.0.0.1:8000/api/hub npm run dev   # in web/

Same trust rules as everywhere else: resources are recomputed from the QASM
bytes, capsule integrity (digests, id, Ed25519 signature) is verified
server-side, and trust levels come from the signature files, not from claims.
"""

from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from quantumverse.canonical import digest_bytes, digest_json
from quantumverse.qasm import parse_qasm
from quantumverse.resources import count_resources
from quantumverse.signing import check_signature, trust_level
from quantumverse.uris import VersionError, resolve_version

from .store import NotFound, Store, StoreError

_EMPTY_RESOURCES = {
    "qubits": 0, "clbits": 0, "depth": 0, "gateCount": 0,
    "twoQubitCount": 0, "tCount": 0, "gates": {},
}

# Placeholder shown on detail pages of artifacts that have no circuit payload
# (problem instances): parses as an empty 1-qubit circuit so the frontend's
# viewer renders instead of erroring.
_NO_CIRCUIT_QASM = (
    "// this artifact has no circuit payload — see its JSON payload instead\n"
    "OPENQASM 3.0;\nqubit[1] q;\n"
)


def _frontend_resources(qasm_text: Optional[str]) -> dict:
    if not qasm_text:
        return dict(_EMPTY_RESOURCES)
    try:
        circuit = parse_qasm(qasm_text)
    except Exception:
        return dict(_EMPTY_RESOURCES)
    r = count_resources(circuit)
    return {
        "qubits": r["num_qubits"],
        "clbits": circuit.num_clbits,
        "depth": r["depth"],
        "gateCount": sum(r["gate_counts"].values()),
        "twoQubitCount": r["two_qubit_gate_count"],
        "tCount": r["t_count"],
        "gates": r["gate_counts"],
    }


def _short(capsule_id: str) -> str:
    return capsule_id.split(":", 1)[1][:6] if capsule_id.startswith("sha256:") else capsule_id[:6]


def _signer_handle(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    return value.removeprefix("qv:").removeprefix("users/")


def create_frontend_router(store: Store) -> APIRouter:
    router = APIRouter(prefix="/api/hub/v1")

    # -- shared loaders ---------------------------------------------------------

    def _capsule_files(hexid: str) -> tuple[dict, dict[str, bytes]]:
        record = store.get_capsule(hexid)
        files = {
            name: store.get_blob(digest) for name, digest in record["files"].items()
        }
        return record, files

    def _capsule_detail(hexid: str) -> dict:
        record, files = _capsule_files(hexid)

        def _json_file(name: str, default):
            raw = files.get(name)
            if raw is None:
                return default
            try:
                return json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                return default

        manifest = _json_file("manifest.json", {})
        device = _json_file("device.json", {})
        execution = _json_file("execution.json", {})
        mitigation = _json_file("mitigation.json", None)
        qasm = files.get("circuit.qasm", b"").decode("utf-8", errors="replace")

        # integrity: recompute everything, trust nothing (matches web/lib/registry.ts)
        capsule_id = manifest.get("id", "")
        hashable = dict(manifest)
        hashable["id"] = ""
        try:
            id_verified = bool(capsule_id) and digest_json(hashable) == capsule_id
        except Exception:
            id_verified = False
        integrity_files = []
        for name, claimed in sorted((manifest.get("files") or {}).items()):
            raw = files.get(name)
            if raw is None:
                integrity_files.append({"name": name, "digest": claimed, "verified": False})
                continue
            if name.endswith(".json"):
                try:
                    actual = digest_json(json.loads(raw.decode("utf-8")))
                except Exception:
                    actual = None
            else:
                actual = digest_bytes(raw)
            integrity_files.append(
                {"name": name, "digest": claimed, "verified": actual == claimed}
            )
        signature_valid = None
        signer = None
        raw_sig = files.get("author.sig")
        if raw_sig is not None:
            try:
                sig_doc = json.loads(raw_sig.decode("utf-8"))
                signature_valid = check_signature(sig_doc, capsule_id) is None
                signer = _signer_handle(sig_doc.get("signer"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                signature_valid = False

        level, _detail = trust_level(files, capsule_id)
        backend = device.get("backend") or {}
        sim = device.get("simulator")
        return {
            "id": capsule_id or record["id"],
            "shortId": _short(capsule_id or record["id"]),
            "title": manifest.get("title", ""),
            "created": manifest.get("created", record.get("created", "")),
            "trustLevel": level,
            "backend": (
                f"{sim.get('engine', '?')} ({sim.get('method', '?')})"
                if isinstance(sim, dict)
                else f"{backend.get('provider', '?')}/{backend.get('name', '?')}"
            ),
            "shots": execution.get("shots", 0),
            "manifest": {
                "capsule_version": manifest.get("capsule_version", "0.1"),
                "id": capsule_id,
                "created": manifest.get("created", ""),
                "title": manifest.get("title", ""),
                "authors": manifest.get("authors", []),
                "license": manifest.get("license", ""),
                "artifacts": manifest.get("artifacts", {}) or {},
                "files": manifest.get("files", {}) or {},
                "replay_of": manifest.get("replay_of"),
                "doi": manifest.get("doi"),
            },
            "device": {
                "backend": {
                    "provider": backend.get("provider", "?"),
                    "name": backend.get("name", "?"),
                    "version": backend.get("version", ""),
                },
                "captured": device.get("captured", ""),
                "topology": device.get("topology"),
                "simulator": (
                    {
                        "engine": sim.get("engine", "?"),
                        "method": sim.get("method", "?"),
                        "noise_model": sim.get("noise_model"),
                    }
                    if isinstance(sim, dict)
                    else None
                ),
            },
            "execution": {
                "job_ids": execution.get("job_ids", []),
                "submitted": execution.get("submitted", ""),
                "completed": execution.get("completed", ""),
                "shots": execution.get("shots", 0),
                "counts_raw": execution.get("counts_raw", {}),
                **(
                    {"counts_mitigated": execution["counts_mitigated"]}
                    if "counts_mitigated" in execution
                    else {}
                ),
                **(
                    {"parameters": execution["parameters"]}
                    if "parameters" in execution
                    else {}
                ),
            },
            "mitigation": mitigation,
            "qasm": qasm,
            "integrity": {
                "idVerified": id_verified,
                "files": integrity_files,
                "signatureValid": signature_valid,
                "signer": signer,
            },
        }

    def _capsules_by_artifact() -> dict[str, list[dict]]:
        """Map 'owner/name' -> capsule summaries, via manifest.artifacts back-refs."""
        by_ref: dict[str, list[dict]] = {}
        for entry in store.list_capsules():
            hexid = entry["id"].split(":", 1)[1]
            try:
                detail = _capsule_detail(hexid)
            except StoreError:
                continue
            summary = {
                k: detail[k]
                for k in ("id", "shortId", "title", "created", "trustLevel", "backend", "shots")
            }
            for uri in (detail["manifest"].get("artifacts") or {}).values():
                ref = str(uri).removeprefix("qv:").split("@")[0]
                by_ref.setdefault(ref, []).append(summary)
        return by_ref

    def _ansatz_qasm(params_doc: dict) -> Optional[str]:
        """For parameters artifacts: fetch the referenced ansatz's circuit."""
        ref = str(params_doc.get("ansatz") or "").removeprefix("qv:").split("@")[0]
        if "/" not in ref:
            return None
        ns, ansatz_name = ref.split("/", 1)
        try:
            record = store.get_artifact(ns, ansatz_name)
            version = resolve_version("latest", record["versions"])
            resolved = store.get_version(ns, ansatz_name, version)
            digest = resolved["files"].get("circuit.qasm")
            return store.get_blob(digest).decode("utf-8") if digest else None
        except (StoreError, VersionError):
            return None

    def _summary(artifact: dict, capsule_map: dict[str, list[dict]]) -> dict:
        ns, name = artifact["namespace"], artifact["name"]
        try:
            latest = resolve_version("latest", artifact["versions"])
        except VersionError:
            latest = artifact["versions"][-1] if artifact["versions"] else "0.0.0"
        resolved = store.get_version(ns, name, latest)
        card = resolved.get("card") or {}
        files = resolved["files"]

        qasm_text = None
        if "circuit.qasm" in files:
            qasm_text = store.get_blob(files["circuit.qasm"]).decode("utf-8", errors="replace")
        elif artifact["type"] == "parameters" and "params.json" in files:
            try:
                params_doc = json.loads(store.get_blob(files["params.json"]).decode("utf-8"))
                qasm_text = _ansatz_qasm(params_doc)
            except (StoreError, json.JSONDecodeError, UnicodeDecodeError):
                qasm_text = None

        linked = capsule_map.get(f"{ns}/{name}", [])
        provenance = card.get("provenance") or {}
        return {
            "owner": ns,
            "name": name,
            "kind": artifact["type"],
            "version": latest,
            "description": card.get("summary") or card.get("description") or "",
            "license": provenance.get("license", ""),
            "tags": card.get("tags") or [],
            "created": resolved.get("created", ""),
            "resources": _frontend_resources(qasm_text),
            "capsuleCount": len(linked),
            "maxTrustLevel": max((c["trustLevel"] for c in linked), default=None),
            "_qasm": qasm_text,  # stripped before returning summaries
            "_files": files,
        }

    def _public(summary: dict) -> dict:
        return {k: v for k, v in summary.items() if not k.startswith("_")}

    # -- routes -----------------------------------------------------------------

    @router.get("/artifacts")
    def list_artifacts(q: Optional[str] = Query(default=None)) -> list[dict]:
        capsule_map = _capsules_by_artifact()
        out = [_public(_summary(a, capsule_map)) for a in store.list_artifacts()]
        if q:
            needle = q.lower()
            out = [
                a for a in out
                if any(
                    needle in str(v).lower()
                    for v in (a["name"], a["owner"], a["description"], a["kind"], *a["tags"])
                )
            ]
        return out

    @router.get("/artifacts/{owner}/{name}")
    def get_artifact(owner: str, name: str) -> dict:
        # the frontend may pass name@version from its URL scheme
        version = None
        if "@" in name:
            name, version = name.split("@", 1)
        try:
            record = store.get_artifact(owner, name)
        except NotFound as exc:
            raise HTTPException(404, str(exc)) from exc
        capsule_map = _capsules_by_artifact()
        artifact = {
            "namespace": owner, "name": name,
            "type": record["type"], "versions": record["versions"],
        }
        if version is not None:
            if version not in record["versions"]:
                raise HTTPException(404, f"{owner}/{name}@{version} not found")
            artifact["versions"] = [version]
        summary = _summary(artifact, capsule_map)

        parameters = None
        files = summary["_files"]
        if "params.json" in files:
            try:
                doc = json.loads(store.get_blob(files["params.json"]).decode("utf-8"))
                raw_params = doc.get("parameters")
                if isinstance(raw_params, dict):
                    objective = doc.get("objective") or {}
                    parameters = {
                        "names": list(raw_params.keys()),
                        "values": [float(v) for v in raw_params.values()],
                        "observable": str(doc.get("instance") or "") or None,
                        "energy": (
                            objective.get("value")
                            if objective.get("name") == "energy"
                            else None
                        ),
                        "units": objective.get("units"),
                        "optimizer": doc.get("method"),
                    }
                elif isinstance(doc.get("names"), list):  # already frontend-shaped
                    parameters = doc
            except (StoreError, json.JSONDecodeError, UnicodeDecodeError, ValueError):
                parameters = None

        return {
            **_public(summary),
            "qasm": summary["_qasm"] or _NO_CIRCUIT_QASM,
            "parameters": parameters,
            "capsules": capsule_map.get(f"{owner}/{name}", []),
        }

    @router.get("/owners/{handle}")
    def get_owner(handle: str) -> dict:
        namespaces = {a["namespace"] for a in store.list_artifacts()}
        namespaces |= {d["namespace"] for d in store.list_devices()}
        if handle not in namespaces:
            raise HTTPException(404, f"owner {handle!r} not found")
        return {
            "handle": handle,
            "display": handle,
            "kind": "org",
            "bio": f"Artifacts published under the {handle!r} namespace on this registry.",
        }

    @router.get("/capsules/{capsule_id}")
    def get_capsule(capsule_id: str) -> dict:
        hexid = capsule_id.split(":", 1)[1] if capsule_id.startswith("sha256:") else capsule_id
        try:
            return _capsule_detail(hexid)
        except NotFound as exc:
            raise HTTPException(404, str(exc)) from exc
        except StoreError as exc:
            raise HTTPException(404, str(exc)) from exc

    return router
