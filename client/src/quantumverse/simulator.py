"""Dense numpy statevector simulator for the shared OpenQASM 3 subset.

Bit order is little-endian, matching Qiskit: qubit 0 is the least
significant bit of the statevector index, and rendered bitstrings are
written qubit ``n-1 … 0`` left-to-right. Measurement ops populate the
classical register; only terminal measurements are supported in v0.
"""

from __future__ import annotations

import cmath
import math
from dataclasses import dataclass
from typing import Optional

import numpy as np

from .qasm import Circuit, Expr, Op

__all__ = ["SimulatorError", "Result", "run", "MAX_QUBITS", "STATEVECTOR_MAX_QUBITS"]

MAX_QUBITS = 24
STATEVECTOR_MAX_QUBITS = 12
_PRUNE_EPS = 1e-12


class SimulatorError(ValueError):
    """Raised for circuits the v0 simulator cannot run."""


@dataclass
class Result:
    """Simulation outcome.

    probabilities: bitstring -> probability, pruned below 1e-12. Keys are
      classical-register bitstrings when the circuit measures, otherwise
      full qubit-basis bitstrings.
    counts: bitstring -> shot count (present only when shots requested).
    statevector: final pre-measurement state (only when num_qubits <= 12).
    """

    probabilities: dict[str, float]
    counts: Optional[dict[str, int]]
    statevector: Optional[np.ndarray]
    num_qubits: int
    num_clbits: int
    shots: Optional[int] = None
    seed: Optional[int] = None


def _u_matrix(theta: float, phi: float, lam: float) -> np.ndarray:
    c, s = math.cos(theta / 2.0), math.sin(theta / 2.0)
    return np.array(
        [
            [c, -cmath.exp(1j * lam) * s],
            [cmath.exp(1j * phi) * s, cmath.exp(1j * (phi + lam)) * c],
        ],
        dtype=np.complex128,
    )


_SQ2 = 1.0 / math.sqrt(2.0)

_FIXED_1Q = {
    "x": np.array([[0, 1], [1, 0]], dtype=np.complex128),
    "y": np.array([[0, -1j], [1j, 0]], dtype=np.complex128),
    "z": np.array([[1, 0], [0, -1]], dtype=np.complex128),
    "h": np.array([[_SQ2, _SQ2], [_SQ2, -_SQ2]], dtype=np.complex128),
    "s": np.array([[1, 0], [0, 1j]], dtype=np.complex128),
    "sdg": np.array([[1, 0], [0, -1j]], dtype=np.complex128),
    "t": np.array([[1, 0], [0, cmath.exp(1j * math.pi / 4)]], dtype=np.complex128),
    "tdg": np.array([[1, 0], [0, cmath.exp(-1j * math.pi / 4)]], dtype=np.complex128),
    "sx": 0.5 * np.array([[1 + 1j, 1 - 1j], [1 - 1j, 1 + 1j]], dtype=np.complex128),
}


def _param_1q(name: str, params: list[float]) -> np.ndarray:
    if name == "rx":
        (theta,) = params
        c, s = math.cos(theta / 2), math.sin(theta / 2)
        return np.array([[c, -1j * s], [-1j * s, c]], dtype=np.complex128)
    if name == "ry":
        (theta,) = params
        c, s = math.cos(theta / 2), math.sin(theta / 2)
        return np.array([[c, -s], [s, c]], dtype=np.complex128)
    if name == "rz":
        (theta,) = params
        return np.array(
            [[cmath.exp(-1j * theta / 2), 0], [0, cmath.exp(1j * theta / 2)]],
            dtype=np.complex128,
        )
    if name == "p":
        (lam,) = params
        return np.array([[1, 0], [0, cmath.exp(1j * lam)]], dtype=np.complex128)
    if name == "u":
        theta, phi, lam = params
        return _u_matrix(theta, phi, lam)
    raise AssertionError(name)  # pragma: no cover


def _controlled(u: np.ndarray) -> np.ndarray:
    """2-qubit controlled-U with operand 0 (control) as the most significant bit."""
    m = np.eye(4, dtype=np.complex128)
    m[2:, 2:] = u
    return m


_SWAP = np.array(
    [[1, 0, 0, 0], [0, 0, 1, 0], [0, 1, 0, 0], [0, 0, 0, 1]], dtype=np.complex128
)


def _gate_matrix(op_name: str, params: list[float]) -> np.ndarray:
    """Unitary for *op_name*, basis ordered with operand 0 as the MSB."""
    if op_name in _FIXED_1Q:
        return _FIXED_1Q[op_name]
    if op_name in ("rx", "ry", "rz", "p", "u"):
        return _param_1q(op_name, params)
    if op_name == "swap":
        return _SWAP
    if op_name.startswith("c") and op_name[1:] in _FIXED_1Q:  # cx cy cz ch
        return _controlled(_FIXED_1Q[op_name[1:]])
    if op_name == "cp":
        (lam,) = params
        m = np.eye(4, dtype=np.complex128)
        m[3, 3] = cmath.exp(1j * lam)
        return m
    if op_name in ("crx", "cry", "crz"):
        return _controlled(_param_1q(op_name[1:], params))
    if op_name == "ccx":
        m = np.eye(8, dtype=np.complex128)
        m[[6, 7], :] = m[[7, 6], :]
        return m
    if op_name == "cswap":
        m = np.eye(8, dtype=np.complex128)
        m[[5, 6], :] = m[[6, 5], :]
        return m
    raise SimulatorError(f"gate {op_name!r} is not supported by the simulator")


def _apply(state: np.ndarray, n: int, mat: np.ndarray, qubits: list[int]) -> np.ndarray:
    """Apply a k-qubit unitary (operand 0 = MSB of the matrix basis) to *state*."""
    k = len(qubits)
    # state.reshape([2]*n) puts qubit (n-1) on axis 0 … qubit 0 on axis n-1.
    axes = [n - 1 - q for q in qubits]
    t = np.moveaxis(state.reshape([2] * n), axes, range(k))
    t = mat @ t.reshape(2**k, -1)
    t = np.moveaxis(t.reshape([2] * k + [2] * (n - k)), range(k), axes)
    return np.ascontiguousarray(t).reshape(2**n)


def _resolve_params(op: Op, bindings: dict[str, float]) -> list[float]:
    resolved = []
    for p in op.params:
        if isinstance(p, Expr):
            try:
                resolved.append(float(p.evaluate(bindings)))
            except KeyError as exc:
                raise SimulatorError(
                    f"unbound parameter in '{op.name}({p.source})': {exc.args[0]}"
                ) from None
        else:
            resolved.append(float(p))
    return resolved


def run(
    circuit: Circuit,
    shots: Optional[int] = None,
    seed: Optional[int] = None,
    param_bindings: Optional[dict[str, float]] = None,
) -> Result:
    """Simulate *circuit*; deterministic sampling for a given *seed*.

    Only terminal measurements are supported: once any qubit is measured, no
    further unitary gate may be applied (barriers are ignored).
    """
    n = circuit.num_qubits
    if n > MAX_QUBITS:
        raise SimulatorError(
            f"circuit has {n} qubits; the dense simulator caps at {MAX_QUBITS}"
        )
    if shots is not None and shots < 1:
        raise SimulatorError(f"shots must be >= 1, got {shots}")
    bindings = dict(param_bindings or {})
    missing = sorted(circuit.used_params - set(bindings))
    if missing:
        raise SimulatorError(
            "circuit has unbound parameters: " + ", ".join(missing)
            + " (pass param_bindings)"
        )

    state = np.zeros(2**n, dtype=np.complex128)
    state[0] = 1.0

    # clbit -> measured qubit (last measurement into a clbit wins)
    meas_map: dict[int, int] = {}
    measured = False
    for op in circuit.ops:
        if op.name == "barrier":
            continue
        if op.name == "measure":
            measured = True
            meas_map[op.clbits[0]] = op.qubits[0]
            continue
        if measured:
            raise SimulatorError(
                f"gate '{op.name}' after measurement: only terminal measurements "
                "are supported in v0"
            )
        mat = _gate_matrix(op.name, _resolve_params(op, bindings))
        state = _apply(state, n, mat, op.qubits)

    probs = np.abs(state) ** 2
    total = probs.sum()
    if total > 0:
        probs = probs / total

    if measured:
        width = circuit.num_clbits
        prob_by_bits: dict[str, float] = {}
        nz = np.nonzero(probs > _PRUNE_EPS)[0]
        for idx in nz:
            bits = ["0"] * width
            for clbit, qubit in meas_map.items():
                bits[width - 1 - clbit] = "1" if (idx >> qubit) & 1 else "0"
            key = "".join(bits)
            prob_by_bits[key] = prob_by_bits.get(key, 0.0) + float(probs[idx])
        probabilities = {k: v for k, v in prob_by_bits.items() if v > _PRUNE_EPS}
    else:
        width = n
        probabilities = {
            format(int(idx), f"0{width}b"): float(probs[idx])
            for idx in np.nonzero(probs > _PRUNE_EPS)[0]
        }

    counts: Optional[dict[str, int]] = None
    if shots is not None:
        keys = sorted(probabilities)
        weights = np.array([probabilities[k] for k in keys], dtype=np.float64)
        weights = weights / weights.sum()
        rng = np.random.default_rng(seed)
        draws = rng.choice(len(keys), size=shots, p=weights)
        counts = {}
        for d in draws:
            k = keys[int(d)]
            counts[k] = counts.get(k, 0) + 1

    statevector = state if n <= STATEVECTOR_MAX_QUBITS else None
    return Result(
        probabilities=probabilities,
        counts=counts,
        statevector=statevector,
        num_qubits=n,
        num_clbits=circuit.num_clbits,
        shots=shots,
        seed=seed,
    )
