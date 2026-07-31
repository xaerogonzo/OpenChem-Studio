"""Standalone script executed BY the STOUT environment's own interpreter.

Never imported by the application: it runs inside a separate Python 3.10
virtual environment where `openchem` is not installed, so it imports
nothing from this package. Same shape as `chem/pka_runner.py`.

Reads one SMILES per line on stdin, writes one JSON object on stdout.
"""

from __future__ import annotations

import json
import sys


def main() -> int:
    smiles = sys.stdin.read().strip()
    if not smiles:
        print(json.dumps({"error": "no SMILES supplied"}))
        return 1

    # TensorFlow writes progress bars and C++ log noise to stdout/stderr on
    # import. The parser on the other side takes the LAST brace-line for
    # exactly this reason, but quieting it keeps the logs readable.
    import os

    os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")

    try:
        from STOUT import translate_forward
    except ImportError as exc:  # pragma: no cover - depends on the sidecar env
        print(json.dumps({"error": f"STOUT is not importable in this environment: {exc}"}))
        return 1

    try:
        name = translate_forward(smiles)
    except Exception as exc:  # noqa: BLE001 - report, never traceback into the parent
        print(json.dumps({"error": f"STOUT failed: {exc}"}))
        return 1

    print(json.dumps({"name": name}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
