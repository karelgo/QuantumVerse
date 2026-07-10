# RFC-0004: Device records and the Device Registry

| | |
|---|---|
| **Status** | Draft |
| **Version** | 0.1 |
| **Discussion** | this repository's issues/PRs |
| **Schema** | [`spec/schemas/device-record.schema.json`](../spec/schemas/device-record.schema.json) |
| **Motivation** | [HARDWARE.md §1](../HARDWARE.md#1-the-device-registry) |

## Summary

A **device record** gives a physical QPU (or a simulator) a first-class, addressable identity on QuantumVerse: `qv:device/<owner>/<name>` (RFC-0003). The record carries what a **Device Card** renders — identity, modality, lineage — while the device's *history* accumulates around it: a calibration timeline fed automatically by [Experiment Capsules](rfc-0001-experiment-capsule.md), and the list of capsules executed on the machine.

This is the registry [HARDWARE.md](../HARDWARE.md) argues for: for cloud vendors it is transparent marketing; for the long tail of lab-built machines it is the only public identity the machine will ever have.

## Design rules

1. **Identity is declared once, history accrues automatically.** A device record is registered explicitly; its calibration timeline is *not* hand-maintained. Every accepted capsule whose `device.json` backend identity matches a registered device appends that capsule's calibration snapshot to the device's timeline. The Drift Observatory is a *consequence* of capsule traffic, not a separate reporting duty.
2. **Devices are versionless** (RFC-0003): a device page accumulates history rather than shipping releases. A chip swap that changes the physical processor SHOULD register a new device and link its predecessor via `lineage.supersedes`.
3. **Claims stay separable.** The record's `lineage` and `summary` are owner-declared; the calibration timeline and capsule list are machine-accumulated. Renderers MUST distinguish the two, exactly as Circuit Cards separate computed from claimed fields (RFC-0002).

## The device record

```json
{
  "record_version": "0.1",
  "summary": "64-qubit transmon machine at the TU Delft quantum lab",
  "modality": "superconducting-transmon",
  "backend": { "provider": "tudelft", "name": "aurora-64" },
  "lineage": {
    "architecture": "VIO",
    "fab": "KiloFab",
    "generation": "batch 27",
    "commissioned": "2027-03-01",
    "supersedes": "qv:device/tudelft/aurora-32"
  },
  "links": { "homepage": "https://example.org/aurora" }
}
```

Field notes:

- **`backend`** — the `{provider, name}` identity this machine's capsules carry in `device.json` (RFC-0001). This is the join key for automatic linkage; it MUST be unique among a registry's devices.
- **`modality`** — free-form lowercase tag (`superconducting-transmon`, `trapped-ion`, `neutral-atom`, `photonic`, `spin`, `simulator`, …). A controlled vocabulary is deliberately deferred until real usage shows what's needed.
- **`lineage`** — all owner-declared, all optional. `supersedes` uses RFC-0003 device addresses.

## Calibration timeline

Each linked capsule contributes one timeline entry:

```json
{
  "captured": "2026-07-10T14:05:00Z",
  "snapshot": "sha256:c9a1…",
  "capsule": "sha256:9f3ac2…",
  "summary": { "num_qubits": 64, "median_t1_us": 112.4, "median_t2_us": 87.1,
               "median_readout_error": 0.011, "median_gate_error": 0.0042 }
}
```

`snapshot` is the content digest of the full `device.json` (retrievable as a blob — nothing is thrown away); `summary` is derived server-side at ingest for cheap plotting. Ordering is by `captured`. Registries MAY also accept direct snapshot submissions (same shape as `device.json`) for owners who want to report calibrations without minting a capsule; such entries have `capsule: null`.

## HTTP mapping

Extending RFC-0003's mapping; normative for the reference registry:

```
POST /api/v1/devices/<owner>/<name>                    register (409 if exists)
GET  /api/v1/devices                                   list device cards
GET  /api/v1/devices/<owner>/<name>                    device card (record + latest calibration + counts)
GET  /api/v1/devices/<owner>/<name>/calibrations       timeline, newest first (?limit=)
POST /api/v1/devices/<owner>/<name>/calibrations       direct snapshot submission (device.json shape)
GET  /api/v1/devices/<owner>/<name>/capsules           capsules linked to this device
```

## Open questions

1. **Ownership & authentication.** v0 registries are open; once auth lands, who may register under an `owner` namespace and who may submit direct calibrations needs the same answer as artifact publishing.
2. **Backend identity collisions across registries.** Two labs could both run a `{quantumverse, qv-sim}` simulator. Federation (FRONTIERS.md §3) will need registry-scoped identity or owner attestation.
3. **Birth certificates.** [HARDWARE.md §3](../HARDWARE.md#3-the-birth-certificate) wants a designated commissioning capsule pinned on the Device Card. Likely a `commissioning_capsule` field in a future revision, once the acceptance-suite RFC exists.
