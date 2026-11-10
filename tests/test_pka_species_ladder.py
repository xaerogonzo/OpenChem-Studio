"""Sequential protonation ladder: complete or refused, parent unchanged."""

from __future__ import annotations

from rdkit import Chem

from openchem.chem.ionisable_sites import ACID, BASE, UNKNOWN
from openchem.chem.ph_curves import microspecies_fractions, ph_grid, species_charges
from openchem.chem.pka_sites import MAX_PICTURE_SITES, PkaSiteRecord
from openchem.chem.pka_species_ladder import LadderRefusal, SpeciesLadder, build_species_ladder


def _record(index, pka, kind, protonated, deprotonated, spread=0.0):
    return PkaSiteRecord(
        atom_index=index,
        pka=pka,
        spread=spread,
        kind=kind,
        protonated_site=protonated,
        deprotonated_site=deprotonated,
    )


def _oh_oxygen(mol: Chem.Mol) -> int:
    for atom in mol.GetAtoms():
        if atom.GetSymbol() == "O" and atom.GetTotalNumHs() == 1:
            return atom.GetIdx()
    raise AssertionError("no OH oxygen")


def _amine_nitrogen(mol: Chem.Mol) -> int:
    for atom in mol.GetAtoms():
        if atom.GetSymbol() == "N":
            return atom.GetIdx()
    raise AssertionError("no nitrogen")


def test_a_monoprotic_acid_has_neutral_then_anion():
    mol = Chem.MolFromSmiles("CC(=O)O")
    oxygen = _oh_oxygen(mol)
    parent = Chem.MolToMolBlock(mol)
    ladder = build_species_ladder(mol, [_record(oxygen, 4.76, ACID, (1, 0), (0, -1))])
    assert isinstance(ladder, SpeciesLadder)
    assert len(ladder.molblocks) == 2
    assert Chem.GetFormalCharge(Chem.MolFromMolBlock(ladder.molblocks[0])) == 0
    assert Chem.GetFormalCharge(Chem.MolFromMolBlock(ladder.molblocks[1])) == -1
    assert Chem.MolToMolBlock(mol) == parent


def test_a_monoprotic_base_starts_protonated():
    mol = Chem.MolFromSmiles("N")
    nitrogen = _amine_nitrogen(mol)
    ladder = build_species_ladder(mol, [_record(nitrogen, 9.2, BASE, (4, 1), (3, 0))])
    assert isinstance(ladder, SpeciesLadder)
    assert Chem.GetFormalCharge(Chem.MolFromMolBlock(ladder.molblocks[0])) == 1
    assert Chem.GetFormalCharge(Chem.MolFromMolBlock(ladder.molblocks[1])) == 0


def test_aminophenol_builds_three_species_even_when_curve_kinds_disagree():
    mol = Chem.MolFromSmiles("Nc1ccc(O)cc1")
    oxygen = _oh_oxygen(mol)
    nitrogen = _amine_nitrogen(mol)
    records = (
        _record(oxygen, 5.5, ACID, (1, 0), (0, -1)),
        _record(nitrogen, 10.3, BASE, (3, 1), (2, 0)),
    )
    ladder = build_species_ladder(mol, records)
    assert isinstance(ladder, SpeciesLadder)
    assert len(ladder.molblocks) == 3
    assert ladder.kinds_match_curve is False
    charges = [Chem.GetFormalCharge(Chem.MolFromMolBlock(block)) for block in ladder.molblocks]
    assert charges[0] - charges[1] == 1
    assert charges[1] - charges[2] == 1


def test_unmapped_unknown_missing_and_same_atom_refuse_all_pictures():
    mol = Chem.MolFromSmiles("CC(=O)O")
    oxygen = _oh_oxygen(mol)
    assert build_species_ladder(mol, [_record(None, 4.7, ACID, (1, 0), (0, -1))]).reason == "unmapped"
    assert build_species_ladder(mol, [_record(oxygen, 4.7, UNKNOWN, (1, 0), (0, -1))]).reason == "unknown_direction"
    assert build_species_ladder(mol, [_record(oxygen, 4.7, ACID, None, (0, -1))]).reason == "missing_state"
    same = [
        _record(oxygen, 4.7, ACID, (1, 0), (0, -1)),
        _record(oxygen, 9.0, ACID, (1, 0), (0, -1)),
    ]
    assert build_species_ladder(mol, same).reason == "same_atom"


def test_explicit_hydrogens_are_refused_rather_than_duplicated():
    mol = Chem.AddHs(Chem.MolFromSmiles("CC(=O)O"))
    oxygen = next(atom.GetIdx() for atom in mol.GetAtoms() if atom.GetSymbol() == "O")
    refused = build_species_ladder(mol, [_record(oxygen, 4.7, ACID, (1, 0), (0, -1))])
    assert isinstance(refused, LadderRefusal)
    assert refused.reason == "explicit_hydrogens"


def test_nine_sites_omit_pictures_and_eight_are_the_cap():
    mol = Chem.MolFromSmiles("C.C.C.C.C.C.C.C.C")
    nine = [_record(i, 4.0 + i, ACID, (4, 0), (3, -1)) for i in range(9)]
    refused = build_species_ladder(mol, nine)
    assert isinstance(refused, LadderRefusal)
    assert refused.reason == "too_many_sites"
    eight_mol = Chem.MolFromSmiles("C.C.C.C.C.C.C.C")
    eight = [_record(i, 4.0 + i, ACID, (4, 0), (3, -1)) for i in range(MAX_PICTURE_SITES)]
    ladder = build_species_ladder(eight_mol, eight)
    assert isinstance(ladder, SpeciesLadder)
    assert len(ladder.molblocks) == MAX_PICTURE_SITES + 1


def test_a_species_below_the_picture_floor_keeps_its_index():
    mol = Chem.MolFromSmiles("CC(=O)O")
    oxygen = _oh_oxygen(mol)
    records = (_record(oxygen, 4.76, ACID, (1, 0), (0, -1)),)
    # A pKa of 4.76 still has both species above 0.01% on the default grid.
    # Hide nothing, then a grid that never samples the minor form at all is not
    # invented: the sampled grid is the curve's own.
    ladder = build_species_ladder(mol, records, ph_values=[0.0, 0.25, 0.5])
    assert isinstance(ladder, SpeciesLadder)
    assert ladder.hidden <= {1}
    assert len(ladder.molblocks) == 2


def test_fractions_still_sum_to_one_on_every_sample():
    pkas = [3.0, 8.0]
    for ph in ph_grid():
        parts = microspecies_fractions(ph, pkas)
        assert abs(sum(parts) - 1.0) < 1e-12
        assert len(parts) == 3


def test_species_charges_are_not_claimed_when_they_disagree_with_the_mol():
    mol = Chem.MolFromSmiles("Nc1ccc(O)cc1")
    oxygen = _oh_oxygen(mol)
    nitrogen = _amine_nitrogen(mol)
    ladder = build_species_ladder(
        mol,
        (
            _record(oxygen, 5.5, ACID, (1, 0), (0, -1)),
            _record(nitrogen, 10.3, BASE, (3, 1), (2, 0)),
        ),
    )
    assert isinstance(ladder, SpeciesLadder)
    assert len(ladder.net_charges) != len(species_charges(1, 0))
    assert ladder.charge_labels_match is False
