"""Regression tests for the hardening pass (adversarial review fixes)."""

import json

import pytest

import quantumverse as qv
from quantumverse.certify import CertifyError, check_circuit, suite_circuits
from quantumverse.qasm import QasmError, parse_qasm
from quantumverse.registry import LocalRegistry, RegistryError
from quantumverse.simulator import run
from quantumverse.uris import is_hexid, is_semver

from conftest import BELL


# -- duplicate classical-bit write (parser parity with JS/Rust sims) ----------

def test_parser_rejects_double_clbit_write():
    src = (
        'OPENQASM 3.0;\ninclude "stdgates.inc";\nqubit[2] q;\nbit[2] c;\n'
        "c[0] = measure q[0];\nc[0] = measure q[1];\n"
    )
    with pytest.raises(QasmError, match="written by more than one measurement"):
        parse_qasm(src)


def test_partial_measurement_uses_declared_register_width():
    # bit[3] but only c[0] written -> keys are width 3 (matches the wasm sim,
    # which now honours num_clbits) not width 1.
    src = (
        'OPENQASM 3.0;\ninclude "stdgates.inc";\nqubit[2] q;\nbit[3] c;\n'
        "h q[0];\nc[0] = measure q[0];\n"
    )
    result = run(parse_qasm(src))
    assert set(result.probabilities) == {"000", "001"}


# -- certification minimum width (GHZ==Bell at n=2) ---------------------------

def test_certification_minimum_width_is_three():
    with pytest.raises(CertifyError, match="width must be 3"):
        suite_circuits(2)
    # bell is intrinsically 2 qubits and still generable
    assert "h q[0];\ncx q[0], q[1];" in check_circuit("bell", 2)
    # a full width-3 suite is fine
    assert set(suite_circuits(3)) == {"readout-zeros", "readout-ones", "bell", "ghz"}


# -- uris helpers -------------------------------------------------------------

def test_is_semver_and_is_hexid():
    assert is_semver("1.0.0") and is_semver("2.3.4-rc.1")
    assert not is_semver("1.0") and not is_semver("v1") and not is_semver("latest")
    assert is_hexid("9f3ac2") and is_hexid("a" * 64)
    assert not is_hexid("XY") and not is_hexid("g0g0g0") and not is_hexid("abc%")


# -- LocalRegistry: validation gate parity with the server --------------------

def test_local_registry_rejects_invalid_capsule(local_registry, bell_capsule):
    tampered = dict(bell_capsule.files)
    execution = json.loads(tampered["execution.json"])
    execution["counts_raw"] = {"00": 999}  # no longer sums to shots / digest stale
    tampered["execution.json"] = json.dumps(execution).encode()
    with pytest.raises(RegistryError, match="invalid"):
        local_registry.push_capsule(tampered)


def test_local_registry_semver_required(local_registry, tmp_path):
    path = tmp_path / "bell.qasm"
    path.write_text(BELL)
    with pytest.raises(RegistryError, match="semantic version"):
        qv.push(path, "qv:demo/bell", type="circuit", version="v1",
                registry=local_registry)


# -- capsule id prefix: no SQL/startswith wildcard surprises ------------------

def test_get_capsule_rejects_non_hex_prefix(local_registry, bell_capsule):
    local_registry.push_capsule(bell_capsule.files)
    for bad in ("%", "_", "ab%", "qv:capsule/", ""):
        with pytest.raises(RegistryError):
            local_registry.get_capsule(LocalRegistry.normalize_capsule_ref(bad) or bad)


def test_normalize_capsule_ref_strips_decorations():
    n = LocalRegistry.normalize_capsule_ref
    assert n("qv:capsule/9f3ac2") == "9f3ac2"
    assert n("capsule/9f3ac2") == "9f3ac2"
    assert n("sha256:9f3ac2") == "9f3ac2"
    assert n("9f3ac2") == "9f3ac2"


# -- signatures are additive: a re-push cannot strip an endorsement -----------

def test_local_push_merges_signatures_never_strips(local_registry, bell_capsule, tmp_path, monkeypatch):
    from quantumverse.signing import generate_keypair, sign_files, trust_level

    monkeypatch.setenv("QV_HOME", str(tmp_path / "qvhome"))
    generate_keypair("default")
    signed = qv.Capsule(sign_files(bell_capsule.files, bell_capsule.id))
    local_registry.push_capsule(signed.files)

    # adversary re-pushes the same capsule WITHOUT author.sig
    stripped = {k: v for k, v in signed.files.items() if k != "author.sig"}
    local_registry.push_capsule(stripped)

    _id, files = local_registry.capsule_files(bell_capsule.id)
    assert "author.sig" in files  # endorsement survived
    assert trust_level(files, bell_capsule.id)[0] == 1


# -- leaderboard resubmission preserves the original timestamp ----------------

def test_local_submit_entry_preserves_submitted(local_registry, tmp_path):
    triangle = {
        "instance_version": "0.1", "name": "maxcut-triangle", "kind": "maxcut",
        "nodes": 3, "edges": [[0, 1], [1, 2], [0, 2]], "weights": [1, 1, 1],
        "max_cut_value": 2,
    }
    ipath = tmp_path / "instance.json"
    ipath.write_text(json.dumps(triangle))
    qv.push(ipath, "qv:instances/maxcut-triangle", type="instance", version="1.0.0",
            registry=local_registry)
    local_registry.create_board({
        "board_version": "0.1", "name": "k3", "title": "K3",
        "instance": "qv:instances/maxcut-triangle@1.0.0", "metric": "maxcut-ratio",
        "higher_is_better": True,
    })
    qaoa = (
        'OPENQASM 3.0;\ninclude "stdgates.inc";\ninput float gamma;\ninput float beta;\n'
        "qubit[3] q;\nbit[3] c;\nh q[0];\nh q[1];\nh q[2];\n"
        "cx q[0], q[1];\nrz(2*gamma) q[1];\ncx q[0], q[1];\n"
        "cx q[1], q[2];\nrz(2*gamma) q[2];\ncx q[1], q[2];\n"
        "cx q[0], q[2];\nrz(2*gamma) q[2];\ncx q[0], q[2];\n"
        "rx(2*beta) q[0];\nrx(2*beta) q[1];\nrx(2*beta) q[2];\nc = measure q;\n"
    )
    with qv.capture(title="QAOA", authors=["T"]) as cap:
        cap.run(qaoa, shots=1024, seed=1, params={"gamma": 1.878, "beta": 1.263})
    capsule = cap.capsule()
    local_registry.push_capsule(capsule.files)

    first = local_registry.submit_entry("k3", capsule.id)
    again = local_registry.submit_entry("k3", capsule.id)
    assert again["submitted"] == first["submitted"]  # clock not reset on resubmit
