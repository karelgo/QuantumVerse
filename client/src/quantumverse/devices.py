"""Device records and calibration summaries (RFC-0004).

The record format and the summary derivation are shared between the client
and the reference registry server so timelines are comparable everywhere.
"""

from __future__ import annotations

from ._schema import schema_errors

__all__ = ["DeviceRecordError", "validate_record", "calibration_summary", "RECORD_VERSION"]

RECORD_VERSION = "0.1"


class DeviceRecordError(ValueError):
    """Raised when a device record violates RFC-0004."""


def validate_record(record: dict) -> None:
    """Raise :class:`DeviceRecordError` if *record* is not a valid RFC-0004 record."""
    errors = schema_errors("device-record", record)
    if errors:
        raise DeviceRecordError(
            "device record failed schema validation:\n  " + "\n  ".join(errors)
        )


def _median(values: list) -> float | None:
    values = sorted(v for v in values if isinstance(v, (int, float)))
    if not values:
        return None
    mid = len(values) // 2
    if len(values) % 2:
        return values[mid]
    return (values[mid - 1] + values[mid]) / 2.0


def calibration_summary(device_doc: dict) -> dict:
    """Cheap plotting summary of one ``device.json`` snapshot (RFC-0004)."""
    qubits = device_doc.get("qubits") or []
    gates = device_doc.get("gates") or []
    summary = {
        "num_qubits": (device_doc.get("topology") or {}).get("num_qubits"),
        "median_t1_us": _median([q.get("t1_us") for q in qubits if isinstance(q, dict)]),
        "median_t2_us": _median([q.get("t2_us") for q in qubits if isinstance(q, dict)]),
        "median_readout_error": _median(
            [q.get("readout_error") for q in qubits if isinstance(q, dict)]
        ),
        "median_gate_error": _median([g.get("error") for g in gates if isinstance(g, dict)]),
    }
    return {k: v for k, v in summary.items() if v is not None}
