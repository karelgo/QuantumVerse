import base64
import json

import pytest

from quantumverse.capsule import Capsule
from quantumverse.cli import main
from quantumverse.signing import (
    SigningError,
    check_signature,
    generate_keypair,
    key_info,
    make_signature,
    sign_files,
    trust_level,
)

from conftest import BELL, SIM_DEVICE


@pytest.fixture
def keyed_home(tmp_path, monkeypatch):
    monkeypatch.setenv("QV_HOME", str(tmp_path / "qvhome"))
    monkeypatch.delenv("QV_REGISTRY_URL", raising=False)
    generate_keypair("default")
    return tmp_path


def test_generate_and_show_key(keyed_home):
    info = key_info("default")
    assert info["algorithm"] == "ed25519"
    assert info["key_id"].startswith("sha256:")
    assert len(base64.b64decode(info["public_key"])) == 32
    with pytest.raises(SigningError, match="already exists"):
        generate_keypair("default")
    with pytest.raises(SigningError, match="no key named"):
        key_info("missing")


def test_key_file_is_private(keyed_home, tmp_path):
    key_path = tmp_path / "qvhome" / "keys" / "default.json"
    assert key_path.stat().st_mode & 0o077 == 0


def test_sign_and_verify_round_trip(keyed_home, bell_capsule):
    signed = sign_files(bell_capsule.files, bell_capsule.id, signer="qv:users/tester")
    capsule = Capsule(signed)
    assert capsule.id == bell_capsule.id  # signatures never change identity
    assert not [f for f in capsule.validate() if f.severity == "error"]
    level, detail = trust_level(capsule.files, capsule.id)
    assert level == 1
    assert "author-signed" in detail and "qv:users/tester" in detail


def test_wrong_capsule_id_fails_verification(keyed_home, bell_capsule):
    other_id = "sha256:" + "0" * 64
    doc = make_signature(other_id)
    reason = check_signature(doc, bell_capsule.id)
    assert reason is not None and "does not verify" in reason


def test_tampered_signature_is_a_validation_error(keyed_home, bell_capsule):
    signed = sign_files(bell_capsule.files, bell_capsule.id)
    doc = json.loads(signed["author.sig"])
    sig = bytearray(base64.b64decode(doc["signature"]))
    sig[0] ^= 0xFF
    doc["signature"] = base64.b64encode(bytes(sig)).decode()
    signed["author.sig"] = json.dumps(doc).encode()
    codes = {f.code for f in Capsule(signed).validate() if f.severity == "error"}
    assert "signature-invalid" in codes
    assert trust_level(signed, bell_capsule.id)[0] == 0


def test_key_id_mismatch_detected(keyed_home, bell_capsule):
    signed = sign_files(bell_capsule.files, bell_capsule.id)
    doc = json.loads(signed["author.sig"])
    doc["key_id"] = "sha256:" + "ab" * 32
    reason = check_signature(doc, bell_capsule.id)
    assert reason is not None and "key_id" in reason


def test_signature_listed_in_manifest_is_an_error(keyed_home, bell_capsule):
    signed = sign_files(bell_capsule.files, bell_capsule.id)
    manifest = json.loads(signed["manifest.json"])
    manifest["files"]["author.sig"] = "sha256:" + "0" * 64
    signed["manifest.json"] = json.dumps(manifest).encode()
    codes = {f.code for f in Capsule(signed).validate() if f.severity == "error"}
    assert "signature-listed" in codes


def test_unsigned_capsule_is_level_zero(bell_capsule):
    level, detail = trust_level(bell_capsule.files, bell_capsule.id)
    assert level == 0 and "unsigned" in detail


def test_receipt_sig_yields_level_two_candidate(keyed_home, bell_capsule):
    # any structurally valid signature in receipt.sig position: level 2 candidate
    doc = make_signature(bell_capsule.id, signer="qv:device/lab/machine")
    files = dict(bell_capsule.files)
    files["receipt.sig"] = json.dumps(doc).encode()
    level, detail = trust_level(files, bell_capsule.id)
    assert level == 2 and "candidate" in detail


def test_cli_key_and_sign_flow(keyed_home, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "bell.qasm").write_text(BELL)
    (tmp_path / "device.json").write_text(json.dumps(SIM_DEVICE))
    (tmp_path / "execution.json").write_text(
        json.dumps({"job_ids": [], "shots": 1000, "counts_raw": {"00": 503, "11": 497}})
    )
    main([
        "capsule", "create", "--circuit", "bell.qasm", "--device", "device.json",
        "--execution", "execution.json", "--title", "Bell", "--author", "CI",
        "-o", "cap.tar",
    ])
    capsys.readouterr()

    assert main(["key", "show"]) == 0
    assert "key_id" in capsys.readouterr().out

    assert main(["capsule", "sign", "cap.tar", "--signer", "qv:users/ci"]) == 0
    out = capsys.readouterr().out
    assert "level 1" in out

    assert main(["capsule", "validate", "cap.tar"]) == 0
    capsys.readouterr()
    assert main(["capsule", "inspect", "cap.tar"]) == 0
    assert "author-signed" in capsys.readouterr().out


def test_cli_refuses_to_sign_invalid_capsule(keyed_home, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "bell.qasm").write_text(BELL)
    (tmp_path / "device.json").write_text(json.dumps(SIM_DEVICE))
    (tmp_path / "execution.json").write_text(
        json.dumps({"job_ids": [], "shots": 1000, "counts_raw": {"00": 503, "11": 497}})
    )
    main([
        "capsule", "create", "--circuit", "bell.qasm", "--device", "device.json",
        "--execution", "execution.json", "--title", "Bell", "--author", "CI",
        "-o", "cap",
    ])
    capsys.readouterr()
    circuit = tmp_path / "cap" / "circuit.qasm"
    circuit.write_text(circuit.read_text().replace("h q[0];", "x q[0];"))
    assert main(["capsule", "sign", "cap"]) == 1
    assert "refusing to sign" in capsys.readouterr().out
