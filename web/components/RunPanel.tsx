"use client";

// The Run button. The simulator worker is created lazily on first press so
// it never taxes the page's critical path. With `reference` counts supplied
// (capsule pages) it doubles as an L1 replay panel: run, compare, verdict.

import { useRef, useState } from "react";
import Histogram from "./Histogram";
import { totalVariation, MAX_SIM_QUBITS, type SimResult } from "@/lib/sim";

interface Reference {
  counts: Record<string, number>;
  label: string;
}

type State =
  | { phase: "idle" }
  | { phase: "running" }
  | { phase: "done"; result: SimResult }
  | { phase: "error"; message: string };

export default function RunPanel({
  qasm,
  numQubits,
  reference,
}: {
  qasm: string;
  numQubits: number;
  reference?: Reference;
}) {
  const workerRef = useRef<Worker | null>(null);
  const [state, setState] = useState<State>({ phase: "idle" });
  const [shots, setShots] = useState(4096);
  const [tab, setTab] = useState<"counts" | "amplitudes">("counts");

  if (numQubits > MAX_SIM_QUBITS) {
    return (
      <p className="muted small" style={{ margin: 0 }}>
        This circuit uses {numQubits} qubits — beyond the {MAX_SIM_QUBITS}-qubit
        in-browser statevector limit. Cloud simulation is the Phase 1 fallback;
        it isn&rsquo;t wired up yet.
      </p>
    );
  }

  const run = () => {
    setState({ phase: "running" });
    if (!workerRef.current) {
      workerRef.current = new Worker(
        new URL("../workers/sim.worker.ts", import.meta.url),
      );
      workerRef.current.onmessage = (
        e: MessageEvent<
          { ok: true; result: SimResult } | { ok: false; error: string }
        >,
      ) => {
        if (e.data.ok) setState({ phase: "done", result: e.data.result });
        else setState({ phase: "error", message: e.data.error });
      };
      workerRef.current.onerror = () =>
        setState({ phase: "error", message: "simulator failed to load" });
    }
    workerRef.current.postMessage({
      qasm,
      shots,
      seed: (Math.random() * 2 ** 31) | 0,
    });
  };

  const verdict =
    state.phase === "done" && reference
      ? totalVariation(state.result.counts, reference.counts)
      : null;

  return (
    <div className="run-panel">
      <div className="run-controls">
        <button
          className="btn btn-primary"
          onClick={run}
          disabled={state.phase === "running"}
        >
          {state.phase === "running"
            ? "Running…"
            : reference
              ? "▶ Replay (L1, noiseless)"
              : "▶ Run"}
        </button>
        <select
          className="select"
          value={shots}
          onChange={(e) => setShots(Number(e.target.value))}
          aria-label="shots"
        >
          {[1024, 4096, 8192, 16384].map((s) => (
            <option key={s} value={s}>
              {s.toLocaleString()} shots
            </option>
          ))}
        </select>
        {state.phase === "done" && (
          <span className="run-note">
            {state.result.shots.toLocaleString()} shots ·{" "}
            {state.result.numQubits} qubits · {state.result.ms} ms · statevector,
            in your browser
          </span>
        )}
      </div>

      {state.phase === "error" && (
        <div className="verdict not-reproduced">{state.message}</div>
      )}

      {verdict !== null && state.phase === "done" && reference && (
        <div
          className={`verdict ${
            verdict < 0.05
              ? "consistent"
              : verdict < 0.15
                ? "degraded"
                : "not-reproduced"
          }`}
        >
          <b>
            {verdict < 0.05
              ? "Consistent"
              : verdict < 0.15
                ? "Degraded"
                : "Not reproduced"}
          </b>{" "}
          — total variation distance {verdict.toFixed(4)} between this noiseless
          replay and {reference.label}.
        </div>
      )}

      {state.phase === "done" && (
        <>
          <div className="result-tabs" role="tablist">
            <button
              className="tab"
              role="tab"
              aria-selected={tab === "counts"}
              onClick={() => setTab("counts")}
            >
              Counts
            </button>
            <button
              className="tab"
              role="tab"
              aria-selected={tab === "amplitudes"}
              onClick={() => setTab("amplitudes")}
            >
              Statevector
            </button>
          </div>
          {tab === "counts" ? (
            <Histogram counts={state.result.counts} shots={state.result.shots} />
          ) : (
            <table className="amp-table">
              <thead>
                <tr>
                  <th>Basis state</th>
                  <th>Amplitude</th>
                  <th>Probability</th>
                </tr>
              </thead>
              <tbody>
                {state.result.amplitudes.map((a) => (
                  <tr key={a.basis}>
                    <td>|{a.basis}⟩</td>
                    <td>
                      {a.re.toFixed(4)}
                      {a.im >= 0 ? " + " : " − "}
                      {Math.abs(a.im).toFixed(4)}i
                    </td>
                    <td>{(a.prob * 100).toFixed(2)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </div>
  );
}
