from __future__ import annotations

from rdkit import Chem

from conftest import synthetic_nmr_spectrum
from openchem.chem.nmr_signals import (
    NMRSignal,
    align_mol_to_spectrum,
    are_diastereotopic,
    build_nmr_signals,
    depiction_atoms,
)
from openchem.domain.scientific_result import NMRSpectrumResult

# The reference case throughout: MarvinSketch's own 1H output for this exact
# molecule is in hand (0.86 6H d, 1.44 3H d, 1.83 1H m, 2.31 1H sx, 2.58 1H
# sx, 3.69 1H m, 7.11 2H sx, 7.21 2H q, 10.61 1H s), so the grouping and
# integration columns can be checked against a real commercial predictor
# rather than against our own output.
IBUPROFEN = "CC(C)Cc1ccc(cc1)C(C)C(=O)O"
ETHYLBENZENE = "CCc1ccccc1"
STYRENE = "C=Cc1ccccc1"


def _mol_and_spectrum(smiles: str):
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    return mol, synthetic_nmr_spectrum(mol, "mol-1")


def _proton_signals(smiles: str) -> list[NMRSignal]:
    mol, spectrum = _mol_and_spectrum(smiles)
    return build_nmr_signals(mol, spectrum, "H")


def _ch2_protons(mol: Chem.Mol, carbon_index: int) -> tuple[int, int]:
    hydrogens = [n.GetIdx() for n in mol.GetAtomWithIdx(carbon_index).GetNeighbors() if n.GetAtomicNum() == 1]
    assert len(hydrogens) == 2
    return hydrogens[0], hydrogens[1]


def _benzylic_carbon(mol: Chem.Mol) -> int:
    """Ibuprofen's ArCH2CH(CH3)2 carbon -- the sp3 CH2 with an aromatic
    neighbour."""
    matches = mol.GetSubstructMatches(Chem.MolFromSmarts("[CX4H2](c)C"))
    assert matches, "expected exactly the benzylic CH2"
    return matches[0][0]


def test_ibuprofen_groups_into_marvins_nine_signals():
    signals = _proton_signals(IBUPROFEN)
    assert len(signals) == 9


def test_ibuprofen_integrations_match_marvins():
    """Marvin reports 6H, 3H, 2H, 2H and five 1H signals for ibuprofen.
    Equivalence grouping alone gets 8 of those; the ninth (the second 1H)
    only appears once the diastereotopic benzylic CH2 is split."""
    signals = _proton_signals(IBUPROFEN)
    assert sorted(s.integration for s in signals) == [1, 1, 1, 1, 1, 2, 2, 3, 6]


def test_ibuprofen_isopropyl_methyls_stay_one_six_proton_signal():
    """Both isopropyl methyls are one 6H doublet (Marvin's 0.86) -- they are
    diastereotopic as groups, but Marvin does not split them and neither
    does this, since the split is only ever applied to geminal protons on
    one carbon."""
    signals = _proton_signals(IBUPROFEN)
    six_proton = [s for s in signals if s.integration == 6]
    assert len(six_proton) == 1
    assert six_proton[0].multiplicity == "d"


def test_ibuprofen_carboxylic_proton_is_a_singlet():
    signals = _proton_signals(IBUPROFEN)
    most_deshielded = signals[0]  # sorted descending by shift
    assert most_deshielded.integration == 1
    assert most_deshielded.multiplicity == "s"


def test_signals_are_ordered_by_descending_shift():
    signals = _proton_signals(IBUPROFEN)
    assert [s.shift for s in signals] == sorted((s.shift for s in signals), reverse=True)


def test_every_signal_carries_its_atoms():
    """`atom_indices` is what drives click-to-highlight, so a signal without
    it would silently render an inert peak."""
    for signal in _proton_signals(IBUPROFEN):
        assert signal.atom_indices
        assert signal.integration == len(signal.atom_indices)


# --- diastereotopic splitting: both gates must pass ---


def test_ibuprofen_benzylic_ch2_is_diastereotopic():
    """The positive gate. The adjacent stereocentre makes these two protons
    inequivalent -- Marvin reports them separately at 2.31 and 2.58."""
    mol = Chem.AddHs(Chem.MolFromSmiles(IBUPROFEN))
    h_a, h_b = _ch2_protons(mol, _benzylic_carbon(mol))
    assert are_diastereotopic(mol, h_a, h_b)


def test_ethylbenzene_ch2_is_not_diastereotopic():
    """The negative gate, and the one a naive substitution test fails:
    substituting either proton DOES make that carbon stereogenic, but with
    no other stereo element the two products are enantiomers, so the protons
    are equivalent in an achiral solvent."""
    mol = Chem.AddHs(Chem.MolFromSmiles(ETHYLBENZENE))
    matches = mol.GetSubstructMatches(Chem.MolFromSmarts("[CX4H2](c)C"))
    h_a, h_b = _ch2_protons(mol, matches[0][0])
    assert not are_diastereotopic(mol, h_a, h_b)


def test_ibuprofen_benzylic_protons_become_two_one_proton_signals():
    mol, spectrum = _mol_and_spectrum(IBUPROFEN)
    benzylic = set(_ch2_protons(mol, _benzylic_carbon(mol)))
    owning = [s for s in build_nmr_signals(mol, spectrum, "H") if set(s.atom_indices) & benzylic]

    assert len(owning) == 2
    assert all(s.integration == 1 for s in owning)


def test_ethylbenzene_ch2_stays_one_two_proton_signal():
    mol, spectrum = _mol_and_spectrum(ETHYLBENZENE)
    matches = mol.GetSubstructMatches(Chem.MolFromSmarts("[CX4H2](c)C"))
    ch2 = set(_ch2_protons(mol, matches[0][0]))
    owning = [s for s in build_nmr_signals(mol, spectrum, "H") if set(s.atom_indices) & ch2]

    assert len(owning) == 1
    assert owning[0].integration == 2


def test_styrene_vinyl_protons_are_diastereotopic():
    """A stereogenic double bond needs no second stereo element: E and Z
    substitution products are diastereomers by definition, which is why the
    "is there another stereocentre?" rule alone would get this wrong."""
    mol = Chem.AddHs(Chem.MolFromSmiles(STYRENE))
    terminal = mol.GetSubstructMatches(Chem.MolFromSmarts("[CX3H2]=[CX3]"))[0][0]
    h_a, h_b = _ch2_protons(mol, terminal)
    assert are_diastereotopic(mol, h_a, h_b)


def test_methyl_protons_are_never_split():
    """A freely rotating methyl is homotopic -- three protons, one signal,
    regardless of what stereocentres the rest of the molecule has."""
    mol, spectrum = _mol_and_spectrum(IBUPROFEN)
    signals = build_nmr_signals(mol, spectrum, "H")
    assert any(s.integration == 3 for s in signals)
    assert not any(s.integration in (4, 5) for s in signals)


# --- multiplicity ---


def test_ethylbenzene_ethyl_group_is_a_classic_triplet_quartet():
    """The textbook first-order case: CH3 sees two protons (t), CH2 sees
    three (q)."""
    mol, spectrum = _mol_and_spectrum(ETHYLBENZENE)
    signals = build_nmr_signals(mol, spectrum, "H")
    by_integration = {s.integration: s for s in signals if s.integration in (2, 3)}
    assert by_integration[3].multiplicity == "t"
    assert by_integration[2].multiplicity == "q"


def test_para_substituted_ring_protons_are_doublets_not_triplets():
    """Regression guard for the pooling bug: each of the two equivalent
    aromatic protons couples to ONE ortho neighbour. Counting the partners
    of every proton in the group instead of one representative would report
    a triplet."""
    mol, spectrum = _mol_and_spectrum(IBUPROFEN)
    aromatic = [s for s in build_nmr_signals(mol, spectrum, "H") if s.integration == 2]
    assert len(aromatic) == 2
    assert {s.multiplicity for s in aromatic} == {"d"}


def test_coupling_to_two_distinct_groups_is_reported_as_a_multiplet():
    """Ibuprofen's isopropyl CH couples to the methyls and to the benzylic
    CH2 with different J values -- a single letter would assert a line
    pattern the molecule doesn't have."""
    mol, spectrum = _mol_and_spectrum(IBUPROFEN)
    isopropyl_ch = mol.GetSubstructMatches(Chem.MolFromSmarts("[CX4H1]([CH3])([CH3])"))[0][0]
    hydrogen = [n.GetIdx() for n in mol.GetAtomWithIdx(isopropyl_ch).GetNeighbors() if n.GetAtomicNum() == 1][0]
    owning = [s for s in build_nmr_signals(mol, spectrum, "H") if hydrogen in s.atom_indices]
    assert owning[0].multiplicity == "m"


def test_carbon_signals_are_singlets_and_not_split():
    """Routine 13C is broadband proton-decoupled; diastereotopic splitting
    is a proton concept and must not run for carbon."""
    mol, spectrum = _mol_and_spectrum(IBUPROFEN)
    carbons = build_nmr_signals(mol, spectrum, "C")
    assert carbons
    assert {s.multiplicity for s in carbons} == {"s"}
    assert all(s.element == "C" for s in carbons)


# --- coupling constants ---


def test_no_coupling_data_means_an_empty_coupling_list():
    """The empirical estimator supplies no J values, and none are invented
    from typical-value tables."""
    assert all(not s.coupling_hz for s in _proton_signals(IBUPROFEN))


def test_real_coupling_values_are_attached_to_their_signals():
    mol = Chem.AddHs(Chem.MolFromSmiles("CCO"))
    methyl = [a.GetIdx() for a in mol.GetAtoms() if a.GetAtomicNum() == 1][:3]
    methylene = [a.GetIdx() for a in mol.GetAtoms() if a.GetAtomicNum() == 1][3:5]
    spectrum = NMRSpectrumResult(
        spectrum_type="nmr_coupling",
        name="NMR",
        units="ppm",
        method="orca",
        molecule_uuid="mol-1",
        values={index: 1.2 for index in methyl} | {index: 3.6 for index in methylene},
        elements={index: "H" for index in methyl + methylene},
        couplings={(methyl[0], methylene[0]): 7.05},
    )

    signals = build_nmr_signals(mol, spectrum, "H")
    assert [s.coupling_hz for s in signals if s.integration == 3] == [[7.05]]


def test_a_coupling_inside_one_signal_is_not_reported():
    """Two protons in the same signal don't split each other -- a J between
    them describes an unobservable coupling, not a line the peak shows."""
    mol = Chem.AddHs(Chem.MolFromSmiles("CCO"))
    methyl = [a.GetIdx() for a in mol.GetAtoms() if a.GetAtomicNum() == 1][:3]
    spectrum = NMRSpectrumResult(
        spectrum_type="nmr_coupling",
        name="NMR",
        units="ppm",
        method="orca",
        molecule_uuid="mol-1",
        values={index: 1.2 for index in methyl},
        elements={index: "H" for index in methyl},
        couplings={(methyl[0], methyl[1]): 12.0},
    )

    assert build_nmr_signals(mol, spectrum, "H")[0].coupling_hz == []


# --- index alignment and depiction mapping ---


def test_align_adds_hydrogens_when_the_spectrum_indexes_them():
    implicit = Chem.MolFromSmiles(IBUPROFEN)
    _explicit, spectrum = _mol_and_spectrum(IBUPROFEN)
    aligned = align_mol_to_spectrum(implicit, spectrum)

    assert aligned.GetNumAtoms() > implicit.GetNumAtoms()
    assert max(spectrum.values) < aligned.GetNumAtoms()


def test_align_leaves_an_already_explicit_mol_alone():
    explicit, spectrum = _mol_and_spectrum(IBUPROFEN)
    assert align_mol_to_spectrum(explicit, spectrum).GetNumAtoms() == explicit.GetNumAtoms()


def test_depiction_maps_protons_onto_their_heavy_parent():
    """The 2D depiction is drawn from the editor molblock, whose hydrogens
    are implicit and have no index -- a proton's shift has to be drawn on
    the atom bearing it."""
    mol, spectrum = _mol_and_spectrum(IBUPROFEN)
    signals = build_nmr_signals(mol, spectrum, "H")
    six_proton = next(s for s in signals if s.integration == 6)

    atoms = depiction_atoms(mol, six_proton)

    assert len(atoms) == 2  # two methyl carbons, not six hydrogens
    assert all(mol.GetAtomWithIdx(index).GetAtomicNum() == 6 for index in atoms)


def test_empty_spectrum_produces_no_signals():
    mol = Chem.AddHs(Chem.MolFromSmiles("C"))
    spectrum = NMRSpectrumResult(
        spectrum_type="nmr_empirical",
        name="NMR",
        units="ppm",
        method="smarts_lookup",
        molecule_uuid="mol-1",
    )
    assert build_nmr_signals(mol, spectrum, "H") == []
