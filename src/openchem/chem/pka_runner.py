"""Standalone pkasolver runner, executed by a SEPARATE Python interpreter.

This module is never imported by the application. It is handed as a script
path to the user's configured pkasolver environment's interpreter (see
`chem/pka_providers.py::compute_pka`), which has its own conflicting pins
-- `numpy<2`, `scipy<1.14`, `torch==2.3.0`, `torch-geometric==2.0.1` --
that must not be forced onto this project (which runs numpy 2.x).

Reads a SMILES string from argv, writes JSON to stdout:
    {"pkas": [{"pka": 4.82, "atom_idx": 7, "site_smiles": "...",
               "protonated_smiles": "...", "deprotonated_smiles": "...", ...}, ...],
     "pkasolver_version": "..."}
    {"error": "..."}

`atom_idx` indexes `site_smiles`, NOT the caller's molecule -- see
`_indexed_smiles` below for why that distinction is the whole point.

Two modes, one payload (`predict`): `pka_runner.py <smiles>` answers one structure
and exits, which is what a fresh-install check runs; `pka_runner.py --serve` loads
pkasolver once and answers one request line at a time, which is how the application
keeps the model warm between structures (`chem/pka_worker.py`; the wire contract is
documented on `serve`).

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


def predict(query, smiles: str) -> dict:
    """One structure's answer as a payload dict: `{"pkas": [...], "pkasolver_version": ...}`
    or `{"error": ...}`. Never raises, because both callers must put it on a
    wire -- a traceback on stdout would be mistaken for the answer.

    The ONE place the payload is built, shared by the one-shot run and the
    persistent `--serve` loop, so the two cannot drift apart: the app compares
    them field for field.
    """
    try:
        from rdkit import Chem

        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return {"error": f"Could not parse SMILES {smiles!r}"}
        states = query.calculate_microstate_pka_values(mol)
        # Attribute names confirmed live against pkasolver's own microstate
        # objects: `reaction_center_idx` (the atom being protonated/
        # deprotonated at that pKa) and `pka_stddev` (spread across the
        # 50-model ensemble -- real, model-reported uncertainty, worth
        # surfacing rather than discarding). `protonated_mol` and
        # `deprotonated_mol` confirmed 2026-09-14, indexed like `ph7_mol`.
        def tagged(state, name):
            microstate = getattr(state, name, None)
            return _indexed_smiles(microstate) if microstate is not None else ""

        pkas = [
            {
                "pka": float(s.pka),
                "atom_idx": int(getattr(s, "reaction_center_idx", -1)),
                "stddev": float(getattr(s, "pka_stddev", 0.0)),
                # The structure `atom_idx` actually indexes. Without it the
                # index is unusable on the far side of the process boundary.
                "site_smiles": tagged(s, "ph7_mol"),
                # What the prediction ENCODES about the site on either side
                # of its pKa -- the model's own two states, so the app never
                # has to infer the direction from calling the site an acid
                # or a base.
                "protonated_smiles": tagged(s, "protonated_mol"),
                "deprotonated_smiles": tagged(s, "deprotonated_mol"),
            }
            for s in states
        ]
        import pkasolver

        version = str(getattr(pkasolver, "__version__", "") or "unknown")
    except Exception as exc:  # noqa: BLE001 - any failure must come back as JSON, not a traceback on stdout
        return {"error": f"{type(exc).__name__}: {exc}"}
    return {"pkas": pkas, "pkasolver_version": version}


def main(argv: list[str]) -> int:
    """One-shot: one SMILES in argv, one JSON object on stdout, exit. Unchanged
    in behaviour -- this is the path a fresh-install check must really run."""
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
        query = _load_pkasolver()
    except Exception as exc:  # noqa: BLE001 - see predict()
        json.dump({"error": f"{type(exc).__name__}: {exc}"}, sys.stdout)
        return 1
    payload = predict(query, smiles)
    json.dump(payload, sys.stdout)
    return 1 if "error" in payload else 0


def serve() -> int:
    """Persistent mode (`--serve`): load pkasolver ONCE, then answer one request
    line at a time until stdin closes.

    Wire contract (the parent is `chem/pka_worker.py`; both ends are in this
    repository and change together):

        child  -> {"ready": true, "pkasolver_version": "..."}          once, after the load
                  {"ready": false, "error": "..."}                      and exit, if it fails
        parent -> {"request_id": "<generation>:<n>", "smiles": "..."}   one line per request
        child  -> the `predict` payload plus the same "request_id"      one line per request

    A bad request or a failed prediction is an `{"error": ...}` RESPONSE and the
    process stays up: a warm model must not be thrown away for one bad molecule.
    Stdin closing (the app exited, even by crashing) ends the loop, so the
    sidecar can never outlive the application that started it.

    **STDOUT IS THE PROTOCOL AND NOTHING ELSE MAY REACH IT.** pkasolver's
    dependencies print banners to stdout (`_parse_runner_output` has always
    had to skip them), so the real stdout is duplicated for the protocol and
    file descriptor 1 is pointed at stderr -- which also catches output written
    by native code, not only by Python's `print`.
    """
    import io
    import os

    warnings.filterwarnings("ignore")
    sys.argv = [sys.argv[0]]
    protocol = os.fdopen(os.dup(1), "w", encoding="utf-8", newline="\n")
    os.dup2(2, 1)
    sys.stdout = sys.stderr

    def emit(obj: dict) -> None:
        protocol.write(json.dumps(obj) + "\n")
        protocol.flush()

    try:
        query = _load_pkasolver()
        import pkasolver

        version = str(getattr(pkasolver, "__version__", "") or "unknown")
    except Exception as exc:  # noqa: BLE001 - reported over the wire, then exit
        emit({"ready": False, "error": f"{type(exc).__name__}: {exc}"})
        return 1
    emit({"ready": True, "pkasolver_version": version})

    for raw in io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8"):
        raw = raw.strip()
        if not raw:
            continue
        try:
            request = json.loads(raw)
            request_id, smiles = request["request_id"], str(request["smiles"])
        except Exception as exc:  # noqa: BLE001 - a malformed request is an answer, not a crash
            emit({"request_id": None, "error": f"malformed request: {type(exc).__name__}: {exc}"})
            continue
        emit({**predict(query, smiles), "request_id": request_id})
    return 0


if __name__ == "__main__":
    sys.exit(serve() if sys.argv[1:2] == ["--serve"] else main(sys.argv))
