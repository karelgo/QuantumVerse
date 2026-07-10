import pytest

BELL = """OPENQASM 3.0;
include "stdgates.inc";
qubit[2] q;
bit[2] c;
h q[0];
cx q[0], q[1];
c = measure q;
"""

# HZH = X on q[1]: same unitary as BELL up to global phase
BELL_VARIANT = """OPENQASM 3.0;
include "stdgates.inc";
qubit[2] q;
bit[2] c;
h q[0];
h q[1];
cz q[0], q[1];
h q[1];
c = measure q;
"""

NOT_BELL = """OPENQASM 3.0;
include "stdgates.inc";
qubit[2] q;
h q[0];
cx q[0], q[1];
x q[1];
"""

ANSATZ = """OPENQASM 3.0;
include "stdgates.inc";
input float theta;
qubit[2] q;
x q[0];
ry(theta) q[1];
cx q[1], q[0];
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
def bell_qasm():
    return BELL


@pytest.fixture
def sim_device():
    return dict(SIM_DEVICE)


@pytest.fixture
def bell_execution():
    return {"job_ids": [], "shots": 1000, "counts_raw": {"00": 503, "11": 497}}


@pytest.fixture
def bell_capsule(bell_qasm, sim_device, bell_execution):
    from quantumverse.capsule import Capsule

    return Capsule.create(
        circuit_qasm=bell_qasm,
        device=sim_device,
        execution=bell_execution,
        title="Bell pair on qv-sim",
        authors=[{"name": "Test Author"}],
        license="CC-BY-4.0",
        environment_lock="pinned test environment\n",
    )


@pytest.fixture
def local_registry(tmp_path, monkeypatch):
    from quantumverse.registry import LocalRegistry

    monkeypatch.setenv("QV_HOME", str(tmp_path / "qvhome"))
    monkeypatch.delenv("QV_REGISTRY_URL", raising=False)
    return LocalRegistry(tmp_path / "qvhome")
