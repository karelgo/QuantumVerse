import json

import pytest

import quantumverse as qv
from quantumverse._schema import schema_errors
from quantumverse.certify import (
    CertifyError,
    check_names,
    check_circuit,
    evaluate_capsule_files,
    ideal_distribution,
    identify_check,
    suite_circuits,
)
from quantumverse.cli import main
from quantumverse.qasm import parse_qasm
from quantumverse.registry import RegistryError
from quantumverse.simulator import run

DEVICE_RECORD = {
    "record_version": "0.1",
    "summary": "Reference simulator",
    "modality": "simulator",
    "backend": {"provider": "quantumverse", "name": "qv-sim"},
}


def _suite_capsules(n=3, shots=4096, seed=7, counts_override=None):
    """Run the suite on the simulator and return [(id, files), ...]."""
    capsules = []
    for name, qasm_text in suite_circuits(n).items():
        with qv.capture(title=f"check {name}", authors=["T"]) as cap:
            cap.run(qasm_text, shots=shots, seed=seed)
        capsule = cap.capsule()
        if counts_override and name in counts_override:
            files = dict(capsule.files)
            execution = json.loads(files["execution.json"])
            execution["counts_raw"] = counts_override[name]
            execution["shots"] = sum(counts_override[name].values())
            files["execution.json"] = json.dumps(execution).encode()
            capsule = qv.Capsule(files)  # deliberately stale manifest digests
        capsules.append((capsule.id, capsule.files))
    return capsules


def test_suite_circuits_parse_and_have_right_ideals():
    for n in (3, 4, 5):
        for name, qasm_text in suite_circuits(n).items():
            circuit = parse_qasm(qasm_text)
            width = 2 if name == "bell" else n
            assert circuit.num_qubits == width
            result = run(circuit)
            ideal = ideal_distribution(name, width)
            for bitstring, probability in ideal.items():
                assert result.probabilities[bitstring] == pytest.approx(probability)


def test_identify_check_by_circuit_text():
    assert identify_check(check_circuit("ghz", 4)) == ("ghz", 4)
    assert identify_check("// a comment\n" + check_circuit("bell", 2)) == ("bell", 2)
    assert identify_check("OPENQASM 3.0;\nqubit[2] q;\nh q[0];") is None
    with pytest.raises(CertifyError):
        check_circuit("ghz", 1)  # below minimum width
    with pytest.raises(CertifyError):
        check_circuit("ghz", 13)  # above maximum width


def test_evaluate_passes_on_clean_simulator_runs():
    certificate = evaluate_capsule_files(
        _suite_capsules(), expected_backend={"provider": "quantumverse", "name": "qv-sim"}
    )
    assert schema_errors("certificate", certificate) == []
    assert certificate["passed"] is True
    assert certificate["width"] == 3
    assert [c["name"] for c in certificate["checks"]] == check_names()


def test_evaluate_fails_broken_readout():
    # a machine that reads |1> as |0> half the time
    bad = evaluate_capsule_files(
        _suite_capsules(counts_override={"readout-ones": {"111": 2048, "011": 2048}})
    )
    assert bad["passed"] is False
    ones = next(c for c in bad["checks"] if c["name"] == "readout-ones")
    assert not ones["pass"] and ones["tv_distance"] == pytest.approx(0.5)


def test_evaluate_rejects_incomplete_and_foreign():
    capsules = _suite_capsules()
    with pytest.raises(CertifyError, match="incomplete suite"):
        evaluate_capsule_files(capsules[:3])
    with pytest.raises(CertifyError, match="ran on"):
        evaluate_capsule_files(
            capsules, expected_backend={"provider": "ibm", "name": "kingston"}
        )
    with pytest.raises(CertifyError, match="duplicate"):
        evaluate_capsule_files(capsules + [capsules[0]])


def test_evaluate_rejects_non_suite_circuit():
    not_a_check = (
        'OPENQASM 3.0;\ninclude "stdgates.inc";\nqubit[2] q;\nbit[2] c;\n'
        "x q[0];\nh q[1];\nc = measure q;\n"
    )
    with qv.capture(title="not a check", authors=["T"]) as cap:
        cap.run(not_a_check, shots=128, seed=1)
    capsule = cap.capsule()
    with pytest.raises(CertifyError, match="not a qv-commissioning-v0 check"):
        evaluate_capsule_files([(capsule.id, capsule.files)])


def test_local_registry_certificate_flow(local_registry):
    local_registry.register_device("quantumverse", "qv-sim", DEVICE_RECORD)
    ids = []
    for capsule_id, files in _suite_capsules(seed=11):
        local_registry.push_capsule(files)
        ids.append(capsule_id)

    certificate = local_registry.submit_certificate("quantumverse", "qv-sim", ids)
    assert certificate["passed"] is True

    card = local_registry.get_device("quantumverse", "qv-sim")
    assert card["certificate"]["passed"] is True
    assert local_registry.get_certificate("quantumverse", "qv-sim") == certificate

    local_registry.register_device(
        "lab", "empty",
        {**DEVICE_RECORD, "backend": {"provider": "lab", "name": "empty"}},
    )
    with pytest.raises(RegistryError, match="no birth certificate"):
        local_registry.get_certificate("lab", "empty")


def test_cli_certify_run_local_and_emit_suite(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("QV_HOME", str(tmp_path / "qvhome"))
    monkeypatch.delenv("QV_REGISTRY_URL", raising=False)
    monkeypatch.chdir(tmp_path)

    main(["device", "register", "quantumverse/qv-sim", "--summary", "ref sim",
          "--modality", "simulator"])
    capsys.readouterr()

    assert main(["device", "certify", "quantumverse/qv-sim",
                 "--qubits", "3", "--seed", "5"]) == 0
    out = capsys.readouterr().out
    assert "overall: PASSED" in out and out.count("PASS") >= 4

    assert main(["device", "show", "quantumverse/qv-sim"]) == 0
    assert "birth certificate: PASSED" in capsys.readouterr().out

    assert main(["device", "certify", "quantumverse/qv-sim",
                 "--emit-suite", "suite-out", "--qubits", "4"]) == 0
    capsys.readouterr()
    ideals = json.loads((tmp_path / "suite-out" / "ideals.json").read_text())
    assert ideals["width"] == 4
    assert set(ideals["checks"]) == set(check_names())
    assert (tmp_path / "suite-out" / "ghz.qasm").exists()


def test_cli_certify_refuses_run_local_for_foreign_hardware(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("QV_HOME", str(tmp_path / "qvhome"))
    monkeypatch.delenv("QV_REGISTRY_URL", raising=False)
    main(["device", "register", "lab/aurora-64", "--summary", "real iron",
          "--modality", "superconducting-transmon"])
    capsys.readouterr()
    assert main(["device", "certify", "lab/aurora-64"]) == 1
    err = capsys.readouterr().err
    assert "--emit-suite" in err
