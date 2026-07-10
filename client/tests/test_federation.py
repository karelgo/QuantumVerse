"""Federation (RFC-0007): sync between registries, trust-nothing replication."""

import json

import pytest

import quantumverse as qv
from quantumverse._schema import schema_errors
from quantumverse.federation import FederationError, sync
from quantumverse.registry import LocalRegistry

from conftest import BELL

TRIANGLE = {
    "instance_version": "0.1", "name": "maxcut-triangle", "kind": "maxcut",
    "nodes": 3, "edges": [[0, 1], [1, 2], [0, 2]], "weights": [1, 1, 1],
    "max_cut_value": 2,
}
QAOA = (
    'OPENQASM 3.0;\ninclude "stdgates.inc";\ninput float gamma;\ninput float beta;\n'
    "qubit[3] q;\nbit[3] c;\nh q[0];\nh q[1];\nh q[2];\n"
    "cx q[0], q[1];\nrz(2*gamma) q[1];\ncx q[0], q[1];\n"
    "cx q[1], q[2];\nrz(2*gamma) q[2];\ncx q[1], q[2];\n"
    "cx q[0], q[2];\nrz(2*gamma) q[2];\ncx q[0], q[2];\n"
    "rx(2*beta) q[0];\nrx(2*beta) q[1];\nrx(2*beta) q[2];\nc = measure q;\n"
)


@pytest.fixture
def two_registries(tmp_path):
    src = LocalRegistry(tmp_path / "src")
    dst = LocalRegistry(tmp_path / "dst")
    return src, dst


def _populate_source(src, tmp_path):
    """A source registry with an artifact, device, capsule, certificate, board+entry."""
    # artifact
    circ = tmp_path / "bell.qasm"
    circ.write_text(BELL)
    qv.push(circ, "qv:seeds/bell", type="circuit", version="1.0.0",
            summary="Bell", tags=["bell"], registry=src)
    inst = tmp_path / "triangle.json"
    inst.write_text(json.dumps(TRIANGLE))
    qv.push(inst, "qv:instances/maxcut-triangle", type="instance", version="1.0.0",
            registry=src)

    # device + a birth certificate (its four commissioning capsules)
    src.register_device("quantumverse", "qv-sim", {
        "record_version": "0.1", "summary": "ref sim", "modality": "simulator",
        "backend": {"provider": "quantumverse", "name": "qv-sim"},
    })
    from quantumverse.certify import suite_circuits
    cert_ids = []
    for name, qasm_text in suite_circuits(3).items():
        with qv.capture(title=f"check {name}", authors=["src"]) as cap:
            cap.run(qasm_text, shots=4096, seed=3)
        capsule = cap.capsule()
        src.push_capsule(capsule.files)
        cert_ids.append(capsule.id)
    src.submit_certificate("quantumverse", "qv-sim", cert_ids)

    # board + a QAOA entry
    src.create_board({
        "board_version": "0.1", "name": "k3", "title": "K3",
        "instance": "qv:instances/maxcut-triangle@1.0.0", "metric": "maxcut-ratio",
        "higher_is_better": True,
    })
    with qv.capture(title="QAOA", authors=["src"]) as cap:
        cap.run(QAOA, shots=4096, seed=42, params={"gamma": 1.8785555922, "beta": 1.2630370614})
    qaoa_capsule = cap.capsule()
    src.push_capsule(qaoa_capsule.files)
    entry = src.submit_entry("k3", qaoa_capsule.id)
    return qaoa_capsule, entry


def test_catalog_is_schema_valid_and_ids_only(two_registries, tmp_path):
    src, _dst = two_registries
    _populate_source(src, tmp_path)
    catalog = src.catalog()
    assert schema_errors("federation-catalog", catalog) == []
    # capsules are ids, entries/certs are capsule-id lists — no scores/verdicts
    assert all(c.startswith("sha256:") for c in catalog["capsules"])
    assert catalog["boards"][0]["entries"]
    assert "score" not in json.dumps(catalog["boards"][0]["entries"])
    assert catalog["devices"][0]["certificates"][0]  # four capsule ids


def test_sync_replicates_everything(two_registries, tmp_path):
    src, dst = two_registries
    qaoa_capsule, src_entry = _populate_source(src, tmp_path)

    report = sync(src, dst)
    assert report.artifacts_synced == 2
    assert report.capsules_synced == 5  # 4 commissioning + 1 qaoa
    assert report.devices_synced == 1
    assert report.certificates_submitted == 1
    assert report.boards_synced == 1
    assert report.entries_submitted == 1

    # artifact crossed and is loadable, byte-identical
    assert qv.load("qv:seeds/bell", registry=dst).text() == BELL
    # capsule id is identical on both sides (content addressing)
    assert dst.get_capsule(qaoa_capsule.id.split(":")[1])["id"] == qaoa_capsule.id
    # device + certificate re-derived and passing
    assert dst.get_device("quantumverse", "qv-sim")["certificate"]["passed"] is True
    # calibration timeline auto-linked from the synced capsules
    assert dst.get_device("quantumverse", "qv-sim")["calibration_count"] == 5


def test_sync_recomputes_scores_not_copies_them(two_registries, tmp_path):
    src, dst = two_registries
    qaoa_capsule, src_entry = _populate_source(src, tmp_path)
    sync(src, dst)

    # the destination's score is computed from the synced capsule's counts —
    # identical to the source's because the bytes are identical, but derived,
    # not trusted from the catalog (which never carried it).
    dst_board = dst.get_board("k3")
    assert dst_board["entries"][0]["capsule"] == qaoa_capsule.id
    assert dst_board["entries"][0]["score"] == pytest.approx(src_entry["score"])
    assert dst_board["entries"][0]["rank"] == 1


def test_sync_is_idempotent(two_registries, tmp_path):
    src, dst = two_registries
    _populate_source(src, tmp_path)
    sync(src, dst)
    second = sync(src, dst)
    # nothing new transfers the second time — everything dedupes by content
    assert second.artifacts_synced == 0 and second.artifacts_skipped == 2
    assert second.capsules_synced == 0 and second.capsules_skipped == 5
    assert second.devices_synced == 0 and second.devices_skipped == 1
    assert second.boards_synced == 0 and second.boards_skipped == 1


def test_sync_preserves_signature_trust(two_registries, tmp_path, monkeypatch):
    from quantumverse.signing import generate_keypair, sign_files, trust_level

    src, dst = two_registries
    monkeypatch.setenv("QV_HOME", str(tmp_path / "qvhome"))
    generate_keypair("default")

    with qv.capture(title="signed run", authors=["src"]) as cap:
        cap.run(BELL, shots=1000, seed=1)
    signed = qv.Capsule(sign_files(cap.capsule().files, cap.capsule().id))
    src.push_capsule(signed.files)

    sync(src, dst)
    _id, files = dst.capsule_files(signed.id)
    assert trust_level(files, signed.id)[0] == 1  # author signature survived the crossing


def test_sync_rejects_same_registry(two_registries):
    src, _dst = two_registries
    with pytest.raises(FederationError, match="same"):
        sync(src, src)
