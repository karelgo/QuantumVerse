"use client";

// The Run button. The simulator worker is created lazily on first press so
// it never taxes the page's critical path. With `reference` counts supplied
// (capsule pages) it doubles as an L1 replay panel: run, compare, verdict —
// and the histogram overlays the recorded distribution as outline bars.

import { useEffect, useRef, useState } from "react";
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

function BlochDisc({ v }: { v: [number, number, number] }) {
  const [x, , z] = v;
  const r = 17;
  return (
    <svg width="44" height="44" viewBox="0 0 44 44" aria-hidden="true">
      <circle cx="22" cy="22" r={r + 2.5} fill="none" stroke="var(--line)" strokeWidth="1.25" />
      <line x1="4" y1="22" x2="40" y2="22" stroke="var(--line)" strokeWidth="0.75" />
      <line x1="22" y1="4" x2="22" y2="40" stroke="var(--line)" strokeWidth="0.75" />
      <circle cx={22 + x * r} cy={22 - z * r} r="3.5" fill="var(--accent-fill)" />
    </svg>
  );
}

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
  const [tab, setTab] = useState<"counts" | "amplitudes" | "bloch">("counts");
  const runRef = useRef<() => void>(() => {});

  const simulable = numQubits <= MAX_SIM_QUBITS;

  const run = () => {
    if (!simulable) return;
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
  runRef.current = run;

  // `r` runs the circuit, matching `/` for search.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "r" || e.metaKey || e.ctrlKey || e.altKey) return;
      const t = e.target as HTMLElement;
      if (
        t instanceof HTMLInputElement ||
        t instanceof HTMLTextAreaElement ||
        t instanceof HTMLSelectElement ||
        t.isContentEditable
      ) {
        return;
      }
      e.preventDefault();
      runRef.current();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  if (!simulable) {
    return (
      <p className="muted small" style={{ margin: 0 }}>
        This circuit uses {numQubits} qubits — beyond the {MAX_SIM_QUBITS}-qubit
        in-browser statevector limit. Cloud simulation is the Phase 1 fallback;
        it isn&rsquo;t wired up yet.
      </p>
    );
  }

  const verdict =
    state.phase === "done" && reference
      ? totalVariation(state.result.counts, reference.counts)
      : null;

  return (
    <div className="run-panel">
      <p className="sr-only" role="status">
        {state.phase === "done"
          ? `Run complete: ${state.result.shots} shots on ${state.result.numQubits} qubits in ${state.result.ms} milliseconds.`
          : state.phase === "error"
            ? `Run failed: ${state.message}`
            : ""}
      </p>
      <div className="run-controls">
        <button
          className="btn btn-primary"
          onClick={run}
          disabled={state.phase === "running"}
          title="Shortcut: r"
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
            {(
              [
                ["counts", "Counts"],
                ["amplitudes", "Statevector"],
                ["bloch", "Bloch"],
              ] as const
            ).map(([id, text]) => (
              <button
                key={id}
                className="tab"
                role="tab"
                aria-selected={tab === id}
                onClick={() => setTab(id)}
              >
                {text}
              </button>
            ))}
          </div>

          {tab === "counts" && (
            <Histogram
              counts={state.result.counts}
              shots={state.result.shots}
              reference={reference?.counts}
              referenceLabel={reference ? "recorded" : undefined}
              label="replay"
            />
          )}

          {tab === "amplitudes" && (
            <table className="amp-table">
              <thead>
                <tr>
                  <th>Basis state</th>
                  <th>Amplitude</th>
                  <th>Phase</th>
                  <th>Probability</th>
                </tr>
              </thead>
              <tbody>
                {state.result.amplitudes.map((a) => {
                  const phase = Math.atan2(a.im, a.re) * (180 / Math.PI);
                  return (
                    <tr key={a.basis}>
                      <td>|{a.basis}⟩</td>
                      <td>
                        {a.re.toFixed(4)}
                        {a.im >= 0 ? " + " : " − "}
                        {Math.abs(a.im).toFixed(4)}i
                      </td>
                      <td>
                        <span
                          className="phase-tick"
                          style={{ transform: `rotate(${-phase}deg)` }}
                          aria-hidden="true"
                        />
                        {phase.toFixed(1)}°
                      </td>
                      <td>
                        <span className="prob-track" aria-hidden="true">
                          <span
                            className="prob-fill"
                            style={{ width: `${a.prob * 100}%` }}
                          />
                        </span>
                        {(a.prob * 100).toFixed(2)}%
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}

          {tab === "bloch" && (
            <div>
              <div className="bloch-grid">
                {state.result.bloch.map((v, q) => {
                  const len = Math.hypot(...v);
                  return (
                    <div className="bloch-cell" key={q}>
                      <BlochDisc v={v} />
                      <div className="bloch-vals mono">
                        <b>q{q}</b>
                        <span>x {v[0].toFixed(2)}</span>
                        <span>y {v[1].toFixed(2)}</span>
                        <span>z {v[2].toFixed(2)}</span>
                        <span className="muted">|r| {len.toFixed(2)}</span>
                      </div>
                    </div>
                  );
                })}
              </div>
              <p className="small muted" style={{ marginTop: 12, marginBottom: 0 }}>
                Reduced single-qubit states before measurement, projected on the
                X–Z plane. |r| &lt; 1 means the qubit is entangled or mixed.
              </p>
            </div>
          )}
        </>
      )}
    </div>
  );
}
