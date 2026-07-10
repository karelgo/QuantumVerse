// Export adapters live at the edges; the core stays QASM. This generates
// framework code from the parsed circuit for the artifact page's tabs.

import type { Circuit } from "./qasm";
import { formatRadians } from "./format";

function py(x: number): string {
  return formatRadians(x)
    .replace("π", "pi")
    .replace("−", "-")
    .replace(/^(\d+)pi/, "$1 * pi");
}

export function toQiskit(circuit: Circuit, ref: string): string {
  const lines = [
    "from math import pi",
    "from qiskit import QuantumCircuit",
    "",
    `# or: qc = qv.load("${ref}", framework="qiskit")`,
    `qc = QuantumCircuit(${circuit.numQubits}${circuit.numClbits ? `, ${circuit.numClbits}` : ""})`,
  ];
  for (const op of circuit.ops) {
    if (op.name === "barrier") {
      lines.push("qc.barrier()");
      continue;
    }
    if (op.name === "measure") {
      lines.push(
        ...op.qubits.map((q, i) => `qc.measure(${q}, ${op.clbits![i]})`),
      );
      continue;
    }
    const args = [...op.params.map(py), ...op.qubits].join(", ");
    lines.push(`qc.${op.name}(${args})`);
  }
  return lines.join("\n");
}

export function loadSnippet(ref: string, kind: string): string {
  if (kind === "parameters") {
    return `import quantumverse as qv\n\nansatz, params = qv.load("${ref}", framework="qiskit")`;
  }
  return `import quantumverse as qv\n\ncircuit = qv.load("${ref}", framework="qiskit")`;
}
