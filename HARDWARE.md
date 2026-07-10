# The Hardware Layer

*Where the machines live — how hardware companies plug into QuantumVerse, and why the platform should give every QPU a home, not just every circuit.*

[VISION.md](VISION.md) treats hardware the way GitHub treats servers: as **substrate**. Devices are things the platform routes jobs *to* (execution adapters), gets signatures *from* (provider receipts), and pulls calibration data *out of* (the [Drift Observatory](FRONTIERS.md#1-the-drift-observatory)). That framing is correct — and incomplete. This document extends the concept with the missing half: **hardware as publisher**. Every physical QPU becomes a first-class citizen of the platform, the way models became citizens of Hugging Face.

> GitHub gave code a home. Hugging Face gave models a home. QuantumVerse gives quantum work a home — **and the machines that run it.**

---

## Two archetypes, two pitches

"Hardware company" is not one thing. The industry has split into two archetypes with opposite shapes, and a neutral platform has to serve both:

### The full-stack cloud vendor — *IonQ*

[IonQ](https://www.ionq.com/) is the vertically integrated model: they build trapped-ion systems, operate them, and sell **access** — through their own cloud, all major hyperscalers, and now rack-mountable on-prem systems ([Forte Enterprise](https://www.ionq.com/quantum-systems/forte-enterprise)) and a cloud-native workload platform (Tempo). Their [roadmap](https://www.ionq.com/roadmap) promises 2 million physical / 80,000 logical qubits by 2030.

What a company like this needs — and what no vendor can manufacture for itself — is **neutral credibility**. Every full-stack vendor publishes its own benchmark metric, and every metric is discounted by the market precisely because its author sells the machine. The existing pillars already serve this archetype: execution adapters route paying jobs to them, [provider-signed receipts](rfcs/rfc-0001-experiment-capsule.md) make their results the most trusted tier on the platform, and verified leaderboards let their hardware win arguments *they don't have to start*. The pitch: **stop grading your own homework — let the commons grade it, and sell against the result.**

### The merchant foundry — *QuantWare*

[QuantWare](https://quantware.com/) is the opposite shape: the **TSMC of quantum**. They don't sell compute — they sell the processors themselves, plus [foundry services](https://quantware.com/product/foundry-services) that fabricate other companies' qubit designs on their open [VIO architecture](https://quantware.com/technology), with an industrial-scale fab (KiloFab) opening in 2026 and a [$178M Series B](https://quantware.com/news/quantware-raises-178-million) behind it. They have shipped QPUs to **50+ customers in 20 countries** — making them the largest commercial QPU supplier by volume.

Read that last fact again, because it's the one the rest of this document is built on. Those fifty-plus customers are labs, startups, and institutes **building their own quantum computers**. Every one of those machines is a real QPU that exists *nowhere* on the map the software world can see: not on AWS or Azure, not on any aggregator's device list, not on any leaderboard. No public identity, no benchmark record, no calibration history. The merchant-hardware model is deliberately creating a **long tail of self-hosted QPUs** — and nobody serves that long tail. Not the clouds (these machines aren't theirs), not the aggregators (they list what's rentable), and, until this document, not QuantumVerse either.

That long tail is to quantum hardware what self-hosted git servers were to code in 2007: real, numerous, growing — and invisible. The platform that makes them visible wins them.

---

## 1. The Device Registry

*Now specified in [RFC-0004](rfcs/rfc-0004-device-records.md) and implemented in the reference registry: `qv device register/show/list/drift`.*

**What it is.** A profile page for every physical QPU on Earth — cloud-hosted or homebuilt. A **Device Card** is to a machine what a Circuit Card is to a circuit: identity (name, owner, institution), topology and native gate set, qubit modality, a live calibration timeline (the [Drift Observatory](FRONTIERS.md#1-the-drift-observatory), scoped to one machine), every verified [Capsule](rfcs/rfc-0001-experiment-capsule.md) ever minted on it, and **lineage** — which chip generation, which fab, which stack: *"64-qubit transmon · VIO architecture · fabricated at KiloFab · commissioned 2027-03."* `Device` becomes an artifact type alongside circuits and parameters, versioned like everything else (a recalibration is a patch release; a chip swap is a major version).

**Why it's novel.** Today a QPU's public existence is a marketing page if the vendor is large, and *nothing at all* if the machine was built by a lab from merchant hardware. There is no vendor-neutral registry of quantum machines — no place where "the field's installed base" is even enumerable. For IonQ, a Device Card is transparent marketing with a trust badge they can't print themselves. For a university lab running a QuantWare-based fridge, it's **the only public identity that machine will ever have** — citable in papers ("runs were performed on [qv:device/tudelft/aurora-64](#)"), linked from grant reports, discoverable by collaborators. And for the foundry itself, the registry is a live map of its installed base in the wild — the thing every component vendor wants and none can build alone, because it's the *customers'* machines.

**What it compounds.** The **credibility loop** — every capsule now points at a device page with history, so "we ran it on hardware" becomes a checkable claim about a specific, known machine. And the **status loop**, extended to institutions: labs compete on their machines' verified track records the way developers compete on contribution graphs.

---

## 2. Self-hosted Quantum CI runners

**What it is.** The GitHub Actions self-hosted-runner model, applied to QPUs. A lab registers its machine as a **runner**: a small agent that accepts dispatched jobs — community benchmark suites, [Quantum CI](VISION.md#5-pillar-ii--the-verification-layer) hardware smoke tests, capsule replays — executes them in idle time, and returns results as signed capsules. The device owner controls what runs, when, and how much; every completed job automatically updates the machine's Device Card and feeds the Drift Observatory.

**Why it's novel.** It inverts the economics of hardware access. The clouds and aggregators serve machines whose owners want to *sell time*. Runners serve machines whose owners want **proof** — a homebuilt machine with no public benchmark record is, to the outside world, indistinguishable from a machine that doesn't work. Registering as a runner is how a lab converts idle QPU-hours into verified, public, comparable evidence that its machine is real and healthy — and optionally into platform credits or bounty revenue. Meanwhile the platform acquires the thing money can't buy: a fleet of diverse, real hardware executing its verification workloads **without owning a single fridge**. IMPLEMENTATION-PLAN already models Quantum CI's runners on GitHub Actions; this extends the model from cloud adapters to the long tail.

**What it compounds.** The **reuse loop** (hardware smoke tests stop being gated on QPU budgets) and the **credibility loop** (leaderboards gain backends no aggregator lists). It is also the supply side the Device Registry needs: a registry entry is a claim, a runner is the claim *proving itself continuously*.

---

## 3. The Birth Certificate

**What it is.** A standardized, capsule-backed **commissioning suite**: randomized benchmarking, gate and readout fidelities, a fixed slice of the community benchmark sets (MQT Bench / QASMBench / SupermarQ), executed the day a machine comes online. The output is the machine's first entry in the Device Registry — a signed, content-addressed, publicly comparable record of what this machine could actually do on day one. Every subsequent recalibration appends to the same lineage; the birth certificate is the fixed point drift is measured against.

**Why it's novel.** QPU procurement is becoming real — governments, HPC centers, and enterprises are buying on-prem systems (IonQ's Forte Enterprise exists precisely because of this market), and a foundry ships processors to dozens of customers a year. Every one of those transactions currently closes on **vendor spec sheets and acceptance tests nobody outside the room can verify**. A capsule-backed commissioning suite is the vendor-neutral nutrition label: buyers write it into procurement contracts ("acceptance = birth certificate ≥ spec"), vendors ship it as the last step of installation, and a foundry like QuantWare can offer it with every QPU — *"verified on QuantumVerse"* as the industry's handover standard. No vendor can own this standard, because a standard owned by a vendor isn't one. A neutral commons can.

**What it compounds.** The **credibility loop**, upstream of research: verification stops being something that happens to *results* and starts being something machines are born into. It also hands the platform's specs their first commercial constituency — buyers with contracts that cite them.

---

## 4. Fleet telemetry

**What it is.** The Drift Observatory's B2B face. A hardware maker whose chips run inside other people's machines gets — **opt-in, owner-controlled, and aggregated** — field data on how its silicon actually behaves across the installed base: coherence-time distributions across fab batches, drift signatures by chip generation, failure precursors. Device owners choose what to share, per metric; in return they get fleet-relative context ("your T1 is in the 78th percentile for this chip generation") that an isolated lab can never compute alone.

**Why it's novel.** Component vendors in every mature industry pay heavily for field telemetry — and quantum's merchant vendors have none: once a QPU ships, the feedback loop is a support ticket. Nobody can build this dataset unilaterally; not the foundry (it's the customers' data), not any single lab (one machine is an anecdote, a fleet is a distribution). Only a neutral commons that already captures calibration snapshots in every capsule sits in the right place. This is also an honest open-core revenue line: the community data stays open, the *vendor-facing analytics* on top of it are the product — sustainability without withholding anything from the commons.

**What it compounds.** The **reuse loop**, at the hardware level — fab-to-field feedback makes the next chip generation better, which makes every downstream artifact better. And it makes hardware vendors structural *stakeholders* in the platform's health rather than logos on an integrations page.

---

## The two pitches, side by side

| | Full-stack cloud vendor *(IonQ)* | Merchant foundry *(QuantWare)* |
|---|---|---|
| What they sell | Access to their machines | The machines themselves |
| What they lack | Neutral credibility for performance claims | Any visibility into chips after they ship |
| Device Registry | Transparent marketing, trust badges | Live map of the installed base |
| CI runners | Demand channel for idle capacity | Their *customers'* machines become visible & provable |
| Birth Certificate | Procurement standard to sell against | Ships with every QPU — the handover standard |
| Fleet telemetry | Cross-fleet drift analytics | Fab-to-field feedback loop |
| What the platform gets | Signed receipts, backends, credits, credibility | The long tail: dozens of real, diverse devices |

Neither archetype is asked to change its business. The cloud vendor keeps selling access; the foundry keeps selling processors. The platform sells neither — it makes both **legible**, and takes its network effects in payment.

---

## The thread

The test from [FRONTIERS.md](FRONTIERS.md) applies here too: not "is it cool," but "does it compound something already turning." Each of these four ideas is the same decision — *capture the device, verify the claim, publish the format* — paid forward into the physical layer of the field. The Device Registry is the Drift Observatory given a face; runners are Quantum CI given hardware; the birth certificate is the Capsule given a commercial job; fleet telemetry is open data given a business model.

And one asymmetry worth naming: software platforms usually treat hardware companies as sponsors to court. This design makes them **users with a problem only the commons can solve** — credibility for one archetype, visibility for the other. That's a far stronger reason to show up than a partnership press release.

*The machines are already out there — fifty-plus customers in twenty countries from one foundry alone. The only question is whether the field can see them.*
