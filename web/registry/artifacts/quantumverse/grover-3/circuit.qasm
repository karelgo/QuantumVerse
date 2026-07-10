OPENQASM 3.0;
include "stdgates.inc";
qubit[3] q;
bit[3] c;
h q;
// --- iteration 1 · oracle marks |101> ---
x q[1];
h q[2];
ccx q[0], q[1], q[2];
h q[2];
x q[1];
// --- diffusion ---
h q;
x q;
h q[2];
ccx q[0], q[1], q[2];
h q[2];
x q;
h q;
// --- iteration 2 · oracle ---
x q[1];
h q[2];
ccx q[0], q[1], q[2];
h q[2];
x q[1];
// --- diffusion ---
h q;
x q;
h q[2];
ccx q[0], q[1], q[2];
h q[2];
x q;
h q;
c = measure q;
