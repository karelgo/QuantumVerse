"""The capture SDK (RFC-0001): experiments become capsules as they run.

    import quantumverse as qv

    # Fully automatic on the built-in simulator:
    with qv.capture(title="Bell on qv-sim", authors=["Me"]) as cap:
        result = cap.run(bell_qasm, shots=4096, seed=42)
    capsule_id = cap.publish(sign_with="default", signer="qv:users/me")

    # Any hardware / any framework — snapshot the device, record the run:
    with qv.capture(title="Bell on ibm_kingston", authors=["Me"],
                    device=qv.device_from_qiskit(backend)) as cap:
        job = backend.run(transpiled, shots=4096)          # your existing code
        cap.record(circuit_qasm=abstract_qasm,
                   compiled_qasm=transpiled_qasm,
                   counts=job.result().get_counts(),
                   shots=4096, job_ids=[job.job_id()])
    capsule = cap.capsule()

The context manager timestamps entry/exit, freezes the environment lock,
builds the canonical capsule (validated, content-addressed), and can sign
and publish it in the same breath.
"""

from __future__ import annotations

from typing import Optional, Union

from .canonical import utc_now
from .capsule import Capsule, CapsuleError
from .qasm import parse_qasm
from .registry import Registry, get_registry
from .simulator import Result, run as _simulate

__all__ = ["CaptureError", "CaptureContext", "capture", "device_from_qiskit"]


class CaptureError(ValueError):
    """Raised when a capture cannot produce a capsule."""


class CaptureContext:
    """Collects one experiment's full context; builds the capsule on demand."""

    def __init__(
        self,
        title: str,
        authors: list,
        license: str = "CC-BY-4.0",
        device: Optional[dict] = None,
        artifacts: Optional[dict] = None,
    ):
        self.title = title
        self.authors = authors
        self.license = license
        self.artifacts = artifacts
        self._device = dict(device) if device else None
        self._mitigation: Optional[dict] = None
        self._recorded: Optional[dict] = None
        self._entered: Optional[str] = None
        self._capsule: Optional[Capsule] = None

    # -- context protocol -------------------------------------------------------

    def __enter__(self) -> "CaptureContext":
        self._entered = utc_now()
        if self._device is not None and not self._device.get("captured"):
            # the snapshot represents the device state at capture entry
            self._device["captured"] = self._entered
        return self

    def __exit__(self, exc_type, _exc, _tb) -> None:
        # deliberately no suppression: a failed experiment is not a capsule
        return None

    # -- recording ----------------------------------------------------------------

    def snapshot_device(self, device: dict) -> None:
        """Attach the backend calibration snapshot (RFC-0001 device.json shape)."""
        self._device = dict(device)
        if not self._device.get("captured"):
            self._device["captured"] = self._entered or utc_now()

    def run(
        self,
        circuit_qasm: str,
        shots: int = 1024,
        seed: Optional[int] = None,
        params: Optional[dict] = None,
    ) -> Result:
        """Run on the built-in simulator and record everything automatically."""
        submitted = utc_now()
        circuit = parse_qasm(circuit_qasm)
        result = _simulate(circuit, shots=shots, seed=seed, param_bindings=params)
        self.snapshot_device(
            {
                "backend": {"provider": "quantumverse", "name": "qv-sim", "version": "0.1.0"},
                "captured": self._entered or submitted,
                "topology": {"num_qubits": circuit.num_qubits},
                "qubits": [],
                "gates": [],
                "simulator": {
                    "engine": "quantumverse.simulator",
                    "method": "statevector",
                    **({"seed": seed} if seed is not None else {}),
                },
            }
        )
        self.record(
            circuit_qasm=circuit_qasm,
            counts=result.counts or {},
            shots=shots,
            parameters=params,
            submitted=submitted,
            completed=utc_now(),
        )
        return result

    def record(
        self,
        circuit_qasm: str,
        counts: dict,
        shots: int,
        compiled_qasm: Optional[str] = None,
        job_ids: Optional[list[str]] = None,
        parameters: Optional[dict] = None,
        submitted: Optional[str] = None,
        completed: Optional[str] = None,
    ) -> None:
        """Record an execution performed elsewhere (hardware, another framework)."""
        if self._recorded is not None:
            raise CaptureError(
                "this capture already recorded an execution — one capsule, one experiment"
            )
        execution: dict = {
            "job_ids": list(job_ids or []),
            "shots": int(shots),
            "counts_raw": {str(k): int(v) for k, v in counts.items()},
        }
        if parameters:
            execution["parameters"] = dict(parameters)
        if submitted:
            execution["submitted"] = submitted
        if completed:
            execution["completed"] = completed
        self._recorded = {
            "circuit_qasm": circuit_qasm,
            "compiled_qasm": compiled_qasm,
            "execution": execution,
        }

    def add_mitigation(self, pipeline: Union[dict, list]) -> None:
        """Attach the mitigation pipeline exactly as applied (RFC-0001)."""
        self._mitigation = pipeline if isinstance(pipeline, dict) else {"pipeline": pipeline}

    # -- output ----------------------------------------------------------------------

    def capsule(
        self, sign_with: Optional[str] = None, signer: Optional[str] = None
    ) -> Capsule:
        """Build (and optionally author-sign) the capsule."""
        if self._recorded is None:
            raise CaptureError("nothing recorded — call cap.run(...) or cap.record(...)")
        if self._device is None:
            raise CaptureError(
                "no device snapshot — pass device= to capture() or call "
                "cap.snapshot_device(...) (RFC-0001: the calibration snapshot is mandatory)"
            )
        if self._capsule is None:
            try:
                self._capsule = Capsule.create(
                    circuit_qasm=self._recorded["circuit_qasm"],
                    device=self._device,
                    execution=self._recorded["execution"],
                    title=self.title,
                    authors=self.authors,
                    license=self.license,
                    mitigation=self._mitigation,
                    compiled_qasm=self._recorded["compiled_qasm"],
                    artifacts=self.artifacts,
                )
            except CapsuleError as exc:
                raise CaptureError(f"capture cannot build a valid capsule: {exc}") from exc
        if sign_with is not None:
            from .signing import sign_files

            self._capsule.files = sign_files(
                self._capsule.files, self._capsule.id, key_name=sign_with, signer=signer
            )
        return self._capsule

    def publish(
        self,
        registry: Optional[Union[str, Registry]] = None,
        sign_with: Optional[str] = None,
        signer: Optional[str] = None,
    ) -> str:
        """Build, optionally sign, and push the capsule; returns its id."""
        capsule = self.capsule(sign_with=sign_with, signer=signer)
        return get_registry(registry).push_capsule(capsule.files)


def capture(
    title: str,
    authors: list,
    license: str = "CC-BY-4.0",
    device: Optional[dict] = None,
    artifacts: Optional[dict] = None,
) -> CaptureContext:
    """Open a capture context (see module docstring for both usage shapes)."""
    return CaptureContext(
        title=title, authors=authors, license=license, device=device, artifacts=artifacts
    )


# ---------------------------------------------------------------------------
# Qiskit adapter (reference integration)
# ---------------------------------------------------------------------------


def device_from_qiskit(backend) -> dict:
    """Translate a Qiskit ``BackendV2``-shaped backend into ``device.json``.

    Duck-typed on the BackendV2 surface (``name``, ``num_qubits``,
    ``coupling_map``, ``target`` with ``qubit_properties`` /
    ``instruction_properties``) so it can be exercised without qiskit
    installed; drift against real qiskit releases is a bug report away.
    """
    name = getattr(backend, "name", None)
    if callable(name):  # BackendV1 compatibility
        name = name()
    num_qubits = getattr(backend, "num_qubits", None)
    if not name or not isinstance(num_qubits, int):
        raise CaptureError(
            "backend does not look like a Qiskit BackendV2 (need .name and .num_qubits)"
        )

    device: dict = {
        "backend": {
            "provider": str(getattr(backend, "provider", None) or "qiskit"),
            "name": str(name),
            **(
                {"version": str(backend.backend_version)}
                if getattr(backend, "backend_version", None)
                else {}
            ),
        },
        "captured": utc_now(),
        "topology": {"num_qubits": num_qubits},
        "qubits": [],
        "gates": [],
        "simulator": None,
    }

    coupling = getattr(backend, "coupling_map", None)
    edges = getattr(coupling, "get_edges", None)
    if callable(edges):
        device["topology"]["coupling_map"] = [list(e) for e in edges()]

    target = getattr(backend, "target", None)
    qubit_props = getattr(target, "qubit_properties", None) if target else None
    if qubit_props:
        for index, props in enumerate(qubit_props):
            entry: dict = {"index": index}
            t1 = getattr(props, "t1", None)
            t2 = getattr(props, "t2", None)
            frequency = getattr(props, "frequency", None)
            if isinstance(t1, (int, float)) and t1 > 0:
                entry["t1_us"] = t1 * 1e6  # qiskit reports seconds
            if isinstance(t2, (int, float)) and t2 > 0:
                entry["t2_us"] = t2 * 1e6
            if isinstance(frequency, (int, float)) and frequency > 0:
                entry["frequency_ghz"] = frequency / 1e9
            device["qubits"].append(entry)

    if target:
        for op_name in getattr(target, "operation_names", []) or []:
            try:
                props_map = target[op_name]
            except Exception:
                continue
            if not hasattr(props_map, "items"):
                continue
            for qubits, inst_props in props_map.items():
                error = getattr(inst_props, "error", None)
                duration = getattr(inst_props, "duration", None)
                if error is None and duration is None:
                    continue
                gate: dict = {"gate": op_name, "qubits": list(qubits)}
                if isinstance(error, (int, float)) and 0 <= error <= 1:
                    gate["error"] = error
                if isinstance(duration, (int, float)) and duration > 0:
                    gate["duration_ns"] = duration * 1e9  # qiskit reports seconds
                device["gates"].append(gate)

    return device
