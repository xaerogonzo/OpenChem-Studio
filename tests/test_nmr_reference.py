from __future__ import annotations

from openchem.chem.nmr_reference import average_reference_shielding, chemical_shift_from_reference, tms_molecule
from openchem.domain.scientific_result import NMRSpectrumResult


def test_tms_molecule_has_a_real_embedded_conformer():
    mol = tms_molecule()

    assert mol.GetNumConformers() == 1
    # Si(CH3)4 with explicit hydrogens: 1 Si + 4 C + 12 H = 17 atoms.
    assert mol.GetNumAtoms() == 17
    symbols = sorted(atom.GetSymbol() for atom in mol.GetAtoms())
    assert symbols.count("Si") == 1
    assert symbols.count("C") == 4
    assert symbols.count("H") == 12


def test_average_reference_shielding_averages_equivalent_nuclei():
    raw = NMRSpectrumResult(
        spectrum_type="nmr_raw_shielding",
        name="raw",
        units="ppm",
        method="orca",
        molecule_uuid="tms",
        values={0: 190.0, 1: 192.0, 2: 188.0, 3: 190.0, 4: 30.0, 5: 32.0},
        elements={0: "C", 1: "C", 2: "C", 3: "C", 4: "H", 5: "H"},
    )

    averaged = average_reference_shielding(raw)

    assert averaged == {"C": 190.0, "H": 31.0}


def test_chemical_shift_from_reference_applies_delta_formula():
    raw = NMRSpectrumResult(
        spectrum_type="nmr_raw_shielding",
        name="raw",
        units="ppm",
        method="orca",
        molecule_uuid="mol-1",
        values={0: 100.0, 1: 25.0, 2: 365.0},
        elements={0: "C", 1: "H", 2: "O"},
    )

    calibrated = chemical_shift_from_reference(raw, {"C": 190.0, "H": 30.0})

    assert calibrated is not None
    assert calibrated.spectrum_type == "nmr_calibrated"
    assert calibrated.molecule_uuid == "mol-1"
    # delta = reference - raw_shielding; O has no cached reference so it's
    # excluded entirely, not zeroed or guessed.
    assert calibrated.values == {0: 90.0, 1: 5.0}
    assert calibrated.elements == {0: "C", 1: "H"}
    assert 2 not in calibrated.values


def test_chemical_shift_from_reference_returns_none_when_nothing_is_covered():
    raw = NMRSpectrumResult(
        spectrum_type="nmr_raw_shielding",
        name="raw",
        units="ppm",
        method="orca",
        molecule_uuid="mol-1",
        values={0: 365.0},
        elements={0: "O"},
    )

    assert chemical_shift_from_reference(raw, {"C": 190.0, "H": 30.0}) is None
