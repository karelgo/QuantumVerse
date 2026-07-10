import pytest

from quantumverse.hub import load, push
from quantumverse.registry import RegistryError

from conftest import BELL


def test_push_and_load_round_trip(local_registry, tmp_path):
    path = tmp_path / "bell.qasm"
    path.write_text(BELL)
    ref = push(path, "qv:demo/bell", type="circuit", version="1.0.0",
               summary="Bell pair", tags=["bell"], registry=local_registry)
    assert ref == "qv:demo/bell@1.0.0"

    artifact = load("qv:demo/bell", registry=local_registry)
    assert artifact.text() == BELL
    assert artifact.meta["version"] == "1.0.0"
    card = artifact.meta["card"]
    assert card["resources"]["num_qubits"] == 2
    assert card["resources"]["gate_counts"] == {"cx": 1, "h": 1}


def test_published_versions_are_immutable(local_registry, tmp_path):
    path = tmp_path / "bell.qasm"
    path.write_text(BELL)
    push(path, "qv:demo/bell", type="circuit", version="1.0.0", registry=local_registry)
    with pytest.raises(RegistryError, match="immutable"):
        push(path, "qv:demo/bell", type="circuit", version="1.0.0", registry=local_registry)


def test_version_resolution_prefers_highest_stable(local_registry, tmp_path):
    path = tmp_path / "bell.qasm"
    path.write_text(BELL)
    for version in ("1.0.0", "1.2.0", "1.10.0"):
        push(path, "qv:demo/bell", type="circuit", version=version, registry=local_registry)
    assert load("qv:demo/bell", registry=local_registry).meta["version"] == "1.10.0"
    assert load("qv:demo/bell@1.2", registry=local_registry).meta["version"] == "1.2.0"


def test_type_mismatch_rejected(local_registry, tmp_path):
    path = tmp_path / "bell.qasm"
    path.write_text(BELL)
    push(path, "qv:demo/bell", type="circuit", version="1.0.0", registry=local_registry)
    params = tmp_path / "params.json"
    params.write_text('{"theta": 0.5}')
    with pytest.raises(RegistryError, match="type"):
        push(params, "qv:demo/bell", type="parameters", version="1.1.0",
             registry=local_registry)


def test_non_json_payload_rejected_for_json_types(local_registry, tmp_path):
    bad = tmp_path / "params.json"
    bad.write_text("not json")
    with pytest.raises(ValueError, match="valid JSON"):
        push(bad, "qv:demo/params", type="parameters", version="1.0.0",
             registry=local_registry)


def test_capsule_push_and_load(local_registry, bell_capsule):
    capsule_id = local_registry.push_capsule(bell_capsule.files)
    assert capsule_id == bell_capsule.id
    hexid = capsule_id.split(":", 1)[1]

    loaded = load(f"qv:capsule/{hexid[:8]}", registry=local_registry)
    assert loaded.meta["kind"] == "capsule"
    assert loaded.files == bell_capsule.files


def test_capsule_prefix_ambiguity_raises(local_registry, bell_capsule):
    local_registry.push_capsule(bell_capsule.files)
    with pytest.raises(RegistryError, match="no capsule"):
        local_registry.get_capsule("ffffff")


def test_search_by_tag_and_type(local_registry, tmp_path):
    path = tmp_path / "bell.qasm"
    path.write_text(BELL)
    push(path, "qv:demo/bell", type="circuit", version="1.0.0",
         summary="Bell pair", tags=["entanglement"], registry=local_registry)
    assert local_registry.search("entanglement")[0]["name"] == "bell"
    assert local_registry.search("bell", type="parameters") == []
    assert local_registry.search("nomatch") == []


def test_blob_digest_verified_on_read(local_registry):
    digest = local_registry.put_blob(b"payload")
    path = local_registry._blob_path(digest)
    path.write_bytes(b"tampered")
    with pytest.raises(RegistryError, match="corrupt"):
        local_registry.get_blob(digest)
