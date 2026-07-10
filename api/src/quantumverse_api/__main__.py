"""Run the registry: ``qv-registry --data ./data --web ../web --port 8000``."""

from __future__ import annotations

import argparse


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="qv-registry", description="QuantumVerse registry server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--data", default=None, help="data directory (default: QV_DATA_DIR or ./data)")
    parser.add_argument("--web", default=None, help="static playground directory to serve at / (optional)")
    args = parser.parse_args(argv)

    import uvicorn

    from .app import create_app

    uvicorn.run(create_app(data_dir=args.data, web_dir=args.web), host=args.host, port=args.port)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
