"""Standalone pkasolver runner, executed by a SEPARATE Python interpreter.

This module is never imported by the application. It is handed as a script
path to the user's configured pkasolver environment's interpreter (see
`chem/pka_providers.py::compute_pka`), which has its own conflicting pins
-- `numpy<2`, `scipy<1.14`, `torch==2.3.0`, `torch-geometric==2.0.1` --
that must not be forced onto this project (which runs numpy 2.x).

Reads a SMILES string from argv, writes JSON to stdout:
    {"pkas": [{"pka": 4.82, "atom_idx": 7}, ...]}
    {"error": "..."}

Keep this file dependency-free apart from what the pkasolver environment
itself provides (rdkit + pkasolver). In particular it must NOT import
anything from `openchem` -- that package isn't installed over there.
"""

from __future__ import annotations

import json
import sys
import types
import warnings


def _load_pkasolver():
    # cairosvg is imported at module scope in pkasolver.query but used at
    # exactly one line (a PNG drawing helper), and needs a native Cairo DLL
    # Windows doesn't ship. Stub it so the prediction path is reachable.
    sys.modules.setdefault("cairosvg", types.ModuleType("cairosvg"))
    sys.modules.setdefault("svgutils", types.ModuleType("svgutils"))
    sys.modules.setdefault("svgutils.transform", types.ModuleType("svgutils.transform"))
    import pkasolver.query as query
    from pkasolver import run_with_mol_list

    # pkasolver shells out to a bare `python` for its own vendored
    # Dimorphite-DL, which breaks whenever `python` on PATH isn't this
    # interpreter. Run it in-process instead -- same library, one less
    # moving part.
    def _in_process(mol, min_ph=7.0, max_ph=7.0, pka_precision=0.0, **_kwargs):
        return run_with_mol_list(
            [mol], min_ph=min_ph, max_ph=max_ph, pka_precision=pka_precision, silent=True
        )

    query._call_dimorphite_dl = _in_process
    return query


def main(argv: list[str]) -> int:
    warnings.filterwarnings("ignore")
    if len(argv) < 2:
        json.dump({"error": "usage: pka_runner.py <smiles>"}, sys.stdout)
        return 2
    smiles = argv[1]
    # pkasolver's vendored Dimorphite-DL parses sys.argv with argparse when
    # invoked in-process, and errors out on OUR arguments ("unrecognized
    # arguments: CC(=O)O"). Blank argv before calling into it.
    sys.argv = [argv[0]]
    try:
        from rdkit import Chem

        query = _load_pkasolver()
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            json.dump({"error": f"Could not parse SMILES {smiles!r}"}, sys.stdout)
            return 1
        states = query.calculate_microstate_pka_values(mol)
        # Attribute names confirmed live against pkasolver's own microstate
        # objects: `reaction_center_idx` (the atom being protonated/
        # deprotonated at that pKa) and `pka_stddev` (spread across the
        # 50-model ensemble -- real, model-reported uncertainty, worth
        # surfacing rather than discarding).
        pkas = [
            {
                "pka": float(s.pka),
                "atom_idx": int(getattr(s, "reaction_center_idx", -1)),
                "stddev": float(getattr(s, "pka_stddev", 0.0)),
            }
            for s in states
        ]
    except Exception as exc:  # noqa: BLE001 - any failure must come back as JSON, not a traceback on stdout
        json.dump({"error": f"{type(exc).__name__}: {exc}"}, sys.stdout)
        return 1
    json.dump({"pkas": pkas}, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
