# Frontend Plan

*The web frontend of QuantumVerse — the `web/` box in the [implementation plan's architecture](IMPLEMENTATION-PLAN.md#system-architecture), specified. What we build, what it looks like, and the bar it has to clear.*

> **Status:** the first implementation lives in [`web/`](web/README.md) — Phase 0 plus the Phase 1/2 core surfaces (artifact pages, search, profiles, Run panel with statevector/Bloch views, auto-sizing embeds, OG share cards, capsule pages with live integrity verification and L1 replay overlaid on the recorded counts). The Rust→WASM sim and leaderboards remain open. One deviation: a single disciplined global stylesheet instead of CSS Modules — closer to the pitch-site ethos in practice.

The pitch site ([`docs/index.html`](docs/index.html)) already proved the identity: editorial serif headlines, one brass accent, chip-dark code, hand-drawn SVG diagrams, zero framework chrome. The product frontend inherits that identity and applies it to real artifacts. The organizing idea:

> **Every page is a document, not a dashboard.** An artifact page should read like a beautifully typeset paper that happens to be runnable — not like a cloud console. GitHub won because a repo page is *legible*. We win the same way.

## Design principles

1. **Content is the interface.** The circuit, the card, the capsule *are* the page. Chrome (nav, sidebars, toolbars) stays under 10% of the viewport. No hero banners inside the app.
2. **One accent, used sparingly.** Brass (`--accent`) marks exactly two things: links and the primary action on a page (usually **Run**). Everything else is ink, muted ink, and lines. Verification state is the only other color: green for verified, nothing for unverified — absence is the signal.
3. **Readable without JavaScript.** Every content page (artifact, capsule, device, leaderboard, profile) server-renders completely: circuit rendered as static SVG, card as HTML, counts as text. JS adds the Run panel, live search, and diff interaction — it never gates reading. This is also what makes pages citable, crawlable, and archivable, which for a *verification* platform is a product feature, not a nicety.
4. **The URL is the state.** Version pinned, framework tab selected, diff range, leaderboard filter — all in the URL. Any view a user can see, they can send.
5. **Motion means something.** One transition speed (150ms), used only for state changes (sim results appearing, diff toggling). `prefers-reduced-motion` honored everywhere. Nothing animates on scroll.
6. **Dark and light from commit one.** The token sheet already defines both; components that only work in one theme don't merge.

## Design system

Phase 0 of the implementation plan already calls for extracting the pitch site's tokens into a shared package. That package (`web/tokens`) is the *entire* theming layer:

| Layer | Decision |
|---|---|
| Tokens | The pitch site's CSS custom properties, verbatim: `--bg/--surface/--ink/--muted/--line/--accent/--good/--code-*`, Fraunces + system sans + mono stacks, the card shadow. Light + dark via `prefers-color-scheme` with a manual override. |
| Type scale | Four sizes only: display (Fraunces, artifact/section titles), body, small (metadata), mono (code, counts, hashes). If a design needs a fifth, the design is wrong. |
| Spacing | One 4px-base scale. Layout via CSS grid + `clamp()`, no breakpoint zoo. |
| Components | Built in-repo on the tokens. **No component library** (no MUI/Radix/shadcn), **no CSS framework** (no Tailwind) — plain CSS Modules. The pitch site styles ~800 lines of vanilla CSS beautifully; the app doesn't need more machinery, and every dependency we skip is identity we keep. |
| Charts & diagrams | Hand-rolled SVG, like the pitch site's drift chart and circuit wires. No charting library. Circuits render server-side to SVG (wires in `--wire`, gates in `--surface` boxes) — the pitch-site aesthetic, generated from QASM. |

## Stack

- **Next.js (App Router) + TypeScript**, per the implementation plan. Content pages are React Server Components — static or cached-per-version (artifact versions are immutable, so cache forever by digest). Interactive surfaces are client islands.
- **JS budget: ≤ 70 KB gzipped** on content pages before interaction. The WASM simulator (~1–2 MB) loads **lazily in a Web Worker** only when Run is pressed — never in the critical path, never blocking the main thread.
- **Data:** the Hub REST/GraphQL API. No client state manager; server components + URL state cover it.
- **Search:** server-rendered results page first; the `/` -to-focus instant-search overlay is an enhancement on top of the same endpoint.

## Information architecture

URLs mirror `qv:` artifact addressing (RFC-0003) — the page *is* the artifact's address:

```
/                              Home: search + curated flagship artifacts (a library desk, not a feed)
/{owner}                       Profile / org — artifacts, capsules, signing keys, the Quantum CV
/{owner}/{artifact}            Artifact page — THE page (Circuit Card, code, Run, versions)
/{owner}/{artifact}@{version}  Pinned version (immutable, cached forever)
/{owner}/{artifact}/diff/{a}..{b}   Semantic diff view
/capsule/{digest}              Experiment Capsule — the citable unit
/devices · /devices/{id}       Device Registry + Device Card (per-machine drift timeline)
/leaderboards/{suite}          Verified leaderboard
/search?q=                     Search with typed filters (kind:circuit qubits:<20 ...)
/embed/{owner}/{artifact}      Chromeless runnable widget for papers, blogs, courses
```

Eight page types. Anything else must displace one of these.

## The pages that matter most

**The artifact page** is the product. Single column, document order: title + one-line claim → **Circuit Card** (RFC-0002 rendered: resource counts, provenance, license, verification badges) → circuit as SVG → code with framework tabs (QASM 3 canonical; qiskit/cirq/pennylane exports) and a copy-ready `qv.load(...)` line → **Run** → versions and forks. A stranger should grasp *what this circuit is and whether it's verified* in five seconds, and run it in ten.

**The Run panel** is the viral surface, so it gets the finish: press Run → worker + WASM load behind a progress shimmer → histogram bars grow in (the one earned animation) → tabs for counts / statevector / Bloch. Degrades honestly: >25 qubits shows the cloud-sim handoff instead of a dead button. The embed route is this panel alone — that's what gets pasted into arXiv HTML and course pages.

**The capsule page** is the credibility surface: verification tier badge (unsigned / author-signed / provider-verified), the content-addressed manifest as an inspectable tree, device calibration snapshot *vs. that device today* (one sparkline — the Drift Observatory in miniature), raw shots, replay actions, and a copy-paste citation block with DOI.

**The diff view** is where semantic diffs become legible: side-by-side circuit SVGs, changed gates tinted, and one plain-language verdict line — *"14 gates changed, depth −31%, equivalent up to global phase"* — with the resource delta as small mono badges. This line is also exactly what Quantum CI posts back to pull requests.

## Component inventory

The whole app is ~14 components; each has one job and both themes:

`CircuitCard` · `CircuitSVG` (QASM→SVG, server-side) · `ResourceBadges` (qubits/depth/T-count mono chips) · `CodeBlock` (framework tabs, copy, chip-dark in both themes) · `RunPanel` (worker + WASM host) · `Histogram` / `BlochSphere` (SVG) · `DiffView` · `VerificationBadge` (trust tiers) · `CapsuleManifestTree` · `DriftSparkline` · `LeaderboardTable` (sortable, server-rendered) · `DeviceTopology` (coupling-map SVG) · `SearchBar`.

## The bar ("superb," measured)

| Dimension | Budget — CI-enforced, not aspirational |
|---|---|
| Performance | LCP < 1.5s on 4G for artifact pages; JS ≤ 70 KB gz pre-interaction; WASM lazy, off-main-thread; Lighthouse ≥ 95 perf/a11y as a CI gate |
| Accessibility | WCAG 2.2 AA; full keyboard paths (`/` search, `r` run); circuit SVGs carry text alternatives ("H on q0; CNOT q0→q1; …"); histogram values in an sr-only table |
| Sharing | Every artifact/capsule gets a generated OG image — mini circuit + counts on the brass identity. The share card is most people's first impression of the platform |
| Honesty in UI | Lossy conversions labeled at the point of copy; unverified means *no* badge, never a fake-reassuring gray check; sim limits stated, not discovered |

## What we deliberately don't build

No component library, no CSS framework, no client state manager, no infinite scroll, no notification center, no onboarding tours, no cookie-banner-requiring analytics (privacy-preserving counts only), no comment threads (discussion lives in RFCs/GitHub until the community demands otherwise). Each of these is a decision we can reverse the day evidence demands it — the point is to start from zero and earn additions, matching the platform's own thesis: absence of clutter is what makes verification legible.

## Phasing (tracks [IMPLEMENTATION-PLAN.md](IMPLEMENTATION-PLAN.md))

| Phase | Frontend ships | Exit gate |
|---|---|---|
| **0** | `web/tokens` extracted from the pitch site; `CircuitSVG` + `CodeBlock` + `CircuitCard` in a bare component gallery, both themes | Gallery renders a real RFC-0001 capsule's circuit from QASM, light + dark, no JS required |
| **1** | Artifact page, profile, search, home; **RunPanel** + embed route; OG images | A stranger reads, runs, and shares an artifact link that unfurls with a circuit card; budgets green in CI |
| **2** | Capsule page, diff view, leaderboard, Device Cards + drift sparklines; CI verdict lines | A capsule page is the canonical citation target a journal pilot can point at |
| **3** | Org/billing surfaces, Circuit Golf (leaderboard + diff, recombined), embed hardening for federation | Embeds render from self-hosted instances unchanged |

---

*Living document, like the rest — revise by PR. The identity it extends is in [`docs/index.html`](docs/index.html); the system it fronts is in [IMPLEMENTATION-PLAN.md](IMPLEMENTATION-PLAN.md); the strategy both serve is in [VISION.md](VISION.md).*
