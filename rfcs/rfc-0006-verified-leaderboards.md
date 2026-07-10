# RFC-0006: Verified leaderboards

| | |
|---|---|
| **Status** | Draft |
| **Version** | 0.1 |
| **Discussion** | this repository's issues/PRs |
| **Schema** | [`spec/schemas/leaderboard.schema.json`](../spec/schemas/leaderboard.schema.json) |
| **Motivation** | [VISION.md Pillar II](../VISION.md#5-pillar-ii--the-verification-layer) — *Papers with Code for quantum, machine-verified instead of self-reported* |

## Summary

A **leaderboard** binds a problem-instance artifact (RFC-0003 reference) to a scoring **metric**, and accumulates **entries** — each of which is nothing but an [Experiment Capsule](rfc-0001-experiment-capsule.md) id. Everything a ranking displays is recomputed by the registry from the capsule's raw counts and the instance definition; nothing about a score is ever taken from the submitter.

## Design rules

1. **An entry is a capsule id. Full stop.** No self-reported numbers exist anywhere in the format. The registry loads the capsule from its own store (unknown capsules are rejected — push first), resolves the pinned instance version from its own store, recomputes the score from `counts_raw`, and stores its own result.
2. **Trust rides along.** Each entry carries the capsule's RFC-0001 trust level (0 unsigned / 1 author-signed / 2 provider-verified). Boards render the badge; consumers filter by it. A "verified leaderboard" in the VISION.md sense is this board filtered to level ≥ 2.
3. **Boards pin exact instance versions.** `instance` is a fully-versioned RFC-0003 reference; scores across a board are comparable because every entry was scored against byte-identical inputs.
4. **Metrics are registered, not embedded.** A metric name refers to a scoring rule in this spec (implemented in `client/src/quantumverse/leaderboard.py`, the reference). Boards cannot ship arbitrary scoring code.

## Board definition

```json
{
  "board_version": "0.1",
  "name": "maxcut-triangle",
  "title": "MaxCut on K3 — expected cut ratio",
  "instance": "qv:instances/maxcut-triangle@1.0.0",
  "metric": "maxcut-ratio",
  "higher_is_better": true
}
```

## Metrics (v0)

| Metric | Applies to | Definition |
|---|---|---|
| `maxcut-ratio` | `maxcut` instances | Expected cut value of the measured bitstring distribution over the instance's known `max_cut_value`. Node *i* is qubit *i*; bitstrings render qubit *n−1 … 0* (platform convention). Every counted bitstring must be exactly *n* bits wide. |

Metrics that need more than Z-basis counts (energy expectations with X/Y terms, fidelities requiring tomography) are deliberately out of v0; they arrive with multi-capsule entries in a future revision.

## Entries

Stored per entry, all registry-derived:

```json
{
  "capsule": "sha256:…",
  "score": 0.999032,
  "shots": 4096,
  "backend": "quantumverse/qv-sim",
  "trust": 1,
  "submitted": "2026-07-10T15:30:00Z"
}
```

One entry per capsule per board (resubmission is idempotent). Ranking sorts by score in the board's declared direction; ties break toward higher trust, then earlier submission.

## HTTP mapping

```
POST /api/v1/leaderboards                        create (409 if name exists)
GET  /api/v1/leaderboards                        list definitions + entry counts
GET  /api/v1/leaderboards/<name>                 definition + ranked entries
POST /api/v1/leaderboards/<name>/entries         {"capsule": "sha256:…"}
```

## Open questions

1. **Recurring execution.** The VISION.md endgame is boards whose entries are *produced* by scheduled platform runs, not just submitted. That needs metered hardware execution — Phase 3 territory. The format here doesn't change: scheduled runs mint capsules and submit them like anyone else.
2. **Multi-basis metrics.** Energy leaderboards need grouped measurement capsules (one entry = several capsules). Extend entries to capsule *sets*?
3. **Anti-gaming.** For sampling-based metrics, a submitter can cherry-pick seeds. Minimum-shots floors per board, and surfacing shots prominently, are the v0 mitigations; statistical audit (replay sampling) is future work.
