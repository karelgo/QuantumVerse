# Seed library

The starter content an empty hub gets seeded with ([IMPLEMENTATION-PLAN.md](../IMPLEMENTATION-PLAN.md): *"seed before launch"*). Nine circuits, two problem instances, and two **trained-parameters artifacts whose values were actually converged on the reference simulator** — not copied from a paper:

| Artifact | Type | Notes |
|---|---|---|
| `qv:seeds/bell`, `ghz-3`, `ghz-5` | circuit | Entanglement basics |
| `qv:seeds/qft-4` | circuit | Fourier transform, `cp` cascade |
| `qv:seeds/grover-2q` | circuit | One iteration, P(11) = 1 |
| `qv:seeds/deutsch-jozsa-3`, `bernstein-vazirani-4` | circuit | Oracle classics |
| `qv:seeds/vqe-h2-ansatz` | circuit | Parameterized (`input float theta`) |
| `qv:seeds/qaoa-maxcut-triangle` | circuit | Parameterized (`gamma`, `beta`) |
| `qv:instances/h2-sto3g` | instance | Tapered 2-qubit H₂ Hamiltonian, exact E₀ = −1.857275 Ha |
| `qv:instances/maxcut-triangle` | instance | K₃ MaxCut, optimum 2 |
| `qv:seeds/vqe-h2-params` | parameters | θ\* = −0.22368, energy gap to exact 8.5×10⁻⁹ Ha |
| `qv:seeds/qaoa-maxcut-triangle-params` | parameters | (γ\*, β\*) reaching ratio 1.0 (K₃ is exact at p=1) |

```bash
python seeds/import.py --registry http://127.0.0.1:8000 --with-capsule
```

The import parses and simulates every circuit before pushing, is idempotent, and `--with-capsule` mints a deterministic Bell capsule (seed 42) as the first Experiment Capsule in the registry.
