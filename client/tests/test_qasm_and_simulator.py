import math

import pytest

from quantumverse.qasm import QasmError, parse_qasm
from quantumverse.resources import count_resources
from quantumverse.simulator import SimulatorError, run

from conftest import ANSATZ, BELL


def test_bell_parse_and_resources():
    circuit = parse_qasm(BELL)
    res = count_resources(circuit)
    assert res["num_qubits"] == 2
    assert res["gate_counts"] == {"cx": 1, "h": 1}
    assert res["two_qubit_gate_count"] == 1
    assert res["t_count"] == 0
    assert res["depth"] == 3  # h, cx, measure layer


def test_t_count_rules():
    src = """OPENQASM 3.0;
include "stdgates.inc";
qubit[3] q;
t q[0];
tdg q[1];
ccx q[0], q[1], q[2];
"""
    res = count_resources(parse_qasm(src))
    assert res["t_count"] == 1 + 1 + 7
    assert res["two_qubit_gate_count"] == 0  # ccx is 3-qubit


def test_bell_probabilities_and_deterministic_counts():
    result = run(parse_qasm(BELL), shots=1000, seed=42)
    assert result.probabilities["00"] == pytest.approx(0.5)
    assert result.probabilities["11"] == pytest.approx(0.5)
    assert set(result.counts) == {"00", "11"}
    assert sum(result.counts.values()) == 1000
    again = run(parse_qasm(BELL), shots=1000, seed=42)
    assert again.counts == result.counts  # same seed, same samples


def test_grover_2q_is_certain():
    src = """OPENQASM 3.0;
include "stdgates.inc";
qubit[2] q;
bit[2] c;
h q[0]; h q[1];
cz q[0], q[1];
h q[0]; h q[1];
x q[0]; x q[1];
cz q[0], q[1];
x q[0]; x q[1];
h q[0]; h q[1];
c = measure q;
"""
    result = run(parse_qasm(src))
    assert result.probabilities["11"] == pytest.approx(1.0)


def test_parameter_binding_matches_analytic_form():
    theta = 0.5
    result = run(parse_qasm(ANSATZ), param_bindings={"theta": theta})
    assert result.probabilities["01"] == pytest.approx(math.cos(theta / 2) ** 2)
    assert result.probabilities["10"] == pytest.approx(math.sin(theta / 2) ** 2)


def test_unbound_parameter_is_an_error():
    with pytest.raises(SimulatorError, match="unbound parameter"):
        run(parse_qasm(ANSATZ))


def test_gate_after_measure_rejected():
    src = """OPENQASM 3.0;
include "stdgates.inc";
qubit[1] q;
bit[1] c;
c[0] = measure q[0];
x q[0];
"""
    with pytest.raises(SimulatorError, match="after measurement"):
        run(parse_qasm(src))


@pytest.mark.parametrize("bad", [
    "OPENQASM 2.0;\nqubit[1] q;",                 # wrong version
    "OPENQASM 3.0;\nqubit[1] q;\nnope q[0];",     # unknown gate
    "OPENQASM 3.0;\nqubit[1] q;\nh q[1];",        # out of range
    "OPENQASM 3.0;\nqubit[1] q;\ncx q[0], q[0];", # duplicate operand
])
def test_parser_rejects(bad):
    with pytest.raises(QasmError):
        parse_qasm(bad)


def test_partial_measurement_marginalizes():
    src = """OPENQASM 3.0;
include "stdgates.inc";
qubit[2] q;
bit[1] c;
h q[0];
cx q[0], q[1];
c[0] = measure q[0];
"""
    result = run(parse_qasm(src))
    assert result.probabilities == pytest.approx({"0": 0.5, "1": 0.5})
