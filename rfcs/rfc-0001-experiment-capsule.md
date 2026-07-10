# RFC-0001: Experiment Capsule format

| | |
|---|---|
| **Status** | Review |
| **Version** | 0.1 |
| **Discussion** | this repository's issues/PRs |
| **Schemas** | [`spec/schemas/`](../spec/schemas/) — manifest, device, execution, mitigation |

## Summary

The **Experiment Capsule** is a self-contained, content-addressed, immutable record of one quantum experiment: what was intended to run, what actually ran, on which device in which calibration state, what came back, and how the raw outcomes were post-processed. A Capsule is *a git commit for a quantum experiment* — citable, forkable, and replayable.

This RFC defines the capsule layout, the manifest and file schemas, the content-addressing scheme, the signature and trust model, and replay semantics.

## Motivation

In classical computing, code is the result. In quantum computing, a result is code **plus** a specific device **plus** that device's state at a specific hour. Devices are recalibrated daily; a result produced on Tuesday can be unreproducible on Thursday on the same machine. Published papers routinely omit the transpiled circuit, the calibration snapshot, or the exact mitigation pipeline — any one of which can move a result by more than the claimed effect.

The Capsule makes the full experimental context a single portable object, so that:

- **"As reported in our paper" can be a link instead of a promise.** Reviewers and readers inspect the raw shots and the exact pipeline.
- **Claims become checkable.** A leaderboard entry backed by a provider-verified capsule is a different epistemic object than a screenshot.
- **Drift becomes measurable.** Replaying a capsule on today's calibration and diffing the outcomes turns "hardware got better/worse" into data.

## Design goals

1. **Self-contained** — a capsule is interpretable with no network access and no proprietary SDK.
2. **Framework-agnostic** — circuits in OpenQASM 3 (QIR permitted as a secondary attachment); metadata in plain JSON.
3. **Content-addressed** — every capsule has a globally unique ID derived from its bytes; identical experiments hash identically.
4. **Hardware-honest** — the *compiled* circuit and the *calibration snapshot* are mandatory, not optional; abstraction is where reproducibility dies.
5. **Verifiable** — a graded trust model, from unsigned to provider-attested, machine-checkable end to end.
6. **Replayable** — well-defined semantics for re-running a capsule at three levels of fidelity.
7. **Small by default** — a typical capsule is tens of kilobytes; bulk raw data is referenced, not inlined (see Open Questions).

## Capsule layout

```
capsule/
├── manifest.json           # REQUIRED  identity, digests, authorship, links
├── circuit.qasm            # REQUIRED  abstract circuit (OpenQASM 3)
├── compiled.qasm           # REQUIRED* exact transpiled circuit that ran
├── device.json             # REQUIRED* backend identity + calibration snapshot
├── execution.json          # REQUIRED  shots, raw counts, timestamps, job IDs
├── mitigation.json         # OPTIONAL  error-mitigation pipeline, exactly as applied
├── environment.lock        # REQUIRED  framework + SDK versions (pip-freeze style)
├── author.sig              # OPTIONAL  author signature (trust level 1)
└── receipt.sig             # OPTIONAL  provider-signed execution receipt
```

`*` — for simulator-only capsules, `compiled.qasm` may be omitted and `device.json` describes the simulator and noise model instead of physical hardware. A capsule that omits them while claiming hardware execution is invalid.

A capsule is transported as a directory or as an uncompressed tar archive with the files in the order listed above (deterministic byte layout keeps archive digests stable).

## `manifest.json`

```json
{
  "capsule_version": "0.1",
  "id": "sha256:9f3ac2e17b40d9c65a8e2f301bd4a7e6c8d5b2a19f0e3c4d5e6f7a8b9c0d1e2f",
  "created": "2026-07-07T14:32:09Z",
  "title": "VQE ground state of H2O, cc-pVDZ active space (4e,4o)",
  "authors": [
    { "name": "A. Researcher", "orcid": "0000-0002-1825-0097", "profile": "qv:users/aresearcher" }
  ],
  "license": "CC-BY-4.0",
  "artifacts": {
    "circuit": "qv:vqe/h2o-ground-state@1.4.2",
    "instance": "qv:instances/h2o-ccpvdz-4e4o@1.0.0"
  },
  "files": {
    "circuit.qasm":     "sha256:71b2…",
    "compiled.qasm":    "sha256:0e4d…",
    "device.json":      "sha256:c9a1…",
    "execution.json":   "sha256:5f68…",
    "mitigation.json":  "sha256:2b77…",
    "environment.lock": "sha256:88d0…"
  },
  "replay_of": null,
  "doi": "10.5281/qv.9f3ac2"
}
```

Field notes:

- **`id`** — computed as described under *Content addressing*; writing it into the manifest is a convenience, and verifiers MUST recompute it.
- **`artifacts`** — optional back-references to hub artifacts (`qv:` URIs) this experiment instantiates. They link capsules to Circuit Cards so verified results can surface on artifact pages.
- **`replay_of`** — the `id` of the capsule this one replays, or `null`. Replays form chains; drift analysis walks them.
- **`doi`** — present once minted; DOI registration metadata points back at the capsule ID, making the citation loop bidirectional.

## Content addressing

- Every JSON file is serialized in **canonical form** ([RFC 8785](https://www.rfc-editor.org/rfc/rfc8785) JSON Canonicalization Scheme) before hashing. Text files (`.qasm`, `.lock`) are hashed as UTF-8 bytes with `\n` line endings.
- Each entry in `manifest.files` is the SHA-256 digest of the corresponding file.
- The **capsule ID** is the SHA-256 digest of the canonical manifest *with the `id` field set to the empty string* (so the ID does not hash itself).
- **Short form** for display: `capsule/` + first 6 hex characters, e.g. `capsule/9f3ac2…` — the platform resolves collisions by extending, exactly as git does.

Two consequences worth stating: capsules are immutable (any edit is a new capsule), and deduplication is free (the same experiment captured twice produces one object).

## File schemas

The JSON examples below are illustrative; the normative JSON Schema documents live in [`spec/schemas/`](../spec/schemas/) and are what validators enforce.

### `device.json` — the calibration snapshot

```json
{
  "backend": { "provider": "ibm", "name": "ibm_kingston", "version": "1.2.8" },
  "captured": "2026-07-07T14:05:00Z",
  "topology": { "num_qubits": 156, "coupling_map": [[0,1],[1,2], "…"] },
  "qubits": [
    { "index": 0, "t1_us": 312.4, "t2_us": 187.9, "readout_error": 0.011, "frequency_ghz": 4.874 }
  ],
  "gates": [
    { "gate": "cz", "qubits": [0,1], "error": 0.0042, "duration_ns": 68 }
  ],
  "simulator": null
}
```

For simulator capsules, `simulator` carries `{ "engine": "...", "method": "statevector|density|mps", "noise_model": { … } }` and `qubits`/`gates` may be empty. Providers are encouraged to expose calibration snapshots in exactly this shape; until they do, capture SDKs translate.

### `execution.json` — what came back

```json
{
  "job_ids": ["cx7q2m9k40rg008h1234"],
  "submitted": "2026-07-07T14:31:02Z",
  "completed": "2026-07-07T14:32:09Z",
  "shots": 4096,
  "counts_raw": { "0000": 1731, "0001": 88, "1111": 1699, "…": 578 },
  "counts_mitigated": { "0000": 1794, "1111": 1761, "…": 541 },
  "parameters": { "theta": [0.7853981, -1.2217304, 0.5235987] }
}
```

`counts_raw` is mandatory and untouched; `counts_mitigated` is optional and MUST be reproducible from `counts_raw` plus `mitigation.json`. `parameters` records bound values for parameterized circuits — for a converged VQE run these *are* the trained-parameters artifact.

### `mitigation.json` — the pipeline, exactly as applied

```json
{
  "pipeline": [
    { "step": "readout_correction", "method": "matrix_inversion",
      "calibration_shots": 8192 },
    { "step": "zne", "method": "richardson",
      "scale_factors": [1.0, 2.0, 3.0], "folding": "global" }
  ]
}
```

Ordered, parameterized, no defaults left implicit. A verifier re-derives `counts_mitigated` by applying the pipeline to `counts_raw`.

## Signatures and trust levels

Two independent signatures may accompany a capsule; each is an Ed25519 signature over the capsule ID.

| Level | Name | Meaning |
|---|---|---|
| 0 | **Unsigned** | Useful for personal record-keeping; carries no attestation |
| 1 | **Author-signed** | The named author vouches for the contents (key published on their profile) |
| 2 | **Provider-verified** | `receipt.sig` from the hardware provider attests that this compiled circuit ran on this backend at this time with these results |

`receipt.sig` contains the provider's signature plus its key identifier. Provider participation is the Phase-3 partnership ask in the [roadmap](../VISION.md#10-roadmap); until then, level-1 capsules with public job IDs offer spot-checkability. **Leaderboard badge tiers map directly onto these levels** — a "verified" leaderboard entry means level 2.

### Signature file format

`author.sig` and `receipt.sig` share one canonical-JSON format, validated by [`spec/schemas/signature.schema.json`](../spec/schemas/signature.schema.json):

```json
{
  "algorithm": "ed25519",
  "key_id": "sha256:1f5c…",
  "public_key": "base64(raw 32-byte public key)",
  "signature": "base64(Ed25519 signature over the ASCII bytes of the capsule id)",
  "signed": "2026-07-10T14:40:00Z",
  "signer": "qv:users/aresearcher"
}
```

Rules:

- The message signed is the ASCII byte string of the capsule id (`sha256:<hex>`), so a signature covers the entire content-addressed capsule.
- Signature files are **never listed in `manifest.files`** and do not contribute to the capsule id — a capsule's identity is its contents, not its endorsements. Adding or removing a signature does not change what capsule it is.
- `key_id` is the SHA-256 digest of the raw public key. Verifiers MUST (a) recompute the capsule id, (b) verify the signature against the embedded `public_key`, and (c) check `key_id` matches that key. The embedded key makes verification self-contained; *trust* in the key comes from its binding to a profile (author) or the provider key registry (receipt) — see Open Questions §5.
- `signer` is a claim, not a proof, until the referenced profile publishes the matching `key_id`.

Trust levels attest *provenance*, not *correctness*: a provider receipt proves the circuit ran and returned these counts, not that the interpretation in a paper is sound.

## Replay semantics

Replaying capsule `X` produces a **new** capsule with `replay_of: X.id`:

| Level | Name | What runs | What it tells you |
|---|---|---|---|
| **L1** | Simulate | `circuit.qasm` on a simulator seeded with the noise model derived from `X`'s `device.json` | Whether the reported counts are consistent with the reported device state |
| **L2** | Re-transpile | `circuit.qasm` re-compiled for a current backend, then simulated or run | Whether the result survives today's compiler and topology |
| **L3** | Re-execute | The same abstract circuit on real hardware, capturing a fresh snapshot | Whether the result survives today's *hardware* — the drift diff |

The platform renders `diff(X, replay)` as: calibration deltas (from the two `device.json` files), distribution distance on counts (total variation and Hellinger), and a verdict band (consistent / degraded / not reproduced). Chains of L3 replays over months are the reproducibility time-series the field currently lacks.

## Capture SDK

Capturing must be one decorator away from existing code, or nobody will do it:

```python
import quantumverse as qv

with qv.capture(title="VQE ground state of H2O",
                artifacts={"circuit": "vqe/h2o-ground-state@1.4.2"}) as cap:
    job = backend.run(transpiled, shots=4096)        # your existing code
    counts = job.result().get_counts()

cap.add_mitigation(pipeline)                          # optional
capsule_id = cap.publish(license="CC-BY-4.0")         # → capsule/9f3ac2…
```

The context manager snapshots the backend calibration at entry, records job metadata and raw counts at exit, freezes the environment lockfile, canonicalizes, hashes, and signs with the author's key. Qiskit is the reference integration; Cirq, PennyLane, and Braket adapters follow the same interface.

## Citation

Once a DOI is minted, both identifiers resolve to the same page:

```bibtex
@misc{qv_9f3ac2,
  title        = {VQE ground state of H2O, cc-pVDZ active space (4e,4o)},
  author       = {A. Researcher},
  year         = {2026},
  doi          = {10.5281/qv.9f3ac2},
  howpublished = {QuantumVerse capsule/9f3ac2},
  note         = {provider-verified execution record}
}
```

Journals piloting "capsule required" for hardware-results papers need nothing beyond this section and a link checker.

## Open questions

Genuinely unsettled — input wanted:

1. **Bulk raw data.** Shot-by-shot records and pulse-level captures can reach gigabytes. Current lean: `counts_raw` stays inline; larger payloads become content-addressed side files referenced from the manifest. Where exactly is the cut-off?
2. **Pulse-level capsules.** `compiled.qasm` assumes gate-model execution. Analog and pulse-level experiments (neutral atoms, annealers) need a sibling format — extend this RFC or write RFC-000N?
3. **Calibration snapshot depth.** Is per-qubit T1/T2 + per-gate error enough for meaningful L1 replay, or do we need full noise-learning outputs when available?
4. **Privacy gradient.** Private capsules that can later be flipped public (e.g., on paper acceptance) — does deferred disclosure interact badly with content addressing?
5. **Receipt key distribution.** How provider keys are published and rotated (TUF-style root of trust vs. plain well-known endpoints).
