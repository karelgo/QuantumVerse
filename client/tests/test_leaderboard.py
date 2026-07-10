import json

import pytest

import quantumverse as qv
from quantumverse.cli import main
from quantumverse.leaderboard import (
    LeaderboardError,
    rank_entries,
    score_capsule_files,
    validate_board,
)
from quantumverse.registry import RegistryError

TRIANGLE = {
    "instance_version": "0.1",
    "name": "maxcut-triangle",
    "kind": "maxcut",
    "nodes": 3,
    "edges": [[0, 1], [1, 2], [0, 2]],
    "weights": [1, 1, 1],
    "max_cut_value": 2,
}

BOARD = {
    "board_version": "0.1",
    "name": "maxcut-triangle",
    "title": "MaxCut on K3",
    "instance": "qv:instances/maxcut-triangle@1.0.0",
    "metric": "maxcut-ratio",
    "higher_is_better": True,
}

QAOA = """OPENQASM 3.0;
include "stdgates.inc";
input float gamma;
input float beta;
qubit[3] q;
bit[3] c;
h q[0];
h q[1];
h q[2];
cx q[0], q[1];
rz(2*gamma) q[1];
cx q[0], q[1];
cx q[1], q[2];
rz(2*gamma) q[2];
cx q[1], q[2];
cx q[0], q[2];
rz(2*gamma) q[2];
cx q[0], q[2];
rx(2*beta) q[0];
rx(2*beta) q[1];
rx(2*beta) q[2];
c = measure q;
"""
CONVERGED = {"gamma": 1.8785555922, "beta": 1.2630370614}


def _qaoa_capsule(params=CONVERGED, shots=4096, seed=42):
    with qv.capture(title="QAOA K3", authors=["T"]) as cap:
        cap.run(QAOA, shots=shots, seed=seed, params=params)
    return cap.capsule()


def test_validate_board():
    validate_board(BOARD)
    with pytest.raises(LeaderboardError):
        validate_board({**BOARD, "metric": "vibes"})
    with pytest.raises(LeaderboardError):
        validate_board({**BOARD, "instance": "qv:instances/maxcut-triangle"})  # unpinned


def test_score_maxcut_ratio_exact_cases():
    # all mass on one node cut from the other two: cut = 2, ratio = 1
    execution = {"counts_raw": {"001": 500, "110": 500}, "shots": 1000}
    entry = score_capsule_files(
        BOARD, TRIANGLE, "sha256:" + "0" * 64,
        {
            "execution.json": json.dumps(execution).encode(),
            "device.json": json.dumps({"backend": {"provider": "p", "name": "n"}}).encode(),
        },
    )
    assert entry["score"] == pytest.approx(1.0)
    assert entry["backend"] == "p/n"

    # uniform over all-same bitstrings: cut = 0
    execution = {"counts_raw": {"000": 500, "111": 500}, "shots": 1000}
    entry = score_capsule_files(
        BOARD, TRIANGLE, "sha256:" + "1" * 64,
        {
            "execution.json": json.dumps(execution).encode(),
            "device.json": json.dumps({"backend": {}}).encode(),
        },
    )
    assert entry["score"] == pytest.approx(0.0)


def test_score_rejects_wrong_width_and_kind():
    files = {
        "execution.json": json.dumps({"counts_raw": {"01": 10}, "shots": 10}).encode(),
        "device.json": json.dumps({"backend": {}}).encode(),
    }
    with pytest.raises(LeaderboardError, match="width"):
        score_capsule_files(BOARD, TRIANGLE, "sha256:" + "2" * 64, files)
    with pytest.raises(LeaderboardError, match="maxcut instance"):
        score_capsule_files(BOARD, {**TRIANGLE, "kind": "qubo"}, "sha256:" + "3" * 64, files)


def test_rank_entries_orders_and_breaks_ties():
    entries = [
        {"capsule": "a", "score": 0.9, "trust": 0, "submitted": "2026-01-01T00:00:00Z"},
        {"capsule": "b", "score": 0.99, "trust": 0, "submitted": "2026-01-02T00:00:00Z"},
        {"capsule": "c", "score": 0.99, "trust": 2, "submitted": "2026-01-03T00:00:00Z"},
    ]
    ranked = rank_entries(entries, higher_is_better=True)
    assert [e["capsule"] for e in ranked] == ["c", "b", "a"]  # trust breaks the tie
    assert [e["rank"] for e in ranked] == [1, 2, 3]
    ranked_low = rank_entries(entries, higher_is_better=False)
    assert ranked_low[0]["capsule"] == "a"


def _seed_board(local_registry, tmp_path):
    instance_path = tmp_path / "instance.json"
    instance_path.write_text(json.dumps(TRIANGLE))
    qv.push(instance_path, "qv:instances/maxcut-triangle", type="instance",
            version="1.0.0", registry=local_registry)
    local_registry.create_board(BOARD)


def test_local_registry_board_flow(local_registry, tmp_path):
    _seed_board(local_registry, tmp_path)

    with pytest.raises(RegistryError, match="already exists"):
        local_registry.create_board(BOARD)
    with pytest.raises(RegistryError, match="not found"):
        local_registry.create_board({**BOARD, "name": "other",
                                     "instance": "qv:instances/missing@1.0.0"})

    good = _qaoa_capsule()
    bad = _qaoa_capsule(params={"gamma": 0.0, "beta": 0.0}, seed=1)
    local_registry.push_capsule(good.files)
    local_registry.push_capsule(bad.files)

    entry = local_registry.submit_entry("maxcut-triangle", good.id)
    assert entry["score"] > 0.99  # converged angles solve K3 at p=1
    local_registry.submit_entry("maxcut-triangle", bad.id)

    board = local_registry.get_board("maxcut-triangle")
    assert [e["capsule"] for e in board["entries"][:1]] == [good.id]
    assert board["entries"][0]["rank"] == 1
    assert board["entries"][1]["score"] == pytest.approx(0.75, abs=0.05)  # uniform ~ 1.5/2

    # resubmission is idempotent, not duplicated
    local_registry.submit_entry("maxcut-triangle", good.id)
    assert len(local_registry.get_board("maxcut-triangle")["entries"]) == 2


def test_min_shots_enforced(local_registry, tmp_path):
    _seed_board_with_min = {**BOARD, "name": "strict", "min_shots": 100000}
    instance_path = tmp_path / "instance.json"
    instance_path.write_text(json.dumps(TRIANGLE))
    qv.push(instance_path, "qv:instances/maxcut-triangle", type="instance",
            version="1.0.0", registry=local_registry)
    local_registry.create_board(_seed_board_with_min)
    capsule = _qaoa_capsule()
    local_registry.push_capsule(capsule.files)
    with pytest.raises(LeaderboardError, match="at least 100000 shots"):
        local_registry.submit_entry("strict", capsule.id)


def test_cli_board_flow(local_registry, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    _seed_board(local_registry, tmp_path)
    capsule = _qaoa_capsule()
    local_registry.push_capsule(capsule.files)

    # the fixture's QV_HOME makes the default registry the same local one
    assert main(["board", "list"]) == 0
    assert "maxcut-triangle" in capsys.readouterr().out

    assert main(["board", "submit", "maxcut-triangle", capsule.id]) == 0
    out = capsys.readouterr().out
    score = float(out.split("scored ", 1)[1].split(" ", 1)[0])
    assert score >= 0.99

    assert main(["board", "show", "maxcut-triangle"]) == 0
    out = capsys.readouterr().out
    assert "#1" in out and "quantumverse/qv-sim" in out

    assert main(["board", "show", "nope"]) == 1
