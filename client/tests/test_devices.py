import json

import pytest

from quantumverse.cli import main
from quantumverse.devices import DeviceRecordError, calibration_summary, validate_record
from quantumverse.registry import RegistryError

RECORD = {
    "record_version": "0.1",
    "summary": "64-qubit transmon in the test lab",
    "modality": "superconducting-transmon",
    "backend": {"provider": "quantumverse", "name": "qv-sim"},
    "lineage": {"architecture": "VIO", "fab": "KiloFab", "commissioned": "2027-03-01"},
}


def test_validate_record_accepts_and_rejects():
    validate_record(RECORD)
    with pytest.raises(DeviceRecordError, match="schema validation"):
        validate_record({"record_version": "0.1", "summary": "x"})
    with pytest.raises(DeviceRecordError):
        validate_record({**RECORD, "modality": "Not Lowercase"})


def test_calibration_summary_medians():
    doc = {
        "topology": {"num_qubits": 3},
        "qubits": [
            {"index": 0, "t1_us": 100.0, "readout_error": 0.01},
            {"index": 1, "t1_us": 300.0, "readout_error": 0.03},
            {"index": 2, "t1_us": 200.0},
        ],
        "gates": [{"gate": "cz", "qubits": [0, 1], "error": 0.004}],
    }
    summary = calibration_summary(doc)
    assert summary["num_qubits"] == 3
    assert summary["median_t1_us"] == 200.0
    assert summary["median_readout_error"] == 0.02
    assert summary["median_gate_error"] == 0.004
    assert "median_t2_us" not in summary  # absent metrics are omitted, not null


def test_register_get_list_local(local_registry):
    card = local_registry.register_device("lab", "aurora-64", RECORD)
    assert card["ref"] == "qv:device/lab/aurora-64"
    assert card["calibration_count"] == 0
    assert local_registry.list_devices()[0]["name"] == "aurora-64"

    with pytest.raises(RegistryError, match="already registered"):
        local_registry.register_device("lab", "aurora-64", RECORD)
    other = {**RECORD, "backend": {"provider": "quantumverse", "name": "qv-sim"}}
    with pytest.raises(RegistryError, match="already claimed"):
        local_registry.register_device("lab", "other", other)


def test_capsule_feeds_calibration_timeline(local_registry, bell_capsule):
    local_registry.register_device("lab", "aurora-64", RECORD)
    local_registry.push_capsule(bell_capsule.files)

    card = local_registry.get_device("lab", "aurora-64")
    assert card["calibration_count"] == 1
    assert card["capsule_count"] == 1
    assert card["latest_calibration"]["summary"]["num_qubits"] == 2

    timeline = local_registry.device_calibrations("lab", "aurora-64")
    assert timeline[0]["capsule"] == bell_capsule.id
    assert timeline[0]["snapshot"].startswith("sha256:")

    # idempotent: pushing the same capsule twice adds no duplicate entry
    local_registry.push_capsule(bell_capsule.files)
    assert local_registry.get_device("lab", "aurora-64")["calibration_count"] == 1


def test_unmatched_capsule_does_not_link(local_registry, bell_capsule):
    other = {**RECORD, "backend": {"provider": "ibm", "name": "kingston"}}
    local_registry.register_device("lab", "other-machine", other)
    local_registry.push_capsule(bell_capsule.files)
    assert local_registry.get_device("lab", "other-machine")["calibration_count"] == 0


def test_device_cli_round_trip(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("QV_HOME", str(tmp_path / "qvhome"))
    monkeypatch.delenv("QV_REGISTRY_URL", raising=False)
    monkeypatch.chdir(tmp_path)

    assert main([
        "device", "register", "qv:device/lab/aurora-64",
        "--summary", "Test machine", "--modality", "superconducting-transmon",
        "--provider", "lab", "--backend-name", "aurora-64",
        "--architecture", "VIO", "--fab", "KiloFab",
    ]) == 0
    assert "registered qv:device/lab/aurora-64" in capsys.readouterr().out

    assert main(["device", "show", "lab/aurora-64"]) == 0
    out = capsys.readouterr().out
    assert "Test machine" in out and "VIO" in out and "0 calibration snapshot(s)" in out

    assert main(["device", "list"]) == 0
    assert "qv:device/lab/aurora-64" in capsys.readouterr().out

    assert main(["device", "drift", "lab/aurora-64"]) == 0
    assert "no calibration history" in capsys.readouterr().out

    assert main(["device", "register", "lab/aurora-64", "--summary", "dup",
                 "--modality", "simulator"]) == 1


def test_device_cli_record_file(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("QV_HOME", str(tmp_path / "qvhome"))
    monkeypatch.delenv("QV_REGISTRY_URL", raising=False)
    record_path = tmp_path / "record.json"
    record_path.write_text(json.dumps(RECORD))
    assert main(["device", "register", "lab/aurora-64", "--record", str(record_path)]) == 0
    capsys.readouterr()
    assert main(["device", "show", "qv:device/lab/aurora-64"]) == 0
    assert "KiloFab" in capsys.readouterr().out
