// QAOA depth p=1 for MaxCut on the triangle graph K3.
// K3 is a special case where p=1 already reaches the exact max cut.
// Converged angles: qv:seeds/qaoa-maxcut-triangle-params. Instance: qv:instances/maxcut-triangle.
OPENQASM 3.0;
include "stdgates.inc";
input float gamma;
input float beta;
qubit[3] q;
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
