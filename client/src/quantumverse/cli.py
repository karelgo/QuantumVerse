"""The ``qv`` command-line interface (argparse, stdlib only).

Commands: capsule create/validate/inspect, card, run, push, pull, search.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from . import __version__
from .capsule import Capsule, CapsuleError
from .cards import CardError, build_card
from .hub import ARTIFACT_TYPES, load, push
from .qasm import QasmError, parse_qasm
from .certify import (
    CertifyError,
    SUITE,
    ideal_distribution,
    suite_circuits,
    threshold,
)
from .devices import RECORD_VERSION, DeviceRecordError
from .registry import RegistryError, get_registry
from .signing import SigningError, generate_keypair, key_info, sign_files, trust_level
from .simulator import SimulatorError, run
from .uris import QvUriError, VersionError, parse_uri
from .verify import (
    VerifyError,
    load_ci_config,
    replay_l1,
    run_ci_config,
    semantic_diff,
)


def _read_text(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def _read_json(path: str) -> dict:
    try:
        return json.loads(_read_text(path))
    except json.JSONDecodeError as exc:
        raise CapsuleError(f"{path} is not valid JSON: {exc}") from exc


# ---------------------------------------------------------------------------
# capsule subcommands
# ---------------------------------------------------------------------------


def _cmd_capsule_create(args: argparse.Namespace) -> int:
    capsule = Capsule.create(
        circuit_qasm=_read_text(args.circuit),
        device=_read_json(args.device),
        execution=_read_json(args.execution),
        title=args.title,
        authors=args.author,
        license=args.license,
        mitigation=_read_json(args.mitigation) if args.mitigation else None,
        compiled_qasm=_read_text(args.compiled) if args.compiled else None,
        environment_lock=_read_text(args.env_lock) if args.env_lock else None,
    )
    out = args.output or f"capsule-{capsule.short_id}.tar"
    if str(out).endswith(".tar"):
        capsule.write_tar(out)
    else:
        capsule.write_dir(out)
    print(f"capsule/{capsule.short_id}  {capsule.id}")
    print(f"wrote {out}")
    return 0


def _cmd_capsule_validate(args: argparse.Namespace) -> int:
    capsule = Capsule.load(args.path)
    findings = capsule.validate()
    for finding in findings:
        print(finding)
    errors = [f for f in findings if f.severity == "error"]
    if errors:
        print(f"invalid: {len(errors)} error(s), "
              f"{len(findings) - len(errors)} warning(s)")
        return 1
    print(f"ok: capsule/{capsule.short_id} is valid"
          + (f" ({len(findings)} warning(s))" if findings else ""))
    return 0


def _cmd_capsule_inspect(args: argparse.Namespace) -> int:
    print(Capsule.load(args.path).inspect())
    return 0


def _cmd_capsule_sign(args: argparse.Namespace) -> int:
    capsule = Capsule.load(args.path)
    errors = [f for f in capsule.validate() if f.severity == "error"]
    if errors:
        for finding in errors:
            print(finding)
        print("refusing to sign an invalid capsule")
        return 1
    capsule.files = sign_files(
        capsule.files, capsule.id, key_name=args.key, signer=args.signer
    )
    out = Path(args.output) if args.output else Path(args.path)
    if out.is_dir() or (not out.exists() and not str(out).endswith(".tar")):
        capsule.write_dir(out)
    else:
        capsule.write_tar(out)
    level, description = trust_level(capsule.files, capsule.id)
    print(f"signed capsule/{capsule.short_id} — {description}")
    print(f"wrote {out}")
    return 0


# ---------------------------------------------------------------------------
# key commands
# ---------------------------------------------------------------------------


def _cmd_key_generate(args: argparse.Namespace) -> int:
    info = generate_keypair(args.name)
    print(f"generated key {info['name']!r}")
    print(f"  key id:     {info['key_id']}")
    print(f"  public key: {info['public_key']}")
    print("publish the key id on your profile so signatures bind to you (RFC-0001)")
    return 0


def _cmd_key_show(args: argparse.Namespace) -> int:
    print(json.dumps(key_info(args.name), indent=2, sort_keys=True))
    return 0


def _cmd_capsule_replay(args: argparse.Namespace) -> int:
    capsule = Capsule.load(args.path)
    report = replay_l1(capsule, seed=args.seed)
    print(report.summary())
    if args.output:
        out = args.output
        if str(out).endswith(".tar"):
            report.replay.write_tar(out)
        else:
            report.replay.write_dir(out)
        print(f"wrote {out}")
    return 0 if report.verdict in ("consistent", "degraded") else 1


# ---------------------------------------------------------------------------
# diff / ci
# ---------------------------------------------------------------------------


def _cmd_diff(args: argparse.Namespace) -> int:
    report = semantic_diff(
        _read_text(args.circuit_a),
        _read_text(args.circuit_b),
        param_bindings=_parse_bindings(args.param or []),
    )
    print(f"{args.circuit_a} -> {args.circuit_b}")
    print(report.summary())
    if report.equivalent is False:
        return 1
    if report.equivalent is None and args.require_equivalence:
        return 1
    return 0


def _cmd_ci(args: argparse.Namespace) -> int:
    config_path = Path(args.config)
    config = load_ci_config(config_path)
    failures = run_ci_config(config, base_dir=config_path.parent)
    checks = config.get("checks", [])
    if failures:
        for failure in failures:
            print(f"FAIL  {failure}")
        print(f"quantum ci: {len(failures)} failure(s) across {len(checks)} check(s)")
        return 1
    print(f"quantum ci: all {len(checks)} check(s) passed")
    return 0


# ---------------------------------------------------------------------------
# card / run
# ---------------------------------------------------------------------------


def _cmd_card(args: argparse.Namespace) -> int:
    provenance = {"license": args.license}
    if args.author:
        provenance["authors"] = args.author
    card = build_card(
        _read_text(args.circuit),
        name=args.name,
        summary=args.summary,
        description=args.description,
        tags=args.tag or None,
        provenance=provenance,
    )
    print(json.dumps(card, indent=2, sort_keys=True))
    return 0


def _parse_bindings(pairs: list[str]) -> dict[str, float]:
    bindings: dict[str, float] = {}
    for pair in pairs:
        name, sep, value = pair.partition("=")
        if not sep or not name:
            raise SimulatorError(f"--param expects name=value, got {pair!r}")
        try:
            bindings[name] = float(value)
        except ValueError:
            raise SimulatorError(f"--param {name}: {value!r} is not a number") from None
    return bindings


def _cmd_run(args: argparse.Namespace) -> int:
    circuit = parse_qasm(_read_text(args.circuit))
    result = run(
        circuit,
        shots=args.shots,
        seed=args.seed,
        param_bindings=_parse_bindings(args.param or []),
    )
    out: dict = {
        "num_qubits": result.num_qubits,
        "probabilities": {k: round(v, 12) for k, v in sorted(result.probabilities.items())},
    }
    if result.counts is not None:
        out["shots"] = result.shots
        out["counts"] = dict(sorted(result.counts.items()))
    print(json.dumps(out, indent=2))
    return 0


# ---------------------------------------------------------------------------
# device commands (RFC-0004)
# ---------------------------------------------------------------------------


def _device_ref(text: str) -> tuple[str, str]:
    """Accept ``owner/name`` or ``qv:device/owner/name``."""
    uri = parse_uri(text)
    if uri.kind == "device":
        return uri.namespace, uri.name
    if uri.kind == "artifact" and uri.version is None:
        return uri.namespace, uri.name
    raise QvUriError(f"{text!r} is not a device reference (want qv:device/<owner>/<name>)")


def _cmd_device_register(args: argparse.Namespace) -> int:
    owner, name = _device_ref(args.ref)
    if args.record:
        record = _read_json(args.record)
    else:
        if not (args.summary and args.modality):
            raise DeviceRecordError(
                "device registration needs --record FILE, or --summary and --modality"
            )
        record = {
            "record_version": RECORD_VERSION,
            "summary": args.summary,
            "modality": args.modality,
            "backend": {
                "provider": args.provider or owner,
                "name": args.backend_name or name,
            },
        }
        lineage = {
            key: value
            for key, value in (
                ("architecture", args.architecture),
                ("fab", args.fab),
                ("generation", args.generation),
                ("commissioned", args.commissioned),
                ("supersedes", args.supersedes),
            )
            if value
        }
        if lineage:
            record["lineage"] = lineage
    card = get_registry(args.registry).register_device(owner, name, record)
    print(f"registered {card['ref']}")
    return 0


def _format_device_card(card: dict) -> str:
    record = card.get("record", {})
    backend = record.get("backend", {})
    lines = [
        f"{card.get('ref')}",
        f"  summary:   {record.get('summary', '?')}",
        f"  modality:  {record.get('modality', '?')}",
        f"  backend:   {backend.get('provider', '?')}/{backend.get('name', '?')}"
        "  (capsule join key)",
    ]
    lineage = record.get("lineage") or {}
    if lineage:
        parts = [f"{k}={v}" for k, v in sorted(lineage.items())]
        lines.append(f"  lineage:   {' · '.join(parts)}")
    lines.append(
        f"  history:   {card.get('calibration_count', 0)} calibration snapshot(s), "
        f"{card.get('capsule_count', 0)} from capsules"
    )
    latest = card.get("latest_calibration")
    if latest:
        summary = latest.get("summary", {})
        stats = " · ".join(f"{k}={v}" for k, v in sorted(summary.items()))
        lines.append(f"  latest:    {latest.get('captured', '?')}  {stats}")
    certificate = card.get("certificate")
    if certificate:
        verdict = "PASSED" if certificate.get("passed") else "FAILED"
        lines.append(
            f"  birth certificate: {verdict} — {certificate.get('suite')} at width "
            f"{certificate.get('width')} (issued {certificate.get('issued')})"
        )
    else:
        lines.append("  birth certificate: none — run 'qv device certify'")
    return "\n".join(lines)


def _cmd_device_show(args: argparse.Namespace) -> int:
    owner, name = _device_ref(args.ref)
    print(_format_device_card(get_registry(args.registry).get_device(owner, name)))
    return 0


def _cmd_device_list(args: argparse.Namespace) -> int:
    devices = get_registry(args.registry).list_devices()
    if not devices:
        print("no devices registered")
        return 0
    for card in devices:
        record = card.get("record", {})
        print(
            f"{card.get('ref')}  [{record.get('modality', '?')}]  "
            f"{card.get('calibration_count', 0)} calibration(s) — {record.get('summary', '')}"
        )
    return 0


def _format_certificate(certificate: dict) -> str:
    lines = [
        f"birth certificate — {certificate['suite']} at width {certificate['width']}"
        f" (issued {certificate['issued']})"
    ]
    for check in certificate["checks"]:
        verdict = "PASS" if check["pass"] else "FAIL"
        lines.append(
            f"  {verdict}  {check['name']:<14} {check['qubits']}q  "
            f"tv={check['tv_distance']:.4f} (max {check['threshold']})  "
            f"capsule/{check['capsule'].split(':', 1)[1][:6]}"
        )
    lines.append(f"  overall: {'PASSED' if certificate['passed'] else 'FAILED'}")
    return "\n".join(lines)


def _cmd_device_certify(args: argparse.Namespace) -> int:
    owner, name = _device_ref(args.ref)

    if args.emit_suite:
        out_dir = Path(args.emit_suite)
        out_dir.mkdir(parents=True, exist_ok=True)
        ideals = {}
        for check_name, qasm_text in suite_circuits(args.qubits).items():
            (out_dir / f"{check_name}.qasm").write_text(qasm_text, encoding="utf-8")
            width = 2 if check_name == "bell" else args.qubits
            ideals[check_name] = {
                "ideal": ideal_distribution(check_name, width),
                "max_tv": threshold(check_name),
            }
        (out_dir / "ideals.json").write_text(
            json.dumps({"suite": SUITE, "width": args.qubits, "checks": ideals}, indent=2)
            + "\n",
            encoding="utf-8",
        )
        print(f"wrote {SUITE} at width {args.qubits} to {out_dir}/")
        print("run each circuit on the machine, capture each run as a capsule, push")
        print("them, then: qv device certify <ref> --from-capsules <id> <id> <id> <id>")
        return 0

    registry = get_registry(args.registry)

    if args.from_capsules:
        certificate = registry.submit_certificate(owner, name, args.from_capsules)
        print(_format_certificate(certificate))
        return 0 if certificate["passed"] else 1

    # --run-local: the reference path, only honest for the built-in simulator
    card = registry.get_device(owner, name)
    backend = card["record"]["backend"]
    if (backend["provider"], backend["name"]) != ("quantumverse", "qv-sim"):
        raise CertifyError(
            f"--run-local executes on the built-in simulator, but {card['ref']} is "
            f"{backend['provider']}/{backend['name']} — use --emit-suite to run the "
            "suite on the machine itself, then --from-capsules"
        )
    from .capture import capture

    capsule_ids = []
    for check_name, qasm_text in suite_circuits(args.qubits).items():
        with capture(
            title=f"{SUITE}: {check_name} (width {args.qubits})",
            authors=[args.author or "qv device certify"],
        ) as cap:
            cap.run(qasm_text, shots=args.shots, seed=args.seed)
        capsule_ids.append(
            cap.publish(registry=registry, sign_with=args.key, signer=args.signer)
        )
        print(f"  ran {check_name}: capsule/{capsule_ids[-1].split(':', 1)[1][:6]}")
    certificate = registry.submit_certificate(owner, name, capsule_ids)
    print(_format_certificate(certificate))
    return 0 if certificate["passed"] else 1


def _cmd_device_drift(args: argparse.Namespace) -> int:
    owner, name = _device_ref(args.ref)
    entries = get_registry(args.registry).device_calibrations(owner, name, limit=args.limit)
    if not entries:
        print(f"no calibration history for qv:device/{owner}/{name}")
        return 0
    print(f"qv:device/{owner}/{name} — {len(entries)} snapshot(s), newest first")
    for entry in entries:
        summary = entry.get("summary", {})
        stats = " · ".join(f"{k}={v}" for k, v in sorted(summary.items()))
        source = entry.get("capsule")
        origin = f"capsule/{source.split(':', 1)[1][:6]}" if source else "direct submission"
        print(f"  {entry.get('captured', '?')}  {stats}  ({origin})")
    return 0


# ---------------------------------------------------------------------------
# registry commands
# ---------------------------------------------------------------------------


def _cmd_push(args: argparse.Namespace) -> int:
    ref = push(
        args.path,
        args.ref,
        type=args.type,
        version=args.version,
        summary=args.summary,
        tags=args.tag or None,
        license=args.license,
        registry=args.registry,
    )
    print(f"pushed {ref}")
    return 0


def _cmd_pull(args: argparse.Namespace) -> int:
    artifact = load(args.ref, registry=args.registry)
    if args.output:
        out_dir = Path(args.output)
    else:
        meta = artifact.meta
        if meta.get("kind") == "capsule":
            out_dir = Path(f"capsule-{str(meta.get('id', ''))[len('sha256:'):][:6]}")
        else:
            out_dir = Path(f"{meta.get('name')}-{meta.get('version')}")
    out_dir.mkdir(parents=True, exist_ok=True)
    for name in sorted(artifact.files):
        (out_dir / name).write_bytes(artifact.files[name])
        print(f"wrote {out_dir / name}")
    print(f"pulled {artifact.ref}")
    return 0


def _cmd_search(args: argparse.Namespace) -> int:
    results = get_registry(args.registry).search(args.query, type=args.type)
    if not results:
        print("no matches")
        return 0
    for r in results:
        ns = r.get("namespace", "?")
        name = r.get("name", "?")
        rtype = r.get("type", "?")
        latest = r.get("latest") or ""
        line = f"qv:{ns}/{name}"
        if latest:
            line += f"@{latest}"
        print(f"{line}  [{rtype}]")
    return 0


# ---------------------------------------------------------------------------
# parser wiring
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="qv",
        description="QuantumVerse client: experiment capsules, circuit cards, "
        "local simulation, and registry push/pull.",
    )
    parser.add_argument("--version", action="version", version=f"qv {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    # qv capsule ...
    p_capsule = sub.add_parser("capsule", help="create, validate, or inspect experiment capsules")
    p_capsule.set_defaults(func=lambda _args: (p_capsule.print_help(), 2)[1])
    capsule_sub = p_capsule.add_subparsers(dest="capsule_command", metavar="ACTION")

    p_cc = capsule_sub.add_parser("create", help="build a capsule from circuit + device + execution")
    p_cc.add_argument("--circuit", required=True, metavar="FILE", help="abstract circuit (OpenQASM 3)")
    p_cc.add_argument("--device", required=True, metavar="FILE", help="device.json calibration snapshot")
    p_cc.add_argument("--execution", required=True, metavar="FILE", help="execution.json results")
    p_cc.add_argument("--mitigation", metavar="FILE", help="mitigation.json pipeline (optional)")
    p_cc.add_argument("--compiled", metavar="FILE", help="compiled/transpiled circuit (required for hardware)")
    p_cc.add_argument("--env-lock", metavar="FILE", help="environment.lock (auto-generated if omitted)")
    p_cc.add_argument("--title", required=True, help="experiment title")
    p_cc.add_argument("--author", action="append", required=True, metavar="NAME",
                      help="author name (repeatable)")
    p_cc.add_argument("--license", default="CC-BY-4.0", help="license (default: CC-BY-4.0)")
    p_cc.add_argument("-o", "--output", metavar="OUT.tar|OUT/",
                      help="output tar (.tar) or directory (default: capsule-<id>.tar)")
    p_cc.set_defaults(func=_cmd_capsule_create)

    p_cv = capsule_sub.add_parser("validate", help="check a capsule; exit 1 on errors")
    p_cv.add_argument("path", metavar="PATH", help="capsule directory or tar")
    p_cv.set_defaults(func=_cmd_capsule_validate)

    p_ci = capsule_sub.add_parser("inspect", help="human-readable capsule summary")
    p_ci.add_argument("path", metavar="PATH", help="capsule directory or tar")
    p_ci.set_defaults(func=_cmd_capsule_inspect)

    p_cs = capsule_sub.add_parser(
        "sign", help="attach an author signature (trust level 1) to a valid capsule"
    )
    p_cs.add_argument("path", metavar="PATH", help="capsule directory or tar")
    p_cs.add_argument("--key", default="default", help="key name (default: 'default')")
    p_cs.add_argument("--signer", metavar="QV_URI", help="identity claim, e.g. qv:users/you")
    p_cs.add_argument("-o", "--output", metavar="OUT.tar|OUT/",
                      help="write elsewhere instead of in place")
    p_cs.set_defaults(func=_cmd_capsule_sign)

    p_cr = capsule_sub.add_parser(
        "replay", help="L1 replay: re-simulate the capsule's circuit and diff distributions"
    )
    p_cr.add_argument("path", metavar="PATH", help="capsule directory or tar")
    p_cr.add_argument("--seed", type=int, help="deterministic sampling seed")
    p_cr.add_argument("-o", "--output", metavar="OUT.tar|OUT/",
                      help="write the replay capsule (replay_of set, level L1)")
    p_cr.set_defaults(func=_cmd_capsule_replay)

    # qv card
    p_card = sub.add_parser("card", help="compute a Circuit Card for a QASM file")
    p_card.add_argument("circuit", metavar="CIRCUIT.qasm")
    p_card.add_argument("--name", required=True, help="card name")
    p_card.add_argument("--summary", required=True, help="one-line summary")
    p_card.add_argument("--description", help="long-form description")
    p_card.add_argument("--license", default="CC-BY-4.0", help="license (default: CC-BY-4.0)")
    p_card.add_argument("--author", action="append", metavar="NAME", help="author (repeatable)")
    p_card.add_argument("--tag", action="append", metavar="TAG", help="tag (repeatable)")
    p_card.set_defaults(func=_cmd_card)

    # qv run
    p_run = sub.add_parser("run", help="simulate a circuit locally")
    p_run.add_argument("circuit", metavar="CIRCUIT.qasm")
    p_run.add_argument("--shots", type=int, help="sample counts for N shots (default: probabilities only)")
    p_run.add_argument("--seed", type=int, help="deterministic sampling seed")
    p_run.add_argument("--param", action="append", metavar="NAME=VALUE",
                       help="bind a symbolic parameter (repeatable)")
    p_run.set_defaults(func=_cmd_run)

    # qv diff
    p_diff = sub.add_parser(
        "diff", help="semantic circuit diff: resource deltas + equivalence up to global phase"
    )
    p_diff.add_argument("circuit_a", metavar="OLD.qasm")
    p_diff.add_argument("circuit_b", metavar="NEW.qasm")
    p_diff.add_argument("--param", action="append", metavar="NAME=VALUE",
                        help="bind a symbolic parameter in both circuits (repeatable)")
    p_diff.add_argument("--require-equivalence", action="store_true",
                        help="fail (exit 1) when equivalence cannot be checked")
    p_diff.set_defaults(func=_cmd_diff)

    # qv ci
    p_qci = sub.add_parser(
        "ci", help="run Quantum CI checks: budgets, golden equivalence, expected distributions"
    )
    p_qci.add_argument("--config", default="quantumverse.ci.json",
                       metavar="FILE", help="CI config (default: quantumverse.ci.json)")
    p_qci.set_defaults(func=_cmd_ci)

    # qv key ...
    p_key = sub.add_parser("key", help="manage Ed25519 signing keys")
    p_key.set_defaults(func=lambda _args: (p_key.print_help(), 2)[1])
    key_sub = p_key.add_subparsers(dest="key_command", metavar="ACTION")

    p_kg = key_sub.add_parser("generate", help="generate a new keypair under ~/.qv/keys")
    p_kg.add_argument("--name", default="default", help="key name (default: 'default')")
    p_kg.set_defaults(func=_cmd_key_generate)

    p_ks = key_sub.add_parser("show", help="print a key's public info (id, public key)")
    p_ks.add_argument("--name", default="default", help="key name (default: 'default')")
    p_ks.set_defaults(func=_cmd_key_show)

    # qv device ...
    p_device = sub.add_parser("device", help="register and inspect devices (RFC-0004)")
    p_device.set_defaults(func=lambda _args: (p_device.print_help(), 2)[1])
    device_sub = p_device.add_subparsers(dest="device_command", metavar="ACTION")

    p_dr = device_sub.add_parser("register", help="register a device record")
    p_dr.add_argument("ref", metavar="REF", help="qv:device/<owner>/<name> or <owner>/<name>")
    p_dr.add_argument("--record", metavar="FILE", help="full RFC-0004 record JSON")
    p_dr.add_argument("--summary", help="one-line device summary")
    p_dr.add_argument("--modality", help="e.g. superconducting-transmon, trapped-ion, simulator")
    p_dr.add_argument("--provider", help="backend.provider capsules carry (default: owner)")
    p_dr.add_argument("--backend-name", help="backend.name capsules carry (default: name)")
    p_dr.add_argument("--architecture", help="lineage: chip architecture")
    p_dr.add_argument("--fab", help="lineage: fabrication facility")
    p_dr.add_argument("--generation", help="lineage: chip generation / batch")
    p_dr.add_argument("--commissioned", help="lineage: commissioning date (YYYY-MM-DD)")
    p_dr.add_argument("--supersedes", help="lineage: qv:device/... this machine replaces")
    p_dr.add_argument("--registry", metavar="URL", help="registry URL (default: QV_REGISTRY_URL or ~/.qv)")
    p_dr.set_defaults(func=_cmd_device_register)

    p_ds = device_sub.add_parser("show", help="render a Device Card")
    p_ds.add_argument("ref", metavar="REF")
    p_ds.add_argument("--registry", metavar="URL")
    p_ds.set_defaults(func=_cmd_device_show)

    p_dl = device_sub.add_parser("list", help="list registered devices")
    p_dl.add_argument("--registry", metavar="URL")
    p_dl.set_defaults(func=_cmd_device_list)

    p_dd = device_sub.add_parser("drift", help="print the calibration timeline, newest first")
    p_dd.add_argument("ref", metavar="REF")
    p_dd.add_argument("--limit", type=int, default=20, help="max snapshots (default 20)")
    p_dd.add_argument("--registry", metavar="URL")
    p_dd.set_defaults(func=_cmd_device_drift)

    p_dc = device_sub.add_parser(
        "certify", help="run or submit the commissioning suite (RFC-0005 birth certificate)"
    )
    p_dc.add_argument("ref", metavar="REF")
    p_dc.add_argument("--qubits", type=int, default=3, help="suite width (default 3)")
    p_dc.add_argument("--emit-suite", metavar="DIR",
                      help="write the suite circuits + ideal distributions to DIR and exit")
    p_dc.add_argument("--from-capsules", nargs="+", metavar="CAPSULE_ID",
                      help="recompute + submit a certificate from already-pushed capsules")
    p_dc.add_argument("--shots", type=int, default=4096, help="--run-local shots (default 4096)")
    p_dc.add_argument("--seed", type=int, help="--run-local sampling seed")
    p_dc.add_argument("--author", help="--run-local capsule author")
    p_dc.add_argument("--key", help="--run-local: sign each capsule with this key")
    p_dc.add_argument("--signer", metavar="QV_URI", help="--run-local: signer claim")
    p_dc.add_argument("--registry", metavar="URL")
    p_dc.set_defaults(func=_cmd_device_certify)

    # qv push / pull / search
    p_push = sub.add_parser("push", help="publish an artifact version to a registry")
    p_push.add_argument("path", metavar="PATH", help="payload file or directory")
    p_push.add_argument("ref", metavar="REF", help="artifact reference, e.g. qv:grover/sat-3q")
    p_push.add_argument("--type", required=True, choices=list(ARTIFACT_TYPES))
    p_push.add_argument("--version", required=True, help="semantic version, e.g. 1.0.0")
    p_push.add_argument("--summary", help="one-line summary for the card")
    p_push.add_argument("--tag", action="append", metavar="TAG", help="tag (repeatable)")
    p_push.add_argument("--license", default="CC-BY-4.0", help="license (default: CC-BY-4.0)")
    p_push.add_argument("--registry", metavar="URL", help="registry URL (default: QV_REGISTRY_URL or ~/.qv)")
    p_push.set_defaults(func=_cmd_push)

    p_pull = sub.add_parser("pull", help="fetch an artifact or capsule by reference")
    p_pull.add_argument("ref", metavar="REF", help="e.g. qv:grover/sat-3q@1.0.0 or qv:capsule/9f3ac2")
    p_pull.add_argument("-o", "--output", metavar="DIR", help="output directory")
    p_pull.add_argument("--registry", metavar="URL", help="registry URL (default: QV_REGISTRY_URL or ~/.qv)")
    p_pull.set_defaults(func=_cmd_pull)

    p_search = sub.add_parser("search", help="search a registry")
    p_search.add_argument("query", metavar="QUERY")
    p_search.add_argument("--type", choices=list(ARTIFACT_TYPES), help="filter by artifact type")
    p_search.add_argument("--registry", metavar="URL", help="registry URL (default: QV_REGISTRY_URL or ~/.qv)")
    p_search.set_defaults(func=_cmd_search)

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 2
    try:
        return args.func(args)
    except (
        QasmError,
        CapsuleError,
        CardError,
        SimulatorError,
        QvUriError,
        VersionError,
        RegistryError,
        VerifyError,
        DeviceRecordError,
        SigningError,
        CertifyError,
        FileNotFoundError,
        ValueError,
        KeyError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
