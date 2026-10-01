from __future__ import annotations

import pytest

from rdkit import Chem

from conftest import synthetic_nmr_spectrum
from openchem.chem.nmr_signals import (
    NMRSignal,
    align_mol_to_spectrum,
    are_diastereotopic,
    build_nmr_signals,
    depiction_atoms,
    lorentzian_envelope,
    RESIDUAL_SOLVENT_PEAKS,
    multiplet_lines,
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


def test_coupling_to_a_different_element_is_excluded_even_though_orca_reports_it():
    """BUG, confirmed live on a real isopropanol "NMR + Spin-Spin Coupling"
    run: ORCA's full matrix reports a coupling constant between every pair
    of magnetically active nuclei it's asked for, including the one-bond
    H-C coupling under a methyl group's own carbon (measured ~180-196 Hz
    on that run) -- a real number, but not what a 1H multiplet's splitting
    pattern is about, and nothing this module's `_multiplicity_for` ever
    counts as a partner. Before the fix, the 6H methyl doublet's
    `coupling_hz` mixed those ~180 Hz values in alongside the real H-H
    one, which is what "doesn't show individual J coupling patterns...
    everything seems to be as if it's a singlet pattern" traced back to:
    a stick plot spacing lines by whichever value sorted first could put
    the pair at a spacing ten times too wide to read as the real
    multiplet."""
    mol = Chem.AddHs(Chem.MolFromSmiles("CCO"))
    methyl = [a.GetIdx() for a in mol.GetAtoms() if a.GetAtomicNum() == 1][:3]
    methylene = [a.GetIdx() for a in mol.GetAtoms() if a.GetAtomicNum() == 1][3:5]
    methyl_carbon = 0  # "CCO": C0-C1-O2, AddHs appends H's in that order
    spectrum = NMRSpectrumResult(
        spectrum_type="nmr_coupling",
        name="NMR",
        units="ppm",
        method="orca",
        molecule_uuid="mol-1",
        values={index: 1.2 for index in methyl} | {index: 3.6 for index in methylene},
        elements={index: "H" for index in methyl + methylene},
        couplings={
            (methyl[0], methylene[0]): 7.05,  # the real, vicinal H-H coupling
            (methyl[0], methyl_carbon): 185.3,  # one-bond C-H -- not a 1H partner
        },
    )

    signals = build_nmr_signals(mol, spectrum, "H")
    methyl_signal = next(s for s in signals if s.integration == 3)

    assert methyl_signal.coupling_hz == [7.05]


def test_coupling_to_an_atom_outside_the_real_partner_walk_is_excluded():
    """A coupling value ORCA reports for a pair that are real atoms, real
    neighbours of each other in the graph sense, but outside the geminal/
    vicinal walk `_coupling_partners` actually does (parent heavy atom
    plus ITS heavy neighbours only) -- ethanol's OH proton is 4 bonds from
    a methyl proton (H-C-C-O-H), which `_multiplicity_for` never counted
    as a splitting partner, so a J value between them must not appear in
    the methyl signal's `coupling_hz` either, however ORCA's own matrix
    reports it."""
    mol = Chem.AddHs(Chem.MolFromSmiles("CCO"))
    hydrogens = [a.GetIdx() for a in mol.GetAtoms() if a.GetAtomicNum() == 1]
    methyl = hydrogens[:3]
    methylene = hydrogens[3:5]
    oh_hydrogen = next(n.GetIdx() for n in mol.GetAtomWithIdx(2).GetNeighbors() if n.GetAtomicNum() == 1)
    spectrum = NMRSpectrumResult(
        spectrum_type="nmr_coupling",
        name="NMR",
        units="ppm",
        method="orca",
        molecule_uuid="mol-1",
        values={index: 1.2 for index in methyl} | {index: 3.6 for index in methylene} | {oh_hydrogen: 2.5},
        elements={index: "H" for index in methyl + methylene + [oh_hydrogen]},
        couplings={
            (methyl[0], methylene[0]): 7.05,
            (methyl[0], oh_hydrogen): 0.3,  # real pair, not a real partner
        },
    )

    signals = build_nmr_signals(mol, spectrum, "H")
    methyl_signal = next(s for s in signals if s.integration == 3)

    assert methyl_signal.coupling_hz == [7.05]


def test_a_coupling_to_a_non_partner_is_excluded_even_when_the_signal_has_real_partners():
    """The structural prediction and the real-J extraction must describe
    the SAME partner set. Ethanol's OH proton genuinely has real
    geminal/vicinal partners (`_coupling_partners` walks real connectivity
    regardless of which atoms this spectrum has values for: O's heavy
    neighbour C1 bears the methylene protons, 3 bonds from OH, so OH is a
    real triplet here) -- but the one coupling value THIS spectrum
    reports for it is to the METHYL protons instead, which are not among
    those real partners (4 bonds away, H-C-C-O-H), and must not appear in
    `coupling_hz` just because it is a present key in `couplings`."""
    mol = Chem.AddHs(Chem.MolFromSmiles("CCO"))
    hydrogens = [a.GetIdx() for a in mol.GetAtoms() if a.GetAtomicNum() == 1]
    methyl = hydrogens[:3]
    oh_hydrogen = next(n.GetIdx() for n in mol.GetAtomWithIdx(2).GetNeighbors() if n.GetAtomicNum() == 1)
    spectrum = NMRSpectrumResult(
        spectrum_type="nmr_coupling",
        name="NMR",
        units="ppm",
        method="orca",
        molecule_uuid="mol-1",
        values={index: 1.2 for index in methyl} | {oh_hydrogen: 2.5},
        elements={index: "H" for index in methyl + [oh_hydrogen]},
        couplings={(methyl[0], oh_hydrogen): 0.3},
    )

    signals = build_nmr_signals(mol, spectrum, "H")
    oh_signal = next(s for s in signals if s.integration == 1)

    assert oh_signal.multiplicity == "t"  # real connectivity: 2 methylene partners
    assert oh_signal.coupling_hz == []  # but no real J was ever reported for THAT pair


def test_13c_never_reports_coupling_even_when_orca_s_matrix_has_it():
    """13C here is always broadband proton-decoupled (every line a
    singlet, stated explicitly in `build_nmr_signals`) -- a one-bond C-H
    coupling genuinely in ORCA's matrix must not leak into a carbon
    signal's `coupling_hz` just because the pair exists."""
    mol = Chem.AddHs(Chem.MolFromSmiles("CCO"))
    carbon = 0
    methyl_h = [a.GetIdx() for a in mol.GetAtoms() if a.GetAtomicNum() == 1][0]
    spectrum = NMRSpectrumResult(
        spectrum_type="nmr_coupling",
        name="NMR",
        units="ppm",
        method="orca",
        molecule_uuid="mol-1",
        values={carbon: 18.0, methyl_h: 1.2},
        elements={carbon: "C", methyl_h: "H"},
        couplings={(carbon, methyl_h): 125.0},
    )

    carbons = build_nmr_signals(mol, spectrum, "C")
    assert carbons[0].coupling_hz == []


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


# --- Multiplet line splitting --------------------------------------------


def test_a_quartet_splits_into_four_lines_at_the_right_spacing():
    """J/frequency is the entire conversion: 7 Hz at 400 MHz is 0.0175
    ppm between adjacent lines, and the multiplet stays centred on the
    signal's own shift."""
    signal = NMRSignal(
        shift=3.70, atom_indices=[0, 1], integration=2, multiplicity="q", coupling_hz=[7.0]
    )

    lines = multiplet_lines(signal, 400.0)

    assert len(lines) == 4
    shifts = [shift for shift, _intensity in lines]
    assert shifts[0] - shifts[1] == pytest.approx(7.0 / 400.0)
    assert sum(shifts) / len(shifts) == pytest.approx(3.70)


def test_multiplet_intensities_are_the_binomial_row_and_sum_to_one():
    """1:3:3:1 for a quartet. Normalised so a quartet and a singlet with
    the same integration enclose the same area -- which is what
    integration means."""
    signal = NMRSignal(
        shift=1.0, atom_indices=[0], integration=1, multiplicity="q", coupling_hz=[7.0]
    )

    intensities = [intensity for _shift, intensity in multiplet_lines(signal, 400.0)]

    assert sum(intensities) == pytest.approx(1.0)
    assert intensities == pytest.approx([1 / 8, 3 / 8, 3 / 8, 1 / 8])


def test_a_higher_field_squeezes_the_multiplet_in_ppm():
    """The reason frequency is an option at all: the same coupling looks
    resolved at 600 MHz and collapsed at 60."""
    signal = NMRSignal(
        shift=2.0, atom_indices=[0], integration=1, multiplicity="d", coupling_hz=[7.0]
    )

    def span(frequency):
        shifts = [shift for shift, _i in multiplet_lines(signal, frequency)]
        return max(shifts) - min(shifts)

    assert span(600.0) < span(60.0)
    assert span(60.0) == pytest.approx(10 * span(600.0))


def test_carbon_multiplets_spread_further_than_proton_ones_at_the_same_field():
    """A "400 MHz" spectrometer observes carbon near 100 MHz, so the same
    J in Hz is about four times wider in ppm."""
    common = {"atom_indices": [0], "integration": 1, "multiplicity": "d", "coupling_hz": [7.0]}
    proton = NMRSignal(shift=2.0, element="H", **common)
    carbon = NMRSignal(shift=20.0, element="C", **common)

    def span(signal):
        shifts = [shift for shift, _i in multiplet_lines(signal, 400.0)]
        return max(shifts) - min(shifts)

    assert span(carbon) > 3 * span(proton)


@pytest.mark.parametrize(
    "multiplicity,coupling",
    [("s", []), ("m", [7.0]), ("d", [])],
)
def test_no_splitting_is_drawn_without_both_a_pattern_and_a_real_coupling(multiplicity, coupling):
    """A singlet has nothing to split; "m" means the pattern is not
    first-order; and a doublet with no measured J has no spacing to draw.
    None of the three may invent one."""
    signal = NMRSignal(
        shift=2.0,
        atom_indices=[0],
        integration=1,
        multiplicity=multiplicity,
        coupling_hz=list(coupling),
    )

    assert multiplet_lines(signal, 400.0) == [(2.0, 1.0)]


def test_residual_solvent_peaks_match_the_published_reference():
    """Gottlieb, Kotlyar & Nudelman (1997) -- measured literature values,
    the only exact numbers on this whole screen."""
    assert RESIDUAL_SOLVENT_PEAKS["CDCl3"] == {"H": 7.26, "C": 77.16}
    assert RESIDUAL_SOLVENT_PEAKS["DMSO-d6"]["H"] == 2.50
    # D2O has no carbon to observe, so it has no 13C entry rather than a
    # placeholder one.
    assert "C" not in RESIDUAL_SOLVENT_PEAKS["D2O"]


def _trapezoid_area(xs: list[float], ys: list[float]) -> float:
    return sum(
        (ys[i] + ys[i - 1]) / 2.0 * abs(xs[i] - xs[i - 1]) for i in range(1, len(xs))
    )


def test_lorentzian_envelope_area_is_proportional_to_integration():
    """Smooth-mode's whole point is that it still means what the sticks
    mean: relative peak AREA equalling relative integration. Two isolated
    singlets, integration 1 and 3 -- each sampled on its own wide, fine grid
    so the other's tails cannot leak in -- must integrate in that same 1:3
    ratio, not just look taller."""
    small = NMRSignal(shift=1.0, atom_indices=[0], integration=1, multiplicity="s")
    large = NMRSignal(shift=9.0, atom_indices=[1, 2, 3], integration=3, multiplicity="s")

    xs = [1.0 + 0.001 * i for i in range(-4000, 4001)]
    small_area = _trapezoid_area(xs, lorentzian_envelope([small], xs))

    xs = [9.0 + 0.001 * i for i in range(-4000, 4001)]
    large_area = _trapezoid_area(xs, lorentzian_envelope([large], xs))

    assert small_area == pytest.approx(1.0, rel=0.02)
    assert large_area == pytest.approx(3.0, rel=0.02)


def test_lorentzian_envelope_splits_a_multiplets_area_across_its_lines():
    """A doublet's two lines must still enclose the signal's WHOLE
    integration between them, not double it or halve it -- the same
    invariant `multiplet_lines`'s own intensities-sum-to-one test protects,
    carried through the convolution."""
    signal = NMRSignal(
        shift=5.0, atom_indices=[0], integration=2, multiplicity="d", coupling_hz=[7.0]
    )
    xs = [5.0 + 0.001 * i for i in range(-8000, 8001)]
    area = _trapezoid_area(xs, lorentzian_envelope([signal], xs, frequency_mhz=400.0))
    assert area == pytest.approx(2.0, rel=0.02)
