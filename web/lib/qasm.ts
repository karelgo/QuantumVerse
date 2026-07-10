// Minimal OpenQASM 2.0 / 3.x parser for the gate-model subset QuantumVerse
// renders and simulates. Framework-agnostic core: everything internal is QASM.

export interface QOp {
  name: string;
  qubits: number[];
  params: number[];
  /** for measure: destination classical bits, aligned with `qubits` */
  clbits?: number[];
}

export interface Circuit {
  numQubits: number;
  numClbits: number;
  ops: QOp[];
  /** qubit index -> register label, e.g. "q[3]" */
  qubitLabels: string[];
}

const GATE_ALIASES: Record<string, string> = {
  cnot: "cx",
  toffoli: "ccx",
  u1: "p",
  phase: "p",
  cu1: "cp",
  cphase: "cp",
  i: "id",
  u: "u3",
};

/** Gates we can render and simulate, with their parameter arity. */
export const KNOWN_GATES: Record<string, { arity: number; params: number }> = {
  id: { arity: 1, params: 0 },
  h: { arity: 1, params: 0 },
  x: { arity: 1, params: 0 },
  y: { arity: 1, params: 0 },
  z: { arity: 1, params: 0 },
  s: { arity: 1, params: 0 },
  sdg: { arity: 1, params: 0 },
  t: { arity: 1, params: 0 },
  tdg: { arity: 1, params: 0 },
  sx: { arity: 1, params: 0 },
  rx: { arity: 1, params: 1 },
  ry: { arity: 1, params: 1 },
  rz: { arity: 1, params: 1 },
  p: { arity: 1, params: 1 },
  u2: { arity: 1, params: 2 },
  u3: { arity: 1, params: 3 },
  cx: { arity: 2, params: 0 },
  cy: { arity: 2, params: 0 },
  cz: { arity: 2, params: 0 },
  ch: { arity: 2, params: 0 },
  swap: { arity: 2, params: 0 },
  cp: { arity: 2, params: 1 },
  crz: { arity: 2, params: 1 },
  ccx: { arity: 3, params: 0 },
  cswap: { arity: 3, params: 0 },
};

interface Register {
  offset: number;
  size: number;
}

class ExprParser {
  private pos = 0;
  constructor(private src: string) {}

  parse(): number {
    const v = this.expr();
    this.skipWs();
    if (this.pos < this.src.length) {
      throw new Error(`unexpected token in expression "${this.src}"`);
    }
    return v;
  }

  private skipWs() {
    while (this.pos < this.src.length && /\s/.test(this.src[this.pos])) this.pos++;
  }

  private expr(): number {
    let v = this.term();
    for (;;) {
      this.skipWs();
      const c = this.src[this.pos];
      if (c === "+") { this.pos++; v += this.term(); }
      else if (c === "-") { this.pos++; v -= this.term(); }
      else return v;
    }
  }

  private term(): number {
    let v = this.factor();
    for (;;) {
      this.skipWs();
      const c = this.src[this.pos];
      if (c === "*") { this.pos++; v *= this.factor(); }
      else if (c === "/") { this.pos++; v /= this.factor(); }
      else return v;
    }
  }

  private factor(): number {
    this.skipWs();
    const c = this.src[this.pos];
    if (c === "-") { this.pos++; return -this.factor(); }
    if (c === "+") { this.pos++; return this.factor(); }
    if (c === "(") {
      this.pos++;
      const v = this.expr();
      this.skipWs();
      if (this.src[this.pos] !== ")") throw new Error(`missing ")" in "${this.src}"`);
      this.pos++;
      return v;
    }
    const rest = this.src.slice(this.pos);
    const pi = rest.match(/^(pi|π)/i);
    if (pi) { this.pos += pi[0].length; return Math.PI; }
    const num = rest.match(/^\d+(\.\d+)?([eE][+-]?\d+)?/);
    if (num) { this.pos += num[0].length; return parseFloat(num[0]); }
    throw new Error(`cannot parse "${this.src}"`);
  }
}

export function evalParam(src: string): number {
  return new ExprParser(src).parse();
}

function stripComments(src: string): string {
  return src.replace(/\/\*[\s\S]*?\*\//g, " ").replace(/\/\/[^\n]*/g, " ");
}

export function parseQasm(src: string): Circuit {
  const qregs = new Map<string, Register>();
  const cregs = new Map<string, Register>();
  let numQubits = 0;
  let numClbits = 0;
  const ops: QOp[] = [];

  const resolve = (
    regs: Map<string, Register>,
    ref: string,
    what: string,
  ): number[] => {
    const m = ref.match(/^([A-Za-z_][\w]*)\s*(?:\[\s*(\d+)\s*\])?$/);
    if (!m) throw new Error(`bad ${what} reference "${ref}"`);
    const reg = regs.get(m[1]);
    if (!reg) throw new Error(`unknown ${what} register "${m[1]}"`);
    if (m[2] !== undefined) {
      const i = parseInt(m[2], 10);
      if (i >= reg.size) throw new Error(`index ${i} out of range for "${m[1]}"`);
      return [reg.offset + i];
    }
    return Array.from({ length: reg.size }, (_, i) => reg.offset + i);
  };

  const statements = stripComments(src)
    .split(";")
    .map((s) => s.replace(/\s+/g, " ").trim())
    .filter(Boolean);

  for (const stmt of statements) {
    if (/^OPENQASM\b/i.test(stmt) || /^include\b/i.test(stmt)) continue;

    // register declarations, QASM2 and QASM3 forms
    let m =
      stmt.match(/^qreg ([A-Za-z_]\w*) ?\[ ?(\d+) ?\]$/) ||
      stmt.match(/^qubit ?\[ ?(\d+) ?\] ([A-Za-z_]\w*)$/) ||
      stmt.match(/^qubit ([A-Za-z_]\w*)$/);
    if (m && /^(qreg|qubit)/.test(stmt)) {
      const name = stmt.startsWith("qreg") ? m[1] : m[2] ?? m[1];
      const size = stmt.startsWith("qreg") ? parseInt(m[2], 10) : m[2] ? parseInt(m[1], 10) : 1;
      qregs.set(name, { offset: numQubits, size });
      numQubits += size;
      continue;
    }
    m =
      stmt.match(/^creg ([A-Za-z_]\w*) ?\[ ?(\d+) ?\]$/) ||
      stmt.match(/^bit ?\[ ?(\d+) ?\] ([A-Za-z_]\w*)$/) ||
      stmt.match(/^bit ([A-Za-z_]\w*)$/);
    if (m && /^(creg|bit)/.test(stmt)) {
      const name = stmt.startsWith("creg") ? m[1] : m[2] ?? m[1];
      const size = stmt.startsWith("creg") ? parseInt(m[2], 10) : m[2] ? parseInt(m[1], 10) : 1;
      cregs.set(name, { offset: numClbits, size });
      numClbits += size;
      continue;
    }

    if (/^barrier\b/.test(stmt)) {
      const rest = stmt.slice("barrier".length).trim();
      const qubits = rest
        ? rest.split(",").flatMap((r) => resolve(qregs, r.trim(), "qubit"))
        : Array.from({ length: numQubits }, (_, i) => i);
      ops.push({ name: "barrier", qubits, params: [] });
      continue;
    }

    // measure: QASM2 `measure q[0] -> c[0]` / QASM3 `c[0] = measure q[0]`
    m =
      stmt.match(/^measure (.+?) ?-> ?(.+)$/) ||
      stmt.match(/^(.+?) ?= ?measure (.+)$/);
    if (m) {
      const qasm2 = stmt.startsWith("measure");
      const qs = resolve(qregs, (qasm2 ? m[1] : m[2]).trim(), "qubit");
      const cs = resolve(cregs, (qasm2 ? m[2] : m[1]).trim(), "classical");
      if (qs.length !== cs.length) {
        throw new Error(`measure width mismatch in "${stmt}"`);
      }
      ops.push({ name: "measure", qubits: qs, params: [], clbits: cs });
      continue;
    }

    // gate application: name(params)? targets
    m = stmt.match(/^([A-Za-z_]\w*) ?(?:\( ?([^)]*) ?\))? (.+)$/);
    if (!m) throw new Error(`cannot parse statement "${stmt}"`);
    let name = m[1].toLowerCase();
    name = GATE_ALIASES[name] ?? name;
    const spec = KNOWN_GATES[name];
    if (!spec) throw new Error(`unsupported gate "${m[1]}"`);
    const params = m[2]
      ? m[2].split(",").map((p) => evalParam(p.trim()))
      : [];
    if (params.length !== spec.params) {
      throw new Error(`gate "${name}" expects ${spec.params} parameter(s)`);
    }
    const targets = m[3].split(",").map((r) => resolve(qregs, r.trim(), "qubit"));
    if (spec.arity === 1 && targets.length === 1 && targets[0].length > 1) {
      // broadcast a single-qubit gate over a whole register: `h q;`
      for (const q of targets[0]) ops.push({ name, qubits: [q], params });
      continue;
    }
    const qubits = targets.map((t) => {
      if (t.length !== 1) throw new Error(`register broadcast unsupported for "${name}"`);
      return t[0];
    });
    if (qubits.length !== spec.arity) {
      throw new Error(`gate "${name}" expects ${spec.arity} qubit(s), got ${qubits.length}`);
    }
    if (new Set(qubits).size !== qubits.length) {
      throw new Error(`duplicate qubit in "${stmt}"`);
    }
    ops.push({ name, qubits, params });
  }

  if (numQubits === 0) throw new Error("no qubit register declared");

  const qubitLabels: string[] = new Array(numQubits);
  for (const [name, reg] of qregs) {
    for (let i = 0; i < reg.size; i++) {
      qubitLabels[reg.offset + i] = qregs.size > 1 || reg.size > 1 ? `${name}[${i}]` : name;
    }
  }

  return { numQubits, numClbits, ops, qubitLabels };
}
