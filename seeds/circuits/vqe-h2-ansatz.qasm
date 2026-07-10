// Minimal two-qubit ansatz for the tapered STO-3G H2 Hamiltonian (R = 0.735 A):
// prepares cos(theta/2)|01> + sin(theta/2)|10>, spanning the ground-state subspace.
// Converged parameters: qv:seeds/vqe-h2-params. Hamiltonian: qv:instances/h2-sto3g.
OPENQASM 3.0;
include "stdgates.inc";
input float theta;
qubit[2] q;
x q[0];
ry(theta) q[1];
cx q[1], q[0];
