# QuantumVerse

**The home for quantum artifacts — where circuits, results, and claims become shareable, runnable, and verifiable.**

GitHub gave code a home. Hugging Face gave models a home. Quantum computing — thousands of researchers producing circuits, trained ansätze, benchmark results, and hardware experiments every week — still shares its work as PDFs and framework-locked zip files that stop reproducing the day the hardware is recalibrated.

QuantumVerse is the missing layer: an open, community-owned platform for publishing, discovering, running, and **verifying** quantum work.

📖 **Read the full vision:** [VISION.md](VISION.md) · 🔭 **What's beyond the pillars:** [FRONTIERS.md](FRONTIERS.md) · 🔩 **Where the machines live:** [HARDWARE.md](HARDWARE.md) · 📐 **First spec:** [RFC-0001](rfcs/rfc-0001-experiment-capsule.md) · 🌐 **Pitch site:** [`docs/index.html`](docs/index.html) (live via GitHub Pages)

**And it runs.** The reference implementation lives in this repository — client, registry, simulator, playground, seed library — built phase by phase against [IMPLEMENTATION-PLAN.md](IMPLEMENTATION-PLAN.md):

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e client -e api

qv-registry --data ./data --web ./playground --port 8000 &   # registry + playground at :8000
python seeds/import.py --registry http://127.0.0.1:8000 --with-capsule

export QV_REGISTRY_URL=http://127.0.0.1:8000
qv pull qv:seeds/vqe-h2-ansatz          # one line to use anyone's work
qv run seeds/circuits/grover-2q.qasm --shots 1024
qv diff old.qasm new.qasm               # semantic diff: equivalence up to global phase
qv ci --config quantumverse.ci.json     # quantum CI: budgets + golden refs + distributions
qv capsule create --circuit … && qv capsule replay …   # RFC-0001 capsules, L1 replay
qv key generate && qv capsule sign cap.tar             # author signature — trust level 1
qv device show qv:device/quantumverse/qv-sim           # Device Cards (RFC-0004)
qv device drift quantumverse/qv-sim                    # calibration timeline, fed by capsules
qv device certify quantumverse/qv-sim --seed 7         # birth certificate (RFC-0005)
qv board show maxcut-triangle                          # verified leaderboard (RFC-0006)
qv board submit maxcut-triangle <capsule-id>           # the registry recomputes your score
qv capsule cite cap.tar                                # BibTeX, straight from the manifest
qv sync https://another-instance.example              # federate: pull a peer's public catalog (RFC-0007)
qv-mcp                                                 # MCP server: agents search/load/run/verify
```

---

## The three pillars

### 🗂 The Hub — *the Hugging Face analog*
Typed, versioned, framework-agnostic artifact repos (OpenQASM 3 / QIR interchange): circuits with **Circuit Cards**, **trained VQE/QAOA parameters** (the "pretrained weights" of quantum — nobody hosts these today), Hamiltonians and benchmark instances, noise models, and compiled-circuit caches. One line to reuse anyone's work:

```python
import quantumverse as qv
ansatz, params = qv.load("vqe/h2o-ground-state", framework="qiskit")
```

### ✅ The Verification Layer — *what GitHub and HF never needed; quantum does*
Hardware drifts daily, so in quantum the device's state is part of the result — and most published results can't be independently reproduced. QuantumVerse makes verifiability a platform primitive:

- **Experiment Capsules** — content-addressed bundles of circuit + transpilation + device calibration snapshot + raw shots + mitigation pipeline. A *git commit for a quantum experiment*: citable, forkable, replayable.
- **Semantic circuit diffs** — ZX-calculus equivalence checking: "14 gates changed, depth −31%, circuits still equivalent."
- **Quantum CI** — equivalence checks, resource-count regression (qubits/depth/T-count), simulator validation, optional metered runs on real QPUs.
- **Verified leaderboards** — automated cross-hardware benchmarks anchored to signed Capsules. *Papers with Code for quantum*, machine-verified instead of self-reported.

### 🎮 The Playground — *the viral surface*
Every circuit page has a **Run** button — a WASM statevector simulator executes up to ~25 qubits in the browser, zero install. Embeddable live widgets for papers, blogs, and courses. **Circuit Golf**: competitive, auto-verified circuit optimization challenges. And a **Hardware Readiness Meter** on every algorithm: resource estimates vs. hardware roadmaps → *"runnable in ~2033."*

---

## Roadmap

| Phase | What ships |
|---|---|
| **0 — Manifesto** *(now)* | This vision, the pitch site, founding contributors |
| **1 — Hub + Playground** | Artifact repos, Circuit Cards, `quantumverse` client, in-browser simulator; seeded with the Algorithm Zoo and open benchmark sets |
| **2 — Verification** | Capsule spec v1, semantic diffs, Quantum CI, first verified leaderboard, Circuit Golf |
| **3 — Institution** | Provider-signed receipts, orgs, bounty marketplace, embeds, DOI minting |

## Principles

**Open core** (Apache-2.0, developed in the open) · **open spec first** (Capsule & Card formats published as standalone standards) · **open data** (public artifacts bulk-downloadable, no lock-in) · **community governance** (spec changes by public RFC).

## Beyond the pillars

Once the artifact layer exists, new infrastructure becomes possible: the **Drift Observatory** (a public weather map of hardware calibration), **agent-native access** (an MCP server so AI assistants can search, load, and verify artifacts), **federation** (self-hosted instances syncing to the commons), the **verified Quantum CV**, and **capsule-backed publishing**. See [FRONTIERS.md](FRONTIERS.md).

And the machines themselves become citizens, not just backends: a **Device Registry** (a profile page for every QPU — including the invisible long tail of lab-built machines running merchant hardware), **self-hosted Quantum CI runners** (the GitHub Actions model, applied to QPUs), a capsule-backed commissioning **"birth certificate"** for hardware procurement, and opt-in **fleet telemetry** for chip makers. See [HARDWARE.md](HARDWARE.md).

## Repository map

| Path | What it is |
|---|---|
| [`VISION.md`](VISION.md) | The full whitepaper — the three pillars in depth |
| [`FRONTIERS.md`](FRONTIERS.md) | The next ring of ideas beyond the pillars |
| [`HARDWARE.md`](HARDWARE.md) | The hardware layer — where QPU makers and machine owners plug in |
| [`IMPLEMENTATION-PLAN.md`](IMPLEMENTATION-PLAN.md) | The phased engineering plan — architecture, build-vs-reuse, exit gates |
| [`FRONTEND-PLAN.md`](FRONTEND-PLAN.md) | The web frontend — design system, page inventory, quality bar |
| [`web/`](web/README.md) | The frontend itself — Next.js app: artifact pages, in-browser simulator, capsule verification |
| [`COMPETITIVE-LANDSCAPE.md`](COMPETITIVE-LANDSCAPE.md) | Honest map of adjacent projects and where the whitespace is |
| [`rfcs/`](rfcs/) | Open specifications, developed by public RFC (0001 Capsule · 0002 Card · 0003 addressing · 0004 devices · 0005 certificates · 0006 leaderboards · 0007 federation) |
| [`spec/`](spec/) | Machine-readable JSON Schemas backing the RFCs |
| [`client/`](client/) | `quantumverse` Python package + `qv` CLI — capsules, cards, simulator, diff, CI, push/pull |
| [`api/`](api/) | `qv-registry` — the reference registry server (FastAPI, SQLite, content-addressed blobs) |
| [`sim/`](sim/) | Rust statevector simulator, built natively and to WASM (no wasm-bindgen) |
| [`playground/`](playground/) | Zero-build in-browser **playground** (`index.html`) and **hub** (`hub.html`) — served by `qv-registry --web` over the live registry |
| [`seeds/`](seeds/) | Starter library: 9 circuits, 2 instances, 2 **converged** trained-parameters artifacts |
| [`quantumverse.ci.json`](quantumverse.ci.json) | This repo's own Quantum CI config (dogfooded in GitHub Actions) |
| [`docs/`](docs/index.html) | The self-contained pitch site (served via GitHub Pages) |
| [`docs/blog/`](docs/blog/how-a-quantum-job-travels.html) | Explainers — *How a Quantum Job Travels* (user → qubit → user, end to end) |

## Get involved

Publish one artifact. Argue with the spec. Star, watch, fork. The RFCs land in this repository first — see [CONTRIBUTING.md](CONTRIBUTING.md) for the dev setup and ground rules, and [LICENSE](LICENSE) (Apache-2.0) for the terms.

Code found its home. Models found their home. **Quantum is next.**
