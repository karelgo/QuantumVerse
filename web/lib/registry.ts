// Phase-0 registry: the filesystem-backed artifact store from the
// implementation plan ("package, validate, hash, and read … entirely locally
// against a filesystem 'registry'"). The Hub API replaces this module's
// internals in Phase 1; its exported shapes are the API contract.

import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { parseQasm } from "./qasm";
import { computeResources } from "./circuit";
import { canonicalJson } from "./canonical";
import { shortDigest } from "./format";
import type {
  ArtifactDetail,
  ArtifactSummary,
  CapsuleDetail,
  CapsuleIntegrity,
  CapsuleSummary,
  Owner,
  TrustLevel,
} from "./types";

const ROOT = path.join(process.cwd(), "registry");

function readJson<T>(...segments: string[]): T {
  return JSON.parse(fs.readFileSync(path.join(ROOT, ...segments), "utf8")) as T;
}

function sha256(data: string | Buffer): string {
  return "sha256:" + crypto.createHash("sha256").update(data).digest("hex");
}

// ---------- owners ----------

export function listOwners(): Owner[] {
  const owners = readJson<Record<string, Omit<Owner, "handle">>>("owners.json");
  return Object.entries(owners).map(([handle, o]) => ({ handle, ...o }));
}

export function getOwner(handle: string): Owner | null {
  return listOwners().find((o) => o.handle === handle) ?? null;
}

// ---------- artifacts ----------

function artifactDirs(): { owner: string; name: string }[] {
  const base = path.join(ROOT, "artifacts");
  const out: { owner: string; name: string }[] = [];
  for (const owner of fs.readdirSync(base)) {
    const ownerDir = path.join(base, owner);
    if (!fs.statSync(ownerDir).isDirectory()) continue;
    for (const name of fs.readdirSync(ownerDir)) {
      if (fs.existsSync(path.join(ownerDir, name, "manifest.json"))) {
        out.push({ owner, name });
      }
    }
  }
  return out;
}

function loadSummary(owner: string, name: string): ArtifactSummary {
  const meta = readJson<Omit<ArtifactSummary, "resources" | "capsuleCount" | "maxTrustLevel">>(
    "artifacts", owner, name, "manifest.json",
  );
  const qasm = fs.readFileSync(
    path.join(ROOT, "artifacts", owner, name, "circuit.qasm"), "utf8",
  );
  const resources = computeResources(parseQasm(qasm));
  const capsules = capsulesForArtifact(`${owner}/${name}`);
  return {
    ...meta,
    owner,
    name,
    resources,
    capsuleCount: capsules.length,
    maxTrustLevel: capsules.length
      ? (Math.max(...capsules.map((c) => c.trustLevel)) as TrustLevel)
      : null,
  };
}

export function listArtifacts(): ArtifactSummary[] {
  return artifactDirs()
    .map(({ owner, name }) => loadSummary(owner, name))
    .sort((a, b) => (a.created < b.created ? 1 : -1));
}

export function searchArtifacts(q: string): ArtifactSummary[] {
  const needle = q.trim().toLowerCase();
  if (!needle) return listArtifacts();
  return listArtifacts().filter((a) =>
    [a.name, a.owner, a.description, a.kind, ...a.tags]
      .join(" ")
      .toLowerCase()
      .includes(needle),
  );
}

export function getArtifact(owner: string, name: string): ArtifactDetail | null {
  const dir = path.join(ROOT, "artifacts", owner, name);
  if (!fs.existsSync(path.join(dir, "manifest.json"))) return null;
  const summary = loadSummary(owner, name);
  const qasm = fs.readFileSync(path.join(dir, "circuit.qasm"), "utf8");
  const paramsPath = path.join(dir, "params.json");
  const parameters = fs.existsSync(paramsPath)
    ? JSON.parse(fs.readFileSync(paramsPath, "utf8"))
    : null;
  return {
    ...summary,
    qasm,
    parameters,
    capsules: capsulesForArtifact(`${owner}/${name}`),
  };
}

// ---------- capsules ----------

const CAPSULE_TEXT_FILES = ["circuit.qasm", "compiled.qasm", "environment.lock"];
const CAPSULE_JSON_FILES = ["device.json", "execution.json", "mitigation.json"];

function capsuleIds(): string[] {
  const base = path.join(ROOT, "capsules");
  if (!fs.existsSync(base)) return [];
  return fs
    .readdirSync(base)
    .filter((d) => fs.existsSync(path.join(base, d, "manifest.json")));
}

// Digest recomputation + signature verification is the expensive path and
// runs for every capsule on every listing. Capsules are immutable, so memoize
// per directory, keyed by file mtimes/sizes (edits — e.g. tampering — bust it).
const capsuleCache = new Map<string, { key: string; value: CapsuleDetail }>();

function loadCapsule(dirName: string): CapsuleDetail {
  const dir = path.join(ROOT, "capsules", dirName);
  const cacheKey = fs
    .readdirSync(dir)
    .map((f) => {
      const s = fs.statSync(path.join(dir, f));
      return `${f}:${s.mtimeMs}:${s.size}`;
    })
    .join("|");
  const hit = capsuleCache.get(dirName);
  if (hit && hit.key === cacheKey) return hit.value;
  const value = readCapsule(dirName);
  capsuleCache.set(dirName, { key: cacheKey, value });
  return value;
}

function readCapsule(dirName: string): CapsuleDetail {
  const dir = path.join(ROOT, "capsules", dirName);
  const manifest = readJson<CapsuleDetail["manifest"]>("capsules", dirName, "manifest.json");
  const device = readJson<CapsuleDetail["device"]>("capsules", dirName, "device.json");
  const execution = readJson<CapsuleDetail["execution"]>("capsules", dirName, "execution.json");
  const mitigationPath = path.join(dir, "mitigation.json");
  const mitigation = fs.existsSync(mitigationPath)
    ? JSON.parse(fs.readFileSync(mitigationPath, "utf8"))
    : null;
  const qasm = fs.readFileSync(path.join(dir, "circuit.qasm"), "utf8");

  // Verify integrity: recompute every digest and the capsule ID (RFC-0001
  // says verifiers MUST recompute; the page renders the outcome).
  const files: CapsuleIntegrity["files"] = Object.entries(manifest.files).map(
    ([fileName, declared]) => {
      const p = path.join(dir, fileName);
      let actual = "";
      if (fs.existsSync(p)) {
        actual = CAPSULE_JSON_FILES.includes(fileName)
          ? sha256(canonicalJson(JSON.parse(fs.readFileSync(p, "utf8"))))
          : sha256(fs.readFileSync(p, "utf8"));
      }
      return { name: fileName, digest: declared, verified: actual === declared };
    },
  );
  const recomputedId = sha256(canonicalJson({ ...manifest, id: "" }));
  const idVerified = recomputedId === manifest.id && files.every((f) => f.verified);

  // Author signature (trust level 1): Ed25519 over the capsule ID, key
  // published on the author's profile.
  let signatureValid: boolean | null = null;
  let signer: string | null = null;
  const sigPath = path.join(dir, "author.sig");
  if (fs.existsSync(sigPath)) {
    const sig = JSON.parse(fs.readFileSync(sigPath, "utf8")) as {
      signer: string;
      signature: string;
    };
    signer = sig.signer;
    const owner = getOwner(sig.signer);
    signatureValid = false;
    if (owner?.signing_key) {
      try {
        const key = crypto.createPublicKey({
          key: Buffer.from(owner.signing_key, "base64"),
          format: "der",
          type: "spki",
        });
        signatureValid = crypto.verify(
          null,
          Buffer.from(manifest.id, "utf8"),
          key,
          Buffer.from(sig.signature, "base64"),
        );
      } catch {
        signatureValid = false;
      }
    }
  }

  const trustLevel: TrustLevel = fs.existsSync(path.join(dir, "receipt.sig"))
    ? 2
    : signatureValid
      ? 1
      : 0;

  return {
    id: manifest.id,
    shortId: shortDigest(manifest.id),
    title: manifest.title,
    created: manifest.created,
    trustLevel,
    backend: device.simulator
      ? `${device.simulator.engine} (${device.simulator.method})`
      : `${device.backend.provider}/${device.backend.name}`,
    shots: execution.shots,
    manifest,
    device,
    execution,
    mitigation,
    qasm,
    integrity: { idVerified, files, signatureValid, signer },
  };
}

function toSummary(c: CapsuleDetail): CapsuleSummary {
  const { id, shortId, title, created, trustLevel, backend, shots } = c;
  return { id, shortId, title, created, trustLevel, backend, shots };
}

export function listCapsules(): CapsuleSummary[] {
  return capsuleIds().map((d) => toSummary(loadCapsule(d)));
}

export function getCapsule(idOrShort: string): CapsuleDetail | null {
  const needle = idOrShort.replace(/^sha256:/, "");
  for (const dirName of capsuleIds()) {
    const c = loadCapsule(dirName);
    const hex = c.id.replace(/^sha256:/, "");
    if (hex === needle || hex.startsWith(needle)) return c;
  }
  return null;
}

export function capsulesForArtifact(ref: string): CapsuleSummary[] {
  return capsuleIds()
    .map((d) => loadCapsule(d))
    .filter((c) =>
      Object.values(c.manifest.artifacts ?? {}).some((uri) =>
        uri.replace(/^qv:/, "").split("@")[0] === ref,
      ),
    )
    .map(toSummary);
}
