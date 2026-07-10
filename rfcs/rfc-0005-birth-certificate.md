# RFC-0005: The birth certificate (commissioning suite)

| | |
|---|---|
| **Status** | Draft |
| **Version** | 0.1 |
| **Discussion** | this repository's issues/PRs |
| **Schema** | [`spec/schemas/certificate.schema.json`](../spec/schemas/certificate.schema.json) |
| **Motivation** | [HARDWARE.md §3](../HARDWARE.md#3-the-birth-certificate) |

## Summary

The **birth certificate** is a standardized, capsule-backed commissioning record: a fixed suite of small circuits a machine runs when it comes online (or at any later checkpoint), scored against ideal distributions, and pinned to the machine's [Device Card](rfc-0004-device-records.md). It is the vendor-neutral acceptance test QPU procurement currently lacks — buyers can write *"acceptance = birth certificate ≥ spec"* into contracts, and vendors can ship it as the last step of installation.

## Design rules

1. **Computed, not claimed.** A submitter names only capsules. Everything else — which suite check each capsule ran, the score, the verdict — is recomputed independently by anyone who reads the certificate, including the registry before it stores one. Suite checks are identified by **exact circuit match** against the suite generator, never by labels.
2. **Whole suite or nothing.** A certificate covers every check at one declared width. Partial suites are not certificates.
3. **Capsule-backed all the way down.** Each check is an ordinary [RFC-0001](rfc-0001-experiment-capsule.md) capsule: raw counts, calibration snapshot, optional signatures. The certificate inherits whatever trust level its weakest capsule has; a level-2 (provider-verified) certificate is the procurement-grade artifact.
4. **One machine.** Every capsule's `device.json` backend identity must match the device being certified.

## Suite `qv-commissioning-v0`

Four checks at a declared width *n* (3 ≤ n ≤ 12 in v0 — the lower bound is 3 because at width 2 the GHZ check collapses onto the Bell check; the upper bound keeps every check simulable so results can always be cross-checked):

| Check | Circuit | Ideal distribution | Default max TV |
|---|---|---|---|
| `readout-zeros` | measure all *n* qubits, no gates | `0…0` w.p. 1 | 0.05 |
| `readout-ones` | X on every qubit, measure | `1…1` w.p. 1 | 0.05 |
| `bell` | H·CX on qubits 0,1 (always width 2) | 00/11 at ½ each | 0.10 |
| `ghz` | H + CX chain across all *n* | `0…0`/`1…1` at ½ each | 0.10 |

Scoring is **total variation distance** between the capsule's normalized `counts_raw` and the ideal distribution; a check passes iff TV ≤ its threshold; the certificate passes iff every check passes. The circuit sources are generated deterministically (see `client/src/quantumverse/certify.py`, the reference implementation); comments and whitespace are ignored when matching.

v0 is deliberately shallow — it certifies *"this machine is alive, reads out, and entangles"*, not *"this machine is good"*. Randomized benchmarking, mirror circuits, and application benchmarks belong to future suite versions (`qv-commissioning-v1`, …), which this RFC's format already accommodates via the `suite` field.

## Certificate document

```json
{
  "certificate_version": "0.1",
  "suite": "qv-commissioning-v0",
  "width": 3,
  "issued": "2026-07-10T15:00:00Z",
  "checks": [
    { "name": "readout-zeros", "qubits": 3, "shots": 4096, "tv_distance": 0.0,
      "threshold": 0.05, "pass": true, "capsule": "sha256:…" }
  ],
  "passed": true
}
```

## Workflow and HTTP mapping

```
qv device certify <ref> --emit-suite DIR      # write the suite circuits + ideals to disk
# … the lab runs them on its machine, capturing each run as a capsule …
qv device certify <ref> --from-capsules ID…   # recompute + submit the certificate
qv device certify <ref> --run-local           # reference path: suite on qv-sim end-to-end

POST /api/v1/devices/<owner>/<name>/certificate   {"capsules": ["sha256:…", …]}
GET  /api/v1/devices/<owner>/<name>/certificate   latest certificate (404 if none)
```

The registry loads each referenced capsule from its own store (unknown capsules are rejected — push them first), verifies backend identity, recomputes every score, and stores **its own** certificate — the submitted list of capsule ids is the only client input. The Device Card (RFC-0004) carries the latest certificate.

## Open questions

1. **Suite depth.** What belongs in v1 — RB sequences, mirror circuits, a SupermarQ slice? Proposals via PR against this RFC.
2. **Recertification cadence.** A birth certificate ages; should Device Cards render certificate age prominently, or should certificates carry an advisory validity window?
3. **Widths above 12.** Larger machines need checks whose ideals aren't classically simulable to verify; sampling-based cross-checks are future work.
