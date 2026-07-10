// qasm.js — parser for the QuantumVerse shared OpenQASM 3 subset.
//
// Turns QASM source into the qv-sim Program JSON:
//   { num_qubits: N, ops: [{g, q, p?, c?}, ...] }
// Angle expressions (pi arithmetic, declared `input float` parameters) are
// evaluated here; the simulator only ever sees plain f64 radians.
//
// Little-endian convention throughout the platform: qubit 0 is the
// least-significant bit; bitstrings render qubit n-1 ... qubit 0.

export class QasmError extends Error {
  constructor(message, line = null) {
    super(line != null ? `line ${line}: ${message}` : message);
    this.name = 'QasmError';
    this.line = line;
  }
}

// gate name -> { a: total qubit operands, p: number of angle parameters }
const GATES = {
  x: { a: 1, p: 0 }, y: { a: 1, p: 0 }, z: { a: 1, p: 0 }, h: { a: 1, p: 0 },
  s: { a: 1, p: 0 }, sdg: { a: 1, p: 0 }, t: { a: 1, p: 0 }, tdg: { a: 1, p: 0 },
  sx: { a: 1, p: 0 },
  rx: { a: 1, p: 1 }, ry: { a: 1, p: 1 }, rz: { a: 1, p: 1 }, p: { a: 1, p: 1 },
  u: { a: 1, p: 3 },
  cx: { a: 2, p: 0 }, cy: { a: 2, p: 0 }, cz: { a: 2, p: 0 }, ch: { a: 2, p: 0 },
  swap: { a: 2, p: 0 },
  cp: { a: 2, p: 1 }, crx: { a: 2, p: 1 }, cry: { a: 2, p: 1 }, crz: { a: 2, p: 1 },
  ccx: { a: 3, p: 0 }, cswap: { a: 3, p: 0 },
};

const ID_RE = /^[A-Za-z_][A-Za-z0-9_]*$/;

/* ------------------------------------------------------------------ *
 * Comment stripping (preserves line structure for error reporting)
 * ------------------------------------------------------------------ */

function stripComments(src) {
  let out = '';
  let i = 0;
  let line = 1;
  while (i < src.length) {
    const c = src[i];
    if (c === '/' && src[i + 1] === '/') {
      while (i < src.length && src[i] !== '\n') i++;
    } else if (c === '/' && src[i + 1] === '*') {
      const startLine = line;
      i += 2;
      let closed = false;
      while (i < src.length) {
        if (src[i] === '*' && src[i + 1] === '/') { i += 2; closed = true; break; }
        if (src[i] === '\n') { out += '\n'; line++; }
        i++;
      }
      if (!closed) throw new QasmError('unterminated /* comment', startLine);
    } else {
      if (c === '\n') line++;
      out += c;
      i++;
    }
  }
  return out;
}

/* ------------------------------------------------------------------ *
 * Statement splitting (on ';', tracking the line of each statement)
 * ------------------------------------------------------------------ */

function splitStatements(src) {
  const stmts = [];
  let buf = '';
  let line = 1;
  let stmtLine = null;
  for (let i = 0; i < src.length; i++) {
    const c = src[i];
    if (c === ';') {
      const text = buf.trim().replace(/\s+/g, ' ');
      if (text.length) stmts.push({ text, line: stmtLine ?? line });
      buf = '';
      stmtLine = null;
    } else {
      if (c === '\n') line++;
      if (stmtLine === null && !/\s/.test(c)) stmtLine = line;
      buf += c;
    }
  }
  const trailing = buf.trim();
  if (trailing.length) {
    throw new QasmError(`missing ';' after '${trailing.slice(0, 40)}'`, stmtLine ?? line);
  }
  return stmts;
}

/* ------------------------------------------------------------------ *
 * Angle-expression evaluation
 *   expr := term (('+'|'-') term)*
 *   term := unary (('*'|'/') unary)*
 *   unary := ('-'|'+') unary | primary
 *   primary := NUMBER | 'pi' | IDENT | '(' expr ')'
 * ------------------------------------------------------------------ */

function tokenizeExpr(text, line) {
  const tokens = [];
  let i = 0;
  while (i < text.length) {
    const c = text[i];
    if (/\s/.test(c)) { i++; continue; }
    if ('+-*/()'.includes(c)) { tokens.push({ t: c }); i++; continue; }
    const rest = text.slice(i);
    let m = rest.match(/^(\d+\.\d*([eE][+-]?\d+)?|\.\d+([eE][+-]?\d+)?|\d+([eE][+-]?\d+)?)/);
    if (m) { tokens.push({ t: 'num', v: parseFloat(m[0]) }); i += m[0].length; continue; }
    m = rest.match(/^[A-Za-z_][A-Za-z0-9_]*/);
    if (m) { tokens.push({ t: 'id', v: m[0] }); i += m[0].length; continue; }
    throw new QasmError(`unexpected character '${c}' in angle expression '${text}'`, line);
  }
  return tokens;
}

// ctx: { params: Map(name -> number|undefined), used: Set, unbound: Set, sawUnbound: bool }
function evalExpr(text, line, ctx) {
  const tokens = tokenizeExpr(text, line);
  if (!tokens.length) throw new QasmError('empty angle expression', line);
  let pos = 0;
  const peek = () => tokens[pos];
  const next = () => tokens[pos++];
  ctx.sawUnbound = false;

  function primary() {
    const tok = next();
    if (!tok) throw new QasmError(`unexpected end of angle expression '${text}'`, line);
    if (tok.t === 'num') return tok.v;
    if (tok.t === '(') {
      const v = expr();
      const close = next();
      if (!close || close.t !== ')') throw new QasmError(`missing ')' in angle expression '${text}'`, line);
      return v;
    }
    if (tok.t === 'id') {
      if (tok.v === 'pi') return Math.PI;
      if (ctx.params.has(tok.v)) {
        ctx.used.add(tok.v);
        const bound = ctx.params.get(tok.v);
        if (typeof bound === 'number') return bound;
        ctx.unbound.add(tok.v);
        ctx.sawUnbound = true;
        return NaN; // placeholder; a collective error is raised after parsing
      }
      throw new QasmError(
        `unknown identifier '${tok.v}' in angle expression (declare it with 'input float ${tok.v};')`, line);
    }
    throw new QasmError(`unexpected '${tok.t}' in angle expression '${text}'`, line);
  }
  function unary() {
    const tok = peek();
    if (tok && (tok.t === '-' || tok.t === '+')) {
      next();
      const v = unary();
      return tok.t === '-' ? -v : v;
    }
    return primary();
  }
  function term() {
    let v = unary();
    for (;;) {
      const tok = peek();
      if (tok && (tok.t === '*' || tok.t === '/')) { next(); const r = unary(); v = tok.t === '*' ? v * r : v / r; }
      else return v;
    }
  }
  function expr() {
    let v = term();
    for (;;) {
      const tok = peek();
      if (tok && (tok.t === '+' || tok.t === '-')) { next(); const r = term(); v = tok.t === '+' ? v + r : v - r; }
      else return v;
    }
  }

  const value = expr();
  if (pos !== tokens.length) throw new QasmError(`trailing input in angle expression '${text}'`, line);
  if (!ctx.sawUnbound && !Number.isFinite(value)) {
    throw new QasmError(`angle expression '${text}' does not evaluate to a finite number`, line);
  }
  return value;
}

// Split a parenthesized argument list on top-level commas.
function splitTopLevel(text, line) {
  const parts = [];
  let depth = 0;
  let buf = '';
  for (const c of text) {
    if (c === '(') depth++;
    if (c === ')') depth--;
    if (depth < 0) throw new QasmError(`unbalanced ')' in '${text}'`, line);
    if (c === ',' && depth === 0) { parts.push(buf); buf = ''; }
    else buf += c;
  }
  if (depth !== 0) throw new QasmError(`unbalanced '(' in '${text}'`, line);
  parts.push(buf);
  return parts;
}

/* ------------------------------------------------------------------ *
 * Main parser
 * ------------------------------------------------------------------ */

/**
 * Parse QASM source in the shared subset.
 *
 * @param {string} source - OpenQASM 3.0 source text.
 * @param {Object<string, number>} bindings - values for `input float` parameters.
 * @returns {{ numQubits: number, numClbits: number, qreg: string,
 *             creg: string|null, parameters: string[], ops: object[] }}
 * @throws {QasmError} with a `line` property on any grammar/semantic error.
 */
export function parseQasm(source, bindings = {}) {
  const stmts = splitStatements(stripComments(String(source ?? '')));
  if (!stmts.length) throw new QasmError("empty program — expected 'OPENQASM 3.0;'", 1);

  let qreg = null;   // { name, size }
  let creg = null;   // { name, size }
  const ctx = { params: new Map(), used: new Set(), unbound: new Set(), sawUnbound: false };
  const ops = [];
  const usedClbits = new Set();
  let measured = false;

  // header
  const head = stmts[0];
  if (!/^OPENQASM 3\.0$/.test(head.text)) {
    throw new QasmError(`expected 'OPENQASM 3.0;' as the first statement, found '${head.text.slice(0, 40)}'`, head.line);
  }

  const parseOperand = (text, line) => {
    const m = text.trim().match(/^([A-Za-z_][A-Za-z0-9_]*)(?:\[(\d+)\])?$/);
    if (!m) throw new QasmError(`bad operand '${text.trim()}'`, line);
    return { reg: m[1], index: m[2] !== undefined ? parseInt(m[2], 10) : null };
  };

  const resolveQubit = (opnd, line) => {
    if (!qreg) throw new QasmError('no qubit register declared yet', line);
    if (opnd.reg !== qreg.name) {
      throw new QasmError(`unknown register '${opnd.reg}' (the qubit register is '${qreg.name}')`, line);
    }
    if (opnd.index !== null && opnd.index >= qreg.size) {
      throw new QasmError(`qubit index ${opnd.index} out of range for '${qreg.name}[${qreg.size}]'`, line);
    }
    return opnd.index; // null => whole-register broadcast
  };

  for (let s = 1; s < stmts.length; s++) {
    const { text, line } = stmts[s];
    let m;

    if (/^OPENQASM\b/.test(text)) {
      throw new QasmError('duplicate OPENQASM header', line);
    }

    // include "stdgates.inc"
    if ((m = text.match(/^include\s+"([^"]*)"$/))) {
      if (m[1] !== 'stdgates.inc') {
        throw new QasmError(`only 'include "stdgates.inc";' is supported (got "${m[1]}")`, line);
      }
      continue;
    }

    // qubit[N] id
    if ((m = text.match(/^qubit\s*\[\s*(\d+)\s*\]\s*([A-Za-z_][A-Za-z0-9_]*)$/))) {
      if (qreg) throw new QasmError(`only one qubit register is allowed (already declared '${qreg.name}')`, line);
      const size = parseInt(m[1], 10);
      if (size < 1) throw new QasmError('qubit register size must be at least 1', line);
      qreg = { name: m[2], size };
      continue;
    }
    if (/^qubit\b/.test(text)) {
      throw new QasmError("qubit declaration must have the form 'qubit[N] name;'", line);
    }

    // bit[N] id
    if ((m = text.match(/^bit\s*\[\s*(\d+)\s*\]\s*([A-Za-z_][A-Za-z0-9_]*)$/))) {
      if (creg) throw new QasmError(`at most one classical register is allowed (already declared '${creg.name}')`, line);
      const size = parseInt(m[1], 10);
      if (size < 1) throw new QasmError('bit register size must be at least 1', line);
      creg = { name: m[2], size };
      continue;
    }
    if (/^bit\b/.test(text)) {
      throw new QasmError("bit declaration must have the form 'bit[N] name;'", line);
    }

    // input float id
    if ((m = text.match(/^input\s+float(?:\s*\[\d+\])?\s+([A-Za-z_][A-Za-z0-9_]*)$/))) {
      const name = m[1];
      if (name === 'pi') throw new QasmError("'pi' cannot be redeclared as a parameter", line);
      if (ctx.params.has(name)) throw new QasmError(`parameter '${name}' declared twice`, line);
      const bound = bindings ? bindings[name] : undefined;
      if (bound !== undefined && (typeof bound !== 'number' || !Number.isFinite(bound))) {
        throw new QasmError(`binding for parameter '${name}' must be a finite number`, line);
      }
      ctx.params.set(name, bound);
      continue;
    }
    if (/^input\b/.test(text)) {
      throw new QasmError("only 'input float name;' parameter declarations are supported", line);
    }

    // barrier reg | barrier reg[i], ...
    if ((m = text.match(/^barrier\s+(.+)$/)) || text === 'barrier') {
      const args = m ? m[1] : '';
      if (!args.trim()) throw new QasmError('barrier requires at least one operand', line);
      for (const part of args.split(',')) resolveQubit(parseOperand(part, line), line);
      continue; // barriers have no simulation semantics
    }

    // measurement: c[i] = measure q[j]  |  c = measure q
    if ((m = text.match(/^([A-Za-z_][A-Za-z0-9_]*)\s*(?:\[\s*(\d+)\s*\])?\s*=\s*measure\s+(.+)$/))) {
      const [, cname, cidxRaw, qtext] = m;
      const qop = parseOperand(qtext, line);
      if (!creg) throw new QasmError("no classical register declared (add e.g. 'bit[2] c;')", line);
      if (cname !== creg.name) throw new QasmError(`unknown classical register '${cname}' (declared: '${creg.name}')`, line);
      const cidx = cidxRaw !== undefined ? parseInt(cidxRaw, 10) : null;
      const qidx = resolveQubit(qop, line);
      if ((cidx === null) !== (qidx === null)) {
        throw new QasmError('measurement must be either fully indexed (c[i] = measure q[j];) or fully broadcast (c = measure q;)', line);
      }
      const pairs = [];
      if (cidx === null) {
        if (creg.size !== qreg.size) {
          throw new QasmError(`broadcast measure needs matching widths ('${qreg.name}[${qreg.size}]' vs '${creg.name}[${creg.size}]')`, line);
        }
        for (let i = 0; i < qreg.size; i++) pairs.push([i, i]);
      } else {
        if (cidx >= creg.size) throw new QasmError(`classical bit index ${cidx} out of range for '${creg.name}[${creg.size}]'`, line);
        pairs.push([qidx, cidx]);
      }
      for (const [, c] of pairs) {
        if (usedClbits.has(c)) throw new QasmError(`classical bit ${creg.name}[${c}] is written by more than one measurement`, line);
        usedClbits.add(c);
      }
      ops.push({ g: 'measure', q: pairs.map(p => p[0]), c: pairs.map(p => p[1]) });
      measured = true;
      continue;
    }

    // gate application: name | name(args)  operands
    m = text.match(/^([A-Za-z_][A-Za-z0-9_]*)\s*(\(.*\))?\s*([^()]*)$/);
    if (!m) throw new QasmError(`cannot parse statement '${text.slice(0, 60)}'`, line);
    const [, gname, parenRaw, operandRaw] = m;
    const spec = GATES[gname];
    if (!spec) {
      throw new QasmError(`unknown gate '${gname}' (supported: ${Object.keys(GATES).join(' ')})`, line);
    }
    if (measured) {
      throw new QasmError(`gate '${gname}' after measurement — measurements must be terminal`, line);
    }

    // parameters
    let params = [];
    if (spec.p > 0) {
      if (!parenRaw) throw new QasmError(`gate '${gname}' requires ${spec.p} angle parameter(s), e.g. ${gname}(pi/2)`, line);
      const inner = parenRaw.slice(1, -1);
      const parts = splitTopLevel(inner, line);
      if (parts.length !== spec.p || (parts.length === 1 && !parts[0].trim())) {
        throw new QasmError(`gate '${gname}' expects ${spec.p} parameter(s), got ${parts[0].trim() ? parts.length : 0}`, line);
      }
      params = parts.map(pt => evalExpr(pt, line, ctx));
    } else if (parenRaw) {
      throw new QasmError(`gate '${gname}' takes no parameters`, line);
    }

    // operands
    const opText = operandRaw.trim();
    if (!opText) throw new QasmError(`gate '${gname}' is missing qubit operands`, line);
    const operands = opText.split(',').map(t => parseOperand(t, line));
    const indices = operands.map(o => resolveQubit(o, line));

    if (indices.some(ix => ix === null)) {
      // whole-register broadcast: single-qubit gates only, single operand
      if (spec.a !== 1 || operands.length !== 1) {
        throw new QasmError('whole-register broadcast is only supported for single-qubit gates', line);
      }
      for (let qb = 0; qb < qreg.size; qb++) {
        ops.push(params.length ? { g: gname, q: [qb], p: params } : { g: gname, q: [qb] });
      }
      continue;
    }
    if (indices.length !== spec.a) {
      throw new QasmError(`gate '${gname}' expects ${spec.a} qubit operand(s), got ${indices.length}`, line);
    }
    for (let a = 0; a < indices.length; a++) {
      for (let b = a + 1; b < indices.length; b++) {
        if (indices[a] === indices[b]) {
          throw new QasmError(`gate '${gname}' uses qubit ${qreg.name}[${indices[a]}] twice`, line);
        }
      }
    }
    ops.push(params.length ? { g: gname, q: indices, p: params } : { g: gname, q: indices });
  }

  if (!qreg) throw new QasmError("no qubit register declared (add e.g. 'qubit[2] q;')", null);
  if (ctx.unbound.size) {
    const names = [...ctx.unbound].sort();
    throw new QasmError(
      `unbound parameter(s): ${names.join(', ')} — pass numeric values via the bindings argument, e.g. { ${names[0]}: 0.5 }`,
      null);
  }

  return {
    numQubits: qreg.size,
    numClbits: creg ? creg.size : 0,
    qreg: qreg.name,
    creg: creg ? creg.name : null,
    parameters: [...ctx.used].sort(),
    ops,
  };
}

/**
 * Convenience: QASM source -> complete qv-sim Program JSON.
 *
 * @param {string} source
 * @param {{bindings?: object, shots?: number|null, seed?: number|null,
 *          wantStatevector?: boolean}} opts
 */
export function compile(source, opts = {}) {
  const parsed = parseQasm(source, opts.bindings ?? {});
  return {
    num_qubits: parsed.numQubits,
    shots: opts.shots ?? null,
    seed: opts.seed ?? null,
    want_statevector: !!opts.wantStatevector,
    ops: parsed.ops,
  };
}
