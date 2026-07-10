---
name: verify
description: Build, launch, and drive the QuantumVerse web app (web/) to verify changes end-to-end.
---

# Verifying QuantumVerse

The runnable surface is the Next.js app in `web/` (plus its JSON API). Everything else in the repo is docs/spec — no runtime surface.

## Build & launch

- `cd web && npm install` (Node 22+). Production check: `npm run build` — it typechecks; treat a red build as a finding.
- Dev server: use the browser preview tool with the `web` config in `.claude/launch.json` (`npm run dev --prefix web`, port 3000). Don't run `next dev` via raw Bash.
- After editing capsule seed data under `web/registry/capsules/`, run `npm run seal` (recomputes digests, capsule IDs, Ed25519 signature; idempotent). Skipping it makes every capsule page show "tampered".

## Flows worth driving

1. **Run button** (the product): `/quantumverse/grover-3` → Run → histogram must spike at `101` ≈ 94–95%. Bell (`/quantumverse/bell-state`) → ~50/50 on `00`/`11`, no cross terms. QFT (`/quantumverse/qft-4`, no measure ops) → Statevector tab shows all 16 amplitudes at exactly 0.2500.
2. **Capsule integrity**: `/capsule/7b49ce` → green ✓ on ID recompute + Ed25519 signature. Tamper probe: edit a byte in `web/registry/capsules/ghz8-aer-8192/execution.json`, reload → ID goes red and exactly that file flags ✗ (restore the byte after; digest must match again).
3. **L1 replay**: same capsule page → Replay → verdict band should read Consistent, TV distance ≈ 0.03–0.06 (the seeded noise floor).
4. **API contract**: `curl localhost:3000/api/v1/artifacts?q=…`, `/api/v1/artifacts/{owner}/{name}`, `/api/v1/capsules/7b49ce` — detail must include computed `resources` and `integrity`; unknowns → 404 JSON.
5. **No-JS readability**: `curl` any artifact page and grep for `role="img" aria-label="Quantum circuit` — the SVG must be in server HTML.
6. **Both themes + mobile**: resize to mobile and check `document.documentElement.scrollWidth <= clientWidth` (no horizontal page scroll — circuits scroll inside `.circuit-scroll` only).
7. **OG cards**: `curl -o /dev/null -w "%{content_type}" localhost:3000/quantumverse/grover-3/opengraph-image-*` → image/png (route hash suffix: grep the page HTML for `og:image`). Description glyphs are sanitized (no ⟩/≈ tofu).
8. **Replay overlay**: on a capsule page, Replay → Counts tab shows filled bars (replay) with dashed outline bars (recorded) + legend. Mitigated tab on the execution histogram overlays raw the same way.
9. **Bloch physics**: GHZ → every qubit reads x=y=z=0, |r|=0. Grover-3 statevector: |101⟩ amp ≈ 0.9723 (94.5%).
10. **Embed handshake**: append an iframe pointing at `/embed/quantumverse/bell-state` and await a `qv:embed-height` postMessage.
11. **Keyboard**: `r` runs the visible circuit; `/` focuses search; a Skip-to-content link is first in tab order.

## Gotchas

- Next inlines the not-found boundary into every page's flight payload — grepping HTML for "No such artifact" matches on **every** page. Use HTTP status codes (or grep for real content) to test 404s.
- Worker results are async: after clicking Run via eval, wait ~500ms before reading `.hist` / `.amp-table`.
- `QV_API_URL` env switches `lib/api.ts` from the filesystem registry to a remote Hub API; unset for local verification.
