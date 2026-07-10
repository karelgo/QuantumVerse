"""Agent-native access (FRONTIERS.md §2): the QuantumVerse MCP server.

Exposes the platform's verbs — *search, load, run, verify, inspect* — as
Model Context Protocol tools, so AI assistants are first-class users pulling
**checked** artifacts instead of hallucinating circuits from memory.

Run against any registry:

    pip install "quantumverse[mcp]"
    QV_REGISTRY_URL=http://127.0.0.1:8000 qv-mcp

Every tool routes through the same client code paths a human uses: loads are
digest-verified, capsule validation is the real RFC-0001 validator, diffs are
exact unitary equivalence, and scores/certificates come from the registry's
own recomputation.
"""

from __future__ import annotations

import json
from typing import Optional

from .capsule import Capsule
from .hub import load
from .qasm import parse_qasm
from .registry import get_registry
from .signing import trust_level
from .simulator import run as simulate
from .verify import replay_l1, semantic_diff

__all__ = ["create_server", "main"]

# Handlers are plain functions returning JSON-serializable dicts, so they are
# testable without an MCP transport; create_server() only does the wiring.


def search_artifacts(query: str, type: Optional[str] = None) -> dict:
    """Search the registry for artifacts by name, summary, or tag."""
    results = get_registry().search(query, type=type)
    return {"results": results}


def load_artifact(ref: str) -> dict:
    """Resolve a qv: reference and fetch its files (digest-verified)."""
    artifact = load(ref)
    files = {}
    for name, data in artifact.files.items():
        try:
            files[name] = data.decode("utf-8")
        except UnicodeDecodeError:
            files[name] = f"<binary, {len(data)} bytes>"
    return {"ref": artifact.ref, "meta": artifact.meta, "files": files}


def run_circuit(
    qasm: str,
    shots: Optional[int] = 1024,
    seed: Optional[int] = None,
    params: Optional[dict] = None,
) -> dict:
    """Simulate an OpenQASM 3 circuit (shared subset, <= 24 qubits)."""
    bindings = {k: float(v) for k, v in (params or {}).items()}
    result = simulate(parse_qasm(qasm), shots=shots, seed=seed, param_bindings=bindings)
    out = {
        "num_qubits": result.num_qubits,
        "probabilities": {k: round(v, 10) for k, v in sorted(result.probabilities.items())},
    }
    if result.counts is not None:
        out["counts"] = dict(sorted(result.counts.items()))
        out["shots"] = result.shots
    return out


def diff_circuits(qasm_a: str, qasm_b: str, params: Optional[dict] = None) -> dict:
    """Semantic circuit diff: resource deltas + equivalence up to global phase."""
    bindings = {k: float(v) for k, v in (params or {}).items()}
    report = semantic_diff(qasm_a, qasm_b, param_bindings=bindings)
    return {
        "equivalent": report.equivalent,
        "reason": report.reason,
        "max_deviation": report.max_deviation,
        "resources_a": report.resources_a,
        "resources_b": report.resources_b,
        "deltas": report.deltas,
    }


def _capsule_from_registry(capsule_ref: str) -> Capsule:
    hexid = capsule_ref.split(":", 1)[1] if capsule_ref.startswith("sha256:") else capsule_ref
    hexid = hexid.removeprefix("capsule/")
    registry = get_registry()
    record = registry.get_capsule(hexid)
    files = {name: registry.get_blob(digest) for name, digest in record["files"].items()}
    return Capsule(files)


def verify_capsule(capsule: str) -> dict:
    """Fetch a capsule and run the full RFC-0001 validation + trust check."""
    cap = _capsule_from_registry(capsule)
    findings = cap.validate()
    level, trust_detail = trust_level(cap.files, cap.id)
    return {
        "id": cap.id,
        "valid": not any(f.severity == "error" for f in findings),
        "findings": [str(f) for f in findings],
        "trust": level,
        "trust_detail": trust_detail,
        "inspect": cap.inspect(),
    }


def replay_capsule(capsule: str, seed: Optional[int] = None) -> dict:
    """L1-replay a capsule: re-simulate its circuit and diff the distributions."""
    report = replay_l1(_capsule_from_registry(capsule), seed=seed)
    return {
        "original": report.original_id,
        "replay_capsule": report.replay.id,
        "tv_distance": report.tv_distance,
        "verdict": report.verdict,
    }


def device_card(ref: str) -> dict:
    """Device Card (RFC-0004): record, calibration history, birth certificate."""
    from .uris import parse_uri

    uri = parse_uri(ref)
    if uri.kind == "device":
        owner, name = uri.namespace, uri.name
    elif uri.kind == "artifact" and uri.version is None:
        owner, name = uri.namespace, uri.name
    else:
        raise ValueError(f"{ref!r} is not a device reference")
    registry = get_registry()
    card = registry.get_device(owner, name)
    card["drift"] = registry.device_calibrations(owner, name, limit=20)
    return card


def leaderboard(name: Optional[str] = None) -> dict:
    """Ranked, registry-recomputed leaderboard entries (RFC-0006)."""
    registry = get_registry()
    if name is None:
        return {"leaderboards": registry.list_boards()}
    return registry.get_board(name)


_TOOLS = [
    search_artifacts,
    load_artifact,
    run_circuit,
    diff_circuits,
    verify_capsule,
    replay_capsule,
    device_card,
    leaderboard,
]


def create_server():
    """Build the FastMCP server (requires the [mcp] extra)."""
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "the MCP server needs the mcp SDK: pip install 'quantumverse[mcp]'"
        ) from exc

    server = FastMCP(
        "quantumverse",
        instructions=(
            "QuantumVerse: verified quantum artifacts. Loads are digest-verified; "
            "capsule validation is RFC-0001; scores and certificates are recomputed "
            "by the registry, never self-reported. Registry selection follows "
            "QV_REGISTRY_URL (HTTP) or the local ~/.qv store."
        ),
    )
    for tool in _TOOLS:
        server.add_tool(tool)
    return server


def main() -> int:  # pragma: no cover - transport loop
    create_server().run()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
