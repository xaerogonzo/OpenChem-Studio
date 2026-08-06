"""The repairs the checker offers.

Pure -- no Qt. Every fix takes a molblock and returns a molblock, which is
what lets the caller push the result through `EditStructureCommand` instead
of the fix editing the project behind the undo stack's back.

The safety label is tested as hard as the transformation is. It is shown on
the button BEFORE the fix runs, and a "lossy" mislabelled "safe" is a
promise the app cannot keep.
"""

from __future__ import annotations

import pytest
from rdkit import Chem
from rdkit.Chem import AllChem
from rdkit.Geometry import Point3D

from openchem.chem.quick_fixes import (
    FixSafety,
    QuickFixRegistry,
    build_default_fix_registry,
    keep_largest_fragment,
    merge_coincident_atoms,
    recompute_layout,
    remove_explicit_hydrogens,
)


def molblock_for(smiles: str, *, add_hs: bool = False, mutate=None) -> str:
    mol = Chem.MolFromSmiles(smiles, sanitize=False)
    mol.UpdatePropertyCache(strict=False)
    if add_hs:
        mol = Chem.AddHs(mol)
    AllChem.Compute2DCoords(mol)
    if mutate is not None:
        mutate(mol.GetConformer())
    return Chem.MolToMolBlock(mol, kekulize=False)


def atom_count(molblock: str) -> int:
    return Chem.MolFromMolBlock(molblock, sanitize=False, removeHs=False).GetNumAtoms()


@pytest.fixture(scope="module")
def fixes() -> QuickFixRegistry:
    return build_default_fix_registry()


def test_keep_largest_fragment_drops_the_counter_ion():
    before = molblock_for("CC(=O)[O-].[Na+]")

    after = keep_largest_fragment(before)

    assert atom_count(before) == 5
    assert atom_count(after) == 4
    assert "Na" not in after


def test_keep_largest_fragment_leaves_a_single_fragment_untouched():
    """Returns the input unchanged rather than a re-serialised equivalent,
    so the caller's "did this change anything?" check is exact."""
    before = molblock_for("CCO")

    assert keep_largest_fragment(before) == before


def test_remove_explicit_hydrogens_folds_them_back_in():
    before = molblock_for("CCO", add_hs=True)

    after = remove_explicit_hydrogens(before)

    assert atom_count(before) == 9
    assert atom_count(after) == 3


def test_removing_hydrogens_keeps_the_ones_that_carry_information():
    """RDKit keeps isotopically labelled hydrogens, so this cannot silently
    turn a deuterated standard back into the unlabelled compound -- which
    is the difference between a SAFE fix and a lossy one mislabelled."""
    before = molblock_for("[2H]OC")

    after = remove_explicit_hydrogens(before)

    assert "2" in after.splitlines()[3] or atom_count(after) == atom_count(before)
    assert atom_count(after) == atom_count(before)


def test_recompute_layout_changes_coordinates_and_nothing_else():
    def stretch(conformer):
        position = conformer.GetAtomPosition(3)
        conformer.SetAtomPosition(3, Point3D(position.x + 9.0, position.y, position.z))

    before = molblock_for("CCCCCC", mutate=stretch)

    after = recompute_layout(before)

    original = Chem.MolFromMolBlock(before, sanitize=False)
    fixed = Chem.MolFromMolBlock(after, sanitize=False)
    assert fixed.GetNumAtoms() == original.GetNumAtoms()
    assert fixed.GetNumBonds() == original.GetNumBonds()
    assert Chem.MolToSmiles(fixed) == Chem.MolToSmiles(original)
    assert after != before  # the coordinates really did move


def test_merge_coincident_atoms_fuses_the_pair_and_keeps_its_bonds():
    """The classic result of clicking an existing atom while a template is
    armed: one atom drawn twice, with the second one's bonds hanging off
    it. The survivor has to inherit them or the fix breaks the molecule."""

    def stack(conformer):
        position = conformer.GetAtomPosition(0)
        conformer.SetAtomPosition(3, Point3D(position.x, position.y, position.z))

    before = molblock_for("CCCCCC", mutate=stack)

    after = merge_coincident_atoms(before)

    assert atom_count(after) == atom_count(before) - 1
    original = Chem.MolFromMolBlock(before, sanitize=False)
    fixed = Chem.MolFromMolBlock(after, sanitize=False)
    # The fragment count, not "every atom still has a bond". Mutation
    # testing found the weaker check useless: dropping the doomed atom's
    # bonds instead of re-pointing them splits a hexane into a 3-chain and
    # a 2-chain, and every atom in both still has a neighbour.
    assert len(Chem.GetMolFrags(fixed)) == len(Chem.GetMolFrags(original))
    # One atom fewer, but every bond kept: the survivor inherits the two
    # the doomed atom had, so hexane's five bonds stay five and the
    # survivor's degree goes 1 -> 3. Measured, not predicted.
    assert fixed.GetNumBonds() == original.GetNumBonds()
    assert max(atom.GetDegree() for atom in fixed.GetAtoms()) == 3


def test_merge_coincident_atoms_does_nothing_when_none_overlap():
    before = molblock_for("CCCCCC")

    assert merge_coincident_atoms(before) == before


@pytest.mark.parametrize(
    "fix_id, expected",
    [
        ("remove_explicit_hydrogens", FixSafety.SAFE),
        ("recompute_layout", FixSafety.REVERSIBLE),
        ("keep_largest_fragment", FixSafety.LOSSY),
        ("merge_coincident_atoms", FixSafety.LOSSY),
    ],
)
def test_each_fix_declares_what_it_costs(fixes, fix_id, expected):
    """Asserted per fix rather than "some fix is lossy", because the label
    is what the button shows before anything happens. Keeping the largest
    fragment of a salt changes the compound's identity, formula and mass;
    making hydrogens implicit changes nothing at all.
    """
    assert fixes.get(fix_id).safety is expected


def test_an_unregistered_fix_id_resolves_to_nothing_rather_than_raising(fixes):
    """An issue may name a fix only its own plugin provides. The button
    simply does not appear."""
    assert fixes.get("no_such_fix") is None
    assert fixes.get("") is None


def test_a_fix_refuses_a_molblock_it_cannot_read(fixes):
    with pytest.raises(ValueError):
        keep_largest_fragment("this is not a molfile")
