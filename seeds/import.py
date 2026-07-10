#!/usr/bin/env python3
"""Seed a QuantumVerse registry with the starter library.

    python seeds/import.py                       # local registry (~/.qv or QV_HOME)
    python seeds/import.py --registry http://127.0.0.1:8000
    python seeds/import.py --with-capsule        # also mint + push a demo capsule

Every circuit is parsed and simulated before it is pushed; the import is
idempotent (already-published versions are reported and skipped).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from quantumverse import push
from quantumverse.capsule import Capsule
from quantumverse.qasm import parse_qasm
from quantumverse.registry import RegistryError, get_registry
from quantumverse.simulator import run

SEEDS = Path(__file__).parent

CIRCUITS = [
    ("bell", "Bell pair — the hello world of entanglement", ["bell", "entanglement", "textbook"]),
    ("ghz-3", "3-qubit GHZ state", ["ghz", "entanglement", "textbook"]),
    ("ghz-5", "5-qubit GHZ state", ["ghz", "entanglement"]),
    ("qft-4", "4-qubit quantum Fourier transform", ["qft", "textbook"]),
    ("grover-2q", "Grover search, 2 qubits, marked state |11> — one iteration, certain success", ["grover", "search", "textbook"]),
    ("deutsch-jozsa-3", "Deutsch-Jozsa with a balanced oracle f(x) = x0", ["deutsch-jozsa", "oracle", "textbook"]),
    ("bernstein-vazirani-4", "Bernstein-Vazirani, secret string 101", ["bernstein-vazirani", "oracle", "textbook"]),
    ("vqe-h2-ansatz", "Minimal 2-qubit VQE ansatz for tapered H2/STO-3G", ["vqe", "ansatz", "chemistry"]),
    ("qaoa-maxcut-triangle", "QAOA p=1 for MaxCut on K3 (exact at p=1)", ["qaoa", "maxcut", "optimization"]),
]

INSTANCES = [
    ("h2-sto3g", "Tapered 2-qubit H2/STO-3G Hamiltonian at R = 0.735 A", ["hamiltonian", "chemistry"]),
    ("maxcut-triangle", "MaxCut on the triangle graph K3", ["maxcut", "graph", "optimization"]),
]

PARAMETERS = [
    ("vqe-h2-params", "Converged VQE parameters for qv:seeds/vqe-h2-ansatz (E = -1.85727502 Ha)", ["vqe", "trained-parameters", "chemistry"]),
    ("qaoa-maxcut-triangle-params", "Converged QAOA angles for qv:seeds/qaoa-maxcut-triangle (ratio 1.0)", ["qaoa", "trained-parameters", "optimization"]),
]

VERSION = "1.0.0"


def _push(path: Path, ref: str, type: str, summary: str, tags: list[str], registry) -> str:
    try:
        published = push(
            path, ref, type=type, version=VERSION, summary=summary, tags=tags,
            license="Apache-2.0", registry=registry,
        )
        return f"pushed  {published}"
    except RegistryError as exc:
        if "already published" in str(exc) or "409" in str(exc):
            return f"exists  {ref}@{VERSION}"
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", help="registry URL (default: QV_REGISTRY_URL or local ~/.qv)")
    parser.add_argument("--with-capsule", action="store_true",
                        help="also mint a deterministic Bell capsule and push it")
    args = parser.parse_args(argv)
    registry = get_registry(args.registry)

    # sanity: every seed circuit must parse (and non-parameterized ones must run)
    for name, _, _ in CIRCUITS:
        circuit = parse_qasm((SEEDS / "circuits" / f"{name}.qasm").read_text(encoding="utf-8"))
        if not circuit.used_params:
            run(circuit, shots=16, seed=0)

    for name, summary, tags in CIRCUITS:
        print(_push(SEEDS / "circuits" / f"{name}.qasm", f"qv:seeds/{name}",
                    "circuit", summary, tags, registry))
    for name, summary, tags in INSTANCES:
        print(_push(SEEDS / "instances" / f"{name}.json", f"qv:instances/{name}",
                    "instance", summary, tags, registry))
    for name, summary, tags in PARAMETERS:
        print(_push(SEEDS / "parameters" / f"{name}.json", f"qv:seeds/{name}",
                    "parameters", summary, tags, registry))

    if args.with_capsule:
        qasm_text = (SEEDS / "circuits" / "bell.qasm").read_text(encoding="utf-8")
        result = run(parse_qasm(qasm_text), shots=4096, seed=42)
        capsule = Capsule.create(
            circuit_qasm=qasm_text,
            device={
                "backend": {"provider": "quantumverse", "name": "qv-sim", "version": "0.1.0"},
                "captured": "2026-07-10T00:00:00Z",
                "topology": {"num_qubits": 2},
                "qubits": [],
                "gates": [],
                "simulator": {"engine": "quantumverse.simulator", "method": "statevector", "seed": 42},
            },
            execution={"job_ids": [], "shots": 4096, "counts_raw": result.counts},
            title="Bell pair on the qv reference simulator (seed 42)",
            authors=[{"name": "QuantumVerse seeds"}],
            license="Apache-2.0",
            artifacts={"circuit": f"qv:seeds/bell@{VERSION}"},
            environment_lock="deterministic seed import\n",
        )
        capsule_id = registry.push_capsule(capsule.files)
        print(f"capsule capsule/{capsule.short_id}  {capsule_id}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
