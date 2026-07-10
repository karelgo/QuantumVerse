# Competitive Landscape

*A deliberately honest map of who else is in this space. Last reviewed: 2026-07. Corrections welcome by PR — if we've mischaracterized your project, open an issue.*

The wrong way to pitch a platform is "nothing like this exists." Something always exists. The right way is to know the field cold, name every adjacent effort fairly, and show precisely where the **whitespace** is. This document does that for QuantumVerse.

## TL;DR

Every one of QuantumVerse's three pillars has prior art — some of it serious. **No one has combined them.** The pieces are owned by different players and don't talk to each other:

- a catalog that lists circuits but can't run or verify them (**QCR**);
- a benchmark platform that verifies results but only for benchmarks (**Metriq**);
- an academic provenance system that models experiment records but isn't a shareable community platform (**QProv**);
- an in-browser simulator locked to one vendor's circuits (**IBM Composer**);
- curated datasets that are framework-locked and team-curated, not community-contributed (**PennyLane Datasets**).

QuantumVerse's bet is the **integration**: one framework-agnostic artifact layer where a circuit is discoverable *and* runnable-in-browser *and* backed by a verifiable capsule *and* socially forkable. That combination is the moat, not any single feature.

One honesty note up front: the **Experiment Capsule** ([RFC-0001](rfcs/rfc-0001-experiment-capsule.md)) is *not* a novel concept. Academic provenance systems have modeled the same `{circuit, device, compilation, execution}` bundle for years. Our contribution is productizing it — content-addressed, citable, replayable, and wrapped in network effects — not inventing it. That the need is already documented in the literature is evidence *for* the thesis, not against it.

---

## A. Hub analogs — sharing & discovering artifacts

| Project | What it is | Overlap | The gap |
|---|---|---|---|
| **QCR — Quantum Circuit Repository** · [qcrepository.org](https://qcrepository.org/) | The closest direct analog. Open-access, multi-framework (Qiskit/Cirq/PennyLane/Braket) repository to "share, discover, and reproduce" quantum circuits; a few hundred curated entries of code, guides, and papers. | The Hub's discovery/sharing job, across frameworks. | A **curated catalog** — no in-browser execution, no verification/capsules, no trained-parameters-as-artifacts, no versioning or social graph. Effectively a modernized [Algorithm Zoo](https://quantumalgorithmzoo.org/). |
| **PennyLane Datasets** · [pennylane.ai/datasets](https://pennylane.ai/datasets/) | Xanadu's curated quantum data: molecules, spin systems, Hamiltonians, Hartree-Fock states, and some VQE data. | "Datasets" and *some* trained parameters. Richer than a molecules-only library. | **Team-curated, not community-contributed**, and **PennyLane-framework-centric**. No verification, no social layer, no arbitrary user artifacts. |
| **Classiq Library** · [github.com/Classiq/classiq-library](https://github.com/Classiq/classiq-library) | "Largest collection of quantum algorithms," tied to Classiq's commercial high-level synthesis platform (Qmod). | A large algorithm collection. | Bound to a proprietary design tool; not a neutral, multi-framework hub. |
| **genQC / VQEzy / HF uploads** · [genQC](https://github.com/FlorianFuerrutter/genQC), [VQEzy (arXiv 2509.17322)](https://arxiv.org/pdf/2509.17322) | Researchers already host quantum circuit-synthesis **model weights on Hugging Face**; VQEzy is an open **VQE-parameter-initialization dataset**. | Direct evidence that "trained parameters / model weights as artifacts" is a real, active need. | One-off and scattered across generic hosts — no quantum-native platform unifying them. *Validates the demand we're targeting.* |

**Read:** the hub idea is proven (QCR, PennyLane) but everyone stops at a catalog. Nobody treats **trained parameters as a first-class, versioned, framework-agnostic, community-contributed artifact type** — the "`from_pretrained` for quantum" slot is genuinely open.

---

## B. Verification — provenance, reproducibility, benchmarks

This is our claimed wedge, so it deserves the most scrutiny. It has the most serious prior art.

| Project | What it is | Overlap | The gap |
|---|---|---|---|
| **QProv** · [IET Quantum Comm. paper](https://ietresearch.onlinelibrary.wiley.com/doi/10.1049/qtc2.12012), [github/UST-QuAntiL/qprov](https://github.com/UST-QuAntiL/qprov) | Academic provenance system (Univ. Stuttgart) capturing `{quantum circuit, quantum computer, compilation, execution}` and **periodically polling hardware calibration** from provider APIs. | **Strong prior art for both the Experiment Capsule and the Drift Observatory.** | A research system for provenance capture/analysis — not a community platform. No content-addressing, no cit/DOI, no sharing/forking, no network effects. |
| **QC-MM** · [Applied Sciences 2026](https://doi.org/10.3390/app16136346) | A metadata model for traceable circuit experiments: time-indexed calibration binding, transpilation traceability, provenance links, validation rules. | More capsule prior art, at the schema level. | A schema paper, not an implementation or platform. |
| **Metriq** · [metriq.info](https://metriq.info/), [Unitary Foundation](https://unitary.foundation/) | Community quantum benchmarking: `metriq-gym` (dispatches benchmarks to real hardware), `metriq-data` (versioned, **PR-reviewed** dataset), `metriq-web`. | **The biggest overlap with our Verification pillar** — and more automated than "self-reported." | Scoped to **benchmarks**, not general artifacts. No hub, no in-browser run, no capsules for arbitrary experiments. A partner to integrate, not fragment. |
| **QubiCSV / reproducibility papers** · [Reproducible Builds for QC (arXiv 2510.02251)](https://arxiv.org/abs/2510.02251), [Experiment Tracking (arXiv 2507.06990)](https://arxiv.org/abs/2507.06990) | Calibration/experiment data storage; build-integrity and experiment-tracking research for quantum software. | The reproducibility problem is a recognized, active research area. | Tools and papers, not a shared platform the community publishes *to*. |
| **Quantum Benchmark Zoo** · [quantumbenchmarkzoo.org](https://quantumbenchmarkzoo.org/) | A living survey/catalog of benchmarking protocols, metrics, and datasets. | Reference material adjacent to verified leaderboards. | A survey, not an execution/verification engine. |

**Read:** the reproducibility crisis is well-documented and partially addressed. QProv especially means our Capsule concept is **not new** — but nobody has turned provenance into a *citable, shareable, forkable artifact with a replay button and a social platform around it*. That productization is the contribution.

---

## C. Playground — in-browser execution

| Project | What it is | Overlap | The gap |
|---|---|---|---|
| **IBM Quantum Composer** · [quantum.cloud.ibm.com/composer](https://quantum.cloud.ibm.com/composer) | The incumbent browser experience: drag-drop builder, statevector sim, q-sphere/histograms, small circuits without login. | The "run it in your browser" moment. | **IBM-locked**; not attached to a cross-framework artifact library; not "run *any* shared artifact." |
| **Quirk** · [algassert.com/quirk](https://algassert.com/quirk) | Beloved open-source in-browser circuit simulator/toy. | Instant, install-free simulation. | Standalone sandbox — no hub, no persistence, no sharing-as-artifact. |
| **PsiQuantum Circuit Designer** | Open-access web app to build and share circuit *diagrams*. | Sharing + browser UI. | Diagram-sharing, not runnable verified artifacts. |

**Read:** in-browser simulation is solved technically (Quirk, Composer) but exists as **standalone tools**, never as the universal "Run" button on every artifact in a shared library.

---

## D. Access aggregators — adjacent, not competitors

These sell **access to hardware**, which we *route through* rather than replace.

| Project | What it is | Relationship |
|---|---|---|
| **qBraid** · [qbraid.com](https://www.qbraid.com/) | Cloud IDE; access to 34+ devices; **18+ SDK cross-framework conversion**; qBook learning. | Partner/backend. Note they already do the framework-conversion we depend on — potential integration, not rivalry. |
| **Strangeworks** · [strangeworks.com](https://strangeworks.com/) | "Largest catalog of quantum resources," consumption-based pricing, enterprise features. $24M Series A (2023). | Partner for execution/brokering. Sells *access*; we host *artifacts*. |
| **Azure Quantum · AWS Braket · IBM Quantum** | The hyperscaler/vendor clouds — hardware, SDKs, job submission. | Execution substrates we integrate with; none is a neutral, cross-vendor artifact hub. |

---

## E. Benchmark suites & problem instances

The standardized inputs a verified leaderboard would run — these are content to host, not competitors:

- **MQT Bench** ([arXiv 2204.13719](https://arxiv.org/pdf/2204.13719)) — TU Munich, benchmarks across abstraction levels.
- **QASMBench** — PNNL, low-level NISQ benchmark suite.
- **SupermarQ** ([paper](https://mrmgroup.cs.princeton.edu/papers/tomesh-supermarq.pdf)) — scalable, feature-based benchmark suite.
- **QED-C** — cross-industry consortium application-oriented benchmarks.

---

## F. Device identity & the hardware long tail

Who hosts the public record of a *machine*? Today: nobody, for most machines.

- **Vendor status pages** (IBM Quantum, IonQ, Rigetti…) show live calibration for **their own fleet only** — snapshots, not history, and gone the moment a device retires.
- **Aggregator device lists** (qBraid, Strangeworks, Braket, Azure) enumerate **what's rentable through them** — a commercial catalog, not an identity layer, and blind to anything off-cloud.
- **The merchant-hardware installed base is invisible.** [QuantWare](https://quantware.com/) alone has shipped QPUs to 50+ customers in 20 countries — labs building their *own* machines. Those devices appear on no list anywhere: no public identity, no benchmark record, no calibration lineage.

There is no vendor-neutral registry of quantum devices, no per-machine verified history, and no standard for capsule-backed commissioning/acceptance results. That's the whitespace [HARDWARE.md](HARDWARE.md) claims — the Device Registry, self-hosted runners, and the birth certificate — and it's uncontested for the same reason trained-parameters was: it only makes sense on top of an artifact + verification layer that doesn't exist yet elsewhere.

---

## The whitespace

Laid out as a matrix, the gap is obvious — every competitor owns one column:

| Capability | QCR | PennyLane DS | Metriq | QProv | Aggregators | IBM Composer | **QuantumVerse** |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| Framework-agnostic artifact hosting | catalog | centric | — | — | — | — | ✅ |
| Trained parameters as first-class artifacts | — | partial | — | — | — | — | ✅ |
| Reproducible experiment records (capsules) | — | — | partial | ✅ research | — | — | ✅ |
| Verified benchmarks | — | — | ✅ | — | — | — | ✅ |
| Semantic circuit diff / quantum CI | — | — | — | — | — | — | ✅ |
| In-browser execution of any artifact | — | — | — | — | IDE | vendor-locked | ✅ |
| Social layer (profiles, forks, orgs) | — | — | — | — | — | — | ✅ |
| QPU access brokering | — | — | via providers | — | ✅ | ✅ | integrates |

No competitor has more than one or two ✅. The thesis is that the **row-spanning integration** — not any single cell — is what compounds into a platform.

## What this means for our positioning

1. **Lead with integration, not novelty.** "The first platform to combine hosting + verification + execution," never "the first quantum artifact platform."
2. **Credit the prior art loudly.** Citing QProv, QC-MM, and Metriq makes us look rigorous and turns potential critics into potential collaborators. The Capsule's academic lineage is a feature.
3. **Integrate, don't fragment.** Metriq (benchmarks), qBraid/Strangeworks (access), and the benchmark suites are partners. The pitch to each: "you own your layer; we make it discoverable and composable."
4. **Guard the two open slots hardest.** Trained-parameters-as-artifacts and capsule-backed-social-verification are the least contested and most defensible ground. That's where to plant the flag first.
