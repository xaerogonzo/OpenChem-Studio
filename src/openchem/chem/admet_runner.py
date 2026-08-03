"""Standalone ADMET-AI runner, executed by a SEPARATE Python interpreter.

This module is never imported by the application. It is handed as a script
path to the user's configured ADMET environment's interpreter (see
`chem/admet_providers.py::compute_admet`), which carries torch,
pytorch-lightning and chemprop -- about 1 GB that has no business in this
project's own dependency tree, or in the frozen PyInstaller build.

Reads a SMILES string from argv, writes JSON to stdout:
    {"endpoints": {"hERG": 0.995, "CYP3A4_Veith": 0.41, ...}}
    {"error": "..."}

Keep this file dependency-free apart from what the ADMET environment
provides (rdkit + admet_ai). In particular it must NOT import anything
from `openchem` -- that package isn't installed over there.

The model is loaded on every invocation, which costs a few seconds. That
is deliberate: a resident process would need lifecycle management for a
calculator a user triggers occasionally, and the alternative -- caching a
loaded model across calls -- is the kind of state that outlives its
usefulness. Revisit only if batch prediction becomes a real workflow.
"""

from __future__ import annotations

import contextlib
import json
import sys
import warnings


def main(argv: list[str]) -> int:
    warnings.filterwarnings("ignore")
    if len(argv) < 2:
        json.dump({"error": "usage: admet_runner.py <smiles>"}, sys.stdout)
        return 2
    smiles = argv[1]

    # stdout is this script's data channel and nothing else may write to
    # it. pytorch-lightning prints a live progress bar there -- "Predicting
    # ---- 1/1" -- once per model in the ensemble, which lands in the
    # middle of the JSON and makes it unparseable at column 1. Send every
    # such byte to stderr for the duration, where it is still visible if a
    # run needs debugging.
    try:
        with contextlib.redirect_stdout(sys.stderr):
            from admet_ai import ADMETModel

            model = ADMETModel()
            frame = model.predict(smiles=[smiles])
    except Exception as exc:  # noqa: BLE001 - reported as JSON, not raised
        json.dump({"error": f"{type(exc).__name__}: {exc}"}, sys.stdout)
        return 1

    try:
        # predict() returns a DataFrame indexed by the input SMILES. Take
        # the row rather than assuming position, since ADMET-AI
        # canonicalizes and a positional read would silently misalign if
        # it ever returns rows in a different order.
        row = frame.loc[smiles] if smiles in frame.index else frame.iloc[0]
        endpoints = {str(k): float(v) for k, v in row.items()}
    except Exception as exc:  # noqa: BLE001
        json.dump({"error": f"could not read predictions: {type(exc).__name__}: {exc}"}, sys.stdout)
        return 1

    json.dump({"endpoints": endpoints}, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
