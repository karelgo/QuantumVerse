"""Parser for the shared OpenQASM 3 subset used across QuantumVerse.

The subset (see RFC-0002 conformance notes and the platform grammar):

- Header ``OPENQASM 3.0;`` then optional ``include "stdgates.inc";``
- Exactly one ``qubit[N] <id>;`` and at most one ``bit[N] <id>;``
- Optional symbolic parameters: ``input float <id>;``
- Gates: x y z h s sdg t tdg sx rx ry rz p u cx cy cz ch swap ccx cswap
  cp crx cry crz (with angle expressions where applicable)
- Angle expressions: literals, ``pi``, declared parameters, unary minus,
  ``+ - * /``, parentheses
- Whole-register broadcast for single-qubit gates (``h q;``)
- Measurement: ``c[i] = measure q[j];`` and ``c = measure q;``
- ``barrier`` statements; ``//`` and ``/* */`` comments

Anything outside the subset raises :class:`QasmError` with a line number.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Optional, Union

__all__ = ["QasmError", "Expr", "Op", "Circuit", "parse_qasm", "GATE_SPECS"]


class QasmError(ValueError):
    """A parse error in the OpenQASM 3 subset, carrying a 1-based line number."""

    def __init__(self, message: str, line: Optional[int] = None):
        self.line = line
        if line is not None:
            message = f"line {line}: {message}"
        super().__init__(message)


# gate name -> (number of qubit operands, number of angle parameters)
GATE_SPECS: dict[str, tuple[int, int]] = {
    "x": (1, 0), "y": (1, 0), "z": (1, 0), "h": (1, 0),
    "s": (1, 0), "sdg": (1, 0), "t": (1, 0), "tdg": (1, 0), "sx": (1, 0),
    "rx": (1, 1), "ry": (1, 1), "rz": (1, 1), "p": (1, 1),
    "u": (1, 3),
    "cx": (2, 0), "cy": (2, 0), "cz": (2, 0), "ch": (2, 0), "swap": (2, 0),
    "ccx": (3, 0), "cswap": (3, 0),
    "cp": (2, 1), "crx": (2, 1), "cry": (2, 1), "crz": (2, 1),
}

TWO_QUBIT_GATES = frozenset({"cx", "cy", "cz", "ch", "swap", "cp", "crx", "cry", "crz"})


class Expr:
    """An angle expression that references symbolic ``input float`` parameters.

    ``source`` is the expression text as written; ``params`` the set of
    parameter names it uses. Calling the object (or :meth:`evaluate`) with a
    ``{name: value}`` binding dict resolves it to a float.
    """

    __slots__ = ("source", "params", "_ast")

    def __init__(self, source: str, ast, params: frozenset[str]):
        self.source = source
        self.params = params
        self._ast = ast

    def evaluate(self, bindings: dict[str, float]) -> float:
        missing = sorted(self.params - set(bindings))
        if missing:
            raise KeyError(f"missing parameter binding(s) for: {', '.join(missing)}")
        return _eval_ast(self._ast, bindings)

    __call__ = evaluate

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Expr({self.source!r})"

    def __eq__(self, other) -> bool:
        return isinstance(other, Expr) and other.source == self.source

    def __hash__(self) -> int:
        return hash(("Expr", self.source))


ParamValue = Union[float, Expr]


@dataclass
class Op:
    """One operation: a gate, a measurement, or a barrier."""

    name: str
    qubits: list[int]
    clbits: list[int] = field(default_factory=list)
    params: list[ParamValue] = field(default_factory=list)

    @property
    def param_names(self) -> frozenset[str]:
        names: set[str] = set()
        for p in self.params:
            if isinstance(p, Expr):
                names |= p.params
        return frozenset(names)


@dataclass
class Circuit:
    """A parsed circuit over the shared subset."""

    num_qubits: int
    num_clbits: int
    qreg: str
    creg: Optional[str]
    ops: list[Op]
    declared_params: list[str]

    @property
    def used_params(self) -> frozenset[str]:
        """Declared ``input float`` parameters actually referenced by an op."""
        names: set[str] = set()
        for op in self.ops:
            names |= op.param_names
        return frozenset(names)


# --------------------------------------------------------------------------
# Tokenizer
# --------------------------------------------------------------------------

_TOKEN_RE = re.compile(
    r"""(?P<ws>\s+)
      | (?P<number>(?:\d+\.\d*|\.\d+|\d+)(?:[eE][+-]?\d+)?)
      | (?P<name>[A-Za-z_][A-Za-z0-9_]*)
      | (?P<string>"[^"\n]*")
      | (?P<sym>\[|\]|\(|\)|,|=|\+|-|\*|/|;)
    """,
    re.VERBOSE,
)


@dataclass
class _Token:
    kind: str  # "number" | "name" | "string" | "sym"
    value: str
    line: int


def _strip_comments(text: str) -> str:
    """Replace comments with spaces, preserving newlines (and thus line numbers)."""
    out: list[str] = []
    i, n = 0, len(text)
    line = 1
    while i < n:
        c = text[i]
        if c == "\n":
            line += 1
            out.append(c)
            i += 1
        elif c == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                i += 1
        elif c == "/" and i + 1 < n and text[i + 1] == "*":
            start_line = line
            i += 2
            while i < n and not (text[i] == "*" and i + 1 < n and text[i + 1] == "/"):
                if text[i] == "\n":
                    line += 1
                    out.append("\n")
                i += 1
            if i >= n:
                raise QasmError("unterminated block comment", start_line)
            i += 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


def _tokenize(text: str) -> list[_Token]:
    tokens: list[_Token] = []
    line = 1
    pos = 0
    n = len(text)
    while pos < n:
        m = _TOKEN_RE.match(text, pos)
        if m is None:
            raise QasmError(f"unexpected character {text[pos]!r}", line)
        kind = m.lastgroup
        value = m.group()
        if kind == "ws":
            line += value.count("\n")
        else:
            tokens.append(_Token(kind, value, line))
        pos = m.end()
    # statement separator handling is done by the caller on ';'
    return tokens


# --------------------------------------------------------------------------
# Expression AST
# --------------------------------------------------------------------------


def _eval_ast(node, bindings) -> float:
    tag = node[0]
    if tag == "num":
        return node[1]
    if tag == "pi":
        return math.pi
    if tag == "param":
        return float(bindings[node[1]])
    if tag == "neg":
        return -_eval_ast(node[1], bindings)
    a = _eval_ast(node[1], bindings)
    b = _eval_ast(node[2], bindings)
    if tag == "+":
        return a + b
    if tag == "-":
        return a - b
    if tag == "*":
        return a * b
    if tag == "/":
        if b == 0:
            raise ZeroDivisionError("division by zero in angle expression")
        return a / b
    raise AssertionError(f"unknown AST node {tag!r}")  # pragma: no cover


# --------------------------------------------------------------------------
# Parser
# --------------------------------------------------------------------------


class _Parser:
    def __init__(self, text: str):
        self.tokens = _tokenize(_strip_comments(text))
        self.pos = 0
        self.qreg: Optional[str] = None
        self.num_qubits = 0
        self.creg: Optional[str] = None
        self.num_clbits = 0
        self.declared_params: list[str] = []
        self.ops: list[Op] = []
        self._saw_include = False
        self._saw_body = False  # any declaration or op

    # --- token helpers -----------------------------------------------------

    def _peek(self) -> Optional[_Token]:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def _next(self, context: str) -> _Token:
        tok = self._peek()
        if tok is None:
            last_line = self.tokens[-1].line if self.tokens else 1
            raise QasmError(f"unexpected end of input while parsing {context}", last_line)
        self.pos += 1
        return tok

    def _expect_sym(self, sym: str, context: str) -> _Token:
        tok = self._next(context)
        if tok.kind != "sym" or tok.value != sym:
            raise QasmError(f"expected {sym!r} {context}, got {tok.value!r}", tok.line)
        return tok

    def _expect_name(self, context: str) -> _Token:
        tok = self._next(context)
        if tok.kind != "name":
            raise QasmError(f"expected identifier {context}, got {tok.value!r}", tok.line)
        return tok

    def _expect_semicolon(self, context: str) -> None:
        tok = self._next(context)
        if tok.kind != "sym" or tok.value != ";":
            raise QasmError(f"expected ';' after {context}, got {tok.value!r}", tok.line)

    # --- top level ----------------------------------------------------------

    def parse(self) -> Circuit:
        # split on ';' lazily: the tokenizer does not treat ';' specially, so
        # re-tokenize including ';' as a symbol.
        self._parse_header()
        while self._peek() is not None:
            self._parse_statement()
        if self.qreg is None:
            last_line = self.tokens[-1].line if self.tokens else 1
            raise QasmError("no qubit register declared (expected 'qubit[N] <id>;')", last_line)
        return Circuit(
            num_qubits=self.num_qubits,
            num_clbits=self.num_clbits,
            qreg=self.qreg,
            creg=self.creg,
            ops=self.ops,
            declared_params=self.declared_params,
        )

    def _parse_header(self) -> None:
        tok = self._peek()
        if tok is None:
            raise QasmError("empty program: expected 'OPENQASM 3.0;'", 1)
        if tok.kind != "name" or tok.value != "OPENQASM":
            raise QasmError(f"expected 'OPENQASM 3.0;' header, got {tok.value!r}", tok.line)
        self.pos += 1
        ver = self._next("OPENQASM version")
        if ver.kind != "number" or ver.value not in ("3.0", "3"):
            raise QasmError(f"unsupported OpenQASM version {ver.value!r} (only 3.0)", ver.line)
        self._expect_semicolon("'OPENQASM 3.0'")

    def _parse_statement(self) -> None:
        tok = self._next("statement")
        if tok.kind == "sym" and tok.value == ";":
            return  # empty statement
        if tok.kind != "name":
            raise QasmError(f"unexpected token {tok.value!r} at start of statement", tok.line)

        keyword = tok.value
        if keyword == "include":
            self._parse_include(tok)
        elif keyword == "qubit":
            self._parse_qubit_decl(tok)
        elif keyword == "bit":
            self._parse_bit_decl(tok)
        elif keyword == "input":
            self._parse_input_decl(tok)
        elif keyword == "barrier":
            self._parse_barrier(tok)
        elif keyword in GATE_SPECS:
            self._parse_gate(tok)
        elif keyword in ("measure",):
            raise QasmError(
                "measurement must assign into a classical bit: "
                "'<bit>[i] = measure <reg>[j];' or '<bit> = measure <reg>;'",
                tok.line,
            )
        elif keyword == self.creg or (self.creg is None and self._looks_like_measure()):
            self._parse_measure(tok)
        elif keyword == "OPENQASM":
            raise QasmError("duplicate OPENQASM header", tok.line)
        else:
            # could still be a measure into an undeclared register
            nxt = self._peek()
            if nxt is not None and nxt.kind == "sym" and nxt.value in ("=", "["):
                self._parse_measure(tok)
            else:
                raise QasmError(f"unknown gate or statement {keyword!r}", tok.line)

    def _looks_like_measure(self) -> bool:
        nxt = self._peek()
        return nxt is not None and nxt.kind == "sym" and nxt.value in ("=", "[")

    # --- statements -----------------------------------------------------------

    def _parse_include(self, kw: _Token) -> None:
        if self._saw_body:
            raise QasmError("'include' must appear before declarations and gates", kw.line)
        if self._saw_include:
            raise QasmError("duplicate include", kw.line)
        tok = self._next("include path")
        if tok.kind != "string":
            raise QasmError(f"expected a quoted include path, got {tok.value!r}", tok.line)
        if tok.value != '"stdgates.inc"':
            raise QasmError(f'only include "stdgates.inc" is supported, got {tok.value}', tok.line)
        self._expect_semicolon("include")
        self._saw_include = True

    def _parse_sized_decl(self, kw: _Token, what: str) -> tuple[str, int]:
        self._expect_sym("[", f"after '{kw.value}'")
        size_tok = self._next(f"{what} size")
        if size_tok.kind != "number" or not size_tok.value.isdigit():
            raise QasmError(f"expected integer {what} size, got {size_tok.value!r}", size_tok.line)
        size = int(size_tok.value)
        if size < 1:
            raise QasmError(f"{what} size must be >= 1, got {size}", size_tok.line)
        self._expect_sym("]", f"after {what} size")
        name_tok = self._expect_name(f"for {what} name")
        if name_tok.value in GATE_SPECS or name_tok.value in ("pi", "measure", "barrier"):
            raise QasmError(f"register name {name_tok.value!r} shadows a reserved word", name_tok.line)
        self._expect_semicolon(f"{what} declaration")
        return name_tok.value, size

    def _parse_qubit_decl(self, kw: _Token) -> None:
        if self.qreg is not None:
            raise QasmError("only one qubit register is allowed in the subset", kw.line)
        if self.ops:
            raise QasmError("qubit register must be declared before any operations", kw.line)
        name, size = self._parse_sized_decl(kw, "qubit register")
        if name == self.creg:
            raise QasmError(f"register name {name!r} already used", kw.line)
        self.qreg, self.num_qubits = name, size
        self._saw_body = True

    def _parse_bit_decl(self, kw: _Token) -> None:
        if self.creg is not None:
            raise QasmError("at most one classical bit register is allowed in the subset", kw.line)
        name, size = self._parse_sized_decl(kw, "bit register")
        if name == self.qreg:
            raise QasmError(f"register name {name!r} already used", kw.line)
        self.creg, self.num_clbits = name, size
        self._saw_body = True

    def _parse_input_decl(self, kw: _Token) -> None:
        type_tok = self._expect_name("after 'input'")
        if type_tok.value != "float":
            raise QasmError(
                f"only 'input float' parameters are supported, got 'input {type_tok.value}'",
                type_tok.line,
            )
        name_tok = self._expect_name("for parameter name")
        name = name_tok.value
        if name == "pi" or name in GATE_SPECS or name in (self.qreg, self.creg):
            raise QasmError(f"parameter name {name!r} shadows a reserved name", name_tok.line)
        if name in self.declared_params:
            raise QasmError(f"duplicate parameter declaration {name!r}", name_tok.line)
        self._expect_semicolon("input declaration")
        self.declared_params.append(name)
        self._saw_body = True

    def _parse_barrier(self, kw: _Token) -> None:
        qubits: list[int] = []
        first = self._next("barrier operand")
        if first.kind != "name":
            raise QasmError(f"expected register operand after 'barrier', got {first.value!r}", first.line)
        self.pos -= 1
        while True:
            operand = self._parse_operand("barrier")
            if operand is None:  # whole register
                qubits.extend(range(self.num_qubits))
            else:
                qubits.append(operand)
            tok = self._next("barrier")
            if tok.kind == "sym" and tok.value == ";":
                break
            if tok.kind == "sym" and tok.value == ",":
                continue
            raise QasmError(f"expected ',' or ';' in barrier, got {tok.value!r}", tok.line)
        # de-duplicate while preserving order
        seen: set[int] = set()
        uniq = [q for q in qubits if not (q in seen or seen.add(q))]
        self.ops.append(Op(name="barrier", qubits=uniq))
        self._saw_body = True

    def _parse_operand(self, context: str) -> Optional[int]:
        """Parse ``reg`` (returns None for whole-register) or ``reg[i]`` (returns index)."""
        name_tok = self._expect_name(f"for {context} operand")
        if self.qreg is None or name_tok.value != self.qreg:
            raise QasmError(
                f"unknown qubit register {name_tok.value!r}"
                + (f" (declared register is {self.qreg!r})" if self.qreg else " (none declared yet)"),
                name_tok.line,
            )
        nxt = self._peek()
        if nxt is not None and nxt.kind == "sym" and nxt.value == "[":
            self.pos += 1
            idx_tok = self._next("qubit index")
            if idx_tok.kind != "number" or not idx_tok.value.isdigit():
                raise QasmError(f"expected integer qubit index, got {idx_tok.value!r}", idx_tok.line)
            idx = int(idx_tok.value)
            if idx >= self.num_qubits:
                raise QasmError(
                    f"qubit index {idx} out of range for '{self.qreg}[{self.num_qubits}]'",
                    idx_tok.line,
                )
            self._expect_sym("]", "after qubit index")
            return idx
        return None

    def _parse_gate(self, kw: _Token) -> None:
        name = kw.value
        arity, n_params = GATE_SPECS[name]
        params: list[ParamValue] = []
        nxt = self._peek()
        if nxt is not None and nxt.kind == "sym" and nxt.value == "(":
            if n_params == 0:
                raise QasmError(f"gate '{name}' takes no parameters", nxt.line)
            self.pos += 1
            for i in range(n_params):
                params.append(self._parse_expression(f"parameter {i + 1} of '{name}'"))
                if i < n_params - 1:
                    self._expect_sym(",", f"between parameters of '{name}'")
            self._expect_sym(")", f"after parameters of '{name}'")
        elif n_params > 0:
            raise QasmError(f"gate '{name}' requires {n_params} parameter(s)", kw.line)

        operands: list[Optional[int]] = []
        while True:
            operands.append(self._parse_operand(f"'{name}'"))
            tok = self._next(f"'{name}' statement")
            if tok.kind == "sym" and tok.value == ";":
                break
            if tok.kind == "sym" and tok.value == ",":
                continue
            raise QasmError(f"expected ',' or ';' after '{name}' operand, got {tok.value!r}", tok.line)

        if any(o is None for o in operands):
            if arity != 1 or len(operands) != 1:
                raise QasmError(
                    f"whole-register broadcast is only allowed for single-qubit gates ('{name}')",
                    kw.line,
                )
            for q in range(self.num_qubits):
                self.ops.append(Op(name=name, qubits=[q], params=list(params)))
        else:
            if len(operands) != arity:
                raise QasmError(
                    f"gate '{name}' expects {arity} qubit operand(s), got {len(operands)}", kw.line
                )
            qubits = [o for o in operands if o is not None]
            if len(set(qubits)) != len(qubits):
                raise QasmError(f"duplicate qubit operand in '{name}'", kw.line)
            self.ops.append(Op(name=name, qubits=qubits, params=params))
        self._saw_body = True

    def _parse_measure(self, first: _Token) -> None:
        if self.creg is None or first.value != self.creg:
            raise QasmError(
                f"unknown classical register {first.value!r} in measurement"
                + (f" (declared register is {self.creg!r})" if self.creg else " (none declared)"),
                first.line,
            )
        clbit: Optional[int] = None
        tok = self._next("measurement")
        if tok.kind == "sym" and tok.value == "[":
            idx_tok = self._next("classical bit index")
            if idx_tok.kind != "number" or not idx_tok.value.isdigit():
                raise QasmError(f"expected integer bit index, got {idx_tok.value!r}", idx_tok.line)
            clbit = int(idx_tok.value)
            if clbit >= self.num_clbits:
                raise QasmError(
                    f"bit index {clbit} out of range for '{self.creg}[{self.num_clbits}]'",
                    idx_tok.line,
                )
            self._expect_sym("]", "after bit index")
            tok = self._next("measurement")
        if tok.kind != "sym" or tok.value != "=":
            raise QasmError(f"expected '=' in measurement, got {tok.value!r}", tok.line)
        kw = self._expect_name("after '='")
        if kw.value != "measure":
            raise QasmError(f"expected 'measure' after '=', got {kw.value!r}", kw.line)
        qubit = self._parse_operand("measure")
        self._expect_semicolon("measurement")

        if clbit is None and qubit is None:
            # whole-register measure: c = measure q;
            if self.num_clbits != self.num_qubits:
                raise QasmError(
                    f"whole-register measurement requires bit[{self.num_qubits}] to match "
                    f"qubit[{self.num_qubits}], but '{self.creg}' has {self.num_clbits} bits",
                    first.line,
                )
            for i in range(self.num_qubits):
                self.ops.append(Op(name="measure", qubits=[i], clbits=[i]))
        elif clbit is not None and qubit is not None:
            self.ops.append(Op(name="measure", qubits=[qubit], clbits=[clbit]))
        else:
            raise QasmError(
                "measurement must be '<bit>[i] = measure <reg>[j];' or '<bit> = measure <reg>;' "
                "(mixing indexed and whole-register operands is not in the subset)",
                first.line,
            )
        self._saw_body = True

    # --- expressions -----------------------------------------------------------

    def _parse_expression(self, context: str) -> ParamValue:
        start = self.pos
        ast, names = self._parse_sum(context)
        source = _render_tokens(self.tokens[start:self.pos])
        if names:
            return Expr(source, ast, frozenset(names))
        try:
            return float(_eval_ast(ast, {}))
        except ZeroDivisionError:
            raise QasmError(f"division by zero in {context}", self.tokens[start].line) from None

    def _parse_sum(self, context: str):
        ast, names = self._parse_term(context)
        while True:
            tok = self._peek()
            if tok is not None and tok.kind == "sym" and tok.value in ("+", "-"):
                self.pos += 1
                rhs, rnames = self._parse_term(context)
                ast = (tok.value, ast, rhs)
                names |= rnames
            else:
                return ast, names

    def _parse_term(self, context: str):
        ast, names = self._parse_factor(context)
        while True:
            tok = self._peek()
            if tok is not None and tok.kind == "sym" and tok.value in ("*", "/"):
                self.pos += 1
                rhs, rnames = self._parse_factor(context)
                ast = (tok.value, ast, rhs)
                names |= rnames
            else:
                return ast, names

    def _parse_factor(self, context: str):
        tok = self._next(context)
        if tok.kind == "sym" and tok.value == "-":
            inner, names = self._parse_factor(context)
            return ("neg", inner), names
        if tok.kind == "sym" and tok.value == "+":
            return self._parse_factor(context)
        if tok.kind == "sym" and tok.value == "(":
            ast, names = self._parse_sum(context)
            self._expect_sym(")", f"in {context}")
            return ast, names
        if tok.kind == "number":
            return ("num", float(tok.value)), set()
        if tok.kind == "name":
            if tok.value == "pi":
                return ("pi",), set()
            if tok.value in self.declared_params:
                return ("param", tok.value), {tok.value}
            raise QasmError(
                f"undeclared identifier {tok.value!r} in {context} "
                f"(declare it with 'input float {tok.value};')",
                tok.line,
            )
        raise QasmError(f"unexpected token {tok.value!r} in {context}", tok.line)


def _render_tokens(tokens: list[_Token]) -> str:
    return "".join(t.value for t in tokens)


def parse_qasm(text: str) -> Circuit:
    """Parse OpenQASM 3 subset source into a :class:`Circuit`.

    Raises :class:`QasmError` (with a line number) on anything outside the
    shared subset.
    """
    if not isinstance(text, str):
        raise QasmError(f"expected QASM source as str, got {type(text).__name__}")
    return _Parser(text).parse()
