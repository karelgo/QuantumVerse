// Circuit layout (visual columns for SVG) and resource counting
// (Circuit Card auto-population, per RFC-0002's direction).

import type { Circuit, QOp } from "./qasm";

export interface LayoutOp extends QOp {
  col: number;
}

export interface CircuitLayout {
  cols: number;
  ops: LayoutOp[];
}

/**
 * Greedy left-packing. For the visual layout a multi-qubit gate reserves
 * every wire it spans so nothing overlaps its vertical connector.
 */
export function layoutCircuit(circuit: Circuit): CircuitLayout {
  const lastCol = new Array<number>(circuit.numQubits).fill(-1);
  const ops: LayoutOp[] = [];
  let cols = 0;

  for (const op of circuit.ops) {
    if (op.name === "barrier") {
      const sync = Math.max(...op.qubits.map((q) => lastCol[q]));
      for (const q of op.qubits) lastCol[q] = sync;
      continue;
    }
    const lo = Math.min(...op.qubits);
    const hi = Math.max(...op.qubits);
    let col = 0;
    for (let q = lo; q <= hi; q++) col = Math.max(col, lastCol[q] + 1);
    for (let q = lo; q <= hi; q++) lastCol[q] = col;
    cols = Math.max(cols, col + 1);
    ops.push({ ...op, col });
  }

  return { cols, ops };
}

export interface CircuitResources {
  qubits: number;
  clbits: number;
  depth: number;
  gateCount: number;
  twoQubitCount: number;
  tCount: number;
  gates: Record<string, number>;
}

/** Logical depth: only the qubits a gate touches advance its layer. */
export function computeResources(circuit: Circuit): CircuitResources {
  const layer = new Array<number>(circuit.numQubits).fill(0);
  const gates: Record<string, number> = {};
  let depth = 0;
  let gateCount = 0;
  let twoQubitCount = 0;
  let tCount = 0;

  for (const op of circuit.ops) {
    if (op.name === "barrier") continue;
    const next = Math.max(...op.qubits.map((q) => layer[q])) + 1;
    for (const q of op.qubits) layer[q] = next;
    depth = Math.max(depth, next);
    if (op.name === "measure") continue;
    gateCount++;
    gates[op.name] = (gates[op.name] ?? 0) + 1;
    if (op.qubits.length >= 2) twoQubitCount++;
    if (op.name === "t" || op.name === "tdg") tCount++;
  }

  return {
    qubits: circuit.numQubits,
    clbits: circuit.numClbits,
    depth,
    gateCount,
    twoQubitCount,
    tCount,
    gates,
  };
}
