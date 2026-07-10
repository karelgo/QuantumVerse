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
