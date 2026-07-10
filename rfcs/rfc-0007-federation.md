# RFC-0007: Federation

| | |
|---|---|
| **Status** | Draft |
| **Version** | 0.1 |
| **Discussion** | this repository's issues/PRs |
| **Schema** | [`spec/schemas/federation-catalog.schema.json`](../spec/schemas/federation-catalog.schema.json) |
| **Motivation** | [FRONTIERS.md §3](../FRONTIERS.md#3-federation) |

## Summary

A QuantumVerse registry is a content-addressed store. **Federation** is syncing between two of them: a self-hosted instance (a lab, a company, a national facility) keeps sensitive work private and publishes finished, public objects to another instance — like a git remote pushing to a shared upstream. Because [every format is an open spec first](../VISION.md#9-open-source-open-governance) and every object is content-addressed, a capsule that crosses the boundary is **byte-identical** to the original: same id, free deduplication, provenance intact.

## Design rules

1. **Sync transfers objects; the destination re-derives everything else.** A peer sends artifacts, capsules, device records, board definitions, and the *capsule ids* that make up certificates and leaderboard entries — never a card's resource counts, never a certificate verdict, never a leaderboard score. The destination recomputes all of those from the transferred bytes exactly as it would for a local upload (RFC-0002/0005/0006). A malicious or buggy peer therefore cannot inject a false score or a forged card; the worst it can do is offer a capsule the destination will validate and reject.
2. **Content addressing makes sync idempotent and safe.** An object already present (same digest / same capsule id / same artifact version) is skipped. Re-running a sync converges; running it against many peers merges without conflict; a capsule authored on one instance and synced through three others keeps one identity everywhere.
3. **Only public objects cross.** A registry exposes exactly what it chooses to federate through its catalog. Private artifacts simply never appear in it. Federation is opt-in per object, structurally — there is no "sync everything including drafts" mode.
4. **Signatures survive the crossing.** `author.sig` / `receipt.sig` are part of the transferred capsule files, so an author-signed capsule stays level 1 after syncing; the signature verifies against the same content-addressed id on the destination.

## The catalog

A federating registry exposes a catalog — the list of what it offers and the digests needed to fetch it, but no blob bytes:

```
GET /api/v1/federation/catalog
```

```json
{
  "catalog_version": "0.1",
  "artifacts": [
    { "namespace": "seeds", "name": "bell", "type": "circuit", "versions": ["1.0.0"] }
  ],
  "capsules": ["sha256:9f3ac2…"],
  "devices": [
    { "ref": "qv:device/quantumverse/qv-sim", "record": { … },
      "certificates": [ ["sha256:cap1…", "sha256:cap2…", "sha256:cap3…", "sha256:cap4…"] ] }
  ],
  "boards": [
    { "definition": { … }, "entries": ["sha256:cap…"] }
  ]
}
```

Certificates and board entries are expressed as the capsule-id lists that produced them, not as their computed results — the destination re-derives the verdict and the scores.

## Sync algorithm

Pulling from a source into a destination:

1. **Fetch the catalog** from the source.
2. **Register devices** absent on the destination — before capsules, so calibration snapshots auto-link (RFC-0004).
3. **Publish artifacts** version by version: skip versions the destination already has (immutable, RFC-0003); otherwise fetch the version's files from the source and publish them (destination rebuilds the Circuit Card).
4. **Push capsules** absent on the destination: fetch files, `push` (destination re-validates against RFC-0001 and merges signatures).
5. **Submit certificates**: replay each device's capsule-id list (destination recomputes the RFC-0005 verdict).
6. **Create boards** and **submit entries**: replay each board's capsule-id list (destination recomputes the RFC-0006 score and trust).

Every write is an ordinary registry operation. The reference implementation is `client/src/quantumverse/federation.py`, exposed as `qv sync <source-url>`.

## Open questions

1. **Push vs. pull.** v0 is pull (`qv sync` reads a remote into the local store). Symmetric push — a private instance publishing outward — is the same algorithm with source/destination swapped, but needs the write-auth story (Phase 3) first.
2. **Incremental sync.** v0 re-walks the whole catalog each time (cheap, since transfers dedup). A cursor / "changed since" catalog is the obvious optimization when catalogs get large.
3. **Cross-host addressing.** [RFC-0003](rfc-0003-artifact-addressing.md) left `qv://host/…` out of scope; a synced object is host-relative and simply exists on both. When an object needs to name *which* instance it came from, that qualified form is the place to define it.
4. **Trust roots for receipts.** Provider `receipt.sig` verification across instances needs the provider key registry that RFC-0001 §Open-Questions defers; until then a level-2 candidate stays a candidate on every instance.
