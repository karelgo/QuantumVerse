import pytest

from quantumverse.verify import (
    VerifyError,
    check_budgets,
    replay_l1,
    run_ci_config,
    semantic_diff,
    total_variation,
)
from quantumverse.qasm import parse_qasm

from conftest import ANSATZ, BELL, BELL_VARIANT, NOT_BELL


def test_semantic_diff_equivalent_up_to_global_phase():
    report = semantic_diff(BELL, BELL_VARIANT)
    assert report.equivalent is True
    assert report.max_deviation < 1e-9
    assert report.deltas["depth"] == 1  # variant is one layer deeper


def test_semantic_diff_detects_inequivalence():
    report = semantic_diff(BELL, NOT_BELL)
    assert report.equivalent is False


def test_semantic_diff_qubit_count_mismatch():
    other = "OPENQASM 3.0;\nqubit[3] q;\nh q[0];"
    report = semantic_diff(BELL, other)
    assert report.equivalent is False
    assert "qubit counts differ" in report.reason


def test_semantic_diff_with_parameters():
    doubled = ANSATZ.replace("ry(theta)", "ry(2*theta)")
    same = semantic_diff(ANSATZ, ANSATZ, param_bindings={"theta": 0.7})
    assert same.equivalent is True
    different = semantic_diff(ANSATZ, doubled, param_bindings={"theta": 0.7})
    assert different.equivalent is False


def test_semantic_diff_unbound_params_reports_unchecked():
    report = semantic_diff(ANSATZ, ANSATZ)
    assert report.equivalent is None
    assert "unbound" in report.reason


def test_global_phase_is_ignored():
    a = "OPENQASM 3.0;\nqubit[1] q;\nrz(pi/2) q[0];"
    b = "OPENQASM 3.0;\nqubit[1] q;\np(pi/2) q[0];"  # rz = p up to global phase
    assert semantic_diff(a, b).equivalent is True


def test_check_budgets():
    circuit = parse_qasm(BELL)
    assert check_budgets(circuit, {"depth": 3, "t_count": 0}) == []
    violations = check_budgets(circuit, {"depth": 2})
    assert len(violations) == 1
    assert violations[0].metric == "depth" and violations[0].actual == 3
    with pytest.raises(VerifyError, match="unknown budget metric"):
        check_budgets(circuit, {"cnots": 1})


def test_total_variation():
    assert total_variation({"0": 500, "1": 500}, {"0": 1, "1": 1}) == pytest.approx(0.0)
    assert total_variation({"0": 1}, {"1": 1}) == pytest.approx(1.0)
    with pytest.raises(VerifyError):
        total_variation({}, {"0": 1})


def test_replay_l1_consistent_for_simulator_capsule(bell_capsule):
    report = replay_l1(bell_capsule, seed=7)
    assert report.verdict == "consistent"
    assert report.tv_distance < 0.05
    manifest = report.replay.manifest
    assert manifest["replay_of"] == bell_capsule.id
    assert manifest["replay_level"] == "L1"
    assert not [f for f in report.replay.validate() if f.severity == "error"]


def test_replay_l1_flags_fabricated_counts(bell_qasm, sim_device):
    from quantumverse.capsule import Capsule

    fabricated = Capsule.create(
        circuit_qasm=bell_qasm,
        device=sim_device,
        execution={"job_ids": [], "shots": 1000, "counts_raw": {"01": 500, "10": 500}},
        title="fabricated", authors=["X"], license="MIT",
    )
    report = replay_l1(fabricated, seed=7)
    assert report.verdict == "not-reproduced"
    assert report.tv_distance > 0.9


def test_run_ci_config(tmp_path):
    (tmp_path / "bell.qasm").write_text(BELL)
    (tmp_path / "golden.qasm").write_text(BELL_VARIANT)
    config = {
        "checks": [{
            "circuit": "bell.qasm",
            "budgets": {"depth": 3, "t_count": 0},
            "reference": "golden.qasm",
            "expect": {"probabilities": {"00": 0.5, "11": 0.5}, "tolerance": 0.01},
        }]
    }
    assert run_ci_config(config, base_dir=tmp_path) == []

    config["checks"][0]["budgets"]["depth"] = 1
    config["checks"][0]["expect"]["probabilities"]["00"] = 0.9
    failures = run_ci_config(config, base_dir=tmp_path)
    assert len(failures) == 2
    assert any("budget violation" in f for f in failures)
    assert any("P(00)" in f for f in failures)

    with pytest.raises(VerifyError, match="non-empty 'checks'"):
        run_ci_config({}, base_dir=tmp_path)
