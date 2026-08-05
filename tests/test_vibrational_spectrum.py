"""IR spectra from ORCA frequency jobs.

The fixtures under `tests/fixtures/orca/` are REAL ORCA 6.1.1 transcripts,
trimmed to the vibrational section but otherwise verbatim -- produced by
running `! B3LYP def2-SVP Opt Freq` on water, and `! B3LYP def2-SVP Freq`
on a deliberately LINEAR water to get a saddle point. This project has
three recorded bugs that only a real backend run exposed, and the ORCA
output format is known to drift between versions, so a hand-written
fixture would be testing an assumption rather than the program.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.chem.orca_engine import OrcaQuantumEngineProvider
from openchem.chem.vibrational_modes import classify_mode

FIXTURES = Path(__file__).parent / "fixtures" / "orca"


def _water() -> Chem.Mol:
    mol = Chem.AddHs(Chem.MolFromSmiles("O"))
    AllChem.EmbedMolecule(mol, randomSeed=42)
    AllChem.MMFFOptimizeMolecule(mol)
    return mol


def _parse(fixture: str):
    text = (FIXTURES / fixture).read_text(encoding="utf-8")
    return OrcaQuantumEngineProvider().parse_vibrational_spectrum(
        text, _water(), "mol-1", "opt_freq"
    )


# --- The spectrum itself ------------------------------------------------


def test_water_gives_its_three_real_modes():
    """Textbook, and the reason water is the fixture: one bend and two
    stretches, no ambiguity about what the answer should be."""
    result = _parse("water_freq.out")
    assert result is not None
    assert len(result.modes) == 3
    wavenumbers = [round(m.wavenumber_cm1, 1) for m in result.modes]
    assert wavenumbers == [1637.7, 3787.2, 3882.1]


def test_ir_intensities_are_read_in_km_per_mol():
    result = _parse("water_freq.out")
    assert [m.ir_intensity_km_mol for m in result.modes] == [55.30, 4.67, 26.51]


def test_the_six_zero_modes_are_dropped():
    """ORCA lists translations and rotations as 0.00 cm-1. They are not
    vibrations and must not appear as peaks at the origin."""
    result = _parse("water_freq.out")
    assert all(m.wavenumber_cm1 > 0 for m in result.modes)


def test_orca_s_own_scaling_factor_is_recorded_not_reapplied():
    """ORCA prints "Scaling factor for frequencies = 1.000000000 (already
    applied!)". Carrying the number is what stops a later reader applying
    it a second time."""
    result = _parse("water_freq.out")
    assert result.scaling_factor == 1.0


def test_a_non_frequency_job_reports_nothing_rather_than_an_empty_spectrum():
    """"This job computed no modes" and "this molecule has no modes" are
    different statements."""
    provider = OrcaQuantumEngineProvider()
    text = (FIXTURES / "water_freq.out").read_text(encoding="utf-8")
    assert provider.parse_vibrational_spectrum(text, _water(), "m", "sp") is None
    assert provider.parse_vibrational_spectrum("", _water(), "m", "opt_freq") is None


def test_mode_data_does_not_leak_into_the_atom_indexed_fields():
    """`SpectrumResult.values`/`elements` are documented as keyed by ATOM
    INDEX. A vibrational peak belongs to a normal mode, not an atom, so
    putting modes there would type-check, render as nonsense in every
    per-atom view, and sum to a meaningless "Overall" in the inspector."""
    result = _parse("water_freq.out")
    assert result.values == {}
    assert result.elements == {}
    assert result.modes


# --- Imaginary frequencies: the silent-invalidation case -----------------


def test_imaginary_modes_are_reported_not_dropped():
    """THE FAILURE THIS GUARDS. ORCA's IR SPECTRUM table OMITS imaginary
    modes -- in this fixture two modes are imaginary and the IR table
    simply starts at mode 7, because ORCA counts them as non-vibrations.
    A parser built on the IR table alone would report a clean spectrum for
    a saddle point.

    Measured on a real `! Freq` run of LINEAR water, which is a saddle
    point by construction."""
    result = _parse("linear_freq.out")
    assert len(result.imaginary_modes) == 2
    assert all(m.wavenumber_cm1 < 0 for m in result.imaginary_modes)


def test_an_imaginary_mode_warns_that_the_thermochemistry_is_invalid():
    """A negative wavenumber means the geometry is a saddle point, which
    silently invalidates every thermochemistry number from the SAME job."""
    result = _parse("linear_freq.out")
    assert "saddle point" in result.imaginary_warning
    assert "thermochemistry" in result.imaginary_warning.lower()


def test_a_minimum_carries_no_warning():
    assert _parse("water_freq.out").imaginary_warning == ""


def test_the_zero_mode_count_is_not_assumed_to_be_six():
    """Nonlinear water has six zero modes (3N-6); LINEAR water has five
    (3N-5). Hardcoding six would mislabel a mode on every linear molecule.
    Linear water has 4 real+imaginary modes against nonlinear water's 3."""
    assert len(_parse("water_freq.out").modes) == 3
    assert len(_parse("linear_freq.out").modes) == 4


# --- Mode character -----------------------------------------------------


def test_water_modes_are_classified_as_one_bend_and_two_stretches():
    result = _parse("water_freq.out")
    assert [m.character for m in result.modes] == ["bend", "stretch", "stretch"]


def test_displacements_are_grouped_per_atom():
    result = _parse("water_freq.out")
    for mode in result.modes:
        assert len(mode.displacements) == 3          # three atoms
        assert all(len(vector) == 3 for vector in mode.displacements)


def test_classification_refuses_rather_than_guesses_without_geometry():
    """Bond axes are what displacements get projected onto. With no
    conformer the question cannot be asked, and silence beats a guess."""
    flat = Chem.AddHs(Chem.MolFromSmiles("O"))
    assert classify_mode(flat, ((0.0, 1.0, 0.0),) * 3, 1600.0) == ""


def test_classification_refuses_a_mismatched_displacement_count():
    assert classify_mode(_water(), ((0.0, 1.0, 0.0),), 1600.0) == ""


def test_classification_never_raises():
    assert classify_mode(None, (), None) == ""
    assert classify_mode(_water(), (), None) == ""


@pytest.mark.parametrize("wavenumber,expected", [(120.0, True), (1372.0, False)])
def test_only_soft_modes_may_be_called_torsions(wavenumber, expected):
    """MEASURED. The geometric test alone labelled 11 of acetone's 24 modes
    torsional, including bands at 1226 and 1372 cm-1 -- and acetone has
    exactly two methyl rotors. A methyl deformation has nearly the same
    displacement pattern as a methyl torsion, and separating them needs the
    dihedral ANGLE change, which this module does not compute. So the label
    is bounded to where it is physically defensible: torsions are soft."""
    from openchem.chem.vibrational_modes import _is_soft

    assert _is_soft(wavenumber) is expected
