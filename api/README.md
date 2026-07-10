# quantumverse-api

The reference QuantumVerse registry server: artifacts (RFC-0003 addressing, RFC-0002 cards rebuilt server-side), Experiment Capsules (RFC-0001, fully re-validated on upload), and content-addressed blobs — FastAPI over SQLite + an on-disk blob store.

```bash
pip install -e ../client -e .
qv-registry --data ./data --web ../web --port 8000
```

Then, from anywhere:

```bash
export QV_REGISTRY_URL=http://127.0.0.1:8000
qv push bell.qasm qv:demo/bell --type circuit --version 1.0.0
qv pull qv:demo/bell
```

The HTTP mapping is normative in [RFC-0003](../rfcs/rfc-0003-artifact-addressing.md); the `quantumverse` client's `RemoteRegistry` is the reference consumer. `--web ../web` additionally serves the in-browser playground at `/`.
