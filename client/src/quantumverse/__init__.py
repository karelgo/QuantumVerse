"""quantumverse — reference client for the QuantumVerse platform.

Capsules (RFC-0001), Circuit Cards (RFC-0002), qv: addressing (RFC-0003),
a statevector simulator for the shared OpenQASM 3 subset, and the ``qv`` CLI.
"""

from .capsule import Capsule
from .cards import build_card
from .capture import capture, device_from_qiskit
from .hub import load, push
from .qasm import parse_qasm
from .resources import count_resources

__version__ = "0.1.0"

__all__ = [
    "__version__",
    "load",
    "push",
    "Capsule",
    "capture",
    "device_from_qiskit",
    "parse_qasm",
    "count_resources",
    "build_card",
]
