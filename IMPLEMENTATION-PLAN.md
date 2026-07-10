# Implementation Plan

*How QuantumVerse actually gets built — the engineering execution plan behind the strategic roadmap in [VISION.md §10](VISION.md#10-roadmap).*

The roadmap in VISION.md says *what* ships in each phase and *why*. This document says *how*: the architecture, the concrete workstreams, what to **reuse instead of build**, the exit gate that ends each phase, and the team it takes. It is written to be executable by a small founding team, not a funded org — every phase produces something real and dogfoodable.

## Build principles

1. **Spec first, then code.** Every interoperable format ships as an [RFC](rfcs/) before it has two implementations. [RFC-0001](rfcs/rfc-0001-experiment-capsule.md) (Capsule) is the template.
2. **Framework-agnostic core.** Internally everything is **OpenQASM 3** (+ QIR where needed). Framework-specific code lives only at the edges, in import/export adapters.
3. **Reuse aggressively.** Equivalence checking, transpilation, resource estimation, and benchmark circuits are solved problems with good open-source tools. We integrate them; we do not reinvent them (see the build-vs-reuse table).
4. **Vertical slices, not horizontal layers.** Each phase ships a thin end-to-end path a real user can walk, then widens it. Never "build the whole backend, then the whole frontend."
5. **Simulators before hardware.** Everything works on free in-browser/cloud simulators first. Real-QPU execution is always optional and metered — it never gates the core loop.
6. **Seed before launch.** An empty hub has no value. Every public milestone is preceded by content import (Algorithm Zoo, MQT Bench, QASMBench, SupermarQ) and hand-curation.
7. **Open source from commit one.** Apache-2.0, public repo, public issues, public RFCs.

## System architecture

```
                         ┌───────────────────────────────────────────┐
                         │                Web frontend                │
                         │   Next.js/React · design system (from the  │
                         │   pitch site) · artifact pages · Circuit   │
                         │   Cards · search · profiles · leaderboards │
                         └───────────────┬───────────────────────────┘
                                         │ REST + GraphQL
     ┌───────────────────┐   ┌───────────▼───────────┐   ┌──────────────────────┐
     │  quantumverse      │   │     Hub API (FastAPI)  │   │  In-browser sim       │
     │  Python client+CLI ├──▶│  auth · artifacts ·    │◀──┤  (Rust → WASM         │
     │  qv.load/push/     │   │  versions · metadata · │   │  statevector, ~25q)   │
     │  capture           │   │  search index          │   └──────────────────────┘
     └───────────────────┘   └───┬───────────┬────────┘
                                 │           │
              ┌──────────────────▼──┐   ┌────▼──────────────────────────┐
              │ Content-addressed    │   │ Metadata store (Postgres)     │
              │ blob store (S3/MinIO)│   │ artifacts, capsules, users,   │
              │ circuits · capsules  │   │ orgs, leaderboards, drift TS  │
              └──────────────────────┘   └───────────────────────────────┘
                                 ▲
     ┌───────────────────────────┴───────────────────────────────────────┐
     │                    Verification & execution workers                 │
     │  equivalence (PyZX, MQT QCEC) · resource counting (TKET, qiskit) ·  │
     │  Quantum CI · capsule validation/replay · execution adapters ──────┼──▶ simulators
     │  (qBraid/Braket/IBM/IonQ) · DOI minting (DataCite) · signing (Ed25519)│    & QPUs
     └─────────────────────────────────────────────────────────────────────┘
```

## Build vs. reuse

The single most important engineering decision: **what not to build.**

| Capability | Reuse | Build ourselves |
|---|---|---|
| Cross-framework conversion | **pytket** (`pytket-qiskit/-cirq/-pennylane/-braket`), **qBraid transpiler**, `qiskit.qasm3` | Thin adapter layer + a normalization/round-trip test suite |
| Circuit equivalence checking | **PyZX** (ZX-calculus), **MQT QCEC** (`mqt.qcec`) | Diff *rendering* + the "equivalent up to global phase" UX |
| Resource counting / T-count | **TKET**, `qiskit.transpiler`, **Azure Resource Estimator**, BenchQ/pyLIQTR | Circuit Card auto-population + regression budgets |
| Benchmark circuits (seed) | **MQT Bench**, **QASMBench**, **SupermarQ**, QED-C | Import pipeline → typed artifacts |
| Statevector simulation (cloud) | `qiskit-aer`, Stim (Clifford), qsim | Job orchestration |
| Statevector simulation (browser) | — | **Rust → WASM** sim (productionize the pitch-site demo) |
| Benchmark execution/dispatch | **metriq-gym** (partner with Unitary Foundation) | Leaderboard UI + signed-capsule anchoring |
| Provenance model (reference) | **QProv**, QC-MM schema | Capsule format, capture SDK, content-addressing, replay |
| DOI minting | **DataCite** Fabrica API | capsule ↔ DOI binding |
| Signing / trust | **Ed25519**, optionally **sigstore** | Trust-tier logic, receipt verification |
| Identity | **ORCID** + GitHub OAuth | Profiles, orgs, the "Quantum CV" |

---

## Phase 0 — Foundations *(≈ weeks 0–6, 1–2 people)*

**Goal:** the skeleton everything hangs on, and the spec pinned down. Nothing public-facing yet.

**Workstreams**
- **Monorepo & CI/CD.** `quantumverse/` monorepo: `client/` (Python), `api/`, `web/`, `sim/` (Rust/WASM), `spec/` (symlink to `rfcs/`). Lint/test/release pipelines.
- **Spec to Review.** Drive [RFC-0001](rfcs/rfc-0001-experiment-capsule.md) from Draft → Review: finalize `manifest.json`, canonical JSON (RFC 8785), the SHA-256 addressing, and JSON Schemas for `device.json`/`execution.json`/`mitigation.json`. Write RFC-0002 (Circuit Card) and RFC-0003 (artifact addressing / `qv:` URIs).
- **Client skeleton, local-only.** `qv` CLI + library that can package, validate, hash, and read a Capsule **entirely locally** against a filesystem "registry." No server yet.
- **Design system extraction.** Pull the pitch site's tokens (Fraunces/mono, the brass palette, component styles) into a shared web package so the app inherits the identity.

**Exit gate:** `qv capsule validate` and `qv capsule inspect` work on a real capsule locally; RFC-0001 is at **Review**; CI is green on all four packages.

---

## Phase 1 — The Hub + Playground *(≈ months 2–6, 2–4 people)*

**Goal:** a stranger can `pip install quantumverse`, load a community artifact into their framework, run it in the browser, and publish their own. This is the reuse loop, closed.

**Workstreams**
- **Registry backend.** FastAPI service; **Postgres** for metadata (artifacts, versions, users, orgs); **content-addressed blob store** (S3/MinIO) for circuits/params/instances keyed by digest; artifact types `circuit` / `parameters` / `instance`; semantic versioning; REST + GraphQL.
- **Client, networked.** `qv.load("vqe/h2o-ground-state", framework="qiskit")` and `qv.push(...)`; export via **pytket/qBraid**; auth via OAuth device flow. Local cache keyed by content hash (Docker-layer-style dedup).
- **Circuit Cards.** Auto-populate resources (qubits, depth, gate counts, **T-count** via TKET/qiskit) on upload; render the card on the artifact page. This is RFC-0002 in practice.
- **In-browser simulator.** Productionize the demo: a **Rust statevector sim compiled to WASM**, ~20–25 qubits, with statevector/Bloch/histogram views. A "Run" button on every circuit page.
- **Search & profiles.** Postgres full-text search first (Meilisearch/OpenSearch later); user and org profiles; fork/star primitives.
- **Seed content.** Import pipelines for **Algorithm Zoo**, **MQT Bench**, **QASMBench**, **SupermarQ**, and open Hamiltonian/QUBO sets → typed artifacts. Hand-curate 50 flagship artifacts with great cards.

**Exit gate (public beta):** end-to-end path works for an outside user; ≥ 100 artifacts live (seeded + first external); in-browser run works on every circuit; the client is on PyPI.

**Risks:** cross-framework round-trip fidelity (mitigate with a normalization test suite + honest "lossy conversion" warnings); WASM sim performance (cap qubit count, offer cloud-sim fallback).

---

## Phase 2 — The Verification Layer *(≈ months 6–14, 4–6 people)*

**Goal:** an experiment can be captured as a citable, replayable Capsule; circuits get semantic diffs and Quantum CI; one narrow, unimpeachable verified leaderboard is live. This is the credibility loop, closed.

**Workstreams**
- **Capsule capture SDK.** `qv.capture(...)` context managers wrapping Qiskit/Cirq/PennyLane/Braket runs — snapshot calibration on entry, record raw counts + job metadata on exit, freeze the lockfile, canonicalize, hash, sign (Ed25519). Capsule storage + a rich capsule page. **DOI minting via DataCite.**
- **Semantic diffs.** Integrate **PyZX** + **MQT QCEC** as verification workers; render "N gates changed, equivalent up to global phase" on artifact diffs and PRs.
- **Quantum CI.** On push: equivalence vs. reference, resource-regression budgets (fail if depth/qubits/T-count exceed limits), simulator validation within tolerance, optional metered hardware smoke tests that emit fresh capsules. Runner model like GitHub Actions.
- **Execution adapters + trust tiers.** Route real runs through **qBraid/Braket/IBM/IonQ**; implement the unsigned / author-signed / provider-verified tiers from RFC-0001.
- **First verified leaderboard.** Deliberately narrow: **one** benchmark suite, **three** backends, automated recurring runs, every entry anchored to a signed capsule. Partner with **Unitary Foundation / metriq-gym** rather than fragment benchmarking.
- **Drift Observatory v0.** Persist `device.json` calibration snapshots from every capsule into a time-series store; ship the basic weather-map UI (the pitch-site chart, fed by real data).
- **Device Registry v0.** `device` artifact type + Device Card pages ([HARDWARE.md §1](HARDWARE.md#1-the-device-registry)): identity, topology, native gates, per-machine calibration timeline (the Observatory scoped to one device), and every capsule minted on it. Seed with the cloud backends the execution adapters already touch; open self-registration to lab-built machines.

**Exit gate:** a hardware-results experiment can be captured → published as a citable capsule → replayed (L1 simulate, L2 re-transpile) → and appears on a live, signed leaderboard. First journal in conversation about a "capsule-required" pilot.

**Risks:** hardware cost (keep it metered/optional, lean on simulators + donated provider credits); leaderboard methodology disputes (publish methodology as an RFC, start narrow, invite scrutiny).

---

## Phase 3 — The Institution *(≈ months 14+, 6–10 people)*

**Goal:** the platform becomes load-bearing infrastructure — and sustainable.

**Workstreams**
- **Provider-signed receipts.** Partnerships with IBM/IonQ/Quantinuum/etc. to sign execution receipts (`receipt.sig`) → true level-2 verification.
- **Orgs, private repos, billing.** Team accounts, private artifacts, metered Quantum-CI minutes and private hosting — the open-core revenue line.
- **Community surface.** Circuit Golf + bounty marketplace (equivalence checker as referee); embeddable runnable widgets for blogs/arXiv/courses.
- **Agent-native.** An **MCP server** exposing search/load/verify/publish (see [FRONTIERS.md](FRONTIERS.md)).
- **Federation.** Draft the federation RFC; self-hostable instances syncing public capsules like git remotes.
- **Publishing & readiness.** Overlay-journal integrations; the Hardware Readiness Meter fed by community-maintained roadmap data.
- **Self-hosted QPU runners.** The GitHub-Actions-runner model for hardware ([HARDWARE.md §2](HARDWARE.md#2-self-hosted-quantum-ci-runners)): an agent device owners run to accept dispatched benchmark/CI jobs in idle time, returning signed capsules. Owner-controlled policy (what runs, when, quotas); results update the Device Card automatically.
- **Birth-certificate suite.** Standardized, capsule-backed commissioning benchmarks ([HARDWARE.md §3](HARDWARE.md#3-the-birth-certificate)) published as an RFC — RB, gate/readout fidelities, a fixed community-benchmark slice — runnable by vendors at installation and citable in procurement.

**Exit gate:** provider partnerships live; private-hosting revenue covers infra; a journal pilot is running; self-hosted instances exist in the wild.

---

## Cross-cutting concerns

- **Security & trust.** Content-addressing makes artifacts tamper-evident; signing keys published on profiles; capsule replay is sandboxed; provider receipts follow a documented key-distribution scheme (RFC, Phase 3).
- **Cost model.** Storage and simulators are cheap and free-tier. **QPU time is the one real cost** — always user-funded or credit-sponsored, never on the platform's default path. Free tier = unlimited public artifacts + browser/cloud simulation.
- **Governance ops.** A technical steering group governs specs; benchmark methodology changes by public RFC; a documented content policy (licensing, takedowns, provenance).
- **Data portability.** Public artifacts are bulk-downloadable from day one — leaving is always easy.

## Risks & mitigations (top of the list)

| Risk | Mitigation |
|---|---|
| Empty-hub cold start | Seed 100+ artifacts (Zoo, MQT Bench, QASMBench, SupermarQ) *before* any public launch |
| Cross-framework conversion is lossy | Reuse TKET/qBraid; ship a round-trip test suite; label lossy conversions honestly |
| QPU cost sinks the budget | Simulators-first; hardware metered & optional; pursue provider credit grants |
| "Capsule is just QProv" critique | Credit prior art loudly; differentiate on content-addressing + citation + platform + network effects |
| Benchmark methodology fights | Start with one narrow suite; publish methodology as an RFC; automate & sign everything |
| Solo-maintainer bus factor | Open governance + 10–20 founding contributors recruited in Phase 0 |

## Success metrics by phase

| Phase | North-star metric | Supporting signals |
|---|---|---|
| 0 | Spec at Review, CI green | Founding contributors recruited |
| 1 | **Published artifacts** (target 100 → 1,000) | `pip install` count, in-browser runs, first external publishers |
| 2 | **Verified capsules** minted | Leaderboard entries, DOIs issued, replay runs, first journal pilot |
| 3 | **MAU + paying orgs** | Provider partnerships, private repos, self-hosted instances, embeds in the wild, **registered devices & active runners** |

## The first ten steps (start here)

1. Create the `quantumverse` monorepo (`client/ api/ web/ sim/ spec/`) with Apache-2.0 + CI.
2. Move RFC-0001 to **Review**; write the `manifest.json` + `device/execution/mitigation` JSON Schemas.
3. Draft **RFC-0002 (Circuit Card)** and **RFC-0003 (artifact addressing / `qv:` URIs)**.
4. Ship the `qv` CLI with **local** capsule validate/inspect (no server).
5. Stand up the FastAPI registry with content-addressed blob storage + Postgres metadata.
6. Implement `qv.load/push` with **pytket/qBraid** export and OAuth device-flow auth.
7. Auto-generate **Circuit Cards** (TKET/qiskit resource counting) on upload.
8. Productionize the **Rust→WASM** statevector simulator; wire the "Run" button.
9. Build the **import pipeline** and seed Algorithm Zoo + MQT Bench + QASMBench + SupermarQ.
10. Hand-curate **50 flagship artifacts**, then open the public beta.

---

*This plan is a living document — it will be wrong in places and should be revised by PR as the build teaches us things. The strategy it serves is in [VISION.md](VISION.md); the ideas beyond it are in [FRONTIERS.md](FRONTIERS.md); the field it competes in is in [COMPETITIVE-LANDSCAPE.md](COMPETITIVE-LANDSCAPE.md).*
