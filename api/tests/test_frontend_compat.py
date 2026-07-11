"""The Next.js frontend seam: /api/hub/v1/* must serve web/lib/types.ts shapes."""

import base64
import json

import pytest
from fastapi.testclient import TestClient

import quantumverse as qv
from quantumverse_api.app import create_app

BELL = """OPENQASM 3.0;
include "stdgates.inc";
qubit[2] q;
bit[2] c;
h q[0];
cx q[0], q[1];
c = measure q;
"""

ANSATZ = """OPENQASM 3.0;
include "stdgates.inc";
input float theta;
qubit[2] q;
x q[0];
ry(theta) q[1];
cx q[1], q[0];
"""

PARAMS_DOC = {
    "parameters_version": "0.1",
    "ansatz": "qv:seeds/ansatz@1.0.0",
    "instance": "qv:instances/h2-sto3g@1.0.0",
    "parameters": {"theta": -0.2236813969},
    "objective": {"name": "energy", "units": "hartree", "value": -1.857275},
    "method": "dense scan",
}


@pytest.fixture
def seeded(tmp_path, monkeypatch):
    monkeypatch.setenv("QV_HOME", str(tmp_path / "qvhome"))
    app = create_app(data_dir=str(tmp_path / "data"))
    client = TestClient(app)

    def publish(ns, name, type_, path, payload, card_fields=None):
        client.post(f"/api/v1/artifacts/{ns}/{name}", json={"type": type_})
        assert client.post(
            f"/api/v1/artifacts/{ns}/{name}/versions",
            json={"version": "1.0.0", "files": {path: {"text": payload}},
                  "card_fields": card_fields or {}},
        ).status_code == 201

    publish("seeds", "bell", "circuit", "circuit.qasm", BELL,
            {"summary": "Bell pair", "tags": ["bell"]})
    publish("seeds", "ansatz", "circuit", "circuit.qasm", ANSATZ,
            {"summary": "Minimal ansatz"})
    publish("seeds", "params", "parameters", "params.json", json.dumps(PARAMS_DOC),
            {"summary": "Converged parameters"})

    # a signed capsule back-referencing the bell artifact
    from quantumverse.signing import generate_keypair, sign_files

    generate_keypair("default")
    with qv.capture(title="Bell run", authors=["Compat test"],
                    artifacts={"circuit": "qv:seeds/bell@1.0.0"}) as cap:
        cap.run(BELL, shots=1000, seed=7)
    capsule = cap.capsule()
    signed = qv.Capsule(sign_files(capsule.files, capsule.id, signer="qv:users/compat"))
    payload = {
        "files": {n: {"b64": base64.b64encode(d).decode()} for n, d in signed.files.items()}
    }
    assert client.post("/api/v1/capsules", json=payload).status_code == 201
    return client, capsule


def test_list_artifacts_shape(seeded):
    client, capsule = seeded
    body = client.get("/api/hub/v1/artifacts").json()
    assert isinstance(body, list) and len(body) == 3  # bare array, not an envelope

    bell = next(a for a in body if a["name"] == "bell")
    assert bell["owner"] == "seeds"
    assert bell["kind"] == "circuit"
    assert bell["version"] == "1.0.0"
    assert bell["description"] == "Bell pair"
    assert bell["resources"]["qubits"] == 2
    assert bell["resources"]["clbits"] == 2
    assert bell["resources"]["gates"] == {"cx": 1, "h": 1}
    assert bell["capsuleCount"] == 1
    assert bell["maxTrustLevel"] == 1  # the linked capsule is author-signed
    assert bell["created"]  # version timestamp present

    # parameters artifact gets resources computed from its referenced ansatz
    params = next(a for a in body if a["name"] == "params")
    assert params["kind"] == "parameters"
    assert params["resources"]["qubits"] == 2
    assert params["capsuleCount"] == 0
    assert params["maxTrustLevel"] is None


def test_search_and_owner(seeded):
    client, _ = seeded
    hits = client.get("/api/hub/v1/artifacts", params={"q": "bell"}).json()
    assert [a["name"] for a in hits] == ["bell"]

    owner = client.get("/api/hub/v1/owners/seeds").json()
    assert owner["handle"] == "seeds" and owner["kind"] == "org"
    assert client.get("/api/hub/v1/owners/nobody").status_code == 404


def test_artifact_detail_shape(seeded):
    client, capsule = seeded
    detail = client.get("/api/hub/v1/artifacts/seeds/bell").json()
    assert detail["qasm"] == BELL
    assert detail["parameters"] is None
    assert len(detail["capsules"]) == 1
    summary = detail["capsules"][0]
    assert summary["id"] == capsule.id
    assert summary["shortId"] == capsule.short_id
    assert summary["trustLevel"] == 1
    assert "quantumverse.simulator (statevector)" == summary["backend"]
    assert summary["shots"] == 1000

    # versioned URL form
    assert client.get("/api/hub/v1/artifacts/seeds/bell@1.0.0").status_code == 200
    assert client.get("/api/hub/v1/artifacts/seeds/bell@9.9.9").status_code == 404
    assert client.get("/api/hub/v1/artifacts/seeds/nope").status_code == 404


def test_parameters_detail_maps_trained_parameters(seeded):
    client, _ = seeded
    detail = client.get("/api/hub/v1/artifacts/seeds/params").json()
    trained = detail["parameters"]
    assert trained["names"] == ["theta"]
    assert trained["values"] == [pytest.approx(-0.2236813969)]
    assert trained["energy"] == pytest.approx(-1.857275)
    assert trained["units"] == "hartree"
    # the detail qasm falls back to the referenced ansatz circuit
    assert detail["qasm"] == ANSATZ


def test_capsule_detail_integrity_and_shapes(seeded):
    client, capsule = seeded
    detail = client.get(f"/api/hub/v1/capsules/{capsule.id}").json()
    assert detail["id"] == capsule.id
    assert detail["trustLevel"] == 1
    manifest = detail["manifest"]
    assert manifest["artifacts"] == {"circuit": "qv:seeds/bell@1.0.0"}
    assert manifest["replay_of"] is None and manifest["doi"] is None
    assert detail["device"]["simulator"]["engine"] == "quantumverse.simulator"
    assert detail["execution"]["counts_raw"]
    assert detail["qasm"] == BELL

    integrity = detail["integrity"]
    assert integrity["idVerified"] is True
    assert integrity["signatureValid"] is True
    assert integrity["signer"] == "compat"
    assert integrity["files"] and all(f["verified"] for f in integrity["files"])

    # short id works too; unknown 404s (frontend maps 404 -> notFound page)
    assert client.get(f"/api/hub/v1/capsules/{capsule.short_id}").status_code == 200
    assert client.get("/api/hub/v1/capsules/ffffff").status_code == 404
