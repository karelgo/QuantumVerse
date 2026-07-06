# QuantumVerse

### The home for quantum artifacts — where circuits, results, and claims become shareable, runnable, and verifiable.

*A vision for the missing layer of the quantum computing ecosystem.*

---

## 1. The moment we're in

Every transformative developer platform arrived at the same instant in its field's history: the moment the community's output outgrew the community's tools for sharing it.

- In 2008, code outgrew tarballs and mailing-list patches. **GitHub** gave code a home, a social layer, and a unit of collaboration (the pull request).
- In 2019, machine learning outgrew "weights on a professor's FTP server." **Hugging Face** gave models a home, a standard artifact (the model card + weights), and a one-line way to use someone else's work (`from_pretrained`).

Quantum computing is at that moment **right now**. Thousands of researchers and engineers produce circuits, ansätze, benchmark results, error-mitigation recipes, and hardware experiments every week. And the way they share them is: a PDF, a screenshot of a circuit, and — if you're lucky — a zip file of framework-locked code that stopped running when the hardware was recalibrated.

There is no home for quantum work. QuantumVerse is that home.

---

## 2. The gap nobody owns

The quantum ecosystem today is rich but shattered:

- **Frameworks are silos.** Qiskit, Cirq, PennyLane, Braket, CUDA-Q, Q# — a circuit written in one is dead weight in another, even though OpenQASM 3 and QIR exist precisely to bridge them.
- **Hardware is a moving target.** Devices are recalibrated daily. A result produced on Tuesday may be unreproducible on Thursday — *on the same machine*. No other field of computing has this problem, and no platform addresses it.
- **Reusable work isn't reused.** A converged VQE ansatz for a molecule, a hardware-optimized transpilation, a tuned error-mitigation pipeline — these cost real money in QPU time and expertise. Today they evaporate when the paper is published. There is no `from_pretrained` for quantum.
- **Claims can't be checked.** "Quantum advantage" announcements arrive as press releases and papers. There is no live, community-verifiable scoreboard where a claim comes attached to the raw shots, the device snapshot, and a replay button.

Several projects hold a sliver of the answer — cloud aggregators give you *access*, benchmark sites collect *submissions*, dataset projects host *molecules*. Section 8 maps them honestly. But nobody owns the **artifact layer**: shareable, framework-agnostic, *verifiable* quantum objects, with the social gravity that makes a platform compound.

That layer is where GitHub-scale network effects live. That layer is QuantumVerse.

---

## 3. What QuantumVerse is

**One sentence:** QuantumVerse is an open platform where the quantum community publishes, discovers, runs, and verifies quantum artifacts — circuits, trained parameters, problem instances, noise models, and full reproducible experiments.

**One analogy:** GitHub gave code a social home. Hugging Face gave models a reusable form. QuantumVerse does both for quantum — and adds the thing quantum uniquely needs and neither predecessor had: a **verification layer**, because in quantum computing the hardware itself is part of the result.

The platform stands on three pillars.

---

## 4. Pillar I — The Hub

*Typed, versioned repositories for every reusable quantum object.*

A QuantumVerse repo isn't a folder of files; it's a **typed artifact** with structure the platform understands, renders, and validates. Artifacts are stored framework-agnostically — OpenQASM 3 and QIR as interchange formats — and exported to whatever framework the consumer uses.

### Artifact types

| Type | What it is | Why it matters |
|---|---|---|
| **Circuit / Algorithm** | A parameterized circuit or algorithm implementation, with a **Circuit Card** | The core unit of quantum work, finally portable and documented |
| **Trained Parameters** | Converged VQE / QAOA / QML parameters bound to an ansatz | The "pretrained weights" of quantum — expensive to produce, free to reuse. Nobody hosts these today |
| **Problem Instances** | Hamiltonians, molecules, spin models, QUBO/optimization benchmarks | The "datasets" of quantum — standardized inputs so results are comparable |
| **Noise Models** | Learned or measured device noise models | Realistic simulation without QPU access |
| **Compiled Circuits** | Hardware-specific transpilations with verified resource counts | Transpilation is expensive compute; share the result like Docker layers |
| **Experiment Capsules** | A complete, replayable experimental record (Pillar II) | The reproducibility primitive |

### The Circuit Card

Every circuit ships with a card — the model-card idea, adapted to what quantum users actually need to know before spending QPU dollars:

- **Resources:** qubit count, circuit depth, gate counts, T-count, two-qubit-gate count
- **Requirements:** connectivity assumptions, native gate sets targeted
- **Noise profile:** measured or estimated sensitivity; which error-mitigation strategies it was validated with
- **Verified results:** per-backend outcomes with links to the Experiment Capsules that back them
- **Provenance:** paper/DOI, authorship, license, lineage (forked from / distilled from)

### One line to use anyone's work

```python
pip install quantumverse

import quantumverse as qv

# Load a community circuit into your framework of choice
circuit = qv.load("grover/sat-3q", framework="qiskit")

# Load trained parameters — skip hours of optimization and QPU cost
ansatz, params = qv.load("vqe/h2o-ground-state", framework="pennylane")

# Load a benchmark instance everyone else is using
hamiltonian = qv.load("instances/lih-sto3g")
```

This is the `from_pretrained` moment for quantum. When reusing a stranger's converged ansatz is one line — and reproducing it from scratch is a week and a QPU budget — the hub becomes self-reinforcing: every consumer has a reason to become a publisher.

---

## 5. Pillar II — The Verification Layer

*The part GitHub and Hugging Face never needed. Quantum does.*

In classical computing, code *is* the result. In quantum computing, a result is code **plus** a specific device **plus** that device's state at a specific hour. Ignore that, and you get the field's open secret: most published quantum results cannot be independently reproduced. QuantumVerse makes verifiability a first-class platform primitive — this is our deepest moat and our largest contribution to the field.

### Experiment Capsules

A **Capsule** is a content-addressed, immutable bundle capturing everything needed to understand — and re-attempt — a quantum experiment:

```
capsule/
├── circuit.qasm            # abstract circuit (OpenQASM 3)
├── compiled.qasm           # exact transpiled circuit that ran
├── device.json             # backend identity + full calibration snapshot
│                           #   (T1/T2, gate fidelities, readout errors, topology)
├── execution.json          # shots, raw counts, timestamps, job IDs
├── mitigation.json         # error-mitigation pipeline, exactly as applied
├── environment.lock        # framework + SDK versions
└── receipt.sig             # optional provider-signed execution receipt
```

A Capsule is a *git commit for a quantum experiment*: hash-addressed, citable (DOI-mintable), forkable, and replayable ("re-run this capsule on today's calibration and diff the outcomes"). For the first time, "as reported in our paper" can be a link instead of a promise — and journals, reviewers, and grant agencies become a natural distribution channel, because Capsules solve *their* problem too.

### Semantic circuit diffs

GitHub diffs text. QuantumVerse diffs **unitaries**. Using ZX-calculus-based equivalence checking, the platform can tell you what a text diff never can:

> ⚡ 14 gates changed, depth reduced 31% — **circuits are equivalent** up to global phase.

An optimization PR that provably preserves semantics is a green badge, not an argument in the comments.

### Quantum CI

On every push, the platform runs the checks the quantum workflow actually needs:

1. **Equivalence check** against the reference circuit (ZX-calculus / simulation cross-validation)
2. **Resource regression** — fail the build if depth, qubit count, or T-count exceeds budget
3. **Simulator validation** — expected outcome distributions within tolerance
4. **Hardware smoke tests** (optional, metered) — scheduled runs on real QPUs, producing fresh Capsules automatically

### Verified leaderboards

Standardized benchmark suites, executed automatically and recurringly across providers, with results anchored to signed Capsules. Think *Papers with Code, for quantum* — but where entries are machine-verified rather than self-reported. The endgame: when the next "quantum advantage" claim lands, the community's first question is *"where's the capsule?"* — and QuantumVerse is where they ask it.

---

## 6. Pillar III — The Playground

*The viral surface. Nobody shares a platform; everybody shares a demo.*

### Run everything, install nothing

Every circuit page on QuantumVerse has a **Run** button. A WebAssembly statevector simulator executes circuits up to ~20–25 qubits *in the browser* — live statevector, Bloch spheres, measurement histograms, no signup, no install. The gap between "found an interesting circuit" and "watched it run" is one click. That's the moment Hugging Face Spaces nailed for ML, delivered for quantum.

### Embeddable everywhere

Any circuit or Capsule embeds as a live, runnable widget in blogs, docs, arXiv HTML, and course pages. Every embed is an inbound door. Quantum educators — a large, underserved, highly motivated community — get their best teaching tool for free, and become the platform's first evangelists.

### Circuit Golf

Competitive circuit optimization: a target unitary, a scoreboard, and automatic verification. Fewest gates wins; lowest depth wins; best fidelity-under-noise wins. Anyone can post a challenge (optionally with a bounty); the platform's equivalence checker is the referee. Code golf built a culture; unitaryHACK proved quantum has the appetite. Circuit Golf gives the community its game — and quietly crowdsources world-class circuit optimization.

### The Hardware Readiness Meter

Every algorithm page answers the question every visitor silently asks: *when does this become real?* Using resource estimates (logical qubits, T-count) against published hardware roadmaps:

> **Shor-2048** — needs ~4,000 logical qubits · projected runnable: **~2033** ▓▓▓░░░░░░░ 27%

GitHub shows you code. QuantumVerse shows you **when your code becomes runnable** — a feature with no analog anywhere, and a magnet for press, educators, and policymakers alike.

---

## 7. Why this can catch on (the honest version)

Platforms don't win on features; they win on **compounding loops**. QuantumVerse is designed around four:

1. **The reuse loop** *(Hub)* — Loading trained parameters saves real QPU money → consumers publish so others reciprocate → more artifacts → more reasons to come.
2. **The credibility loop** *(Verification)* — Capsules make results citable and checkable → researchers link them in papers → readers arrive at QuantumVerse → their next experiment ships as a Capsule.
3. **The education loop** *(Playground)* — In-browser running makes it the easiest place to *learn* quantum → courses embed it → every student is a future publisher.
4. **The status loop** *(Community)* — Verified badges, leaderboard ranks, and golf trophies are portable reputation in a young field where reputation is scarce and precious.

And one structural advantage: **the field is small enough to win.** GitHub needed millions of users to tip; the active quantum community is tens of thousands of people who all read the same arXiv listings and attend the same five conferences. A platform that becomes indispensable to 5,000 of them has effectively won the category — before the field's growth curve goes vertical.

---

## 8. Ecosystem positioning

QuantumVerse complements the frameworks and hardware providers — it's the layer *between* them. Against existing platforms, the honest map:

| | Cloud aggregators (Strangeworks, qBraid) | Metriq | PennyLane Datasets | Algorithm Zoo | **QuantumVerse** |
|---|---|---|---|---|---|
| Framework-agnostic artifact hosting | — | — | PennyLane-centric | — | ✅ core |
| Trained parameters as artifacts | — | — | partial | — | ✅ core |
| Reproducible experiment records | — | — | — | — | ✅ **Capsules** |
| Verified (not self-reported) benchmarks | — | self-reported | — | — | ✅ core |
| Semantic circuit diff / quantum CI | — | — | — | — | ✅ core |
| In-browser execution of any artifact | IDE-based | — | — | — | ✅ core |
| Social layer (profiles, forks, orgs) | — | — | — | — | ✅ core |
| QPU access brokering | ✅ their core | — | — | — | integrates, doesn't compete |

The aggregators sell *access*; we host *artifacts* — and route execution through them, making them partners rather than rivals. Metriq pioneered community benchmarking; we'd rather integrate and automate its mission than fragment it. The zoo is a beloved static index; QuantumVerse is what its entries link *to*.

---

## 9. Open source, open governance

QuantumVerse only works as a community institution. The founding commitments:

- **Open core.** The platform, the `quantumverse` client, the artifact and Capsule specifications: Apache-2.0, developed in the open, from day one.
- **Open spec first.** The Capsule and Circuit Card formats are published as standalone specifications anyone can implement — the formats should outlive any one host, and neutrality is what earns hardware vendors' participation.
- **Open data.** Public artifacts are bulk-downloadable. No lock-in; leaving must always be easy — that's *why* nobody will want to.
- **Community governance.** A technical steering group spanning academia, vendors, and independent developers governs the specs; benchmark methodology changes happen by public RFC.

Sustainability, in one paragraph: the open-core path that funded GitHub and Hugging Face — free forever for public artifacts and community use; later, paid private hosting for companies, managed Quantum CI minutes, and enterprise features. Nothing in the community offering is ever the product being withheld.

---

## 10. Roadmap

**Phase 0 — The Manifesto** *(now)*
This document, the pitch site, and the founding conversations. Recruit 10–20 respected early voices from the QOSF / unitaryHACK / framework-dev communities as founding contributors.

**Phase 1 — The Hub + Playground** *(months 1–6)*
Artifact repos for circuits, parameters, and instances; Circuit Cards; the `quantumverse` Python client with Qiskit/Cirq/PennyLane export; in-browser WASM simulator on every circuit page. **Seed strategy:** mirror the Algorithm Zoo as runnable circuits, import open Hamiltonian/QUBO benchmark sets, and hand-curate 50 flagship artifacts so day-one visitors find a living library, not an empty shelf.

**Phase 2 — The Verification Layer** *(months 6–14)*
Capsule format v1 + capture SDK; semantic circuit diffs; Quantum CI; first automated verified leaderboard (start narrow: one benchmark suite, three backends, unimpeachable methodology). Launch Circuit Golf. Court two journals to pilot "Capsule required" for hardware-results papers.

**Phase 3 — The Institution** *(months 14+)*
Provider-signed execution receipts with hardware partners; organizations and private repos; bounty marketplace; embeddable widgets everywhere; DOI minting; the readiness meter fed by community-maintained roadmap data.

---

## 11. The ask

If this vision resonates:

- **Researchers & developers:** publish one artifact. One circuit, one converged ansatz, one benchmark instance. The library starts with you.
- **Framework & hardware teams:** talk to us about interchange formats and signed receipts. Neutral infrastructure only works if it's *actually* neutral — help us keep it that way.
- **Educators:** tell us what the embeddable playground needs to replace your slide screenshots.
- **Everyone:** star, watch, argue. The spec RFCs land in this repository first.

Code found its home. Models found their home. **Quantum is next.**
