"""Offering a coordinate-bond drawing, never imposing one.

**Amavadin is the motivating case**: a vanadium held by nitrogen and
oxygen donors, which drawn with plain single bonds over-counts the metal's
valence. The three-layer rule says perception reports what is there, this
offers the alternative, and only the user changes the structure -- so what
these tests guard is as much the restraint as the conversion.
"""

from __future__ import annotations

import pytest
from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.chem.checkers.representation import _check_metal_donor_bonds
from openchem.chem.quick_fixes import build_default_fix_registry, metal_bonds_to_dative
from openchem.chem.structure_check import PARSED_MOLECULE, CheckContext

VANADIUM = "[V](O)(O)(O)N"
SODIUM_CHLORIDE = "[Na]Cl"
ASPIRIN = "CC(=O)Oc1ccccc1C(=O)O"


def _molblock(smiles: str) -> str:
    molecule = Chem.MolFromSmiles(smiles, sanitize=False)
    molecule.UpdatePropertyCache(strict=False)
    AllChem.Compute2DCoords(molecule)
    return Chem.MolToMolBlock(molecule, kekulize=False)


def _bond_types(molblock: str) -> list[str]:
    molecule = Chem.MolFromMolBlock(molblock, sanitize=False, removeHs=False)
    return sorted(str(bond.GetBondType()) for bond in molecule.GetBonds())


def _issues(smiles: str):
    molecule = Chem.MolFromSmiles(smiles, sanitize=False)
    molecule.UpdatePropertyCache(strict=False)
    return _check_metal_donor_bonds(
        CheckContext(mol=molecule, capabilities=frozenset({PARSED_MOLECULE}))
    )


# --- the conversion ---------------------------------------------------------


def test_every_metal_donor_bond_is_converted():
    """**Not merely some of them.** Collecting the edits before applying
    any is load-bearing: mutating while iterating `GetBonds()` invalidates
    the iteration, and this exact molecule came back from a first attempt
    as a DATIVE/SINGLE mix from four identical bonds -- a silent half
    conversion rather than an error."""
    converted = metal_bonds_to_dative(_molblock(VANADIUM))

    assert _bond_types(converted) == ["DATIVE"] * 4


def test_the_conversion_survives_a_molblock_round_trip():
    """The fix's whole contract is molblock in, molblock out, so a bond
    type that did not survive being written would make it a no-op that
    looked like it worked."""
    molecule = Chem.MolFromMolBlock(
        metal_bonds_to_dative(_molblock(VANADIUM)), sanitize=False, removeHs=False
    )

    assert all(str(bond.GetBondType()) == "DATIVE" for bond in molecule.GetBonds())


def test_no_atom_is_added_removed_or_recharged():
    """**Only bond types change.** Neutralising the formal charges a
    plain-bond drawing often carries would be a second, separate edit, and
    one fix doing two things is a fix nobody can predict."""
    before = Chem.MolFromMolBlock(_molblock(VANADIUM), sanitize=False, removeHs=False)
    after = Chem.MolFromMolBlock(
        metal_bonds_to_dative(_molblock(VANADIUM)), sanitize=False, removeHs=False
    )

    assert after.GetNumAtoms() == before.GetNumAtoms()
    assert after.GetNumBonds() == before.GetNumBonds()
    assert [a.GetFormalCharge() for a in after.GetAtoms()] == [
        a.GetFormalCharge() for a in before.GetAtoms()
    ]


def test_the_dative_bond_begins_at_the_donor():
    """That is how RDKit records which way the pair went, so the direction
    is the whole content of the change."""
    molecule = Chem.MolFromMolBlock(
        metal_bonds_to_dative(_molblock(VANADIUM)), sanitize=False, removeHs=False
    )

    for bond in molecule.GetBonds():
        assert bond.GetBeginAtom().GetSymbol() in {"O", "N"}
        assert bond.GetEndAtom().GetSymbol() == "V"


# --- what it must NOT touch -------------------------------------------------


def test_an_alkali_halide_is_left_alone():
    """**An alkali halide is ionic, not coordinate.** Offering to redraw
    Na-Cl as a coordinate bond would be wrong about the commonest salt
    there is, which is why the donor set excludes the halogens and the
    metal set stops at the transition series."""
    assert _bond_types(metal_bonds_to_dative(_molblock(SODIUM_CHLORIDE))) == ["SINGLE"]
    assert _issues(SODIUM_CHLORIDE) == []


def test_an_ordinary_organic_is_returned_unchanged():
    """Byte-identical, not merely equivalent: a fix with nothing to do
    must not rewrite the drawing."""
    original = _molblock(ASPIRIN)

    assert metal_bonds_to_dative(original) == original
    assert _issues(ASPIRIN) == []


@pytest.mark.parametrize("smiles", ["[Fe+2].[cH-]1cccc1.[cH-]1cccc1", "C[Li]"])
def test_structures_with_no_metal_donor_single_bond_are_untouched(smiles):
    original = _molblock(smiles)

    assert metal_bonds_to_dative(original) == original


# --- how it is offered ------------------------------------------------------


def test_the_fix_is_registered_so_a_button_can_appear():
    """An issue carries a `fix_id` string, and a `fix_id` naming nothing
    registered simply means no button."""
    fix = build_default_fix_registry().get("metal_bonds_to_dative")

    assert fix is not None
    assert fix.label == "Draw metal bonds as coordinate bonds"


def test_the_issue_names_the_fix_that_repairs_it():
    (issue,) = _issues(VANADIUM)

    assert issue.fix_id == "metal_bonds_to_dative"
    assert build_default_fix_registry().get(issue.fix_id) is not None


def test_the_issue_is_information_rather_than_a_warning():
    """**Both drawings appear in the literature and neither is an error.**
    Painting this red would be the app asserting a preference it has no
    grounds for."""
    from openchem.chem.structure_check import Severity

    (issue,) = _issues(VANADIUM)

    assert issue.severity is Severity.INFO


def test_the_issue_highlights_the_metal_and_its_donors():
    molecule = Chem.MolFromSmiles(VANADIUM, sanitize=False)
    (issue,) = _issues(VANADIUM)

    symbols = {molecule.GetAtomWithIdx(i).GetSymbol() for i in issue.atom_indices}
    assert symbols == {"V", "O", "N"}


def test_the_fix_is_reversible_not_lossy():
    """Nothing goes away: the connectivity is identical afterwards and
    only which atom supplied the electrons has changed. Declaring it LOSSY
    would warn about a cost that is not paid."""
    from openchem.chem.quick_fixes import FixSafety

    assert build_default_fix_registry().get("metal_bonds_to_dative").safety is (
        FixSafety.REVERSIBLE
    )
