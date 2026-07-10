"""Experiment Capsule (RFC-0001): create, read, validate, inspect, write.

A capsule is a self-contained, content-addressed record of one quantum
experiment. JSON payloads are hashed over their RFC 8785 canonical form;
text payloads over raw UTF-8 bytes with ``\\n`` line endings. The capsule
id is the digest of the canonical manifest with ``id`` set to ``""``.
"""

from __future__ import annotations

import importlib.metadata
import io
import json
import platform
import tarfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

from ._schema import schema_errors
from .canonical import canonical_bytes, digest_bytes, digest_json, utc_now
from .qasm import QasmError, parse_qasm

__all__ = ["CapsuleError", "Finding", "Capsule", "FILE_ORDER"]

# RFC-0001 capsule layout order (deterministic tar byte layout).
FILE_ORDER = [
    "manifest.json",
    "circuit.qasm",
    "compiled.qasm",
    "device.json",
    "execution.json",
    "mitigation.json",
    "environment.lock",
    "author.sig",
    "receipt.sig",
]

# Signature files are never content-addressed: a capsule's identity is its
# contents, not its endorsements (RFC-0001).
_SIGNATURE_FILES = ("author.sig", "receipt.sig")

_JSON_PAYLOADS = {"device.json", "execution.json", "mitigation.json"}
_TEXT_PAYLOADS = {"circuit.qasm", "compiled.qasm", "environment.lock"}

_KEY_PACKAGES = ("quantumverse", "rfc8785", "jsonschema", "httpx", "numpy", "qiskit")


class CapsuleError(ValueError):
    """Raised when a capsule cannot be built or read."""


@dataclass
class Finding:
    """One validation finding; severity is ``error`` or ``warning``."""

    severity: str
    code: str
    message: str

    def __str__(self) -> str:
        tag = "ERROR" if self.severity == "error" else "WARN"
        return f"[{tag}] {self.code}: {self.message}"


def _auto_environment_lock() -> str:
    lines = []
    for name in _KEY_PACKAGES:
        try:
            lines.append(f"{name}=={importlib.metadata.version(name)}")
        except importlib.metadata.PackageNotFoundError:
            pass
    return "python " + platform.python_version() + "\n" + "\n".join(sorted(lines)) + "\n"


def _normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if text and not text.endswith("\n"):
        text += "\n"
    return text


class Capsule:
    """An Experiment Capsule held in memory as a ``{filename: bytes}`` map."""

    def __init__(self, files: dict[str, bytes]):
        self.files = dict(files)

    # -- constructors ---------------------------------------------------------

    @classmethod
    def from_dir(cls, path: Union[str, Path]) -> "Capsule":
        path = Path(path)
        if not path.is_dir():
            raise CapsuleError(f"{path} is not a directory")
        files = {p.name: p.read_bytes() for p in sorted(path.iterdir()) if p.is_file()}
        if not files:
            raise CapsuleError(f"{path} contains no files")
        return cls(files)

    @classmethod
    def from_tar(cls, path: Union[str, Path]) -> "Capsule":
        path = Path(path)
        files: dict[str, bytes] = {}
        try:
            with tarfile.open(path, "r:") as tf:
                for member in tf.getmembers():
                    if not member.isfile():
                        continue
                    name = Path(member.name).name
                    fh = tf.extractfile(member)
                    if fh is not None:
                        files[name] = fh.read()
        except tarfile.TarError as exc:
            raise CapsuleError(f"cannot read capsule tar {path}: {exc}") from exc
        if not files:
            raise CapsuleError(f"{path} contains no files")
        return cls(files)

    @classmethod
    def load(cls, path: Union[str, Path]) -> "Capsule":
        """Load from a directory or an uncompressed tar archive."""
        path = Path(path)
        if path.is_dir():
            return cls.from_dir(path)
        if path.is_file():
            return cls.from_tar(path)
        raise CapsuleError(f"no such capsule: {path}")

    # -- creation -------------------------------------------------------------

    @classmethod
    def create(
        cls,
        circuit_qasm: str,
        device: dict,
        execution: dict,
        title: str,
        authors: list,
        license: str,
        mitigation: Optional[dict] = None,
        compiled_qasm: Optional[str] = None,
        environment_lock: Optional[str] = None,
        artifacts: Optional[dict] = None,
        replay_of: Optional[str] = None,
        replay_level: Optional[str] = None,
    ) -> "Capsule":
        """Build a canonical capsule, computing digests and the capsule id.

        Raises :class:`CapsuleError` on schema violations or RFC consistency
        errors (hardware without compiled circuit, counts/shots mismatch, …).
        """
        problems: list[str] = []
        for schema_name, doc in (("device", device), ("execution", execution)):
            for msg in schema_errors(schema_name, doc):
                problems.append(f"{schema_name}.json: {msg}")
        if mitigation is not None:
            for msg in schema_errors("mitigation", mitigation):
                problems.append(f"mitigation.json: {msg}")
        if problems:
            raise CapsuleError("invalid capsule inputs:\n  " + "\n  ".join(problems))

        if device.get("simulator") is None and compiled_qasm is None:
            raise CapsuleError(
                "hardware capsules (device.simulator == null) require compiled_qasm "
                "(RFC-0001: abstraction is where reproducibility dies)"
            )
        counts_raw = execution.get("counts_raw", {})
        if isinstance(counts_raw, dict) and sum(counts_raw.values()) != execution.get("shots"):
            raise CapsuleError(
                f"sum(counts_raw) = {sum(counts_raw.values())} does not equal "
                f"shots = {execution.get('shots')}"
            )
        if "counts_mitigated" in execution and mitigation is None:
            raise CapsuleError("execution.counts_mitigated requires mitigation.json")

        norm_authors = []
        for a in authors:
            norm_authors.append({"name": a} if isinstance(a, str) else dict(a))

        files: dict[str, bytes] = {}
        files["circuit.qasm"] = _normalize_text(circuit_qasm).encode("utf-8")
        if compiled_qasm is not None:
            files["compiled.qasm"] = _normalize_text(compiled_qasm).encode("utf-8")
        files["device.json"] = canonical_bytes(device)
        files["execution.json"] = canonical_bytes(execution)
        if mitigation is not None:
            files["mitigation.json"] = canonical_bytes(mitigation)
        if environment_lock is None:
            environment_lock = _auto_environment_lock()
        files["environment.lock"] = _normalize_text(environment_lock).encode("utf-8")

        manifest: dict = {
            "capsule_version": "0.1",
            "id": "",
            "created": utc_now(),
            "title": title,
            "authors": norm_authors,
            "license": license,
            "files": {name: digest_bytes(data) for name, data in sorted(files.items())},
            "replay_of": replay_of,
        }
        if replay_level is not None:
            if replay_of is None:
                raise CapsuleError("replay_level requires replay_of")
            manifest["replay_level"] = replay_level
        if artifacts:
            manifest["artifacts"] = dict(artifacts)

        manifest["id"] = digest_json(manifest)  # id == "" during hashing

        errs = schema_errors("manifest", manifest)
        if errs:
            raise CapsuleError(
                "manifest failed schema validation:\n  " + "\n  ".join(errs)
            )

        files["manifest.json"] = canonical_bytes(manifest)
        return cls(files)

    # -- accessors --------------------------------------------------------------

    @property
    def manifest(self) -> dict:
        raw = self.files.get("manifest.json")
        if raw is None:
            raise CapsuleError("capsule has no manifest.json")
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CapsuleError(f"manifest.json is not valid JSON: {exc}") from exc

    @property
    def id(self) -> str:
        return self.manifest.get("id", "")

    @property
    def short_id(self) -> str:
        cid = self.id
        return cid[len("sha256:"):][:6] if cid.startswith("sha256:") else cid[:6]

    # -- validation --------------------------------------------------------------

    def validate(self) -> list[Finding]:
        """Return all findings; a capsule is valid iff no finding has severity error."""
        findings: list[Finding] = []
        err = lambda code, msg: findings.append(Finding("error", code, msg))
        warn = lambda code, msg: findings.append(Finding("warning", code, msg))

        raw_manifest = self.files.get("manifest.json")
        if raw_manifest is None:
            err("manifest-missing", "manifest.json is required")
            return findings
        try:
            manifest = json.loads(raw_manifest.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            err("manifest-unparseable", f"manifest.json is not valid JSON: {exc}")
            return findings

        for msg in schema_errors("manifest", manifest):
            err("manifest-schema", f"manifest.json: {msg}")

        manifest_files = manifest.get("files")
        if not isinstance(manifest_files, dict):
            manifest_files = {}

        for sig_name in _SIGNATURE_FILES:
            if sig_name in manifest_files:
                err(
                    "signature-listed",
                    f"{sig_name} must never be listed in manifest.files",
                )

        # id recomputation
        cid = manifest.get("id")
        if not isinstance(cid, str) or cid == "":
            err("id-missing", "manifest.id must be set (empty only during hashing)")
        else:
            hashable = dict(manifest)
            hashable["id"] = ""
            try:
                recomputed = digest_json(hashable)
            except Exception as exc:  # non-canonicalizable manifest
                recomputed = None
                err("id-recompute", f"cannot canonicalize manifest: {exc}")
            if recomputed is not None and recomputed != cid:
                err(
                    "id-mismatch",
                    f"manifest.id is {cid} but canonical manifest hashes to {recomputed}",
                )

        # file digests
        parsed_json: dict[str, dict] = {}
        for name, digest in manifest_files.items():
            data = self.files.get(name)
            if data is None:
                err("file-missing", f"{name} is listed in manifest.files but absent")
                continue
            if name in _TEXT_PAYLOADS or name.endswith((".qasm", ".lock")):
                try:
                    text = data.decode("utf-8")
                except UnicodeDecodeError as exc:
                    err("file-encoding", f"{name} is not valid UTF-8: {exc}")
                    continue
                if "\r" in text:
                    err(
                        "file-line-endings",
                        f"{name} contains '\\r': text files must use '\\n' line endings",
                    )
                actual = digest_bytes(data)
                if actual != digest:
                    err(
                        "digest-mismatch",
                        f"{name}: manifest says {digest}, bytes hash to {actual}",
                    )
            elif name.endswith(".json"):
                try:
                    doc = json.loads(data.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    err("file-unparseable", f"{name} is not valid JSON: {exc}")
                    continue
                parsed_json[name] = doc
                actual = digest_json(doc)
                if actual != digest:
                    err(
                        "digest-mismatch",
                        f"{name}: manifest says {digest}, canonical form hashes to {actual}",
                    )
            else:
                actual = digest_bytes(data)
                if actual != digest:
                    err(
                        "digest-mismatch",
                        f"{name}: manifest says {digest}, bytes hash to {actual}",
                    )

        # extra payload files not accounted for by the manifest
        for name in sorted(self.files):
            if name == "manifest.json" or name in _SIGNATURE_FILES:
                continue
            if name not in manifest_files:
                err("file-extra", f"{name} is present but not listed in manifest.files")

        # signature files, when present, must verify over the capsule id
        capsule_id = manifest.get("id")
        if isinstance(capsule_id, str) and capsule_id:
            from .signing import check_signature

            for sig_name in _SIGNATURE_FILES:
                raw = self.files.get(sig_name)
                if raw is None:
                    continue
                try:
                    sig_doc = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    err("signature-unparseable", f"{sig_name} is not valid JSON: {exc}")
                    continue
                reason = check_signature(sig_doc, capsule_id)
                if reason is not None:
                    err("signature-invalid", f"{sig_name}: {reason}")

        # per-file schema validation
        device = parsed_json.get("device.json")
        if device is not None:
            for msg in schema_errors("device", device):
                err("device-schema", f"device.json: {msg}")
            if device.get("simulator", "absent") is None:
                if "compiled.qasm" not in manifest_files or "compiled.qasm" not in self.files:
                    err(
                        "hardware-compiled-missing",
                        "hardware capsule (device.simulator == null) requires compiled.qasm",
                    )

        execution = parsed_json.get("execution.json")
        if execution is not None:
            for msg in schema_errors("execution", execution):
                err("execution-schema", f"execution.json: {msg}")
            counts_raw = execution.get("counts_raw")
            shots = execution.get("shots")
            if isinstance(counts_raw, dict) and counts_raw and isinstance(shots, int):
                if all(isinstance(v, int) for v in counts_raw.values()):
                    total = sum(counts_raw.values())
                    if total != shots:
                        err(
                            "counts-shots-mismatch",
                            f"sum(counts_raw) = {total} does not equal shots = {shots}",
                        )
            bitstrings = []
            if isinstance(counts_raw, dict):
                bitstrings += list(counts_raw)
            mitigated = execution.get("counts_mitigated")
            if isinstance(mitigated, dict):
                bitstrings += list(mitigated)
            lengths = {len(b) for b in bitstrings if isinstance(b, str)}
            if len(lengths) > 1:
                err(
                    "bitstring-width",
                    f"count bitstrings have mixed lengths {sorted(lengths)}; "
                    "all outcomes must share one classical register width",
                )
            if mitigated is not None and "mitigation.json" not in manifest_files:
                err(
                    "mitigation-missing",
                    "execution.counts_mitigated present but mitigation.json is not in the capsule",
                )

        mitigation = parsed_json.get("mitigation.json")
        if mitigation is not None:
            for msg in schema_errors("mitigation", mitigation):
                err("mitigation-schema", f"mitigation.json: {msg}")

        # circuit parseability under the shared subset is a warning, not an error:
        # capsules may carry circuits using constructs outside the subset.
        circuit_raw = self.files.get("circuit.qasm")
        if circuit_raw is not None:
            try:
                parse_qasm(circuit_raw.decode("utf-8"))
            except (QasmError, UnicodeDecodeError) as exc:
                warn(
                    "circuit-unparseable",
                    f"circuit.qasm does not parse under the shared OpenQASM 3 subset: {exc}",
                )

        return findings

    # -- inspection ---------------------------------------------------------------

    def inspect(self) -> str:
        """Human-readable multi-line capsule summary."""
        lines: list[str] = []
        try:
            manifest = self.manifest
        except CapsuleError as exc:
            return f"unreadable capsule: {exc}"

        cid = manifest.get("id", "")
        lines.append(f"capsule/{self.short_id}  ({cid})")
        lines.append(f"  title:    {manifest.get('title', '?')}")
        lines.append(f"  created:  {manifest.get('created', '?')}")
        authors = manifest.get("authors", [])
        names = []
        for a in authors:
            if isinstance(a, dict):
                n = a.get("name", "?")
                if a.get("orcid"):
                    n += f" (orcid {a['orcid']})"
                names.append(n)
        lines.append(f"  authors:  {', '.join(names) or '?'}")
        lines.append(f"  license:  {manifest.get('license', '?')}")

        device = self._try_json("device.json")
        if device is not None:
            backend = device.get("backend", {})
            sim = device.get("simulator", "absent")
            kind = "simulator" if isinstance(sim, dict) else "hardware"
            desc = f"{backend.get('provider', '?')}/{backend.get('name', '?')} [{kind}]"
            if isinstance(sim, dict):
                desc += f" engine={sim.get('engine', '?')} method={sim.get('method', '?')}"
            lines.append(f"  backend:  {desc}")
            topo = device.get("topology", {})
            if "num_qubits" in topo:
                lines.append(f"  device qubits: {topo['num_qubits']}")

        execution = self._try_json("execution.json")
        if execution is not None:
            shots = execution.get("shots", "?")
            jobs = execution.get("job_ids", [])
            lines.append(f"  shots:    {shots}  (job ids: {', '.join(jobs) or 'none'})")
            counts = execution.get("counts_raw", {})
            if isinstance(counts, dict) and counts:
                top = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:4]
                shown = ", ".join(f"{k}:{v}" for k, v in top)
                more = f" (+{len(counts) - len(top)} more)" if len(counts) > len(top) else ""
                lines.append(f"  counts:   {len(counts)} outcomes — {shown}{more}")
            if "counts_mitigated" in execution:
                lines.append("  mitigated counts: present")

        mitigation = self._try_json("mitigation.json")
        if mitigation is not None:
            steps = [s.get("step", "?") for s in mitigation.get("pipeline", []) if isinstance(s, dict)]
            lines.append(f"  mitigation: {' -> '.join(steps) or '(empty pipeline)'}")

        artifacts = manifest.get("artifacts")
        if isinstance(artifacts, dict) and artifacts:
            for role, ref in sorted(artifacts.items()):
                lines.append(f"  artifact: {role} = {ref}")

        replay_of = manifest.get("replay_of")
        lines.append(f"  replay of: {replay_of or 'none (original run)'}")

        from .signing import trust_level

        _, trust = trust_level(self.files, manifest.get("id", ""))
        lines.append(f"  trust:    {trust}")

        lines.append("  files:")
        listed = manifest.get("files", {}) if isinstance(manifest.get("files"), dict) else {}
        for name in FILE_ORDER:
            if name in self.files:
                if name == "manifest.json":
                    digest = "(identity: hashes to the capsule id)"
                elif name in _SIGNATURE_FILES:
                    digest = "(signature; never content-addressed)"
                else:
                    digest = listed.get(name, "(NOT IN MANIFEST)")
                short = digest[:16] + "…" if isinstance(digest, str) and len(digest) > 17 else digest
                lines.append(f"    {name:<18} {len(self.files[name]):>7} B  {short}")
        return "\n".join(lines)

    def bibtex(self) -> str:
        """BibTeX citation per RFC-0001 §Citation."""
        manifest = self.manifest
        cid = manifest.get("id", "")
        short = self.short_id
        authors = " and ".join(
            a.get("name", "?") for a in manifest.get("authors", []) if isinstance(a, dict)
        )
        year = str(manifest.get("created", ""))[:4] or "????"
        from .signing import trust_level

        level, _ = trust_level(self.files, cid)
        note = {
            0: "execution record",
            1: "author-signed execution record",
            2: "provider-verified execution record",
        }.get(level, "execution record")
        lines = [
            f"@misc{{qv_{short},",
            f"  title        = {{{manifest.get('title', '?')}}},",
            f"  author       = {{{authors}}},",
            f"  year         = {{{year}}},",
        ]
        doi = manifest.get("doi")
        if doi:
            lines.append(f"  doi          = {{{doi}}},")
        lines += [
            f"  howpublished = {{QuantumVerse capsule/{short}}},",
            f"  note         = {{{note}; id {cid}}},",
            "}",
        ]
        return "\n".join(lines)

    def _try_json(self, name: str) -> Optional[dict]:
        raw = self.files.get(name)
        if raw is None:
            return None
        try:
            doc = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        return doc if isinstance(doc, dict) else None

    # -- writing ---------------------------------------------------------------------

    def write(self, path: Union[str, Path]) -> Path:
        """Write to *path*, choosing tar vs directory the way ``load`` reads it.

        A ``.tar`` suffix (or an existing file) writes a tar archive; anything
        else writes a directory. This is the single dispatch every CLI verb
        that emits a capsule should call, so they stay consistent.
        """
        path = Path(path)
        if str(path).endswith(".tar") or path.is_file():
            return self.write_tar(path)
        return self.write_dir(path)

    def _ordered_names(self) -> list[str]:
        ordered = [n for n in FILE_ORDER if n in self.files]
        ordered += sorted(n for n in self.files if n not in FILE_ORDER)
        return ordered

    def write_dir(self, path: Union[str, Path]) -> Path:
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        for name in self._ordered_names():
            (path / name).write_bytes(self.files[name])
        return path

    def write_tar(self, path: Union[str, Path]) -> Path:
        """Write an uncompressed tar with RFC file ordering and stable metadata."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(path, "w:") as tf:
            for name in self._ordered_names():
                data = self.files[name]
                info = tarfile.TarInfo(name=name)
                info.size = len(data)
                info.mtime = 0
                info.uid = info.gid = 0
                info.uname = info.gname = ""
                info.mode = 0o644
                tf.addfile(info, io.BytesIO(data))
        return path
