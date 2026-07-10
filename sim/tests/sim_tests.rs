//! Native tests for qv-sim: exact amplitudes, gate identities, truth tables,
//! seeded sampling determinism, and error paths.

use serde_json::{json, Value};

const TOL: f64 = 1e-12;
const FR: f64 = std::f64::consts::FRAC_1_SQRT_2;

fn run(program: Value) -> Value {
    serde_json::from_str(&qv_sim::run_program_json(&program.to_string())).unwrap()
}

fn statevector(num_qubits: u64, ops: Value) -> Vec<(f64, f64)> {
    let out = run(json!({
        "num_qubits": num_qubits,
        "shots": null,
        "seed": null,
        "want_statevector": true,
        "ops": ops
    }));
    assert!(out["error"].is_null(), "unexpected error: {}", out["error"]);
    out["statevector"]
        .as_array()
        .expect("statevector missing")
        .iter()
        .map(|a| (a[0].as_f64().unwrap(), a[1].as_f64().unwrap()))
        .collect()
}

fn assert_sv_eq(a: &[(f64, f64)], b: &[(f64, f64)], tol: f64) {
    assert_eq!(a.len(), b.len());
    for (i, (x, y)) in a.iter().zip(b.iter()).enumerate() {
        assert!(
            (x.0 - y.0).abs() < tol && (x.1 - y.1).abs() < tol,
            "amplitude {i} differs: {x:?} vs {y:?}"
        );
    }
}

/// Compare statevectors up to a global phase.
fn assert_sv_eq_global_phase(a: &[(f64, f64)], b: &[(f64, f64)], tol: f64) {
    assert_eq!(a.len(), b.len());
    let k = a
        .iter()
        .position(|&(re, im)| re * re + im * im > 1e-9)
        .expect("zero vector");
    let (ar, ai) = a[k];
    let (br, bi) = b[k];
    let norm = ar * ar + ai * ai;
    // phase = b[k] / a[k]
    let (pr, pi) = ((br * ar + bi * ai) / norm, (bi * ar - br * ai) / norm);
    let rotated: Vec<(f64, f64)> = a
        .iter()
        .map(|&(re, im)| (re * pr - im * pi, re * pi + im * pr))
        .collect();
    assert_sv_eq(&rotated, b, tol);
}

// ---------------------------------------------------------------------------
// Bell / GHZ
// ---------------------------------------------------------------------------

#[test]
fn bell_exact_amplitudes() {
    let sv = statevector(2, json!([{"g":"h","q":[0]}, {"g":"cx","q":[0,1]}]));
    let expected = vec![(FR, 0.0), (0.0, 0.0), (0.0, 0.0), (FR, 0.0)];
    assert_sv_eq(&sv, &expected, TOL);
}

#[test]
fn bell_probabilities_and_counts_50_50() {
    let out = run(json!({
        "num_qubits": 2,
        "shots": 10000,
        "seed": 12345,
        "want_statevector": false,
        "ops": [
            {"g":"h","q":[0]}, {"g":"cx","q":[0,1]},
            {"g":"measure","q":[0],"c":[0]}, {"g":"measure","q":[1],"c":[1]}
        ]
    }));
    assert!(out["error"].is_null());
    let probs = out["probabilities"].as_object().unwrap();
    assert_eq!(probs.len(), 2);
    assert!((probs["00"].as_f64().unwrap() - 0.5).abs() < TOL);
    assert!((probs["11"].as_f64().unwrap() - 0.5).abs() < TOL);

    let counts = out["counts"].as_object().unwrap();
    assert_eq!(counts.len(), 2, "only 00 and 11 may appear: {counts:?}");
    let c00 = counts["00"].as_u64().unwrap();
    let c11 = counts["11"].as_u64().unwrap();
    assert_eq!(c00 + c11, 10000);
    // ~6 sigma tolerance around 5000 (sigma = 50)
    assert!((4700..=5300).contains(&c00), "c00 = {c00}");
}

#[test]
fn ghz3_probabilities() {
    let out = run(json!({
        "num_qubits": 3,
        "shots": null,
        "want_statevector": false,
        "ops": [{"g":"h","q":[0]}, {"g":"cx","q":[0,1]}, {"g":"cx","q":[1,2]}]
    }));
    assert!(out["error"].is_null());
    let probs = out["probabilities"].as_object().unwrap();
    assert_eq!(probs.len(), 2);
    assert!((probs["000"].as_f64().unwrap() - 0.5).abs() < TOL);
    assert!((probs["111"].as_f64().unwrap() - 0.5).abs() < TOL);
}

// ---------------------------------------------------------------------------
// Gate identities (statevector compare after a generic prep)
// ---------------------------------------------------------------------------

/// Generic single-qubit prep so identities aren't trivially satisfied on |0>.
fn prep() -> Vec<Value> {
    vec![
        json!({"g":"ry","q":[0],"p":[0.777]}),
        json!({"g":"p","q":[0],"p":[0.3]}),
    ]
}

fn with_prep(extra: &[Value]) -> Value {
    let mut ops = prep();
    ops.extend_from_slice(extra);
    Value::Array(ops)
}

#[test]
fn identity_hzh_equals_x() {
    let a = statevector(
        1,
        with_prep(&[
            json!({"g":"h","q":[0]}),
            json!({"g":"z","q":[0]}),
            json!({"g":"h","q":[0]}),
        ]),
    );
    let b = statevector(1, with_prep(&[json!({"g":"x","q":[0]})]));
    assert_sv_eq(&a, &b, 1e-10);
}

#[test]
fn identity_ss_equals_z_and_tt_equals_s() {
    let ss = statevector(
        1,
        with_prep(&[json!({"g":"s","q":[0]}), json!({"g":"s","q":[0]})]),
    );
    let z = statevector(1, with_prep(&[json!({"g":"z","q":[0]})]));
    assert_sv_eq(&ss, &z, TOL);

    let tt = statevector(
        1,
        with_prep(&[json!({"g":"t","q":[0]}), json!({"g":"t","q":[0]})]),
    );
    let s = statevector(1, with_prep(&[json!({"g":"s","q":[0]})]));
    assert_sv_eq(&tt, &s, TOL);
}

#[test]
fn identity_sxsx_equals_x() {
    let a = statevector(
        1,
        with_prep(&[json!({"g":"sx","q":[0]}), json!({"g":"sx","q":[0]})]),
    );
    let b = statevector(1, with_prep(&[json!({"g":"x","q":[0]})]));
    assert_sv_eq(&a, &b, TOL);
}

#[test]
fn identity_tdg_t_is_identity_and_sdg_s_is_identity() {
    let a = statevector(
        1,
        with_prep(&[
            json!({"g":"t","q":[0]}),
            json!({"g":"tdg","q":[0]}),
            json!({"g":"s","q":[0]}),
            json!({"g":"sdg","q":[0]}),
        ]),
    );
    let b = statevector(1, with_prep(&[]));
    assert_sv_eq(&a, &b, TOL);
}

#[test]
fn identity_rz_equals_p_up_to_global_phase() {
    let a = statevector(1, with_prep(&[json!({"g":"rz","q":[0],"p":[0.9]})]));
    let b = statevector(1, with_prep(&[json!({"g":"p","q":[0],"p":[0.9]})]));
    assert_sv_eq_global_phase(&a, &b, 1e-10);
}

#[test]
fn identity_h_rz_h_equals_rx() {
    let a = statevector(
        1,
        with_prep(&[
            json!({"g":"h","q":[0]}),
            json!({"g":"rz","q":[0],"p":[1.234]}),
            json!({"g":"h","q":[0]}),
        ]),
    );
    let b = statevector(1, with_prep(&[json!({"g":"rx","q":[0],"p":[1.234]})]));
    assert_sv_eq(&a, &b, 1e-10);
}

#[test]
fn identity_u_pi_0_pi_equals_x() {
    let pi = std::f64::consts::PI;
    let a = statevector(1, with_prep(&[json!({"g":"u","q":[0],"p":[pi, 0.0, pi]})]));
    let b = statevector(1, with_prep(&[json!({"g":"x","q":[0]})]));
    assert_sv_eq(&a, &b, 1e-10);
}

#[test]
fn identity_swap_equals_three_cx() {
    let entangle = vec![
        json!({"g":"ry","q":[0],"p":[0.5]}),
        json!({"g":"ry","q":[1],"p":[1.1]}),
        json!({"g":"cx","q":[0,1]}),
    ];
    let mut a_ops = entangle.clone();
    a_ops.push(json!({"g":"swap","q":[0,1]}));
    let mut b_ops = entangle;
    b_ops.push(json!({"g":"cx","q":[0,1]}));
    b_ops.push(json!({"g":"cx","q":[1,0]}));
    b_ops.push(json!({"g":"cx","q":[0,1]}));
    let a = statevector(2, Value::Array(a_ops));
    let b = statevector(2, Value::Array(b_ops));
    assert_sv_eq(&a, &b, TOL);
}

// ---------------------------------------------------------------------------
// Truth tables
// ---------------------------------------------------------------------------

#[test]
fn ccx_truth_table() {
    // ccx q:[0,1,2] — controls q0,q1, target q2.
    // Bitstrings are rendered q2 q1 q0.
    for input in 0u32..8 {
        let mut ops = Vec::new();
        for q in 0..3 {
            if (input >> q) & 1 == 1 {
                ops.push(json!({"g":"x","q":[q]}));
            }
        }
        ops.push(json!({"g":"ccx","q":[0,1,2]}));
        let expected = if input & 0b011 == 0b011 {
            input ^ 0b100
        } else {
            input
        };
        let out = run(json!({"num_qubits": 3, "ops": ops}));
        assert!(out["error"].is_null());
        let probs = out["probabilities"].as_object().unwrap();
        let key = format!("{expected:03b}");
        assert_eq!(probs.len(), 1, "input {input}: {probs:?}");
        assert!(
            (probs[&key].as_f64().unwrap() - 1.0).abs() < TOL,
            "input {input} -> expected {key}"
        );
    }
}

#[test]
fn cswap_truth_table() {
    // cswap q:[0,1,2] — control q0, swap q1<->q2.
    for input in 0u32..8 {
        let mut ops = Vec::new();
        for q in 0..3 {
            if (input >> q) & 1 == 1 {
                ops.push(json!({"g":"x","q":[q]}));
            }
        }
        ops.push(json!({"g":"cswap","q":[0,1,2]}));
        let expected = if input & 1 == 1 {
            (input & 1) | ((input >> 1) & 1) << 2 | ((input >> 2) & 1) << 1
        } else {
            input
        };
        let out = run(json!({"num_qubits": 3, "ops": ops}));
        let probs = out["probabilities"].as_object().unwrap();
        let key = format!("{expected:03b}");
        assert_eq!(probs.len(), 1);
        assert!((probs[&key].as_f64().unwrap() - 1.0).abs() < TOL);
    }
}

// ---------------------------------------------------------------------------
// Measurement semantics
// ---------------------------------------------------------------------------

#[test]
fn partial_measurement_marginalizes() {
    // Bell, measure only q0 into c0 -> {"0": 0.5, "1": 0.5}
    let out = run(json!({
        "num_qubits": 2,
        "ops": [
            {"g":"h","q":[0]}, {"g":"cx","q":[0,1]},
            {"g":"measure","q":[0],"c":[0]}
        ]
    }));
    let probs = out["probabilities"].as_object().unwrap();
    assert_eq!(probs.len(), 2);
    assert!((probs["0"].as_f64().unwrap() - 0.5).abs() < TOL);
    assert!((probs["1"].as_f64().unwrap() - 0.5).abs() < TOL);
}

#[test]
fn num_clbits_sets_render_width() {
    // Bell, measure only q0 into c0, but declare a 3-bit register: the Python
    // client renders at num_clbits, so the wasm sim must too -> "000"/"001".
    let out = run(json!({
        "num_qubits": 2,
        "num_clbits": 3,
        "ops": [
            {"g":"h","q":[0]}, {"g":"cx","q":[0,1]},
            {"g":"measure","q":[0],"c":[0]}
        ]
    }));
    let probs = out["probabilities"].as_object().unwrap();
    assert_eq!(probs.len(), 2);
    assert!((probs["000"].as_f64().unwrap() - 0.5).abs() < TOL);
    assert!((probs["001"].as_f64().unwrap() - 0.5).abs() < TOL);
}

#[test]
fn num_clbits_narrower_than_measured_bit_errors() {
    let out = run(json!({
        "num_qubits": 2,
        "num_clbits": 1,
        "ops": [{"g":"measure","q":[0],"c":[0]}, {"g":"measure","q":[1],"c":[1]}]
    }));
    assert!(out["error"].as_str().unwrap().contains("narrower"));
}

#[test]
fn measurement_maps_qubits_to_clbits() {
    // Bell; q0 -> c0, q1 -> c2. Width 3, bit 1 always 0: "000" / "101".
    let out = run(json!({
        "num_qubits": 2,
        "ops": [
            {"g":"h","q":[0]}, {"g":"cx","q":[0,1]},
            {"g":"measure","q":[0],"c":[0]},
            {"g":"measure","q":[1],"c":[2]}
        ]
    }));
    let probs = out["probabilities"].as_object().unwrap();
    assert_eq!(probs.len(), 2);
    assert!((probs["000"].as_f64().unwrap() - 0.5).abs() < TOL);
    assert!((probs["101"].as_f64().unwrap() - 0.5).abs() < TOL);
}

#[test]
fn no_measure_with_shots_measures_all_qubits() {
    let out = run(json!({
        "num_qubits": 2,
        "shots": 100,
        "seed": 7,
        "ops": [{"g":"x","q":[1]}]
    }));
    let counts = out["counts"].as_object().unwrap();
    assert_eq!(counts.len(), 1);
    assert_eq!(counts["10"].as_u64().unwrap(), 100);
}

#[test]
fn barrier_is_ignored() {
    let a = statevector(
        2,
        json!([{"g":"h","q":[0]}, {"g":"barrier","q":[0,1]}, {"g":"cx","q":[0,1]}]),
    );
    let b = statevector(2, json!([{"g":"h","q":[0]}, {"g":"cx","q":[0,1]}]));
    assert_sv_eq(&a, &b, TOL);
}

// ---------------------------------------------------------------------------
// Sampling determinism
// ---------------------------------------------------------------------------

#[test]
fn seeded_counts_are_deterministic() {
    let prog = json!({
        "num_qubits": 3,
        "shots": 2048,
        "seed": 424242,
        "ops": [{"g":"h","q":[0]}, {"g":"h","q":[1]}, {"g":"cx","q":[1,2]}]
    });
    let a = run(prog.clone());
    let b = run(prog);
    assert_eq!(a["counts"], b["counts"]);
    assert!(a["counts"].as_object().unwrap().len() > 1);

    let c = run(json!({
        "num_qubits": 3,
        "shots": 2048,
        "seed": 1,
        "ops": [{"g":"h","q":[0]}, {"g":"h","q":[1]}, {"g":"cx","q":[1,2]}]
    }));
    assert_ne!(a["counts"], c["counts"], "different seeds should differ");
}

#[test]
fn null_seed_is_deterministic_default() {
    let prog = json!({
        "num_qubits": 1,
        "shots": 500,
        "seed": null,
        "ops": [{"g":"h","q":[0]}]
    });
    let a = run(prog.clone());
    let b = run(prog);
    assert_eq!(a["counts"], b["counts"]);
}

// ---------------------------------------------------------------------------
// Statevector gating
// ---------------------------------------------------------------------------

#[test]
fn statevector_omitted_above_8_qubits() {
    let out = run(json!({
        "num_qubits": 9,
        "want_statevector": true,
        "ops": [{"g":"h","q":[0]}]
    }));
    assert!(out["error"].is_null());
    assert!(out.get("statevector").is_none());
}

#[test]
fn statevector_omitted_when_not_wanted() {
    let out = run(json!({"num_qubits": 1, "ops": [{"g":"h","q":[0]}]}));
    assert!(out.get("statevector").is_none());
    assert!(out.get("counts").is_none(), "no shots => no counts");
}

// ---------------------------------------------------------------------------
// Error paths (never panic; {"error": "..."} out)
// ---------------------------------------------------------------------------

fn expect_error(program: Value, needle: &str) {
    let out = run(program);
    let msg = out["error"].as_str().unwrap_or_else(|| {
        panic!("expected error containing '{needle}', got: {out}");
    });
    assert!(
        msg.contains(needle),
        "expected error containing '{needle}', got '{msg}'"
    );
}

#[test]
fn error_bad_gate_name() {
    expect_error(
        json!({"num_qubits": 1, "ops": [{"g":"foo","q":[0]}]}),
        "unknown gate 'foo'",
    );
}

#[test]
fn error_qubit_out_of_bounds() {
    expect_error(
        json!({"num_qubits": 2, "ops": [{"g":"h","q":[2]}]}),
        "out of range",
    );
}

#[test]
fn error_too_many_qubits() {
    expect_error(
        json!({"num_qubits": 25, "ops": []}),
        "num_qubits must be between 1 and 24",
    );
    expect_error(
        json!({"num_qubits": 0, "ops": []}),
        "num_qubits must be between 1 and 24",
    );
}

#[test]
fn error_wrong_arity_and_params() {
    expect_error(
        json!({"num_qubits": 2, "ops": [{"g":"h","q":[0,1]}]}),
        "expects 1 qubit operand(s), got 2",
    );
    expect_error(
        json!({"num_qubits": 2, "ops": [{"g":"rz","q":[0]}]}),
        "expects 1 parameter(s), got 0",
    );
    expect_error(
        json!({"num_qubits": 2, "ops": [{"g":"cx","q":[1,1]}]}),
        "duplicate qubit operand",
    );
}

#[test]
fn error_gate_after_measure() {
    expect_error(
        json!({"num_qubits": 1, "ops": [
            {"g":"h","q":[0]},
            {"g":"measure","q":[0],"c":[0]},
            {"g":"x","q":[0]}
        ]}),
        "measurements must be terminal",
    );
}

#[test]
fn error_duplicate_clbit() {
    expect_error(
        json!({"num_qubits": 2, "ops": [
            {"g":"measure","q":[0],"c":[0]},
            {"g":"measure","q":[1],"c":[0]}
        ]}),
        "more than one measurement",
    );
}

#[test]
fn error_invalid_json() {
    let out: Value = serde_json::from_str(&qv_sim::run_program_json("not json {{")).unwrap();
    assert!(out["error"]
        .as_str()
        .unwrap()
        .contains("invalid program JSON"));
}

// ---------------------------------------------------------------------------
// ABI round-trip (native)
// ---------------------------------------------------------------------------

#[test]
fn abi_round_trip() {
    let program = json!({
        "num_qubits": 2,
        "shots": 16,
        "seed": 9,
        "want_statevector": true,
        "ops": [{"g":"h","q":[0]}, {"g":"cx","q":[0,1]}]
    })
    .to_string();
    let bytes = program.as_bytes();

    let in_ptr = qv_sim::qv_alloc(bytes.len());
    assert!(!in_ptr.is_null());
    unsafe { core::ptr::copy_nonoverlapping(bytes.as_ptr(), in_ptr, bytes.len()) };

    let out_ptr = qv_sim::qv_run(in_ptr, bytes.len());
    qv_sim::qv_free(in_ptr, bytes.len());
    assert!(!out_ptr.is_null());

    let mut len_le = [0u8; 4];
    unsafe { core::ptr::copy_nonoverlapping(out_ptr, len_le.as_mut_ptr(), 4) };
    let json_len = u32::from_le_bytes(len_le) as usize;
    let json_bytes =
        unsafe { core::slice::from_raw_parts(out_ptr.add(4), json_len) }.to_vec();
    qv_sim::qv_free(out_ptr, 4 + json_len);

    let out: Value = serde_json::from_slice(&json_bytes).unwrap();
    assert!(out["error"].is_null());
    assert_eq!(out["statevector"].as_array().unwrap().len(), 4);
    let counts = out["counts"].as_object().unwrap();
    let total: u64 = counts.values().map(|v| v.as_u64().unwrap()).sum();
    assert_eq!(total, 16);
}
