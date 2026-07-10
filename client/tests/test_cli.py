import json

import pytest

from quantumverse.cli import main

from conftest import BELL, BELL_VARIANT, NOT_BELL, SIM_DEVICE


@pytest.fixture
def workspace(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("QV_HOME", str(tmp_path / "qvhome"))
    monkeypatch.delenv("QV_REGISTRY_URL", raising=False)
    (tmp_path / "bell.qasm").write_text(BELL)
    (tmp_path / "variant.qasm").write_text(BELL_VARIANT)
    (tmp_path / "notbell.qasm").write_text(NOT_BELL)
    (tmp_path / "device.json").write_text(json.dumps(SIM_DEVICE))
    (tmp_path / "execution.json").write_text(
        json.dumps({"job_ids": [], "shots": 1000, "counts_raw": {"00": 503, "11": 497}})
    )
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_run_command(workspace, capsys):
    assert main(["run", "bell.qasm", "--shots", "100", "--seed", "1"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["num_qubits"] == 2
    assert sum(out["counts"].values()) == 100


def test_card_command(workspace, capsys):
    assert main(["card", "bell.qasm", "--name", "bell", "--summary", "Bell pair"]) == 0
    card = json.loads(capsys.readouterr().out)
    assert card["resources"]["two_qubit_gate_count"] == 1


def test_capsule_create_validate_inspect_replay(workspace, capsys):
    rc = main([
        "capsule", "create", "--circuit", "bell.qasm", "--device", "device.json",
        "--execution", "execution.json", "--title", "Bell", "--author", "CI",
        "-o", "cap.tar",
    ])
    assert rc == 0
    capsys.readouterr()

    assert main(["capsule", "validate", "cap.tar"]) == 0
    assert "is valid" in capsys.readouterr().out

    assert main(["capsule", "inspect", "cap.tar"]) == 0
    assert "Bell" in capsys.readouterr().out

    assert main(["capsule", "replay", "cap.tar", "--seed", "3", "-o", "replay.tar"]) == 0
    out = capsys.readouterr().out
    assert "verdict: consistent" in out
    assert main(["capsule", "validate", "replay.tar"]) == 0


def test_capsule_validate_fails_on_tamper(workspace, capsys):
    main([
        "capsule", "create", "--circuit", "bell.qasm", "--device", "device.json",
        "--execution", "execution.json", "--title", "Bell", "--author", "CI",
        "-o", "cap",
    ])
    capsys.readouterr()
    circuit = (workspace / "cap" / "circuit.qasm")
    circuit.write_text(circuit.read_text().replace("h q[0];", "x q[0];"))
    assert main(["capsule", "validate", "cap"]) == 1
    assert "digest-mismatch" in capsys.readouterr().out


def test_diff_exit_codes(workspace, capsys):
    assert main(["diff", "bell.qasm", "variant.qasm"]) == 0
    assert "EQUIVALENT" in capsys.readouterr().out
    assert main(["diff", "bell.qasm", "notbell.qasm"]) == 1


def test_ci_command(workspace, capsys):
    (workspace / "quantumverse.ci.json").write_text(json.dumps({
        "checks": [{"circuit": "bell.qasm", "budgets": {"depth": 3},
                    "reference": "variant.qasm"}]
    }))
    assert main(["ci"]) == 0
    assert "passed" in capsys.readouterr().out

    (workspace / "quantumverse.ci.json").write_text(json.dumps({
        "checks": [{"circuit": "bell.qasm", "reference": "notbell.qasm"}]
    }))
    assert main(["ci"]) == 1
    assert "NOT equivalent" in capsys.readouterr().out


def test_push_pull_search_local(workspace, capsys):
    assert main(["push", "bell.qasm", "qv:demo/bell", "--type", "circuit",
                 "--version", "1.0.0", "--summary", "Bell"]) == 0
    capsys.readouterr()
    assert main(["search", "bell"]) == 0
    assert "qv:demo/bell@1.0.0" in capsys.readouterr().out
    assert main(["pull", "qv:demo/bell", "-o", "out"]) == 0
    assert (workspace / "out" / "circuit.qasm").read_text() == BELL


def test_error_paths_return_1(workspace, capsys):
    assert main(["run", "missing.qasm"]) == 1
    assert main(["diff", "bell.qasm", "missing.qasm"]) == 1
    assert main(["pull", "qv:not/there"]) == 1
