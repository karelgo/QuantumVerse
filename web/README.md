# QuantumVerse web

The product frontend from [FRONTEND-PLAN.md](../FRONTEND-PLAN.md): Next.js App Router, the pitch site's design tokens (same Fraunces woff2, same brass palette, light + dark), no component library, no CSS framework, hand-rolled SVG.

```bash
npm install
npm run dev      # http://localhost:3000
npm run build    # production build + typecheck
npm run seal     # re-seal capsules after editing registry/capsules/**
```

## How it connects to the rest of the system

- **Registry (data).** `registry/` is the Phase-0 filesystem registry from the [implementation plan](../IMPLEMENTATION-PLAN.md): typed artifacts (`artifacts/{owner}/{name}/manifest.json` + `circuit.qasm` [+ `params.json`]) and RFC-0001 capsules (`capsules/*/`). Circuit Card resources (qubits, depth, gate mix, T-count) are **computed from the QASM bytes** at read time, never hand-entered.
- **The Hub API seam — now live.** Pages read through [`lib/api.ts`](lib/api.ts). With `QV_API_URL` unset they hit the local registry; point it at a running `qv-registry` (the FastAPI service in [`api/`](../api/)) and no page changes — the registry serves these exact shapes at `/api/hub/v1/*` ([`api/src/quantumverse_api/frontend.py`](../api/src/quantumverse_api/frontend.py)):

  ```bash
  qv-registry --data ./data --port 8000 &          # from the repo root, seeded via seeds/import.py
  QV_API_URL=http://127.0.0.1:8000/api/hub npm run dev
  ```
 The same shapes are served *by* this app at `/api/v1/artifacts[...]`, `/api/v1/capsules/{digest}`, `/api/v1/owners/{handle}` — so the `quantumverse` Python client can develop against this app today.
- **RFC-0001 for real.** Capsule pages recompute every file digest and the capsule ID over canonical JSON ([`lib/canonical.ts`](lib/canonical.ts)) and verify Ed25519 author signatures against the key on the owner's profile — the trust tiers in the spec, rendered. [`scripts/seal-capsules.mjs`](scripts/seal-capsules.mjs) is the sealing counterpart (a proto `qv capsule validate`).
- **The simulator seam.** The Run button parses OpenQASM 3 ([`lib/qasm.ts`](lib/qasm.ts)) and runs a dense statevector simulation ([`lib/sim.ts`](lib/sim.ts)) in a lazily-created Web Worker, ≤20 qubits. The planned Rust→WASM engine replaces `lib/sim.ts` behind the same worker message shape.
- **Identity.** `public/fonts/fraunces.woff2` is extracted from `docs/index.html` — byte-identical to the pitch site's embedded font; tokens in [`app/globals.css`](app/globals.css) are copied verbatim.

## Layout

```
app/            routes: home · /search · /{owner} · /{owner}/{artifact}[@ver]
                · /capsule/{digest} · /embed/{owner}/{artifact} · /api/v1/*
components/     ~12 components (CircuitSVG, RunPanel, Histogram, CodeTabs, …)
lib/            qasm parser · layout/resources · simulator · codegen ·
                canonical JSON · registry (fs) · api seam
workers/        sim.worker.ts (off-main-thread execution)
registry/       seed artifacts, owners, sealed capsules
```
