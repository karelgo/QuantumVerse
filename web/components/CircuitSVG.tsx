// Server-rendered circuit diagram: the page is readable (and this SVG is
// crawlable/printable) with JavaScript disabled. Colors ride the theme tokens.

import HScroll from "./HScroll";
import { parseQasm, type QOp } from "@/lib/qasm";
import { layoutCircuit } from "@/lib/circuit";
import { formatRadians } from "@/lib/format";

const ROW_H = 44;
const COL_W = 48;
const LABEL_W = 64;
const BOX = 32;

function opLabel(op: QOp): string {
  const NAMES: Record<string, string> = {
    cx: "CNOT",
    ccx: "Toffoli",
    measure: "measure",
  };
  const name = NAMES[op.name] ?? op.name.toUpperCase();
  const params = op.params.length
    ? `(${op.params.map(formatRadians).join(", ")})`
    : "";
  const qubits = op.qubits.map((q) => `q${q}`).join(op.name === "cx" ? "→" : ",");
  return `${name}${params} on ${qubits}`;
}

function GateBox({
  x,
  y,
  name,
  param,
}: {
  x: number;
  y: number;
  name: string;
  param?: string;
}) {
  return (
    <g>
      <rect
        x={x - BOX / 2}
        y={y - BOX / 2}
        width={BOX}
        height={BOX}
        rx={7}
        fill="var(--surface)"
        stroke="var(--line)"
        strokeWidth={1.25}
      />
      <text
        x={x}
        y={param ? y - 1.5 : y + 4}
        textAnchor="middle"
        fontSize={param ? 10.5 : 12}
        fontFamily="var(--mono)"
        fill="var(--ink)"
      >
        {name}
      </text>
      {param && (
        <text
          x={x}
          y={y + 10.5}
          textAnchor="middle"
          fontSize={8}
          fontFamily="var(--mono)"
          fill="var(--muted)"
        >
          {param}
        </text>
      )}
    </g>
  );
}

function Dot({ x, y }: { x: number; y: number }) {
  return <circle cx={x} cy={y} r={3.5} fill="var(--ink)" />;
}

function Oplus({ x, y }: { x: number; y: number }) {
  return (
    <g stroke="var(--ink)" strokeWidth={1.4} fill="none">
      <circle cx={x} cy={y} r={9} />
      <line x1={x - 9} y1={y} x2={x + 9} y2={y} />
      <line x1={x} y1={y - 9} x2={x} y2={y + 9} />
    </g>
  );
}

function Cross({ x, y }: { x: number; y: number }) {
  return (
    <g stroke="var(--ink)" strokeWidth={1.5}>
      <line x1={x - 5.5} y1={y - 5.5} x2={x + 5.5} y2={y + 5.5} />
      <line x1={x - 5.5} y1={y + 5.5} x2={x + 5.5} y2={y - 5.5} />
    </g>
  );
}

function Meter({ x, y }: { x: number; y: number }) {
  return (
    <g>
      <rect
        x={x - BOX / 2}
        y={y - BOX / 2}
        width={BOX}
        height={BOX}
        rx={7}
        fill="var(--surface)"
        stroke="var(--line)"
        strokeWidth={1.25}
      />
      <path
        d={`M ${x - 8} ${y + 6} A 8 8 0 0 1 ${x + 8} ${y + 6}`}
        fill="none"
        stroke="var(--ink)"
        strokeWidth={1.4}
      />
      <line
        x1={x}
        y1={y + 6}
        x2={x + 5.5}
        y2={y - 3.5}
        stroke="var(--ink)"
        strokeWidth={1.4}
      />
    </g>
  );
}

const GATE_TEXT: Record<string, string> = {
  h: "H", x: "X", y: "Y", z: "Z", s: "S", sdg: "S†", t: "T", tdg: "T†",
  sx: "√X", rx: "Rx", ry: "Ry", rz: "Rz", p: "P", u2: "U2", u3: "U3",
  id: "I", ch: "H", cy: "Y", crz: "Rz", cp: "P",
};

export default function CircuitSVG({ qasm }: { qasm: string }) {
  let parsed;
  try {
    parsed = parseQasm(qasm);
  } catch {
    return <pre className="codeblock">{qasm}</pre>;
  }
  const layout = layoutCircuit(parsed);
  const n = parsed.numQubits;
  const width = LABEL_W + Math.max(layout.cols, 1) * COL_W + 14;
  const height = n * ROW_H + 6;
  const wireY = (q: number) => q * ROW_H + ROW_H / 2 + 3;
  const colX = (c: number) => LABEL_W + c * COL_W + COL_W / 2;

  const description = layout.ops.map(opLabel).join("; ");

  return (
    <HScroll>
      <svg
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={`Quantum circuit on ${n} qubits: ${description}`}
        xmlns="http://www.w3.org/2000/svg"
      >
        {Array.from({ length: n }, (_, q) => (
          <g key={q}>
            <text
              x={LABEL_W - 12}
              y={wireY(q) + 3.5}
              textAnchor="end"
              fontSize={11}
              fontFamily="var(--mono)"
              fill="var(--muted)"
            >
              {parsed.qubitLabels[q]}
            </text>
            <line
              x1={LABEL_W}
              y1={wireY(q)}
              x2={width - 8}
              y2={wireY(q)}
              stroke="var(--wire)"
              strokeWidth={1}
            />
          </g>
        ))}
        {layout.ops.map((op, i) => {
          const x = colX(op.col);
          const ys = op.qubits.map(wireY);
          const connector =
            op.qubits.length > 1 ? (
              <line
                x1={x}
                y1={Math.min(...ys)}
                x2={x}
                y2={Math.max(...ys)}
                stroke="var(--ink)"
                strokeWidth={1.4}
              />
            ) : null;
          const param = op.params.length
            ? op.params.map(formatRadians).join(",")
            : undefined;

          switch (op.name) {
            case "measure":
              return (
                <g key={i}>
                  {op.qubits.map((q, k) => (
                    <Meter key={k} x={x} y={wireY(q)} />
                  ))}
                </g>
              );
            case "cx":
            case "cy":
              return (
                <g key={i}>
                  {connector}
                  <Dot x={x} y={ys[0]} />
                  {op.name === "cx" ? (
                    <Oplus x={x} y={ys[1]} />
                  ) : (
                    <GateBox x={x} y={ys[1]} name="Y" />
                  )}
                </g>
              );
            case "cz":
              return (
                <g key={i}>
                  {connector}
                  <Dot x={x} y={ys[0]} />
                  <Dot x={x} y={ys[1]} />
                </g>
              );
            case "ch":
            case "cp":
            case "crz":
              return (
                <g key={i}>
                  {connector}
                  <Dot x={x} y={ys[0]} />
                  <GateBox x={x} y={ys[1]} name={GATE_TEXT[op.name]} param={param} />
                </g>
              );
            case "swap":
              return (
                <g key={i}>
                  {connector}
                  <Cross x={x} y={ys[0]} />
                  <Cross x={x} y={ys[1]} />
                </g>
              );
            case "cswap":
              return (
                <g key={i}>
                  {connector}
                  <Dot x={x} y={ys[0]} />
                  <Cross x={x} y={ys[1]} />
                  <Cross x={x} y={ys[2]} />
                </g>
              );
            case "ccx":
              return (
                <g key={i}>
                  {connector}
                  <Dot x={x} y={ys[0]} />
                  <Dot x={x} y={ys[1]} />
                  <Oplus x={x} y={ys[2]} />
                </g>
              );
            default:
              return (
                <GateBox
                  key={i}
                  x={x}
                  y={ys[0]}
                  name={GATE_TEXT[op.name] ?? op.name}
                  param={param}
                />
              );
          }
        })}
      </svg>
    </HScroll>
  );
}
