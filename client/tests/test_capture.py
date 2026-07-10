import json
from types import SimpleNamespace

import pytest

import quantumverse as qv
from quantumverse._schema import schema_errors
from quantumverse.capture import CaptureError, device_from_qiskit
from quantumverse.signing import generate_keypair, trust_level

from conftest import BELL, SIM_DEVICE


def _errors(capsule):
    return [f for f in capsule.validate() if f.severity == "error"]


def test_simulator_capture_is_fully_automatic():
    with qv.capture(title="Bell capture", authors=["Tester"]) as cap:
        result = cap.run(BELL, shots=2048, seed=42)
    assert set(result.counts) == {"00", "11"}

    capsule = cap.capsule()
    assert _errors(capsule) == []
    manifest = capsule.manifest
    assert manifest["title"] == "Bell capture"

    execution = json.loads(capsule.files["execution.json"])
    assert execution["shots"] == 2048
    assert execution["counts_raw"] == result.counts
    assert "submitted" in execution and "completed" in execution

    device = json.loads(capsule.files["device.json"])
    assert device["backend"]["name"] == "qv-sim"
    assert device["simulator"]["seed"] == 42


def test_hardware_shape_capture_via_record(bell_qasm):
    hardware_device = {**SIM_DEVICE, "simulator": None}
    with qv.capture(title="HW run", authors=["Tester"], device=hardware_device) as cap:
        cap.record(
            circuit_qasm=bell_qasm,
            compiled_qasm=bell_qasm,
            counts={"00": 510, "11": 490},
            shots=1000,
            job_ids=["job-123"],
        )
    capsule = cap.capsule()
    assert _errors(capsule) == []
    assert "compiled.qasm" in capsule.files
    execution = json.loads(capsule.files["execution.json"])
    assert execution["job_ids"] == ["job-123"]


def test_hardware_capture_without_compiled_fails(bell_qasm):
    hardware_device = {**SIM_DEVICE, "simulator": None}
    with qv.capture(title="HW run", authors=["Tester"], device=hardware_device) as cap:
        cap.record(circuit_qasm=bell_qasm, counts={"00": 1000}, shots=1000)
    with pytest.raises(CaptureError, match="compiled"):
        cap.capsule()


def test_capture_guards(bell_qasm):
    cap = qv.capture(title="x", authors=["a"])
    with pytest.raises(CaptureError, match="nothing recorded"):
        cap.capsule()

    with qv.capture(title="x", authors=["a"]) as cap2:
        cap2.record(circuit_qasm=bell_qasm, counts={"00": 4}, shots=4)
        with pytest.raises(CaptureError, match="already recorded"):
            cap2.record(circuit_qasm=bell_qasm, counts={"00": 4}, shots=4)
        with pytest.raises(CaptureError, match="no device snapshot"):
            cap2.capsule()


def test_capture_with_mitigation():
    with qv.capture(title="Mitigated", authors=["Tester"]) as cap:
        cap.run(BELL, shots=1024, seed=1)
        cap.add_mitigation([{"step": "readout_correction", "method": "matrix_inversion"}])
    capsule = cap.capsule()
    # counts_mitigated not present, so mitigation is just a recorded pipeline
    assert _errors(capsule) == []
    assert "mitigation.json" in capsule.files


def test_capture_sign_and_publish(tmp_path, monkeypatch, local_registry):
    monkeypatch.setenv("QV_HOME", str(tmp_path / "qvhome"))
    generate_keypair("default")
    with qv.capture(title="Signed capture", authors=["Tester"]) as cap:
        cap.run(BELL, shots=512, seed=3)
    capsule_id = cap.publish(
        registry=local_registry, sign_with="default", signer="qv:users/tester"
    )
    record = local_registry.get_capsule(capsule_id.split(":", 1)[1][:8])
    assert record["id"] == capsule_id
    fetched = {
        name: local_registry.get_blob(digest) for name, digest in record["files"].items()
    }
    assert trust_level(fetched, capsule_id)[0] == 1


def _fake_backend():
    """A BackendV2-shaped object, per the qiskit adapter's duck-typed surface."""
    qprops = [
        SimpleNamespace(t1=120e-6, t2=90e-6, frequency=4.9e9),
        SimpleNamespace(t1=100e-6, t2=None, frequency=5.0e9),
    ]
    gate_props = {
        "cx": {
            (0, 1): SimpleNamespace(error=0.011, duration=300e-9),
            (1, 0): SimpleNamespace(error=0.013, duration=300e-9),
        },
        "x": {(0,): SimpleNamespace(error=0.0002, duration=35e-9)},
    }

    class Target:
        qubit_properties = qprops
        operation_names = list(gate_props)

        def __getitem__(self, name):
            return gate_props[name]

    return SimpleNamespace(
        name="fake_kingston",
        num_qubits=2,
        backend_version="1.2.8",
        coupling_map=SimpleNamespace(get_edges=lambda: [(0, 1), (1, 0)]),
        target=Target(),
    )


def test_device_from_qiskit_backendv2_shape():
    device = device_from_qiskit(_fake_backend())
    assert schema_errors("device", device) == []
    assert device["backend"] == {
        "provider": "qiskit", "name": "fake_kingston", "version": "1.2.8",
    }
    assert device["topology"] == {"num_qubits": 2, "coupling_map": [[0, 1], [1, 0]]}
    q0 = device["qubits"][0]
    assert q0["t1_us"] == pytest.approx(120.0)  # seconds -> microseconds
    assert q0["frequency_ghz"] == pytest.approx(4.9)
    assert "t2_us" not in device["qubits"][1]  # None dropped, not nulled
    cx01 = next(g for g in device["gates"] if g["gate"] == "cx" and g["qubits"] == [0, 1])
    assert cx01["error"] == 0.011
    assert cx01["duration_ns"] == pytest.approx(300.0)  # seconds -> nanoseconds


def test_device_from_qiskit_rejects_non_backends():
    with pytest.raises(CaptureError, match="BackendV2"):
        device_from_qiskit(object())


def test_qiskit_snapshot_makes_a_valid_hardware_capsule(bell_qasm):
    with qv.capture(
        title="Fake HW", authors=["Tester"], device=device_from_qiskit(_fake_backend())
    ) as cap:
        cap.record(
            circuit_qasm=bell_qasm, compiled_qasm=bell_qasm,
            counts={"00": 490, "11": 510}, shots=1000, job_ids=["j1"],
        )
    assert _errors(cap.capsule()) == []
