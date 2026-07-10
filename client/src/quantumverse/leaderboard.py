"""Verified leaderboards (RFC-0006): scores computed, never claimed.

A leaderboard binds a problem-instance artifact to a scoring metric. An
entry is nothing but a capsule id: the registry loads the capsule from its
own store, resolves the instance from its own store, recomputes the score
from ``counts_raw``, and ranks the result with the capsule's trust level.
This module is the shared scoring core, used identically by client and
server (like ``certify.py`` and ``devices.py``).
"""

from __future__ import annotations

from typing import Callable

from ._schema import schema_errors

__all__ = [
    "LeaderboardError",
    "METRICS",
    "validate_board",
    "score_capsule_files",
    "rank_entries",
]


class LeaderboardError(ValueError):
    """Raised when a board is malformed or an entry cannot be scored."""


def validate_board(board: dict) -> None:
    errors = schema_errors("leaderboard", board)
    if errors:
        raise LeaderboardError(
            "leaderboard definition failed schema validation:\n  " + "\n  ".join(errors)
        )


def _score_maxcut_ratio(instance: dict, execution: dict) -> float:
    """Expected cut over the known optimum, from Z-basis counts.

    Bitstrings render qubit ``n-1 … 0`` left to right (the platform's
    little-endian convention); node *i* is qubit *i*.
    """
    if instance.get("kind") != "maxcut":
        raise LeaderboardError(
            f"metric maxcut-ratio needs a maxcut instance, got kind={instance.get('kind')!r}"
        )
    nodes = instance.get("nodes")
    edges = instance.get("edges") or []
    weights = instance.get("weights") or [1] * len(edges)
    optimum = instance.get("max_cut_value")
    if not isinstance(nodes, int) or nodes < 1 or not edges:
        raise LeaderboardError("maxcut instance is missing nodes/edges")
    if not isinstance(optimum, (int, float)) or optimum <= 0:
        raise LeaderboardError("maxcut instance is missing max_cut_value")
    if len(weights) != len(edges):
        raise LeaderboardError("maxcut instance weights do not match edges")

    counts = execution.get("counts_raw") or {}
    if not counts:
        raise LeaderboardError("capsule has no raw counts to score")
    total_shots = 0
    total_cut = 0.0
    for bitstring, count in counts.items():
        if len(bitstring) != nodes:
            raise LeaderboardError(
                f"bitstring width {len(bitstring)} does not match the instance's "
                f"{nodes} nodes — the circuit must measure one bit per node"
            )
        bits = [bitstring[nodes - 1 - i] for i in range(nodes)]  # node i = qubit i
        cut = sum(
            w for (a, b), w in zip(edges, weights) if bits[a] != bits[b]
        )
        total_cut += cut * count
        total_shots += count
    return (total_cut / total_shots) / float(optimum)


METRICS: dict[str, Callable[[dict, dict], float]] = {
    "maxcut-ratio": _score_maxcut_ratio,
}


def score_capsule_files(
    board: dict, instance: dict, capsule_id: str, files: dict[str, bytes]
) -> dict:
    """Recompute one entry — the trust-nothing core shared by client and server.

    Returns ``{capsule, score, shots, backend}``; the caller adds rank and
    the capsule's trust level.
    """
    import json

    metric = board.get("metric")
    scorer = METRICS.get(metric)
    if scorer is None:
        raise LeaderboardError(
            f"unknown metric {metric!r}; known: {', '.join(sorted(METRICS))}"
        )
    execution_raw = files.get("execution.json")
    device_raw = files.get("device.json")
    if execution_raw is None or device_raw is None:
        raise LeaderboardError(f"{capsule_id}: not a complete capsule")
    try:
        execution = json.loads(execution_raw.decode("utf-8"))
        device = json.loads(device_raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LeaderboardError(f"{capsule_id}: unreadable capsule payloads: {exc}") from exc

    score = scorer(instance, execution)
    backend = device.get("backend") or {}
    return {
        "capsule": capsule_id,
        "score": round(float(score), 6),
        "shots": execution.get("shots"),
        "backend": f"{backend.get('provider', '?')}/{backend.get('name', '?')}",
    }


def rank_entries(entries: list[dict], higher_is_better: bool) -> list[dict]:
    """Sort entries per RFC-0006 (score, then trust, then earlier submission)
    and stamp 1-based ranks."""
    ordered = sorted(
        entries,
        key=lambda e: (
            -e["score"] if higher_is_better else e["score"],
            -e.get("trust", 0),
            e.get("submitted", ""),
        ),
    )
    return [{**entry, "rank": i + 1} for i, entry in enumerate(ordered)]
