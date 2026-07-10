"""Verification: semantic circuit equivalence, resource budgets, capsule replay.

The Phase-2 slice of the Verification Layer (VISION.md Pillar II), on top of
the built-in statevector simulator:

- :func:`circuit_unitary` — the full unitary of a circuit (small circuits).
- :func:`semantic_diff` — equivalence up to global phase + resource deltas.
- :func:`check_budgets` — resource-regression checks for Quantum CI.
- :func:`replay_l1` — RFC-0001 L1 replay: re-simulate a capsule's abstract
  circuit and diff the outcome distributions.
"""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from .capsule import Capsule, CapsuleError
from .qasm import Circuit, parse_qasm
from .resources import count_resources
from .simulator import SimulatorError, _apply, _gate_matrix, _resolve_params, run

__all__ = [
    "VerifyError",
    "DiffReport",
    "BudgetViolation",
    "ReplayReport",
    "MAX_DIFF_QUBITS",
    "circuit_unitary",
    "semantic_diff",
    "check_budgets",
    "replay_l1",
    "total_variation",
]

MAX_DIFF_QUBITS = 10
_ATOL = 1e-9

# Verdict bands for replay distribution distance (total variation).
REPLAY_CONSISTENT = 0.05
REPLAY_DEGRADED = 0.15


class VerifyError(ValueError):
    """Raised when a verification cannot be carried out at all."""


def _strip_measurements(circuit: Circuit) -> tuple[Circuit, dict[int, int]]:
    """Return a measurement-free copy plus the clbit -> qubit map."""
    ops = []
    meas_map: dict[int, int] = {}
    for op in circuit.ops:
        if op.name == "measure":
            meas_map[op.clbits[0]] = op.qubits[0]
        elif op.name == "barrier":
            continue
        else:
            if meas_map:
                raise VerifyError(
                    f"gate '{op.name}' after measurement: equivalence checking "
                    "requires terminal measurements only"
                )
            ops.append(op)
    return dataclasses.replace(circuit, ops=ops), meas_map


def circuit_unitary(
    circuit: Circuit,
    param_bindings: Optional[dict[str, float]] = None,
    max_qubits: int = MAX_DIFF_QUBITS,
) -> np.ndarray:
    """Compute the circuit's full unitary (measurements stripped).

    Columns are the images of computational basis states; basis order is
    little-endian to match the simulator.
    """
    stripped, _ = _strip_measurements(circuit)
    n = stripped.num_qubits
    if n > max_qubits:
        raise VerifyError(
            f"circuit has {n} qubits; unitary extraction caps at {max_qubits}"
        )
    bindings = dict(param_bindings or {})
    missing = sorted(stripped.used_params - set(bindings))
    if missing:
        raise VerifyError(
            "circuit has unbound parameters: " + ", ".join(missing)
            + " (pass param bindings)"
        )
    dim = 2**n
    unitary = np.zeros((dim, dim), dtype=np.complex128)
    mats = [
        (_gate_matrix(op.name, _resolve_params(op, bindings)), op.qubits)
        for op in stripped.ops
    ]
    for col in range(dim):
        state = np.zeros(dim, dtype=np.complex128)
        state[col] = 1.0
        for mat, qubits in mats:
            state = _apply(state, n, mat, qubits)
        unitary[:, col] = state
    return unitary


@dataclass
class DiffReport:
    """Outcome of a semantic diff between two circuits."""

    equivalent: Optional[bool]  # None => could not be checked
    reason: str
    max_deviation: Optional[float]
    resources_a: dict
    resources_b: dict
    deltas: dict = field(default_factory=dict)

    def summary(self) -> str:
        lines = []
        for key in ("num_qubits", "depth", "two_qubit_gate_count", "t_count"):
            a = self.resources_a.get(key)
            b = self.resources_b.get(key)
            delta = self.deltas.get(key, 0)
            arrow = f"{a} -> {b}" + (f"  ({delta:+d})" if delta else "  (unchanged)")
            lines.append(f"  {key:<22} {arrow}")
        if self.equivalent is True:
            verdict = "circuits are EQUIVALENT up to global phase"
        elif self.equivalent is False:
            verdict = "circuits are NOT equivalent"
        else:
            verdict = "equivalence not checked"
        lines.append(f"  verdict: {verdict} — {self.reason}")
        return "\n".join(lines)


def semantic_diff(
    qasm_a: str,
    qasm_b: str,
    param_bindings: Optional[dict[str, float]] = None,
) -> DiffReport:
    """Compare two circuits: resource deltas plus unitary equivalence.

    Equivalence is checked up to global phase by exact unitary comparison,
    for circuits of up to :data:`MAX_DIFF_QUBITS` qubits with all parameters
    bound. Larger or unbindable circuits report ``equivalent=None``.
    """
    circ_a = parse_qasm(qasm_a)
    circ_b = parse_qasm(qasm_b)
    res_a = count_resources(circ_a)
    res_b = count_resources(circ_b)
    deltas = {
        key: res_b[key] - res_a[key]
        for key in ("num_qubits", "depth", "two_qubit_gate_count", "t_count")
    }

    if circ_a.num_qubits != circ_b.num_qubits:
        return DiffReport(
            equivalent=False,
            reason=f"qubit counts differ ({circ_a.num_qubits} vs {circ_b.num_qubits})",
            max_deviation=None,
            resources_a=res_a,
            resources_b=res_b,
            deltas=deltas,
        )

    try:
        u_a = circuit_unitary(circ_a, param_bindings)
        u_b = circuit_unitary(circ_b, param_bindings)
    except (VerifyError, SimulatorError) as exc:
        return DiffReport(
            equivalent=None,
            reason=str(exc),
            max_deviation=None,
            resources_a=res_a,
            resources_b=res_b,
            deltas=deltas,
        )

    # Align global phase on the largest-magnitude entry of U_a.
    idx = np.unravel_index(np.argmax(np.abs(u_a)), u_a.shape)
    ref = u_a[idx]
    other = u_b[idx]
    if abs(other) < _ATOL:
        equivalent, deviation = False, float(np.max(np.abs(u_b - u_a)))
    else:
        phase = other / ref
        phase /= abs(phase)
        deviation = float(np.max(np.abs(u_a * phase - u_b)))
        equivalent = deviation <= 1e-8
    return DiffReport(
        equivalent=equivalent,
        reason=(
            f"max elementwise deviation {deviation:.2e} after global-phase alignment"
        ),
        max_deviation=deviation,
        resources_a=res_a,
        resources_b=res_b,
        deltas=deltas,
    )


@dataclass
class BudgetViolation:
    metric: str
    budget: int
    actual: int

    def __str__(self) -> str:
        return f"{self.metric}: {self.actual} exceeds budget {self.budget}"


_BUDGET_METRICS = ("num_qubits", "depth", "gate_count", "two_qubit_gate_count", "t_count")


def check_budgets(circuit: Circuit, budgets: dict) -> list[BudgetViolation]:
    """Check resource budgets; returns violations (empty list == pass)."""
    res = count_resources(circuit)
    res["gate_count"] = sum(res.get("gate_counts", {}).values())
    violations = []
    for metric, budget in budgets.items():
        if metric not in _BUDGET_METRICS:
            raise VerifyError(
                f"unknown budget metric {metric!r}; expected one of {', '.join(_BUDGET_METRICS)}"
            )
        if not isinstance(budget, int) or budget < 0:
            raise VerifyError(f"budget for {metric!r} must be a non-negative integer")
        actual = res.get(metric, 0)
        if actual > budget:
            violations.append(BudgetViolation(metric=metric, budget=budget, actual=actual))
    return violations


def total_variation(p: dict[str, float], q: dict[str, float]) -> float:
    """Total variation distance between two distributions over bitstrings."""

    def _normalize(d: dict[str, float]) -> dict[str, float]:
        total = float(sum(d.values()))
        if total <= 0:
            raise VerifyError("cannot normalize an empty or zero distribution")
        return {k: v / total for k, v in d.items()}

    pn, qn = _normalize(p), _normalize(q)
    keys = set(pn) | set(qn)
    return 0.5 * sum(abs(pn.get(k, 0.0) - qn.get(k, 0.0)) for k in keys)


@dataclass
class ReplayReport:
    """Outcome of an L1 capsule replay."""

    original_id: str
    replay: Capsule
    tv_distance: float
    verdict: str  # consistent | degraded | not-reproduced

    def summary(self) -> str:
        return (
            f"replayed capsule/{self.original_id.split(':', 1)[1][:6]} at L1 (simulate)\n"
            f"  new capsule: capsule/{self.replay.short_id}\n"
            f"  total variation vs original counts: {self.tv_distance:.4f}\n"
            f"  verdict: {self.verdict}"
        )


def replay_l1(capsule: Capsule, seed: Optional[int] = None) -> ReplayReport:
    """RFC-0001 L1 replay: re-simulate ``circuit.qasm`` and diff distributions.

    The replay is noiseless in v0 (the noise model derived from device.json
    is future work), so hardware capsules with strong noise will legitimately
    land in ``degraded``; the verdict bands make that visible rather than
    hiding it.
    """
    manifest = capsule.manifest
    original_id = manifest.get("id", "")
    circuit_raw = capsule.files.get("circuit.qasm")
    if circuit_raw is None:
        raise VerifyError("capsule has no circuit.qasm to replay")
    execution = capsule._try_json("execution.json")
    if execution is None:
        raise VerifyError("capsule has no readable execution.json")

    circuit = parse_qasm(circuit_raw.decode("utf-8"))

    bindings: dict[str, float] = {}
    for name, value in (execution.get("parameters") or {}).items():
        if isinstance(value, (int, float)):
            bindings[name] = float(value)
        else:
            raise VerifyError(
                f"parameter {name!r} is an array; L1 replay v0 supports scalar "
                "parameter bindings only (bind array entries to scalar names)"
            )

    shots = int(execution.get("shots", 1024))
    result = run(circuit, shots=shots, seed=seed, param_bindings=bindings)

    counts_raw = execution.get("counts_raw", {})
    tv = total_variation(
        {k: float(v) for k, v in counts_raw.items()},
        {k: float(v) for k, v in (result.counts or {}).items()},
    )
    if tv <= REPLAY_CONSISTENT:
        verdict = "consistent"
    elif tv <= REPLAY_DEGRADED:
        verdict = "degraded"
    else:
        verdict = "not-reproduced"

    device = {
        "backend": {"provider": "quantumverse", "name": "qv-sim", "version": "0.1.0"},
        "captured": _now(),
        "topology": {"num_qubits": circuit.num_qubits},
        "qubits": [],
        "gates": [],
        "simulator": {
            "engine": "quantumverse.simulator",
            "method": "statevector",
            **({"seed": seed} if seed is not None else {}),
        },
    }
    new_execution = {
        "job_ids": [],
        "shots": shots,
        "counts_raw": dict(sorted((result.counts or {}).items())),
    }
    if bindings:
        new_execution["parameters"] = bindings

    replay = Capsule.create(
        circuit_qasm=circuit_raw.decode("utf-8"),
        device=device,
        execution=new_execution,
        title=f"L1 replay of {manifest.get('title', original_id)}",
        authors=[a if isinstance(a, dict) else {"name": str(a)} for a in manifest.get("authors", [{"name": "unknown"}])],
        license=manifest.get("license", "CC-BY-4.0"),
        replay_of=original_id or None,
        replay_level="L1",
    )
    return ReplayReport(original_id=original_id, replay=replay, tv_distance=tv, verdict=verdict)


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Quantum CI config runner
# ---------------------------------------------------------------------------


def run_ci_config(config: dict, base_dir=".") -> list[str]:
    """Run a ``quantumverse.ci.json`` config; returns failure messages.

    Config shape:
        {"checks": [{
            "circuit": "path.qasm",
            "budgets": {"depth": 30, "t_count": 14, ...},         # optional
            "reference": "golden.qasm",                            # optional
            "params": {"theta": 0.5},                              # optional
            "expect": {"probabilities": {"00": 0.5}, "tolerance": 0.02}  # optional
        }, ...]}
    """
    from pathlib import Path

    base = Path(base_dir)
    checks = config.get("checks")
    if not isinstance(checks, list) or not checks:
        raise VerifyError("CI config needs a non-empty 'checks' array")

    failures: list[str] = []
    for i, check in enumerate(checks):
        label = check.get("circuit", f"check[{i}]")
        try:
            qasm_text = (base / check["circuit"]).read_text(encoding="utf-8")
            circuit = parse_qasm(qasm_text)
            params = {k: float(v) for k, v in (check.get("params") or {}).items()}

            for violation in check_budgets(circuit, check.get("budgets") or {}):
                failures.append(f"{label}: budget violation — {violation}")

            if check.get("reference"):
                ref_text = (base / check["reference"]).read_text(encoding="utf-8")
                report = semantic_diff(ref_text, qasm_text, param_bindings=params)
                if report.equivalent is False:
                    failures.append(
                        f"{label}: NOT equivalent to reference {check['reference']} "
                        f"({report.reason})"
                    )
                elif report.equivalent is None:
                    failures.append(
                        f"{label}: equivalence vs {check['reference']} could not be "
                        f"checked ({report.reason})"
                    )

            expect = check.get("expect")
            if expect:
                result = run(circuit, param_bindings=params)
                tolerance = float(expect.get("tolerance", 0.02))
                for bitstring, expected in (expect.get("probabilities") or {}).items():
                    actual = result.probabilities.get(bitstring, 0.0)
                    if abs(actual - float(expected)) > tolerance:
                        failures.append(
                            f"{label}: P({bitstring}) = {actual:.4f}, expected "
                            f"{float(expected):.4f} ± {tolerance}"
                        )
        except (OSError, KeyError, ValueError) as exc:
            failures.append(f"{label}: check could not run — {exc}")
    return failures


def load_ci_config(path) -> dict:
    from pathlib import Path

    text = Path(path).read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise VerifyError(f"{path} is not valid JSON: {exc}") from exc
