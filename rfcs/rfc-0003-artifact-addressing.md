# RFC-0003: Artifact addressing and `qv:` URIs

| | |
|---|---|
| **Status** | Draft |
| **Version** | 0.1 |
| **Discussion** | this repository's issues/PRs |

## Summary

This RFC defines how things on QuantumVerse are named: the `qv:` URI scheme, namespace and name grammar, version resolution, and the address forms for the platform's object kinds (artifacts, users, devices, capsules). Every cross-reference in every other spec — capsule manifests, Circuit Card lineage, client `load()` calls — uses these addresses.

## Motivation

Content addressing (RFC-0001) answers *"is this exactly the bytes I expect?"* but humans and tools also need stable, memorable, mutable names: `vqe/h2o-ground-state` should keep working as versions ship. Git solved this with refs over hashes; Docker with tags over digests. QuantumVerse needs the same two-layer scheme, specified once.

## Grammar

```
qv-uri      = "qv:" path [ "@" version ]
path        = artifact-path / user-path / device-path / capsule-path
artifact-path = namespace "/" name
user-path     = "users/" handle
device-path   = "device/" namespace "/" name
capsule-path  = "capsule/" hexid

namespace   = segment          ; a user handle or organization name
name        = segment
handle      = segment
segment     = lowercase-alnum *( ["-"] lowercase-alnum )   ; 1–64 chars, no leading/trailing/double hyphen
hexid       = 6*64 lowercase-hexdigit
version     = semver / "latest"
```

- Segments are lowercase ASCII alphanumerics and single interior hyphens, 1–64 characters. Case-insensitive input MUST be lowered before comparison; storage is always lowercase.
- `users`, `device`, `capsule`, `instances`, and `spec` are **reserved namespaces** and cannot be registered as user or organization handles.
- The scheme prefix `qv:` is optional in contexts that are unambiguously QuantumVerse-native (CLI arguments, client calls); it is required in documents that leave the platform (manifests, cards, papers).

## Versioning and resolution

Artifact versions are [semantic versions](https://semver.org). Resolution rules:

| Reference | Resolves to |
|---|---|
| `qv:vqe/h2o-ground-state` | Highest stable version (equivalent to `@latest`) |
| `qv:vqe/h2o-ground-state@1.4.2` | Exactly 1.4.2 |
| `qv:vqe/h2o-ground-state@1.4` | Highest 1.4.x |
| `qv:vqe/h2o-ground-state@1` | Highest 1.x.y |
| `qv:capsule/9f3ac2` | Unique capsule whose id starts `9f3ac2` (error if ambiguous, git-style) |

Two hard rules:

1. **Published versions are immutable.** Re-publishing an existing version number is an error; yanking hides a version from resolution but never deletes bytes (existing digests keep resolving).
2. **Every name resolution is answerable with a digest.** Registries MUST be able to return, for any resolved reference, the content digests of the files it denotes — names are a convenience layer over content addressing, never a substitute for it.

## Object kinds and their addresses

| Kind | Address form | Example |
|---|---|---|
| Circuit / algorithm | `qv:<ns>/<name>@<ver>` | `qv:grover/sat-3q@1.0.0` |
| Trained parameters | `qv:<ns>/<name>@<ver>` | `qv:vqe/h2o-params@2.1.0` |
| Problem instance | `qv:instances/<name>@<ver>` | `qv:instances/lih-sto3g@1.0.0` |
| Noise model | `qv:<ns>/<name>@<ver>` | `qv:ibm/kingston-noise@0.3.0` |
| User / org profile | `qv:users/<handle>` | `qv:users/aresearcher` |
| Device | `qv:device/<owner>/<name>` | `qv:device/tudelft/aurora-64` |
| Capsule | `qv:capsule/<hexid>` | `qv:capsule/9f3ac2` |

Artifact *type* is a property of the artifact record (`circuit`, `parameters`, `instance`, `noise-model`, `compiled`), not of the address — the same grammar serves all types. `instances/` is a curated shared namespace for benchmark inputs; publishing there is PR-gated like any commons.

Devices are versionless by address: a device page accumulates history (calibration lineage, capsules) rather than shipping releases. Chip swaps that change the physical processor SHOULD register a new device name and link predecessors via the device record.

## HTTP mapping

Registries expose resolution over HTTPS. The normative mapping used by the reference implementation:

```
qv:<ns>/<name>@<ver>   →  GET /api/v1/artifacts/<ns>/<name>?version=<ver>
qv:capsule/<hexid>     →  GET /api/v1/capsules/<hexid>
qv:device/<ns>/<name>  →  GET /api/v1/devices/<ns>/<name>
blob by digest         →  GET /api/v1/blobs/sha256:<hex>
```

Federated instances (FRONTIERS.md §3) resolve the same URIs against their own host; a `qv:` URI is host-relative by design, like a git ref. A future RFC will define cross-host qualification (`qv://host/…`) if federation demands it; deliberately out of scope here.

## Open questions

1. **Namespace squatting.** First-come handles with an arbitration process, or verified-org claims from day one?
2. **Renames.** Support namespace/name renames with permanent redirects (GitHub-style), or treat names as immutable once used?
3. **Pre-release versions.** Allow semver pre-release tags (`1.0.0-rc.1`) in public resolution, or restrict them to private registries?
