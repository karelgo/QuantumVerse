// Seal every capsule in registry/capsules per RFC-0001:
//   1. validate (counts sum to shots, required files present)
//   2. compute file digests over canonical JSON / raw text bytes
//   3. compute the capsule ID (canonical manifest with id = "")
//   4. author-sign designated capsules (Ed25519; pubkey → owners.json)
//
// Idempotent — run `npm run seal` after editing any capsule file.

import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { fileURLToPath } from "node:url";

const ROOT = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "registry");
const CAPSULES = path.join(ROOT, "capsules");
const KEYS = path.join(ROOT, "keys");

// capsule dir -> signing owner handle (author-signed, trust level 1)
const SIGN = { "ghz8-aer-8192": "quantumverse" };

const JSON_FILES = ["device.json", "execution.json", "mitigation.json"];
const TEXT_FILES = ["circuit.qasm", "compiled.qasm", "environment.lock"];

// mirrors web/lib/canonical.ts (RFC 8785 subset)
function canonicalJson(value) {
  if (value === null || typeof value !== "object") return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  const entries = Object.entries(value)
    .filter(([, v]) => v !== undefined)
    .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0));
  return `{${entries.map(([k, v]) => `${JSON.stringify(k)}:${canonicalJson(v)}`).join(",")}}`;
}

const sha256 = (data) =>
  "sha256:" + crypto.createHash("sha256").update(data).digest("hex");

function signingKey(handle) {
  fs.mkdirSync(KEYS, { recursive: true });
  const keyPath = path.join(KEYS, `${handle}.json`);
  if (!fs.existsSync(keyPath)) {
    const { publicKey, privateKey } = crypto.generateKeyPairSync("ed25519");
    fs.writeFileSync(
      keyPath,
      JSON.stringify({
        public: publicKey.export({ format: "der", type: "spki" }).toString("base64"),
        private: privateKey.export({ format: "der", type: "pkcs8" }).toString("base64"),
      }, null, 2),
    );
    console.log(`generated Ed25519 keypair for ${handle} (private key stays untracked)`);
  }
  return JSON.parse(fs.readFileSync(keyPath, "utf8"));
}

const owners = JSON.parse(fs.readFileSync(path.join(ROOT, "owners.json"), "utf8"));
let ownersDirty = false;

for (const dir of fs.readdirSync(CAPSULES)) {
  const cdir = path.join(CAPSULES, dir);
  const manifestPath = path.join(cdir, "manifest.json");
  if (!fs.existsSync(manifestPath)) continue;
  const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));

  // validate
  const execution = JSON.parse(fs.readFileSync(path.join(cdir, "execution.json"), "utf8"));
  const sum = Object.values(execution.counts_raw).reduce((a, b) => a + b, 0);
  if (sum !== execution.shots) {
    throw new Error(`${dir}: counts_raw sums to ${sum}, expected ${execution.shots}`);
  }
  for (const required of ["circuit.qasm", "device.json", "environment.lock"]) {
    if (!fs.existsSync(path.join(cdir, required))) {
      throw new Error(`${dir}: missing required file ${required}`);
    }
  }

  // digests
  manifest.files = {};
  for (const name of [...TEXT_FILES, ...JSON_FILES]) {
    const p = path.join(cdir, name);
    if (!fs.existsSync(p)) continue;
    manifest.files[name] = JSON_FILES.includes(name)
      ? sha256(canonicalJson(JSON.parse(fs.readFileSync(p, "utf8"))))
      : sha256(fs.readFileSync(p, "utf8"));
  }

  // capsule ID over the canonical manifest with id = ""
  manifest.id = "";
  manifest.id = sha256(canonicalJson(manifest));
  fs.writeFileSync(manifestPath, JSON.stringify(manifest, null, 2) + "\n");

  // author signature
  if (SIGN[dir]) {
    const handle = SIGN[dir];
    const key = signingKey(handle);
    if (owners[handle].signing_key !== key.public) {
      owners[handle].signing_key = key.public;
      ownersDirty = true;
    }
    const privateKey = crypto.createPrivateKey({
      key: Buffer.from(key.private, "base64"),
      format: "der",
      type: "pkcs8",
    });
    const signature = crypto
      .sign(null, Buffer.from(manifest.id, "utf8"), privateKey)
      .toString("base64");
    fs.writeFileSync(
      path.join(cdir, "author.sig"),
      JSON.stringify({ signer: handle, algorithm: "ed25519", signature }, null, 2) + "\n",
    );
  }

  console.log(`sealed ${dir} → capsule/${manifest.id.replace("sha256:", "").slice(0, 6)}…`);
}

if (ownersDirty) {
  fs.writeFileSync(
    path.join(ROOT, "owners.json"),
    JSON.stringify(owners, null, 2) + "\n",
  );
  console.log("updated owners.json with signing key");
}
