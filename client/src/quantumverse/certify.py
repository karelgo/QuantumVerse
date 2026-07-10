"""The commissioning suite and birth certificates (RFC-0005).

A certificate is computed, not claimed: a submitter only names capsules.
Anyone — the client for display, the registry before storage — can identify
which suite check each capsule ran (by its circuit text), recompute the
total-variation scores from the raw counts, and assemble the certificate
independently. Shared between client and server, like ``devices.py``.
"""

from __future__ import annotations

import json
from typing import Optional

from .canonical import utc_now
from .qasm import parse_qasm
from .verify import total_variation

__all__ = [
    "CertifyError",
    "SUITE",
    "MIN_QUBITS",
    "MAX_QUBITS",
    "check_names",
    "check_circuit",
    "ideal_distribution",
    "threshold",
    "suite_circuits",
    "identify_check",
    "evaluate_capsule_files",
]

SUITE = "qv-commissioning-v0"
# The suite width must be >= 3: at width 2 the GHZ check is textually identical
# to the Bell check, so the four checks are only distinct from 3 qubits up.
MIN_QUBITS = 3
MAX_QUBITS = 12  # suite circuits stay simulable everywhere for cross-checking

# Per-check pass thresholds on total variation distance (RFC-0005 defaults).
_THRESHOLDS = {
    "readout-zeros": 0.05,
    "readout-ones": 0.05,
    "bell": 0.10,
    "ghz": 0.10,
}


class CertifyError(ValueError):
    """Raised when a certificate cannot be computed."""


def check_names() -> list[str]:
    return list(_THRESHOLDS)


def threshold(name: str) -> float:
    try:
        return _THRESHOLDS[name]
    except KeyError:
        raise CertifyError(f"unknown commissioning check {name!r}") from None


def check_circuit(name: str, n: int) -> str:
    """OpenQASM 3 source of one suite check at width *n* (deterministic text)."""
    # The bell check is intrinsically 2 qubits and bypasses the suite-width
    # range; the scaling checks (readout/ghz) must be within [MIN, MAX].
    if name != "bell" and not MIN_QUBITS <= n <= MAX_QUBITS:
        raise CertifyError(
            f"suite width must be {MIN_QUBITS}..{MAX_QUBITS} qubits, got {n}"
        )
    header = f'OPENQASM 3.0;\ninclude "stdgates.inc";\nqubit[{n}] q;\nbit[{n}] c;\n'
    if name == "readout-zeros":
        body = ""
    elif name == "readout-ones":
        body = "".join(f"x q[{i}];\n" for i in range(n))
    elif name == "bell":
        if n != 2:
            raise CertifyError("the bell check is always 2 qubits")
        body = "h q[0];\ncx q[0], q[1];\n"
    elif name == "ghz":
        body = "h q[0];\n" + "".join(f"cx q[{i}], q[{i + 1}];\n" for i in range(n - 1))
    else:
        raise CertifyError(f"unknown commissioning check {name!r}")
    return header + body + "c = measure q;\n"


def ideal_distribution(name: str, n: int) -> dict[str, float]:
    if name == "readout-zeros":
        return {"0" * n: 1.0}
    if name == "readout-ones":
        return {"1" * n: 1.0}
    if name == "bell":
        return {"00": 0.5, "11": 0.5}
    if name == "ghz":
        return {"0" * n: 0.5, "1" * n: 0.5}
    raise CertifyError(f"unknown commissioning check {name!r}")


def suite_circuits(n: int) -> dict[str, str]:
    """The full suite at width *n*: check name -> QASM source."""
    return {
        "readout-zeros": check_circuit("readout-zeros", n),
        "readout-ones": check_circuit("readout-ones", n),
        "bell": check_circuit("bell", 2),
        "ghz": check_circuit("ghz", n),
    }


def _normalize(qasm_text: str) -> str:
    lines = []
    for line in qasm_text.replace("\r\n", "\n").split("\n"):
        line = line.split("//", 1)[0].strip()
        if line:
            lines.append(line)
    return "\n".join(lines)


def identify_check(qasm_text: str) -> Optional[tuple[str, int]]:
    """Which suite check is this circuit? Returns ``(name, width)`` or None.

    Identification is by exact normalized text match against the generated
    suite circuit at the width the circuit declares — no trust in labels.
    """
    try:
        n = parse_qasm(qasm_text).num_qubits
    except Exception:
        return None
    normalized = _normalize(qasm_text)
    for name in check_names():
        width = 2 if name == "bell" else n
        if width != n:
            continue
        try:
            candidate = check_circuit(name, width)
        except CertifyError:
            continue
        if _normalize(candidate) == normalized:
            return name, width
    return None


def evaluate_capsule_files(
    capsules: list[tuple[str, dict[str, bytes]]],
    expected_backend: Optional[dict] = None,
) -> dict:
    """Compute a certificate from capsules — the shared, trust-nothing core.

    *capsules* is ``[(capsule_id, files), ...]``. Each capsule must be one
    suite check; together they must cover the whole suite at one width.
    With *expected_backend*, every capsule's device.json backend identity
    must match it (the certificate is about one machine).
    """
    seen: dict[str, dict] = {}
    width: Optional[int] = None
    for capsule_id, files in capsules:
        circuit_raw = files.get("circuit.qasm")
        execution_raw = files.get("execution.json")
        device_raw = files.get("device.json")
        if circuit_raw is None or execution_raw is None or device_raw is None:
            raise CertifyError(f"{capsule_id}: not a complete capsule")

        identified = identify_check(circuit_raw.decode("utf-8"))
        if identified is None:
            raise CertifyError(
                f"{capsule_id}: circuit is not a {SUITE} check "
                "(commissioning circuits must match the suite exactly)"
            )
        name, n = identified
        if name in seen:
            raise CertifyError(f"duplicate {name!r} check ({capsule_id} and {seen[name]['capsule']})")
        if name != "bell":
            if width is None:
                width = n
            elif n != width:
                raise CertifyError(
                    f"mixed suite widths: {name} ran at {n} qubits, others at {width}"
                )

        if expected_backend is not None:
            device_doc = json.loads(device_raw.decode("utf-8"))
            backend = device_doc.get("backend") or {}
            got = (backend.get("provider"), backend.get("name"))
            want = (expected_backend.get("provider"), expected_backend.get("name"))
            if got != want:
                raise CertifyError(
                    f"{capsule_id}: ran on {got[0]}/{got[1]}, but this certificate is "
                    f"for {want[0]}/{want[1]}"
                )

        execution = json.loads(execution_raw.decode("utf-8"))
        counts = execution.get("counts_raw") or {}
        if not counts:
            raise CertifyError(f"{capsule_id}: no raw counts to score")
        tv = total_variation(
            ideal_distribution(name, n), {k: float(v) for k, v in counts.items()}
        )
        seen[name] = {
            "name": name,
            "qubits": n,
            "shots": execution.get("shots"),
            "tv_distance": round(tv, 6),
            "threshold": threshold(name),
            "pass": tv <= threshold(name),
            "capsule": capsule_id,
        }

    missing = [name for name in check_names() if name not in seen]
    if missing:
        raise CertifyError(
            f"incomplete suite: missing check(s) {', '.join(missing)} — "
            "a birth certificate covers the whole suite or nothing"
        )

    checks = [seen[name] for name in check_names()]
    return {
        "certificate_version": "0.1",
        "suite": SUITE,
        "width": width,
        "issued": utc_now(),
        "checks": checks,
        "passed": all(c["pass"] for c in checks),
    }
