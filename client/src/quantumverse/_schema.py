"""Loading and applying the vendored JSON Schemas (byte-identical to spec/schemas)."""

from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources as _importlib_resources

import jsonschema

SCHEMA_NAMES = {
    "manifest": "manifest.schema.json",
    "device": "device.schema.json",
    "execution": "execution.schema.json",
    "mitigation": "mitigation.schema.json",
    "circuit-card": "circuit-card.schema.json",
    "device-record": "device-record.schema.json",
}


def schema_bytes(name: str) -> bytes:
    """Raw bytes of a vendored schema (name: manifest|device|execution|mitigation|circuit-card)."""
    filename = SCHEMA_NAMES[name]
    return (_importlib_resources.files("quantumverse.schemas") / filename).read_bytes()


@lru_cache(maxsize=None)
def load_schema(name: str) -> dict:
    return json.loads(schema_bytes(name).decode("utf-8"))


@lru_cache(maxsize=None)
def _validator(name: str) -> jsonschema.Draft202012Validator:
    return jsonschema.Draft202012Validator(load_schema(name))


def schema_errors(name: str, instance) -> list[str]:
    """Human-readable schema violations of *instance* against schema *name* (empty = valid)."""
    errors = []
    for err in sorted(_validator(name).iter_errors(instance), key=lambda e: list(e.absolute_path)):
        where = "/".join(str(p) for p in err.absolute_path) or "(root)"
        errors.append(f"{where}: {err.message}")
    return errors


def validate_schema(name: str, instance) -> None:
    """Raise ``jsonschema.ValidationError`` if *instance* violates schema *name*."""
    _validator(name).validate(instance)
