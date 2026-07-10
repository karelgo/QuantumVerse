"""Circuit Card construction (RFC-0002).

``build_card`` parses the circuit, machine-populates the ``resources``
block (computed, never claimed), assembles the card, and validates it
against the vendored circuit-card schema before returning it.
"""

from __future__ import annotations

from typing import Optional

from ._schema import schema_errors
from .qasm import parse_qasm
from .resources import count_resources

__all__ = ["CardError", "build_card"]

CARD_VERSION = "0.1"


class CardError(ValueError):
    """Raised when a card cannot be built or fails schema validation."""


def build_card(
    qasm_text: str,
    name: str,
    summary: str,
    provenance: dict,
    description: Optional[str] = None,
    tags: Optional[list[str]] = None,
    requirements: Optional[dict] = None,
    noise_profile: Optional[dict] = None,
    verified_results: Optional[list[dict]] = None,
) -> dict:
    """Build a schema-valid Circuit Card for *qasm_text*.

    ``resources`` is always computed from the source (RFC-0002 design rule 1).
    ``provenance`` must contain at least ``license``.
    """
    circuit = parse_qasm(qasm_text)

    card: dict = {
        "card_version": CARD_VERSION,
        "name": name,
        "summary": summary,
        "resources": count_resources(circuit),
        "provenance": dict(provenance),
    }
    if description is not None:
        card["description"] = description
    if requirements is not None:
        card["requirements"] = dict(requirements)
    if noise_profile is not None:
        card["noise_profile"] = dict(noise_profile)
    if verified_results is not None:
        card["verified_results"] = list(verified_results)
    if tags is not None:
        card["tags"] = list(tags)

    errors = schema_errors("circuit-card", card)
    if errors:
        raise CardError(
            "circuit card failed schema validation:\n  " + "\n  ".join(errors)
        )
    return card
