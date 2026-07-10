import json

import pytest

import quantumverse as qv
from quantumverse import mcp_server
from quantumverse.signing import generate_keypair, sign_files

from conftest import ANSATZ, BELL, BELL_VARIANT, NOT_BELL


@pytest.fixture
def seeded_registry(local_registry, tmp_path):
    """A local registry with an artifact, a capsule, a device, and a board."""
    path = tmp_path / "bell.qasm"
    path.write_text(BELL)
    qv.push(path, "qv:demo/bell", type="circuit", version="1.0.0",
            summary="Bell pair", tags=["bell"], registry=local_registry)

    local_registry.register_device("quantumverse", "qv-sim", {
        "record_version": "0.1", "summary": "ref sim", "modality": "simulator",
        "backend": {"provider": "quantumverse", "name": "qv-sim"},
    })
    with qv.capture(title="Bell run", authors=["MCP test"]) as cap:
        cap.run(BELL, shots=1000, seed=5)
    capsule = cap.capsule()
    local_registry.push_capsule(capsule.files)
    return local_registry, capsule


def test_mcp_search_and_load(seeded_registry):
    results = mcp_server.search_artifacts("bell")["results"]
    assert results[0]["name"] == "bell"

    loaded = mcp_server.load_artifact("qv:demo/bell")
    assert loaded["ref"] == "qv:demo/bell@1.0.0"
    assert loaded["files"]["circuit.qasm"] == BELL
    assert loaded["meta"]["card"]["resources"]["num_qubits"] == 2


def test_mcp_run_and_diff():
    result = mcp_server.run_circuit(BELL, shots=100, seed=1)
    assert set(result["counts"]) == {"00", "11"}

    bound = mcp_server.run_circuit(ANSATZ, shots=None, params={"theta": 0.5})
    assert "01" in bound["probabilities"]

    same = mcp_server.diff_circuits(BELL, BELL_VARIANT)
    assert same["equivalent"] is True
    different = mcp_server.diff_circuits(BELL, NOT_BELL)
    assert different["equivalent"] is False


def test_mcp_verify_and_replay(seeded_registry, tmp_path, monkeypatch):
    _registry, capsule = seeded_registry

    monkeypatch.setenv("QV_HOME", str(tmp_path / "qvhome"))
    verified = mcp_server.verify_capsule(capsule.id)
    assert verified["valid"] is True
    assert verified["trust"] == 0
    assert "Bell run" in verified["inspect"]

    replayed = mcp_server.replay_capsule(capsule.short_id, seed=6)
    assert replayed["verdict"] == "consistent"
    assert replayed["original"] == capsule.id


def test_mcp_device_and_board(seeded_registry, tmp_path):
    registry, _capsule = seeded_registry
    card = mcp_server.device_card("qv:device/quantumverse/qv-sim")
    assert card["capsule_count"] == 1
    assert len(card["drift"]) == 1

    instance_path = tmp_path / "instance.json"
    instance_path.write_text(json.dumps({
        "instance_version": "0.1", "name": "maxcut-triangle", "kind": "maxcut",
        "nodes": 3, "edges": [[0, 1], [1, 2], [0, 2]], "weights": [1, 1, 1],
        "max_cut_value": 2,
    }))
    qv.push(instance_path, "qv:instances/maxcut-triangle", type="instance",
            version="1.0.0", registry=registry)
    registry.create_board({
        "board_version": "0.1", "name": "maxcut-triangle", "title": "K3",
        "instance": "qv:instances/maxcut-triangle@1.0.0", "metric": "maxcut-ratio",
        "higher_is_better": True,
    })
    boards = mcp_server.leaderboard()
    assert boards["leaderboards"][0]["name"] == "maxcut-triangle"
    board = mcp_server.leaderboard("maxcut-triangle")
    assert board["entries"] == []


def test_mcp_server_wires_all_tools():
    pytest.importorskip("mcp")
    server = mcp_server.create_server()
    import anyio

    tools = anyio.run(server.list_tools)
    names = {t.name for t in tools}
    assert names == {
        "search_artifacts", "load_artifact", "run_circuit", "diff_circuits",
        "verify_capsule", "replay_capsule", "device_card", "leaderboard",
    }


def test_capsule_cite(bell_capsule, tmp_path, monkeypatch):
    text = bell_capsule.bibtex()
    assert text.startswith(f"@misc{{qv_{bell_capsule.short_id},")
    assert "Bell pair on qv-sim" in text
    assert "Test Author" in text
    assert "execution record" in text
    assert bell_capsule.id in text
    assert "doi" not in text  # no DOI minted yet

    # signing upgrades the note
    monkeypatch.setenv("QV_HOME", str(tmp_path / "qvhome"))
    generate_keypair("default")
    signed = qv.Capsule(sign_files(bell_capsule.files, bell_capsule.id))
    assert "author-signed execution record" in signed.bibtex()


def test_cli_cite(bell_capsule, tmp_path, monkeypatch, capsys):
    from quantumverse.cli import main

    monkeypatch.chdir(tmp_path)
    bell_capsule.write_tar(tmp_path / "cap.tar")
    assert main(["capsule", "cite", "cap.tar"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("@misc{qv_") and out.rstrip().endswith("}")
