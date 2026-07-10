import base64
import json

import pytest
from fastapi.testclient import TestClient

from quantumverse.capsule import Capsule
from quantumverse_api.app import create_app

BELL = """OPENQASM 3.0;
include "stdgates.inc";
qubit[2] q;
bit[2] c;
h q[0];
cx q[0], q[1];
c = measure q;
"""

SIM_DEVICE = {
    "backend": {"provider": "quantumverse", "name": "qv-sim", "version": "0.1.0"},
    "captured": "2026-07-10T00:00:00Z",
    "topology": {"num_qubits": 2},
    "qubits": [],
    "gates": [],
    "simulator": {"engine": "quantumverse.simulator", "method": "statevector", "seed": 42},
}


@pytest.fixture
def client(tmp_path):
    app = create_app(data_dir=str(tmp_path / "data"))
    with TestClient(app) as test_client:
        yield test_client


def _publish_bell(client, version="1.0.0"):
    response = client.post("/api/v1/artifacts/demo/bell", json={"type": "circuit"})
    assert response.status_code in (200, 201)
    response = client.post(
        "/api/v1/artifacts/demo/bell/versions",
        json={
            "version": version,
            "files": {"circuit.qasm": {"text": BELL}},
            "card_fields": {"summary": "Bell pair", "tags": ["bell"]},
        },
    )
    return response


def test_healthz(client):
    assert client.get("/healthz").json()["status"] == "ok"


def test_artifact_lifecycle(client):
    response = _publish_bell(client)
    assert response.status_code == 201
    files = response.json()["files"]
    assert files["circuit.qasm"].startswith("sha256:")

    record = client.get("/api/v1/artifacts/demo/bell").json()
    assert record["type"] == "circuit"
    assert record["versions"] == ["1.0.0"]
    assert record["latest"] == "1.0.0"

    resolved = client.get(
        "/api/v1/artifacts/demo/bell/resolve", params={"version": "latest"}
    ).json()
    assert resolved["version"] == "1.0.0"
    blob = client.get(f"/api/v1/blobs/{resolved['files']['circuit.qasm']}")
    assert blob.status_code == 200
    assert blob.content.decode() == BELL


def test_card_is_rebuilt_server_side(client):
    client.post("/api/v1/artifacts/demo/bell", json={"type": "circuit"})
    response = client.post(
        "/api/v1/artifacts/demo/bell/versions",
        json={
            "version": "1.0.0",
            "files": {"circuit.qasm": {"text": BELL}},
            # a lying card: resources must be recomputed, not trusted
            "card_fields": {"summary": "Bell", "resources": {"num_qubits": 99}},
        },
    )
    assert response.status_code == 201
    card = client.get(
        "/api/v1/artifacts/demo/bell/resolve", params={"version": "1.0.0"}
    ).json()["card"]
    assert card["resources"]["num_qubits"] == 2  # RFC-0002: computed, not claimed
    assert card["summary"] == "Bell"


def test_immutability_conflict(client):
    assert _publish_bell(client).status_code == 201
    response = _publish_bell(client)
    assert response.status_code == 409
    assert "immutable" in response.json()["detail"]


def test_type_conflict_and_bad_inputs(client):
    client.post("/api/v1/artifacts/demo/bell", json={"type": "circuit"})
    assert client.post(
        "/api/v1/artifacts/demo/bell", json={"type": "parameters"}
    ).status_code == 409
    assert client.post(
        "/api/v1/artifacts/demo/thing", json={"type": "nonsense"}
    ).status_code == 400
    assert client.post(
        "/api/v1/artifacts/BAD--NS/thing", json={"type": "circuit"}
    ).status_code == 400
    assert client.post(
        "/api/v1/artifacts/demo/thing/versions",
        json={"version": "not-semver", "files": {}},
    ).status_code == 400


def test_unparseable_circuit_rejected(client):
    client.post("/api/v1/artifacts/demo/bad", json={"type": "circuit"})
    response = client.post(
        "/api/v1/artifacts/demo/bad/versions",
        json={"version": "1.0.0", "files": {"circuit.qasm": {"text": "not qasm"}}},
    )
    assert response.status_code == 422
    assert "rejected" in response.json()["detail"]


def test_missing_payload_file_rejected(client):
    client.post("/api/v1/artifacts/demo/params", json={"type": "parameters"})
    response = client.post(
        "/api/v1/artifacts/demo/params/versions",
        json={"version": "1.0.0", "files": {"other.json": {"text": "{}"}}},
    )
    assert response.status_code == 422
    assert "params.json" in response.json()["detail"]


def test_binary_b64_round_trip(client):
    client.post("/api/v1/artifacts/demo/noise", json={"type": "noise-model"})
    payload = json.dumps({"model": "depolarizing", "p": 0.01}).encode()
    response = client.post(
        "/api/v1/artifacts/demo/noise/versions",
        json={
            "version": "1.0.0",
            "files": {"noise.json": {"b64": base64.b64encode(payload).decode()}},
        },
    )
    assert response.status_code == 201
    digest = response.json()["files"]["noise.json"]
    assert client.get(f"/api/v1/blobs/{digest}").content == payload


def test_version_resolution_over_http(client):
    client.post("/api/v1/artifacts/demo/bell", json={"type": "circuit"})
    for version in ("1.0.0", "1.2.0", "1.10.0"):
        client.post(
            "/api/v1/artifacts/demo/bell/versions",
            json={"version": version, "files": {"circuit.qasm": {"text": BELL}}},
        )
    resolved = client.get(
        "/api/v1/artifacts/demo/bell/resolve", params={"version": "1.2"}
    ).json()
    assert resolved["version"] == "1.2.0"
    assert client.get(
        "/api/v1/artifacts/demo/bell/resolve", params={"version": "3"}
    ).status_code == 404


def test_search(client):
    _publish_bell(client)
    results = client.get("/api/v1/search", params={"q": "bell"}).json()["results"]
    assert results and results[0]["name"] == "bell"
    assert results[0]["summary"] == "Bell pair"
    assert client.get(
        "/api/v1/search", params={"q": "bell", "type": "parameters"}
    ).json()["results"] == []


def _bell_capsule() -> Capsule:
    return Capsule.create(
        circuit_qasm=BELL,
        device=SIM_DEVICE,
        execution={"job_ids": [], "shots": 1000, "counts_raw": {"00": 503, "11": 497}},
        title="Bell pair on qv-sim",
        authors=[{"name": "API test"}],
        license="CC-BY-4.0",
        environment_lock="pinned\n",
    )


def _capsule_payload(capsule: Capsule) -> dict:
    return {
        "files": {
            name: {"b64": base64.b64encode(data).decode()}
            for name, data in capsule.files.items()
        }
    }


def test_capsule_upload_fetch_and_revalidate(client):
    capsule = _bell_capsule()
    response = client.post("/api/v1/capsules", json=_capsule_payload(capsule))
    assert response.status_code == 201
    assert response.json()["id"] == capsule.id

    hexid = capsule.id.split(":", 1)[1]
    record = client.get(f"/api/v1/capsules/{hexid[:8]}").json()
    fetched = {}
    for name, digest in record["files"].items():
        fetched[name] = client.get(f"/api/v1/blobs/{digest}").content
    assert not [f for f in Capsule(fetched).validate() if f.severity == "error"]

    listed = client.get("/api/v1/capsules").json()["capsules"]
    assert listed[0]["id"] == capsule.id
    assert "Bell" in listed[0]["title"]


def test_invalid_capsule_rejected(client):
    capsule = _bell_capsule()
    tampered = dict(capsule.files)
    execution = json.loads(tampered["execution.json"])
    execution["counts_raw"] = {"00": 1000}
    tampered["execution.json"] = json.dumps(execution).encode()
    response = client.post(
        "/api/v1/capsules", json=_capsule_payload(Capsule(tampered))
    )
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert any("digest-mismatch" in e for e in detail["errors"])


def test_capsule_lookup_errors(client):
    assert client.get("/api/v1/capsules/zz").status_code == 400
    assert client.get("/api/v1/capsules/abcdef").status_code == 404


def test_signed_capsule_reports_trust_level(client, tmp_path, monkeypatch):
    from quantumverse.signing import generate_keypair, sign_files

    monkeypatch.setenv("QV_HOME", str(tmp_path / "qvhome"))
    generate_keypair("default")

    capsule = _bell_capsule()
    signed = Capsule(sign_files(capsule.files, capsule.id, signer="qv:users/api-test"))
    response = client.post("/api/v1/capsules", json=_capsule_payload(signed))
    assert response.status_code == 201
    body = response.json()
    assert body["trust"] == 1
    assert "author-signed" in body["trust_detail"]

    hexid = capsule.id.split(":", 1)[1]
    assert client.get(f"/api/v1/capsules/{hexid[:8]}").json()["trust"] == 1
    assert client.get("/api/v1/capsules").json()["capsules"][0]["trust"] == 1


def test_invalid_signature_rejected_by_registry(client, tmp_path, monkeypatch):
    from quantumverse.signing import generate_keypair, sign_files

    monkeypatch.setenv("QV_HOME", str(tmp_path / "qvhome"))
    generate_keypair("default")

    capsule = _bell_capsule()
    files = sign_files(capsule.files, capsule.id)
    doc = json.loads(files["author.sig"])
    doc["signature"] = "A" * 86 + "=="  # structurally plausible, cryptographically wrong
    files["author.sig"] = json.dumps(doc).encode()
    response = client.post("/api/v1/capsules", json=_capsule_payload(Capsule(files)))
    assert response.status_code == 422
    assert any("signature-invalid" in e for e in response.json()["detail"]["errors"])


# -- devices (RFC-0004) -------------------------------------------------------

DEVICE_RECORD = {
    "record_version": "0.1",
    "summary": "Reference simulator",
    "modality": "simulator",
    "backend": {"provider": "quantumverse", "name": "qv-sim"},
}


def test_device_register_and_card(client):
    response = client.post(
        "/api/v1/devices/quantumverse/qv-sim", json={"record": DEVICE_RECORD}
    )
    assert response.status_code == 201
    card = response.json()
    assert card["ref"] == "qv:device/quantumverse/qv-sim"
    assert card["calibration_count"] == 0

    assert client.get("/api/v1/devices/quantumverse/qv-sim").json()["record"] == DEVICE_RECORD
    assert client.get("/api/v1/devices").json()["devices"][0]["name"] == "qv-sim"
    assert client.get("/api/v1/devices/no/body").status_code == 404


def test_device_conflicts_and_validation(client):
    assert client.post(
        "/api/v1/devices/quantumverse/qv-sim", json={"record": DEVICE_RECORD}
    ).status_code == 201
    # same address again
    assert client.post(
        "/api/v1/devices/quantumverse/qv-sim", json={"record": DEVICE_RECORD}
    ).status_code == 409
    # same backend identity under a different address
    assert client.post(
        "/api/v1/devices/lab/clone", json={"record": DEVICE_RECORD}
    ).status_code == 409
    # schema-invalid record
    assert client.post(
        "/api/v1/devices/lab/bad", json={"record": {"record_version": "0.1"}}
    ).status_code == 422
    # malformed address
    assert client.post(
        "/api/v1/devices/BAD--/x", json={"record": DEVICE_RECORD}
    ).status_code == 400


def test_capsule_feeds_device_timeline(client):
    client.post("/api/v1/devices/quantumverse/qv-sim", json={"record": DEVICE_RECORD})
    capsule = _bell_capsule()
    assert client.post("/api/v1/capsules", json=_capsule_payload(capsule)).status_code == 201

    card = client.get("/api/v1/devices/quantumverse/qv-sim").json()
    assert card["calibration_count"] == 1
    assert card["capsule_count"] == 1
    assert card["latest_calibration"]["summary"]["num_qubits"] == 2

    timeline = client.get(
        "/api/v1/devices/quantumverse/qv-sim/calibrations"
    ).json()["calibrations"]
    assert timeline[0]["capsule"] == capsule.id
    # the full snapshot is retrievable as a blob
    snapshot = client.get(f"/api/v1/blobs/{timeline[0]['snapshot']}")
    assert snapshot.status_code == 200
    assert json.loads(snapshot.content)["backend"]["name"] == "qv-sim"

    linked = client.get("/api/v1/devices/quantumverse/qv-sim/capsules").json()["capsules"]
    assert linked[0]["id"] == capsule.id

    # re-uploading the same capsule adds no duplicate timeline entry
    client.post("/api/v1/capsules", json=_capsule_payload(capsule))
    assert client.get(
        "/api/v1/devices/quantumverse/qv-sim"
    ).json()["calibration_count"] == 1


def test_birth_certificate_recomputed_server_side(client):
    import quantumverse as qv
    from quantumverse.certify import suite_circuits

    client.post("/api/v1/devices/quantumverse/qv-sim", json={"record": DEVICE_RECORD})

    capsule_ids = []
    for name, qasm_text in suite_circuits(3).items():
        with qv.capture(title=f"check {name}", authors=["API test"]) as cap:
            cap.run(qasm_text, shots=4096, seed=13)
        capsule = cap.capsule()
        assert client.post(
            "/api/v1/capsules", json=_capsule_payload(capsule)
        ).status_code == 201
        capsule_ids.append(capsule.id)

    # unknown capsule id -> rejected (push first; the server only trusts its own store)
    bogus = ["sha256:" + "0" * 64]
    assert client.post(
        "/api/v1/devices/quantumverse/qv-sim/certificate", json={"capsules": bogus}
    ).status_code == 404

    # incomplete suite -> 422
    assert client.post(
        "/api/v1/devices/quantumverse/qv-sim/certificate",
        json={"capsules": capsule_ids[:2]},
    ).status_code == 422

    response = client.post(
        "/api/v1/devices/quantumverse/qv-sim/certificate", json={"capsules": capsule_ids}
    )
    assert response.status_code == 201
    certificate = response.json()
    assert certificate["passed"] is True
    assert len(certificate["checks"]) == 4
    assert all(c["capsule"] in capsule_ids for c in certificate["checks"])

    # pinned to the Device Card and retrievable on its own
    card = client.get("/api/v1/devices/quantumverse/qv-sim").json()
    assert card["certificate"]["passed"] is True
    assert client.get(
        "/api/v1/devices/quantumverse/qv-sim/certificate"
    ).json() == certificate

    # a device with no certificate 404s
    other = {**DEVICE_RECORD, "backend": {"provider": "lab", "name": "bare"}}
    client.post("/api/v1/devices/lab/bare", json={"record": other})
    assert client.get("/api/v1/devices/lab/bare/certificate").status_code == 404


def test_direct_calibration_submission(client):
    client.post("/api/v1/devices/quantumverse/qv-sim", json={"record": DEVICE_RECORD})
    snapshot = {
        "backend": {"provider": "quantumverse", "name": "qv-sim"},
        "captured": "2026-07-11T00:00:00Z",
        "topology": {"num_qubits": 2},
        "qubits": [{"index": 0, "t1_us": 100.0}, {"index": 1, "t1_us": 200.0}],
        "gates": [],
        "simulator": {"engine": "quantumverse.simulator", "method": "statevector"},
    }
    response = client.post(
        "/api/v1/devices/quantumverse/qv-sim/calibrations", json=snapshot
    )
    assert response.status_code == 201
    assert response.json()["summary"]["median_t1_us"] == 150.0

    timeline = client.get(
        "/api/v1/devices/quantumverse/qv-sim/calibrations"
    ).json()["calibrations"]
    assert timeline[0]["capsule"] is None  # direct submission, not capsule-backed

    assert client.post(
        "/api/v1/devices/quantumverse/qv-sim/calibrations", json={"nonsense": True}
    ).status_code == 422
