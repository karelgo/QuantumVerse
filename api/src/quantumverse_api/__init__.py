"""quantumverse-api — the reference QuantumVerse registry server.

Implements the RFC-0003 HTTP mapping over a SQLite metadata store and an
on-disk content-addressed blob store. The `quantumverse` client library is
the single source of truth for validation, hashing, and Circuit Cards.
"""

from .app import create_app

__version__ = "0.1.0"
__all__ = ["create_app", "__version__"]
