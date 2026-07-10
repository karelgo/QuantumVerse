import json
from pathlib import Path

import pytest

from quantumverse.capsule import Capsule, CapsuleError


def _errors(capsule):
    return [f for f in capsule.validate() if f.severity == "error"]


def test_create_produces_valid_capsule(bell_capsule):
    assert bell_capsule.id.startswith("sha256:")
    assert _errors(bell_capsule) == []


def test_id_is_stable_across_tar_and_dir_round_trips(bell_capsule, tmp_path):
    tar = bell_capsule.write_tar(tmp_path / "c.tar")
    directory = bell_capsule.write_dir(tmp_path / "c")
    from_tar = Capsule.load(tar)
    from_dir = Capsule.load(directory)
    assert from_tar.id == from_dir.id == bell_capsule.id
    assert _errors(from_tar) == [] and _errors(from_dir) == []


def test_tar_bytes_are_deterministic(bell_capsule, tmp_path):
    a = bell_capsule.write_tar(tmp_path / "a.tar").read_bytes()
    b = bell_capsule.write_tar(tmp_path / "b.tar").read_bytes()
    assert a == b


def test_tampered_payload_is_detected(bell_capsule):
    tampered = Capsule(dict(bell_capsule.files))
    execution = json.loads(tampered.files["execution.json"])
    execution["counts_raw"] = {"00": 1000}
    tampered.files["execution.json"] = json.dumps(execution).encode()
    codes = {f.code for f in tampered.validate() if f.severity == "error"}
    assert "digest-mismatch" in codes


def test_tampered_manifest_id_is_detected(bell_capsule):
    tampered = Capsule(dict(bell_capsule.files))
    manifest = json.loads(tampered.files["manifest.json"])
    manifest["title"] = "something else"
    tampered.files["manifest.json"] = json.dumps(manifest).encode()
    codes = {f.code for f in tampered.validate() if f.severity == "error"}
    assert "id-mismatch" in codes


def test_extra_unlisted_file_is_an_error(bell_capsule):
    capsule = Capsule(dict(bell_capsule.files))
    capsule.files["notes.txt"] = b"stray"
    codes = {f.code for f in capsule.validate() if f.severity == "error"}
    assert "file-extra" in codes


def test_hardware_capsule_requires_compiled(bell_qasm, sim_device, bell_execution):
    hardware_device = dict(sim_device)
    hardware_device["simulator"] = None
    with pytest.raises(CapsuleError, match="compiled_qasm"):
        Capsule.create(
            circuit_qasm=bell_qasm,
            device=hardware_device,
            execution=bell_execution,
            title="hw", authors=["A"], license="MIT",
        )


def test_counts_must_sum_to_shots(bell_qasm, sim_device):
    with pytest.raises(CapsuleError, match="does not equal"):
        Capsule.create(
            circuit_qasm=bell_qasm,
            device=sim_device,
            execution={"job_ids": [], "shots": 10, "counts_raw": {"00": 3}},
            title="bad", authors=["A"], license="MIT",
        )


def test_mitigated_counts_require_mitigation(bell_qasm, sim_device):
    with pytest.raises(CapsuleError, match="mitigation"):
        Capsule.create(
            circuit_qasm=bell_qasm,
            device=sim_device,
            execution={
                "job_ids": [], "shots": 4,
                "counts_raw": {"00": 4}, "counts_mitigated": {"00": 4.0},
            },
            title="bad", authors=["A"], license="MIT",
        )


def test_replay_level_requires_replay_of(bell_qasm, sim_device, bell_execution):
    with pytest.raises(CapsuleError, match="replay_level requires replay_of"):
        Capsule.create(
            circuit_qasm=bell_qasm,
            device=sim_device,
            execution=bell_execution,
            title="r", authors=["A"], license="MIT",
            replay_level="L1",
        )


def test_inspect_mentions_key_facts(bell_capsule):
    text = bell_capsule.inspect()
    assert "Bell pair on qv-sim" in text
    assert "simulator" in text
    assert "level 0 (unsigned)" in text
    assert bell_capsule.short_id in text


def test_vendored_schemas_match_spec_dir():
    """spec/schemas is the single source of truth (see spec/README.md)."""
    repo_root = Path(__file__).resolve().parents[2]
    spec_dir = repo_root / "spec" / "schemas"
    vendored_dir = repo_root / "client" / "src" / "quantumverse" / "schemas"
    if not spec_dir.is_dir():  # running from an sdist without the spec tree
        pytest.skip("spec/schemas not present")
    spec_files = {p.name for p in spec_dir.glob("*.json")}
    vendored_files = {p.name for p in vendored_dir.glob("*.json")}
    assert spec_files == vendored_files
    for name in sorted(spec_files):
        assert (spec_dir / name).read_bytes() == (vendored_dir / name).read_bytes(), (
            f"{name}: vendored copy differs from spec/schemas — re-sync them"
        )
