"""Resource counting per RFC-0002 (Circuit Card ``resources`` block).

The rules here are part of the RFC-0002 conformance suite; independent
implementations must agree exactly:

- ``gate_counts``: per gate name, each broadcast expansion counted
  separately; ``measure`` and ``barrier`` excluded.
- ``two_qubit_gate_count``: cx cy cz ch swap cp crx cry crz count 1 each;
  ccx and cswap are three-qubit gates and do not count.
- ``t_count``: t = 1, tdg = 1, ccx = 7, cswap = 7, everything else 0.
- ``depth``: ASAP layering — a gate (or measure) lands on layer
  ``1 + max(layer of each involved qubit)``; barriers synchronize their
  qubits to the common max but occupy no layer. Depth is the max layer.
- ``num_parameters``: distinct declared ``input float`` identifiers
  actually used by an operation.
"""

from __future__ import annotations

from collections import Counter

from .qasm import TWO_QUBIT_GATES, Circuit

__all__ = ["count_resources", "T_COSTS"]

T_COSTS = {"t": 1, "tdg": 1, "ccx": 7, "cswap": 7}


def count_resources(circuit: Circuit) -> dict:
    """Compute the RFC-0002 ``resources`` block for a parsed circuit."""
    gate_counts: Counter[str] = Counter()
    two_qubit = 0
    t_count = 0
    layer = [0] * circuit.num_qubits

    for op in circuit.ops:
        if op.name == "barrier":
            if op.qubits:
                common = max(layer[q] for q in op.qubits)
                for q in op.qubits:
                    layer[q] = common
            continue
        # unitary gates and measure both occupy a layer on their qubits
        new_layer = 1 + max(layer[q] for q in op.qubits)
        for q in op.qubits:
            layer[q] = new_layer
        if op.name == "measure":
            continue
        gate_counts[op.name] += 1
        if op.name in TWO_QUBIT_GATES:
            two_qubit += 1
        t_count += T_COSTS.get(op.name, 0)

    return {
        "num_qubits": circuit.num_qubits,
        "depth": max(layer) if layer else 0,
        "gate_counts": dict(sorted(gate_counts.items())),
        "two_qubit_gate_count": two_qubit,
        "t_count": t_count,
        "num_parameters": len(circuit.used_params),
    }
