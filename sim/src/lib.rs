//! qv-sim — dense statevector simulator for the QuantumVerse shared OpenQASM 3 subset.
//!
//! Conventions (identical to the Python client):
//! - **Little-endian**: qubit 0 is the least-significant bit of the state index.
//! - Rendered bitstrings are `qubit n-1 … qubit 0` (or `clbit m-1 … clbit 0`
//!   when explicit measurements map qubits onto classical bits).
//!
//! The crate builds natively (rlib, for `cargo test`) and as a
//! `wasm32-unknown-unknown` cdylib exposing a manual C-style ABI —
//! see `qv_alloc` / `qv_free` / `qv_run` at the bottom of this file.

use serde::Deserialize;
use serde_json::{json, Map, Value};
use std::alloc::Layout;
use std::collections::BTreeMap;

/// Hard cap on register width (2^24 amplitudes ≈ 256 MB of state).
pub const MAX_QUBITS: usize = 24;
/// Classical register width cap (bounds the marginal-distribution table).
pub const MAX_CLBITS: usize = 24;
/// Probabilities below this are pruned from the output.
const PRUNE_EPS: f64 = 1e-12;
/// xorshift64* seed used when the program supplies `"seed": null`.
const DEFAULT_SEED: u64 = 0x9e37_79b9_7f4a_7c15;

// ---------------------------------------------------------------------------
// Program JSON (input)
// ---------------------------------------------------------------------------

#[derive(Deserialize)]
struct OpIn {
    g: String,
    #[serde(default)]
    q: Vec<usize>,
    #[serde(default)]
    p: Vec<f64>,
    #[serde(default)]
    c: Vec<usize>,
}

#[derive(Deserialize)]
struct ProgramIn {
    num_qubits: usize,
    #[serde(default)]
    shots: Option<u64>,
    #[serde(default)]
    seed: Option<u64>,
    #[serde(default)]
    want_statevector: bool,
    #[serde(default)]
    ops: Vec<OpIn>,
}

// ---------------------------------------------------------------------------
// Complex helpers & gate matrices
// ---------------------------------------------------------------------------

type C = (f64, f64); // (re, im)

enum Base {
    /// 2x2 matrix applied to the last operand; preceding operands are controls.
    Mat,
    /// Swap of the last two operands; preceding operands are controls.
    Swap,
}

/// name -> (number of control operands, base operation, number of parameters)
fn gate_spec(name: &str) -> Option<(usize, Base, usize)> {
    Some(match name {
        "x" | "y" | "z" | "h" | "s" | "sdg" | "t" | "tdg" | "sx" => (0, Base::Mat, 0),
        "rx" | "ry" | "rz" | "p" => (0, Base::Mat, 1),
        "u" => (0, Base::Mat, 3),
        "cx" | "cy" | "cz" | "ch" => (1, Base::Mat, 0),
        "cp" | "crx" | "cry" | "crz" => (1, Base::Mat, 1),
        "ccx" => (2, Base::Mat, 0),
        "swap" => (0, Base::Swap, 0),
        "cswap" => (1, Base::Swap, 0),
        _ => return None,
    })
}

/// The 2x2 matrix a `Base::Mat` gate applies to its target qubit.
fn base_matrix(name: &str, p: &[f64]) -> [[C; 2]; 2] {
    let fr = std::f64::consts::FRAC_1_SQRT_2;
    match name {
        "x" | "cx" | "ccx" => [[(0., 0.), (1., 0.)], [(1., 0.), (0., 0.)]],
        "y" | "cy" => [[(0., 0.), (0., -1.)], [(0., 1.), (0., 0.)]],
        "z" | "cz" => [[(1., 0.), (0., 0.)], [(0., 0.), (-1., 0.)]],
        "h" | "ch" => [[(fr, 0.), (fr, 0.)], [(fr, 0.), (-fr, 0.)]],
        "s" => [[(1., 0.), (0., 0.)], [(0., 0.), (0., 1.)]],
        "sdg" => [[(1., 0.), (0., 0.)], [(0., 0.), (0., -1.)]],
        "t" => [[(1., 0.), (0., 0.)], [(0., 0.), (fr, fr)]],
        "tdg" => [[(1., 0.), (0., 0.)], [(0., 0.), (fr, -fr)]],
        "sx" => [[(0.5, 0.5), (0.5, -0.5)], [(0.5, -0.5), (0.5, 0.5)]],
        "rx" | "crx" => {
            let (c2, s2) = ((p[0] / 2.).cos(), (p[0] / 2.).sin());
            [[(c2, 0.), (0., -s2)], [(0., -s2), (c2, 0.)]]
        }
        "ry" | "cry" => {
            let (c2, s2) = ((p[0] / 2.).cos(), (p[0] / 2.).sin());
            [[(c2, 0.), (-s2, 0.)], [(s2, 0.), (c2, 0.)]]
        }
        "rz" | "crz" => {
            let h = p[0] / 2.;
            [[(h.cos(), -h.sin()), (0., 0.)], [(0., 0.), (h.cos(), h.sin())]]
        }
        "p" | "cp" => [[(1., 0.), (0., 0.)], [(0., 0.), (p[0].cos(), p[0].sin())]],
        "u" => {
            // OpenQASM 3 u(theta, phi, lambda):
            //   [[cos(t/2),            -e^{i*lambda} sin(t/2)      ],
            //    [e^{i*phi} sin(t/2),   e^{i*(phi+lambda)} cos(t/2)]]
            let (th, ph, la) = (p[0], p[1], p[2]);
            let (c2, s2) = ((th / 2.).cos(), (th / 2.).sin());
            [
                [(c2, 0.), (-la.cos() * s2, -la.sin() * s2)],
                [
                    (ph.cos() * s2, ph.sin() * s2),
                    ((ph + la).cos() * c2, (ph + la).sin() * c2),
                ],
            ]
        }
        // unreachable by construction (gate_spec gates only); identity keeps us panic-free
        _ => [[(1., 0.), (0., 0.)], [(0., 0.), (1., 0.)]],
    }
}

// ---------------------------------------------------------------------------
// State evolution
// ---------------------------------------------------------------------------

/// Apply a 2x2 matrix to `target`, restricted to basis states where every bit
/// in `ctrl_mask` is set. `ctrl_mask == 0` means "no controls".
fn apply_mat(re: &mut [f64], im: &mut [f64], ctrl_mask: usize, target: usize, m: &[[C; 2]; 2]) {
    let dim = re.len();
    let tbit = 1usize << target;
    let (m00r, m00i) = m[0][0];
    let (m01r, m01i) = m[0][1];
    let (m10r, m10i) = m[1][0];
    let (m11r, m11i) = m[1][1];
    for i in 0..dim {
        if i & tbit == 0 && (i & ctrl_mask) == ctrl_mask {
            let j = i | tbit;
            let (ar, ai) = (re[i], im[i]);
            let (br, bi) = (re[j], im[j]);
            re[i] = m00r * ar - m00i * ai + m01r * br - m01i * bi;
            im[i] = m00r * ai + m00i * ar + m01r * bi + m01i * br;
            re[j] = m10r * ar - m10i * ai + m11r * br - m11i * bi;
            im[j] = m10r * ai + m10i * ar + m11r * bi + m11i * br;
        }
    }
}

/// Swap qubits `a` and `b`, restricted to basis states where every bit in
/// `ctrl_mask` is set.
fn apply_swap(re: &mut [f64], im: &mut [f64], ctrl_mask: usize, a: usize, b: usize) {
    let dim = re.len();
    let abit = 1usize << a;
    let bbit = 1usize << b;
    for i in 0..dim {
        if (i & abit) != 0 && (i & bbit) == 0 && (i & ctrl_mask) == ctrl_mask {
            let j = (i ^ abit) | bbit;
            re.swap(i, j);
            im.swap(i, j);
        }
    }
}

// ---------------------------------------------------------------------------
// RNG — xorshift64* (no getrandom; seeded from the program JSON)
// ---------------------------------------------------------------------------

struct XorShift64Star(u64);

impl XorShift64Star {
    fn new(seed: u64) -> Self {
        // xorshift state must be nonzero
        Self(if seed == 0 { DEFAULT_SEED } else { seed })
    }
    fn next_u64(&mut self) -> u64 {
        let mut x = self.0;
        x ^= x >> 12;
        x ^= x << 25;
        x ^= x >> 27;
        self.0 = x;
        x.wrapping_mul(0x2545_F491_4F6C_DD1D)
    }
    /// Uniform in [0, 1) with 53 bits of precision.
    fn next_f64(&mut self) -> f64 {
        (self.next_u64() >> 11) as f64 * (1.0 / (1u64 << 53) as f64)
    }
}

// ---------------------------------------------------------------------------
// Core run
// ---------------------------------------------------------------------------

fn bitstring(key: usize, width: usize) -> String {
    (0..width)
        .rev()
        .map(|b| if (key >> b) & 1 == 1 { '1' } else { '0' })
        .collect()
}

fn run_inner(input: &str) -> Result<String, String> {
    let prog: ProgramIn =
        serde_json::from_str(input).map_err(|e| format!("invalid program JSON: {e}"))?;

    let n = prog.num_qubits;
    if n < 1 || n > MAX_QUBITS {
        return Err(format!(
            "num_qubits must be between 1 and {MAX_QUBITS} (got {n})"
        ));
    }
    let dim = 1usize << n;
    let mut re = vec![0.0f64; dim];
    let mut im = vec![0.0f64; dim];
    re[0] = 1.0;

    let mut measures: Vec<(usize, usize)> = Vec::new(); // (qubit, clbit)
    let mut clbit_mask: u32 = 0;
    let mut measured = false;

    for (k, op) in prog.ops.iter().enumerate() {
        let gname = op.g.as_str();
        if gname == "barrier" {
            continue; // no semantic effect
        }
        if gname == "measure" {
            if op.q.is_empty() || op.q.len() != op.c.len() {
                return Err(format!(
                    "op {k}: measure requires equal-length non-empty 'q' and 'c' arrays"
                ));
            }
            for (&q, &c) in op.q.iter().zip(op.c.iter()) {
                if q >= n {
                    return Err(format!(
                        "op {k}: qubit index {q} out of range for {n}-qubit program"
                    ));
                }
                if c >= MAX_CLBITS {
                    return Err(format!(
                        "op {k}: classical bit index {c} out of range (max {})",
                        MAX_CLBITS - 1
                    ));
                }
                if clbit_mask & (1u32 << c) != 0 {
                    return Err(format!(
                        "op {k}: classical bit {c} is written by more than one measurement"
                    ));
                }
                clbit_mask |= 1 << c;
                measures.push((q, c));
            }
            measured = true;
            continue;
        }
        if measured {
            return Err(format!(
                "op {k} ('{gname}'): operations after measurement are not supported (measurements must be terminal)"
            ));
        }
        let (nctrl, base, nparam) =
            gate_spec(gname).ok_or_else(|| format!("op {k}: unknown gate '{gname}'"))?;
        let arity = nctrl
            + match base {
                Base::Mat => 1,
                Base::Swap => 2,
            };
        if op.q.len() != arity {
            return Err(format!(
                "op {k}: gate '{gname}' expects {arity} qubit operand(s), got {}",
                op.q.len()
            ));
        }
        if op.p.len() != nparam {
            return Err(format!(
                "op {k}: gate '{gname}' expects {nparam} parameter(s), got {}",
                op.p.len()
            ));
        }
        for &q in &op.q {
            if q >= n {
                return Err(format!(
                    "op {k}: qubit index {q} out of range for {n}-qubit program"
                ));
            }
        }
        for a in 0..op.q.len() {
            for b in (a + 1)..op.q.len() {
                if op.q[a] == op.q[b] {
                    return Err(format!(
                        "op {k}: gate '{gname}' has duplicate qubit operand {}",
                        op.q[a]
                    ));
                }
            }
        }
        for &pv in &op.p {
            if !pv.is_finite() {
                return Err(format!("op {k}: gate '{gname}' has a non-finite parameter"));
            }
        }

        let ctrl_mask: usize = op.q[..nctrl].iter().map(|&q| 1usize << q).sum();
        match base {
            Base::Mat => apply_mat(
                &mut re,
                &mut im,
                ctrl_mask,
                op.q[nctrl],
                &base_matrix(gname, &op.p),
            ),
            Base::Swap => apply_swap(&mut re, &mut im, ctrl_mask, op.q[nctrl], op.q[nctrl + 1]),
        }
    }

    // Default: no explicit measurements => measure all qubits in order.
    if measures.is_empty() {
        for q in 0..n {
            measures.push((q, q));
        }
    }
    let width = measures.iter().map(|&(_, c)| c + 1).max().unwrap_or(1);

    // Marginal distribution over the classical register.
    let mdim = 1usize << width;
    let mut marg = vec![0.0f64; mdim];
    for idx in 0..dim {
        let pr = re[idx] * re[idx] + im[idx] * im[idx];
        if pr == 0.0 {
            continue;
        }
        let mut key = 0usize;
        for &(q, c) in &measures {
            if (idx >> q) & 1 == 1 {
                key |= 1usize << c;
            }
        }
        marg[key] += pr;
    }

    let mut out = Map::new();

    let mut probs = Map::new();
    for (key, &pv) in marg.iter().enumerate() {
        if pv >= PRUNE_EPS {
            probs.insert(bitstring(key, width), json!(pv));
        }
    }
    out.insert("probabilities".into(), Value::Object(probs));

    if let Some(shots) = prog.shots {
        // Cumulative distribution over nonzero outcomes; inverse-CDF sampling.
        let mut keys: Vec<usize> = Vec::new();
        let mut cum: Vec<f64> = Vec::new();
        let mut acc = 0.0f64;
        for (key, &pv) in marg.iter().enumerate() {
            if pv > 0.0 {
                acc += pv;
                keys.push(key);
                cum.push(acc);
            }
        }
        let mut counts: BTreeMap<usize, u64> = BTreeMap::new();
        if !keys.is_empty() {
            let total = acc;
            let mut rng = XorShift64Star::new(prog.seed.unwrap_or(DEFAULT_SEED));
            for _ in 0..shots {
                let r = rng.next_f64() * total;
                // first index with cum[i] > r
                let (mut lo, mut hi) = (0usize, cum.len());
                while lo < hi {
                    let mid = (lo + hi) / 2;
                    if cum[mid] > r {
                        hi = mid;
                    } else {
                        lo = mid + 1;
                    }
                }
                let key = keys[lo.min(keys.len() - 1)];
                *counts.entry(key).or_insert(0) += 1;
            }
        }
        let mut cm = Map::new();
        for (key, cnt) in counts {
            cm.insert(bitstring(key, width), json!(cnt));
        }
        out.insert("counts".into(), Value::Object(cm));
    }

    if prog.want_statevector && n <= 8 {
        let sv: Vec<Value> = (0..dim).map(|i| json!([re[i], im[i]])).collect();
        out.insert("statevector".into(), Value::Array(sv));
    }

    out.insert("error".into(), Value::Null);
    Ok(Value::Object(out).to_string())
}

fn err_json(msg: &str) -> String {
    json!({ "error": msg }).to_string()
}

/// Run a program (JSON string in, JSON string out). Never panics: bad input
/// yields `{"error": "..."}`.
pub fn run_program_json(input: &str) -> String {
    match run_inner(input) {
        Ok(s) => s,
        Err(e) => err_json(&e),
    }
}

// ---------------------------------------------------------------------------
// C-style ABI (native + wasm32-unknown-unknown, no wasm-bindgen)
// ---------------------------------------------------------------------------

/// Allocate `len` bytes; the caller writes into the buffer and passes it to
/// `qv_run`, then releases it with `qv_free(ptr, len)`.
#[no_mangle]
pub extern "C" fn qv_alloc(len: usize) -> *mut u8 {
    if len == 0 {
        return core::ptr::NonNull::<u8>::dangling().as_ptr();
    }
    match Layout::from_size_align(len, 1) {
        Ok(layout) => unsafe { std::alloc::alloc(layout) },
        Err(_) => core::ptr::null_mut(),
    }
}

/// Free a buffer previously returned by `qv_alloc` (or by `qv_run`, in which
/// case `len` is `4 + json_len`).
#[no_mangle]
pub extern "C" fn qv_free(ptr: *mut u8, len: usize) {
    if ptr.is_null() || len == 0 {
        return;
    }
    if let Ok(layout) = Layout::from_size_align(len, 1) {
        unsafe { std::alloc::dealloc(ptr, layout) }
    }
}

/// Run a program. `ptr`/`len` describe UTF-8 program JSON. The return value
/// points at `[4-byte little-endian length][JSON bytes]`; the caller reads the
/// length `L`, decodes the JSON, and frees with `qv_free(ret, 4 + L)`.
/// Returns null only if the result buffer itself cannot be allocated.
#[no_mangle]
pub extern "C" fn qv_run(ptr: *const u8, len: usize) -> *mut u8 {
    let json_out = run_abi_bytes(ptr, len);
    let bytes = json_out.as_bytes();
    let n = bytes.len();
    let out = qv_alloc(4 + n);
    if out.is_null() {
        return out;
    }
    let len_le = (n as u32).to_le_bytes();
    unsafe {
        core::ptr::copy_nonoverlapping(len_le.as_ptr(), out, 4);
        core::ptr::copy_nonoverlapping(bytes.as_ptr(), out.add(4), n);
    }
    out
}

fn run_abi_bytes(ptr: *const u8, len: usize) -> String {
    let input: &[u8] = if len == 0 {
        &[]
    } else if ptr.is_null() {
        return err_json("null input pointer");
    } else {
        unsafe { core::slice::from_raw_parts(ptr, len) }
    };
    let text = match core::str::from_utf8(input) {
        Ok(t) => t,
        Err(_) => return err_json("input is not valid UTF-8"),
    };
    // Belt and suspenders: the simulator is written panic-free, but on native
    // targets catch any unwind rather than crossing the FFI boundary with it.
    // (On wasm32-unknown-unknown panics abort; they cannot unwind across.)
    match std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| run_program_json(text))) {
        Ok(s) => s,
        Err(_) => err_json("internal simulator panic"),
    }
}
