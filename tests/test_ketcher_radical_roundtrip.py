"""Probe: what does the embedded Ketcher write for an unpaired electron, and does the multiplicity chain (OS1 to OS3) survive it?

Every earlier open-shell test fed the application a molfile RDKit had written. This one asks the real editor (the vendored bundle, Indigo's writer). Measured 2026-11-24:

* Ketcher keeps the three radical codes of the molfile (1 singlet, 2 doublet, 3 triplet) through `setMolecule` and `getMolfile`, whether the structure came in as a molfile or as KET
  (its `radical` atom property: 1, 2, 3), so a singlet carbene drawn in the editor reaches the application as a singlet.
* Ketcher's SMILES reader maps `[CH2]` to the SINGLET code (1) and `[CH3]`, `[OH]`, `[N]=O` and the nitroxide to 2, `[O][O]` to 2 on each atom, where RDKit's `[CH2]` is a
  triplet by default. The application never hands Ketcher a SMILES (every structure goes in as a molblock), so this is recorded, not acted on.
* **A lone atom loses the code on the way in**: RDKit writes no `M  RAD` line for an O or H atom with no bond (it carries the radical in the atom line's valence field), so a
  singlet code on a lone atom was dropped from the stored molblock and the multiplicity fell back to the triplet default. `molblock_keeping_spin` now puts it back.

The assertions hold these measurements, so a Ketcher upgrade cannot change them silently.
"""

from __future__ import annotations

import json

import pytest
from rdkit import RDLogger

from openchem.chem.engine import ChemistryEngine
from openchem.chem.open_shell import rad_codes
from openchem.domain.molecule import MoleculeModel
from tests.test_ketcher_editor_backend import _get_molblock_sync, _ready_backend, _run_js, _wait_until

RDLogger.DisableLog("rdApp.*")
ENGINE = ChemistryEngine()

LONE_C = "\n  t\n\n  1  0  0  0  0  0  0  0  0  0999 V2000\n    0.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\nM  RAD  1   1   {code}\nM  END\n"
LONE_O = LONE_C.replace(" C   ", " O   ")

FINDING_KET = {1: {0: 1}, 2: {0: 2}, 3: {0: 3}}
FINDING_MOLFILE = {1: {0: 1}, 2: {0: 2}, 3: {0: 3}}
FINDING_SMILES = {
    "[CH3]": {0: 2},
    "[CH2]": {0: 1},
    "[O][O]": {0: 2, 1: 2},
    "[N]=O": {0: 2},
    "[OH]": {0: 2},
    "[O]": {0: 1},
    "CC1(C)CCCC(C)(C)N1[O]": {10: 2},
}


def _ket(radical: int | None) -> str:
    atom: dict = {"label": "C", "location": [0, 0, 0]}
    if radical is not None:
        atom["radical"] = radical
    return json.dumps({"root": {"nodes": [{"$ref": "mol0"}]}, "mol0": {"type": "molecule", "atoms": [atom], "bonds": []}})


def _through_ketcher(qapp, backend, payload: str) -> str:
    _run_js(qapp, backend, "window.ketcher.setMolecule(%s); 1" % json.dumps(payload))
    _wait_until(qapp, lambda: False, timeout_seconds=1.0)
    return _get_molblock_sync(qapp, backend, timeout_seconds=10) or ""


def test_ketcher_keeps_the_three_radical_codes_of_its_own_atom_property(qapp):
    backend = _ready_backend(qapp)
    measured = {code: rad_codes(_through_ketcher(qapp, backend, _ket(code))) for code in (1, 2, 3)}
    assert measured == FINDING_KET, f"Ketcher's KET radical round-trip changed: {measured!r}"
    assert rad_codes(_through_ketcher(qapp, backend, _ket(None))) == {}


def test_ketcher_keeps_the_three_radical_codes_of_a_molfile(qapp):
    backend = _ready_backend(qapp)
    measured = {code: rad_codes(_through_ketcher(qapp, backend, LONE_C.format(code=code))) for code in (1, 2, 3)}
    assert measured == FINDING_MOLFILE, f"Ketcher's molfile radical round-trip changed: {measured!r}"


def test_ketchers_smiles_reader_marks_a_bare_methylene_as_singlet(qapp):
    """Recorded, not acted on: the application loads molblocks only, so this never reaches a calculation. RDKit reads the same SMILES as triplet."""
    backend = _ready_backend(qapp)
    measured = {smiles: rad_codes(_through_ketcher(qapp, backend, smiles)) for smiles in FINDING_SMILES}
    assert measured == FINDING_SMILES, f"Ketcher's SMILES radical mapping changed: {measured!r}"


@pytest.mark.parametrize("code, multiplicity", [(1, 1), (2, 2), (3, 3)])
def test_a_radical_drawn_in_ketcher_reaches_the_stored_structure_with_its_multiplicity(qapp, code, multiplicity):
    backend = _ready_backend(qapp)
    returned = _through_ketcher(qapp, backend, LONE_C.format(code=code))
    model = MoleculeModel(display_name="drawn")
    ENGINE.set_structure_from_molblock(model, returned)
    assert ENGINE.default_multiplicity(model) == multiplicity


def test_a_singlet_lone_atom_drawn_in_ketcher_is_not_turned_into_a_triplet(qapp):
    """The measured loss: RDKit writes no RAD line for a bare O atom, so the singlet code vanished and the default said 3."""
    backend = _ready_backend(qapp)
    singlet, triplet = MoleculeModel(display_name="s"), MoleculeModel(display_name="t")
    ENGINE.set_structure_from_molblock(singlet, _through_ketcher(qapp, backend, LONE_O.format(code=1)))
    ENGINE.set_structure_from_molblock(triplet, _through_ketcher(qapp, backend, LONE_O.format(code=3)))
    assert (ENGINE.default_multiplicity(singlet), ENGINE.default_multiplicity(triplet)) == (1, 3)
    assert singlet.canonical_smiles == triplet.canonical_smiles == "[O]"
