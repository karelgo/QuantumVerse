// Dense statevector simulator. TypeScript today, the seam the Rust→WASM
// engine drops into later — same inputs (parsed QASM), same outputs.

import type { Circuit } from "./qasm";

export const MAX_SIM_QUBITS = 20;

export interface Amplitude {
  basis: string;
  re: number;
  im: number;
  prob: number;
}

export interface SimResult {
  counts: Record<string, number>;
  shots: number;
  numQubits: number;
  measuredBits: number;
  amplitudes: Amplitude[];
  /** per-qubit reduced Bloch vectors [⟨X⟩, ⟨Y⟩, ⟨Z⟩], pre-measurement */
  bloch: [number, number, number][];
  ms: number;
}

type Mat = [number, number, number, number, number, number, number, number]; // row-major, re/im pairs

const SQ = Math.SQRT1_2;

function mat(name: string, p: number[]): Mat {
  switch (name) {
    case "id": return [1, 0, 0, 0, 0, 0, 1, 0];
    case "h": return [SQ, 0, SQ, 0, SQ, 0, -SQ, 0];
    case "x": return [0, 0, 1, 0, 1, 0, 0, 0];
    case "y": return [0, 0, 0, -1, 0, 1, 0, 0];
    case "z": return [1, 0, 0, 0, 0, 0, -1, 0];
    case "s": return [1, 0, 0, 0, 0, 0, 0, 1];
    case "sdg": return [1, 0, 0, 0, 0, 0, 0, -1];
    case "t": return [1, 0, 0, 0, 0, 0, SQ, SQ];
    case "tdg": return [1, 0, 0, 0, 0, 0, SQ, -SQ];
    case "sx": return [0.5, 0.5, 0.5, -0.5, 0.5, -0.5, 0.5, 0.5];
    case "rx": {
      const c = Math.cos(p[0] / 2), s = Math.sin(p[0] / 2);
      return [c, 0, 0, -s, 0, -s, c, 0];
    }
    case "ry": {
      const c = Math.cos(p[0] / 2), s = Math.sin(p[0] / 2);
      return [c, 0, -s, 0, s, 0, c, 0];
    }
    case "rz": {
      const c = Math.cos(p[0] / 2), s = Math.sin(p[0] / 2);
      return [c, -s, 0, 0, 0, 0, c, s];
    }
    case "p": return [1, 0, 0, 0, 0, 0, Math.cos(p[0]), Math.sin(p[0])];
    case "u2": return mat("u3", [Math.PI / 2, p[0], p[1]]);
    case "u3": {
      const [th, ph, la] = p;
      const c = Math.cos(th / 2), s = Math.sin(th / 2);
      return [
        c, 0,
        -s * Math.cos(la), -s * Math.sin(la),
        s * Math.cos(ph), s * Math.sin(ph),
        c * Math.cos(ph + la), c * Math.sin(ph + la),
      ];
    }
    default:
      throw new Error(`no matrix for gate "${name}"`);
  }
}

/** Deterministic RNG (mulberry32) so replays are reproducible per seed. */
function rng(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a |= 0; a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function simulate(circuit: Circuit, shots: number, seed = 0x5eed): SimResult {
  const t0 = Date.now();
  const n = circuit.numQubits;
  if (n > MAX_SIM_QUBITS) {
    throw new Error(
      `${n} qubits exceeds the in-browser statevector limit of ${MAX_SIM_QUBITS}`,
    );
  }
  const dim = 1 << n;
  const re = new Float64Array(dim);
  const im = new Float64Array(dim);
  re[0] = 1;

  const apply1 = (target: number, m: Mat, ctlMask: number) => {
    const step = 1 << target;
    for (let base = 0; base < dim; base += step << 1) {
      for (let i = base; i < base + step; i++) {
        if ((i & ctlMask) !== ctlMask) continue;
        const j = i + step;
        const ar = re[i], ai = im[i], br = re[j], bi = im[j];
        re[i] = m[0] * ar - m[1] * ai + m[2] * br - m[3] * bi;
        im[i] = m[0] * ai + m[1] * ar + m[2] * bi + m[3] * br;
        re[j] = m[4] * ar - m[5] * ai + m[6] * br - m[7] * bi;
        im[j] = m[4] * ai + m[5] * ar + m[6] * bi + m[7] * br;
      }
    }
  };

  const phaseWhere = (mask: number, cos: number, sin: number) => {
    for (let i = 0; i < dim; i++) {
      if ((i & mask) === mask) {
        const r = re[i], q = im[i];
        re[i] = r * cos - q * sin;
        im[i] = q * cos + r * sin;
      }
    }
  };

  const swap = (a: number, b: number, ctlMask: number) => {
    const ba = 1 << a, bb = 1 << b;
    for (let i = 0; i < dim; i++) {
      if ((i & ba) && !(i & bb) && (i & ctlMask) === ctlMask) {
        const j = (i & ~ba) | bb;
        const r = re[i], q = im[i];
        re[i] = re[j]; im[i] = im[j];
        re[j] = r; im[j] = q;
      }
    }
  };

  const measureMap = new Map<number, number>(); // clbit -> qubit
  const measured = new Set<number>();

  for (const op of circuit.ops) {
    if (op.name === "barrier") continue;
    if (op.name === "measure") {
      op.qubits.forEach((q, i) => {
        measureMap.set(op.clbits![i], q);
        measured.add(q);
      });
      continue;
    }
    if (op.qubits.some((q) => measured.has(q))) {
      throw new Error("gates after measurement are not supported by this simulator");
    }
    const q = op.qubits;
    switch (op.name) {
      case "cx": apply1(q[1], mat("x", []), 1 << q[0]); break;
      case "cy": apply1(q[1], mat("y", []), 1 << q[0]); break;
      case "ch": apply1(q[1], mat("h", []), 1 << q[0]); break;
      case "cz": phaseWhere((1 << q[0]) | (1 << q[1]), -1, 0); break;
      case "cp": phaseWhere((1 << q[0]) | (1 << q[1]), Math.cos(op.params[0]), Math.sin(op.params[0])); break;
      case "crz": apply1(q[1], mat("rz", op.params), 1 << q[0]); break;
      case "swap": swap(q[0], q[1], 0); break;
      case "cswap": swap(q[1], q[2], 1 << q[0]); break;
      case "ccx": apply1(q[2], mat("x", []), (1 << q[0]) | (1 << q[1])); break;
      default: apply1(q[0], mat(op.name, op.params), 0);
    }
  }

  // cumulative distribution over basis states, then sample
  const cdf = new Float64Array(dim);
  let acc = 0;
  for (let i = 0; i < dim; i++) {
    acc += re[i] * re[i] + im[i] * im[i];
    cdf[i] = acc;
  }
  const norm = acc; // guard tiny float drift

  const clbits = measureMap.size
    ? [...measureMap.keys()].sort((a, b) => a - b)
    : null;
  const width = clbits ? clbits.length : n;

  const bitstring = (basis: number): string => {
    let s = "";
    if (clbits) {
      for (let k = clbits.length - 1; k >= 0; k--) {
        s += (basis >> measureMap.get(clbits[k])!) & 1;
      }
    } else {
      for (let k = n - 1; k >= 0; k--) s += (basis >> k) & 1;
    }
    return s;
  };

  const rand = rng(seed);
  const counts: Record<string, number> = {};
  for (let s = 0; s < shots; s++) {
    const r = rand() * norm;
    let lo = 0, hi = dim - 1;
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      if (cdf[mid] > r) hi = mid;
      else lo = mid + 1;
    }
    const key = bitstring(lo);
    counts[key] = (counts[key] ?? 0) + 1;
  }

  // per-qubit Bloch vectors: ⟨X⟩ = 2ΣRe(ā₀a₁), ⟨Y⟩ = 2ΣIm(ā₀a₁), ⟨Z⟩ = P₀ − P₁
  const bloch: [number, number, number][] = [];
  for (let q = 0; q < n; q++) {
    const step = 1 << q;
    let bx = 0,
      by = 0,
      bz = 0;
    for (let base = 0; base < dim; base += step << 1) {
      for (let i = base; i < base + step; i++) {
        const j = i + step;
        bx += 2 * (re[i] * re[j] + im[i] * im[j]);
        by += 2 * (re[i] * im[j] - im[i] * re[j]);
        bz += re[i] * re[i] + im[i] * im[i] - re[j] * re[j] - im[j] * im[j];
      }
    }
    bloch.push([bx, by, bz]);
  }

  // top amplitudes for the statevector view
  const idx = [...Array(dim).keys()]
    .map((i) => ({ i, prob: re[i] * re[i] + im[i] * im[i] }))
    .filter((e) => e.prob > 1e-12)
    .sort((a, b) => b.prob - a.prob)
    .slice(0, 16);
  const amplitudes: Amplitude[] = idx.map(({ i, prob }) => {
    let basis = "";
    for (let k = n - 1; k >= 0; k--) basis += (i >> k) & 1;
    return { basis, re: re[i], im: im[i], prob };
  });

  return {
    counts,
    shots,
    numQubits: n,
    measuredBits: width,
    amplitudes,
    bloch,
    ms: Date.now() - t0,
  };
}

/** Total variation distance between two count distributions (replay verdicts). */
export function totalVariation(
  a: Record<string, number>,
  b: Record<string, number>,
): number {
  const sa = Object.values(a).reduce((x, y) => x + y, 0) || 1;
  const sb = Object.values(b).reduce((x, y) => x + y, 0) || 1;
  const keys = new Set([...Object.keys(a), ...Object.keys(b)]);
  let tv = 0;
  for (const k of keys) tv += Math.abs((a[k] ?? 0) / sa - (b[k] ?? 0) / sb);
  return tv / 2;
}
