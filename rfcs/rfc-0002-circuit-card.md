# RFC-0002: Circuit Card format

| | |
|---|---|
| **Status** | Draft |
| **Version** | 0.1 |
| **Discussion** | this repository's issues/PRs |
| **Schema** | [`spec/schemas/circuit-card.schema.json`](../spec/schemas/circuit-card.schema.json) |

## Summary

The **Circuit Card** is the structured metadata document that accompanies every circuit artifact on QuantumVerse — the model-card idea, adapted to what quantum users actually need to know before spending QPU dollars. It answers, at a glance: *how big is this, what does it need, how noisy can I be, has it ever actually worked, and where did it come from?*

## Motivation

A circuit file alone is not reusable knowledge. Whether a circuit fits your device (qubits, depth, connectivity), what it costs in fault-tolerant terms (T-count), and whether its claimed results are backed by evidence — none of that is visible in QASM source. Model cards made ML artifacts comparable and trustworthy; Circuit Cards do the same for quantum, with one improvement: the resource numbers are **computed, not claimed**.

## Design rules

1. **Machine-populated resources.** Everything in `resources` is derived from the circuit by the platform on upload (gate counts, depth, qubit count, two-qubit-gate count, T-count). Hand-written values are overwritten. A card can't lie about size.
2. **Claims link to capsules.** `verified_results` entries reference [Experiment Capsules](rfc-0001-experiment-capsule.md) by content address. A backend badge on a card is only rendered when a capsule backs it.
3. **Lineage is explicit.** `provenance.forked_from` uses [RFC-0003](rfc-0003-artifact-addressing.md) URIs, so derivation chains are navigable.
4. **Plain JSON, versioned schema.** Cards are stored as `card.json` alongside the circuit source in the artifact; `card_version` gates schema evolution.

## Document layout

```json
{
  "card_version": "0.1",
  "name": "Grover search, 3-qubit SAT instance",
  "summary": "Two-iteration Grover search over a 3-variable satisfiability oracle.",
  "description": "Optional long-form markdown…",
  "resources": {
    "num_qubits": 3,
    "depth": 24,
    "gate_counts": { "h": 9, "x": 6, "ccx": 2, "cz": 2 },
    "two_qubit_gate_count": 2,
    "t_count": 14,
    "num_parameters": 0
  },
  "requirements": {
    "connectivity": "line",
    "native_gates": ["rz", "sx", "cx"]
  },
  "noise_profile": {
    "sensitivity": "medium",
    "validated_mitigation": ["readout_correction"]
  },
  "verified_results": [
    { "capsule": "sha256:9f3ac2…", "backend": "ibm_kingston", "note": "84% success probability at 4096 shots" }
  ],
  "provenance": {
    "license": "Apache-2.0",
    "authors": ["A. Researcher"],
    "paper": "https://arxiv.org/abs/xxxx.xxxxx",
    "forked_from": "qv:grover/sat-2q@1.0.0"
  },
  "tags": ["grover", "search", "textbook"]
}
```

Field notes:

- **`resources.t_count`** counts explicit `t`/`tdg` gates plus the T-cost of decomposable gates the platform recognizes (e.g. `ccx` = 7). The counting rules are part of this spec's conformance suite so independent implementations agree.
- **`resources.depth`** is circuit depth over the gate set as written (no recompilation), counting a gate on qubits {a,b} as occupying both wires for one layer.
- **`resources.num_parameters`** is the number of unbound symbolic parameters; nonzero marks the circuit as an ansatz, which is what a Trained Parameters artifact binds to.
- **`noise_profile`** is author-declared (it cannot be derived from source) and is rendered as a claim, visually distinct from computed fields.

## Rendering obligations

Platforms rendering a card MUST visually distinguish (a) computed fields, (b) author claims, and (c) capsule-backed verified results. Conflating them defeats the format's purpose.

## Open questions

1. **Resource counting for parameterized angles.** Should T-count for `rz(θ)` report a synthesis estimate at a stated precision (e.g. ε = 1e-10) as a separate `t_count_synthesized` field?
2. **Multi-circuit artifacts.** Variational workflows often ship families of circuits. One card per artifact with per-member resource ranges, or one card per member?
3. **Card localization.** `summary`/`description` language tags — worth the complexity now?
