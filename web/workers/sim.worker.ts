// Off-main-thread statevector simulation. Loaded lazily by RunPanel the
// first time Run is pressed — never in a page's critical path.

import { parseQasm } from "../lib/qasm";
import { simulate } from "../lib/sim";

export interface SimRequest {
  qasm: string;
  shots: number;
  seed?: number;
}

self.onmessage = (e: MessageEvent<SimRequest>) => {
  try {
    const circuit = parseQasm(e.data.qasm);
    const result = simulate(circuit, e.data.shots, e.data.seed);
    self.postMessage({ ok: true, result });
  } catch (err) {
    self.postMessage({
      ok: false,
      error: err instanceof Error ? err.message : String(err),
    });
  }
};
