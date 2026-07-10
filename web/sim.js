// sim.js — reference JS wrapper for the qv-sim WASM ABI (see ../sim/README.md).
//
// Usage:
//   import { loadSim } from './sim.js';
//   const sim = await loadSim('./qv_sim.wasm');
//   const result = sim.run(programJson);   // object in, object out

export async function loadSim(url = './qv_sim.wasm') {
  const resp = await fetch(url);
  if (!resp.ok) throw new Error(`failed to fetch ${url}: HTTP ${resp.status}`);
  const bytes = await resp.arrayBuffer();
  const { instance } = await WebAssembly.instantiate(bytes, {});
  const { qv_alloc, qv_free, qv_run, memory } = instance.exports;
  if (!qv_alloc || !qv_free || !qv_run || !memory) {
    throw new Error('qv_sim.wasm is missing expected exports (qv_alloc/qv_free/qv_run/memory)');
  }

  const encoder = new TextEncoder();
  const decoder = new TextDecoder();

  function run(program) {
    const inputBytes = encoder.encode(JSON.stringify(program));
    const inPtr = qv_alloc(inputBytes.length);
    if (inPtr === 0) throw new Error('qv_alloc failed (out of memory)');
    // Views must be re-created after every exported call: growth detaches them.
    new Uint8Array(memory.buffer, inPtr, inputBytes.length).set(inputBytes);

    const outPtr = qv_run(inPtr, inputBytes.length);
    qv_free(inPtr, inputBytes.length);
    if (outPtr === 0) throw new Error('qv_run failed (out of memory)');

    const lenView = new DataView(memory.buffer, outPtr, 4);
    const outLen = lenView.getUint32(0, true /* little-endian */);
    const outBytes = new Uint8Array(memory.buffer, outPtr + 4, outLen).slice();
    qv_free(outPtr, 4 + outLen);

    const result = JSON.parse(decoder.decode(outBytes));
    if (result.error) throw new Error(result.error);
    return result;
  }

  return { run };
}
