# Contributing to QuantumVerse

Everything here — the specs, the client, the registry, the simulator, the playground — is developed in the open under [Apache-2.0](LICENSE). The two things worth reading first: [VISION.md](VISION.md) for *why*, and [IMPLEMENTATION-PLAN.md](IMPLEMENTATION-PLAN.md) for *how it's being built*.

## Ground rules

1. **Spec first.** Anything another implementation would have to interoperate with changes by [RFC](rfcs/README.md), not by code review on an implementation PR. Formats live in `rfcs/` (prose) + `spec/schemas/` (enforceable JSON Schemas). The schemas in `spec/schemas/` are the single source of truth; the client vendors byte-identical copies (`client/src/quantumverse/schemas/`) and CI fails if they drift — after editing a schema, copy it over and let the sync test confirm.
2. **Computed, not claimed.** The platform's standing design rule: anything derivable is derived by the reader, never trusted from the writer — card resources, capsule ids, certificate scores, leaderboard entries. New features should keep this shape.
3. **Both registries or neither.** The local registry (`~/.qv`) and the HTTP registry expose the same operations; a feature that only works remotely (or only locally) needs a stated reason. Shared logic lives in the client package (`devices.py`, `certify.py`, `leaderboard.py` are the pattern) so both sides derive results identically.

## Dev setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e "client[dev,mcp]" -e "api[dev]"

pytest client/tests api/tests -q          # Python suites
(cd sim && cargo test)                     # Rust simulator
qv ci --config quantumverse.ci.json        # the repo's own Quantum CI

# WASM rebuild after touching sim/src/lib.rs (the built binary is committed):
(cd sim && cargo build --release --target wasm32-unknown-unknown \
  && cp target/wasm32-unknown-unknown/release/qv_sim.wasm ../playground/qv_sim.wasm)
```

Run the full stack locally:

```bash
qv-registry --data ./data --web ./playground --port 8000 &
python seeds/import.py --registry http://127.0.0.1:8000 --with-capsule
open http://127.0.0.1:8000        # the playground, browsing the live registry
```

## Pull requests

- Tests accompany behavior. The suites are fast (<10s) on purpose; keep them that way.
- One vertical slice per PR (the git history of this repo is the template: spec → implementation → tests → docs in one coherent commit).
- CI must be green: client, api, sim (native + wasm build), schema sync, and the Quantum CI dogfood job.

## Where help is most wanted

RFC review (all six are Draft/Review — argue with them), framework adapters beyond the Qiskit device snapshot (Cirq, PennyLane, Braket capture), commissioning suite v1 proposals (RB, mirror circuits), and additional leaderboard metrics (multi-basis energy estimation needs a format extension — see RFC-0006 open questions).
