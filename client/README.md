# quantumverse

Reference client for the QuantumVerse platform: Experiment Capsules (RFC-0001), Circuit Cards (RFC-0002), `qv:` addressing (RFC-0003), a statevector simulator for the shared OpenQASM 3 subset, semantic circuit diffs, Quantum CI checks, and the `qv` CLI.

```bash
pip install -e .

qv run bell.qasm --shots 1000
qv card bell.qasm --name bell --summary "Bell pair"
qv capsule create --circuit bell.qasm --device device.json --execution execution.json \
   --title "Bell on qv-sim" --author "You"
qv capsule validate capsule-xxxxxx.tar
qv capsule replay capsule-xxxxxx.tar
qv diff old.qasm new.qasm            # resource deltas + equivalence up to global phase
qv ci --config quantumverse.ci.json  # budgets, golden equivalence, expected distributions
qv push bell.qasm qv:demo/bell --type circuit --version 1.0.0
qv pull qv:demo/bell
```

Registry selection: `--registry URL` &gt; `QV_REGISTRY_URL` env &gt; local `~/.qv` (or `QV_HOME`).

```python
import quantumverse as qv

art = qv.load("demo/bell")                 # LoadedArtifact
print(art.text())                          # circuit.qasm
circuit = art.qiskit()                     # optional [qiskit] extra

# Capture an experiment as a capsule while it runs (RFC-0001):
with qv.capture(title="Bell on qv-sim", authors=["Me"]) as cap:
    result = cap.run(art.text(), shots=4096, seed=42)
capsule_id = cap.publish(sign_with="default", signer="qv:users/me")

# On hardware: snapshot the device, record your existing run
with qv.capture(title="Bell on real iron", authors=["Me"],
                device=qv.device_from_qiskit(backend)) as cap:
    job = backend.run(transpiled, shots=4096)          # your code, unchanged
    cap.record(circuit_qasm=abstract_qasm, compiled_qasm=transpiled_qasm,
               counts=job.result().get_counts(), shots=4096,
               job_ids=[job.job_id()])
capsule = cap.capsule(sign_with="default")
```
