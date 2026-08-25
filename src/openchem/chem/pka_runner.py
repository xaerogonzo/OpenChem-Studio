"""Standalone pkasolver runner, executed by a SEPARATE Python interpreter.

This module is never imported by the application. It is handed as a script
path to the user's configured pkasolver environment's interpreter (see
`chem/pka_providers.py::compute_pka`), which has its own conflicting pins
-- `numpy<2`, `scipy<1.14`, `torch==2.3.0`, `torch-geometric==2.0.1` --
that must not be forced onto this project (which runs numpy 2.x).

Reads a SMILES string from argv, writes JSON to stdout:
    {"pkas": [{"pka": 4.82, "atom_idx": 7, "site_smiles": "...", ...}, ...]}
    {"error": "..."}

`atom_idx` indexes `site_smiles`, NOT the caller's molecule -- see
`_indexed_smiles` below for why that distinction is the whole point.

Keep this file dependency-free apart from what the pkasolver environment
itself provides (rdkit + pkasolver). In particular it must NOT import
anything from `openchem` -- that package isn't installed over there.
"""

from __future__ import annotations

#: See `chem/admet_runner.py` for what this declares and why. Same
#: mechanism, a different sidecar.
REACHED_BY = (
    "script_path: handed to the pkasolver environment's interpreter by "
    "chem/pka_providers.py, which is why nothing imports it"
)

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


def _indexed_smiles(mol) -> str:
    """SMILES carrying each atom's index as an atom map number.

    THE REASON THIS EXISTS. `States.reaction_center_idx` is an index into
    pkasolver's own pH-7 microstate (`States.ph7_mol`), which Dimorphite-DL
    built by round-tripping our molecule through SMILES -- so its atom
    numbering is its own, not the caller's. Confirmed live: for
    4-aminobenzoic acid the carboxylic pKa reports index 7, which is the
    carboxylate OXYGEN in the microstate and a ring CARBON in ours.

    A plain `MolToSmiles` here would not be enough to repair that, because
    it renumbers again on the way out: RDKit writes atoms in canonical
    order and re-parsing numbers them in the order they appear in the
    string. Atom map numbers survive both trips, so the app can rebuild
    pkasolver's numbering exactly and map from there.

    from rdkit import Chem

    is deliberately local -- this module must stay importable by the
    pkasolver environment's interpreter and nothing else.
    """
    from rdkit import Chem

    tagged = Chem.Mol(mol)
    for atom in tagged.GetAtoms():
        atom.SetAtomMapNum(atom.GetIdx() + 1)
    return Chem.MolToSmiles(tagged)


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
                # The structure `atom_idx` actually indexes. Without it the
                # index is unusable on the far side of the process boundary.
                "site_smiles": _indexed_smiles(s.ph7_mol) if getattr(s, "ph7_mol", None) is not None else "",
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
