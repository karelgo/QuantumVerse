# QuantumVerse specifications

Machine-readable companions to the [RFCs](../rfcs/). The RFCs are the normative prose; the JSON Schemas here are the enforceable artifacts implementations validate against. When prose and schema disagree, that's a bug — file it.

| Schema | Validates | Normative RFC |
|---|---|---|
| [`schemas/manifest.schema.json`](schemas/manifest.schema.json) | `manifest.json` in an Experiment Capsule | [RFC-0001](../rfcs/rfc-0001-experiment-capsule.md) |
| [`schemas/device.schema.json`](schemas/device.schema.json) | `device.json` — backend + calibration snapshot | [RFC-0001](../rfcs/rfc-0001-experiment-capsule.md) |
| [`schemas/execution.schema.json`](schemas/execution.schema.json) | `execution.json` — shots, counts, parameters | [RFC-0001](../rfcs/rfc-0001-experiment-capsule.md) |
| [`schemas/mitigation.schema.json`](schemas/mitigation.schema.json) | `mitigation.json` — the mitigation pipeline | [RFC-0001](../rfcs/rfc-0001-experiment-capsule.md) |
| [`schemas/circuit-card.schema.json`](schemas/circuit-card.schema.json) | `card.json` — the Circuit Card | [RFC-0002](../rfcs/rfc-0002-circuit-card.md) |
| [`schemas/device-record.schema.json`](schemas/device-record.schema.json) | Device Registry records | [RFC-0004](../rfcs/rfc-0004-device-records.md) |
| [`schemas/signature.schema.json`](schemas/signature.schema.json) | `author.sig` / `receipt.sig` signature files | [RFC-0001](../rfcs/rfc-0001-experiment-capsule.md) |
| [`schemas/certificate.schema.json`](schemas/certificate.schema.json) | Birth certificates (commissioning records) | [RFC-0005](../rfcs/rfc-0005-birth-certificate.md) |
| [`schemas/leaderboard.schema.json`](schemas/leaderboard.schema.json) | Leaderboard definitions | [RFC-0006](../rfcs/rfc-0006-verified-leaderboards.md) |

Addressing (`qv:` URIs) is defined in [RFC-0003](../rfcs/rfc-0003-artifact-addressing.md); its grammar is enforced in code (see `client/src/quantumverse/uris.py`) rather than by JSON Schema.

The reference implementation vendors these schemas as package data (`client/src/quantumverse/schemas/`); a test asserts the vendored copies are byte-identical to this directory, so this directory remains the single source of truth.

Canonical JSON throughout is [RFC 8785](https://www.rfc-editor.org/rfc/rfc8785) (JCS). Digests are lowercase-hex SHA-256, prefixed `sha256:`.
