# QuantumVerse RFCs

The formats and protocols that QuantumVerse runs on are developed here, in the open, before any implementation is considered stable. This is the "open spec first" commitment from [VISION.md](../VISION.md) §9 made concrete: the specs should outlive any one host, and neutrality is what earns the ecosystem's participation.

## Process

Deliberately lightweight:

1. **Propose** — open a pull request adding `rfc-NNNN-short-name.md` (next free number). Use [RFC-0001](rfc-0001-experiment-capsule.md) as a template for tone and structure: motivation first, schemas second, open questions last.
2. **Review** — discussion happens on the PR. Anyone may comment; substantive objections must be answered in the text, not just the thread.
3. **Decide** — the technical steering group merges when rough consensus is reached. Merging at status **Draft** means "stable enough to prototype against," not "finished."

## Statuses

| Status | Meaning |
|---|---|
| **Draft** | Open for breaking changes; prototype against it, don't ship against it |
| **Review** | Feature-frozen; call for final objections |
| **Accepted** | Stable; changes require a superseding RFC |
| **Superseded** | Replaced — header links to the successor |

## What needs an RFC

Anything another implementation would have to interoperate with: artifact formats, manifest schemas, signature and receipt protocols, replay semantics, federation APIs, benchmark methodology. UI, copy, and internal implementation details do not.

## Index

| RFC | Title | Status |
|---|---|---|
| [0001](rfc-0001-experiment-capsule.md) | Experiment Capsule format | Draft |
