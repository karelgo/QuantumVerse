# qv-sim — QuantumVerse statevector simulator

A dense statevector simulator for the QuantumVerse **shared OpenQASM 3 subset**,
written in Rust. It builds natively (for tests and embedding) and to
`wasm32-unknown-unknown` **without wasm-bindgen** — the playground in
[`web/`](../web/) talks to it over a small manual C-style ABI.

- **Convention** (identical to the Python client): little-endian — qubit 0 is
  the least-significant bit of the state index; rendered bitstrings are
  `qubit n-1 … qubit 0`.
- **Gates**: `x y z h s sdg t tdg sx rx ry rz p u cx cy cz ch swap ccx cswap
  cp crx cry crz`, plus terminal `measure` and (ignored) `barrier`.
- **Cap**: 24 qubits (2^24 amplitudes ≈ 256 MB of state).
- **RNG**: xorshift64\* seeded from the program JSON (`"seed"`); a `null` seed
  falls back to a fixed default, so results are always reproducible. No
  `getrandom`, no OS entropy — the module has **zero wasm imports**.

## Build & test

```sh
cd sim
cargo test                                          # native test suite
cargo build --release --target wasm32-unknown-unknown
cp target/wasm32-unknown-unknown/release/qv_sim.wasm ../web/qv_sim.wasm
```

The built `web/qv_sim.wasm` is committed on purpose: it is the engine of the
GitHub-Pages playground, which has no build step. **Re-run the two commands
above and re-copy whenever `src/lib.rs` changes.**

## Program JSON (input)

```json
{
  "num_qubits": 2,
  "shots": 1024,
  "seed": 42,
  "want_statevector": true,
  "ops": [
    { "g": "h",  "q": [0] },
    { "g": "rz", "q": [1], "p": [0.7853981633974483] },
    { "g": "cx", "q": [0, 1] },
    { "g": "measure", "q": [0], "c": [0] },
    { "g": "measure", "q": [1], "c": [1] }
  ]
}
```

- `shots` and `seed` may be `null`/omitted. `want_statevector` defaults to `false`.
- Angles (`p`) are already-evaluated `f64` radians — expression evaluation
  (`pi/2`, bound parameters, …) happens in the caller (`web/qasm.js` or the
  Python client).
- Operand order for controlled gates: **controls first, target last**
  (`cx` = `[control, target]`, `ccx` = `[c0, c1, target]`,
  `cswap` = `[control, a, b]`).
- Only **terminal** measurements are supported; a gate after a `measure` op is
  an error. If there are no `measure` ops, all qubits are measured in order
  (qubit *i* → classical bit *i*).
- Explicit measurements map qubits onto classical bits; unmeasured qubits are
  marginalized out. Classical bit indices are capped at 23.

## Result JSON (output)

```json
{
  "probabilities": { "00": 0.5, "11": 0.5 },
  "counts": { "00": 520, "11": 504 },
  "statevector": [[0.7071067811865476, 0.0], [0.0, 0.0], [0.0, 0.0], [0.7071067811865476, 0.0]],
  "error": null
}
```

- `probabilities` — outcome distribution over the classical register, entries
  `< 1e-12` pruned.
- `counts` — present iff `shots` was set; sampled with the seeded xorshift64\*.
- `statevector` — present iff `want_statevector` **and** `num_qubits <= 8`;
  `[re, im]` pairs in state-index order (pre-measurement state).
- On any invalid input the result is `{"error": "message"}` — the simulator
  never panics across the ABI.

## C-style ABI (wasm exports)

| Export | Signature | Meaning |
|---|---|---|
| `qv_alloc` | `(len: usize) -> *mut u8` | Allocate `len` bytes (returns null on failure). |
| `qv_free` | `(ptr: *mut u8, len: usize)` | Free a buffer from `qv_alloc`/`qv_run`. `len` must be the allocation size. |
| `qv_run` | `(ptr: *const u8, len: usize) -> *mut u8` | Run program JSON at `ptr..ptr+len`. |
| `memory` | `WebAssembly.Memory` | The linear memory all pointers index into. |

Call sequence (see `web/sim.js` for the reference wrapper):

1. UTF-8-encode the program JSON → `bytes`.
2. `in = qv_alloc(bytes.length)`; copy `bytes` into `memory` at `in`.
3. `out = qv_run(in, bytes.length)`; then `qv_free(in, bytes.length)`.
4. At `out`: 4-byte **little-endian** length `L`, followed by `L` bytes of
   UTF-8 result JSON.
5. `qv_free(out, 4 + L)`.

Re-read `memory.buffer` after every exported call — memory growth detaches
previously created views.
