from __future__ import annotations

import pytest

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


# --- a reference geometry must not depend on when it was built ----------------


def _mmff_energy(mol):
    from rdkit.Chem import AllChem

    properties = AllChem.MMFFGetMoleculeProperties(mol)
    return AllChem.MMFFGetMoleculeForceField(mol, properties).CalcEnergy()


def test_the_tms_reference_is_the_same_structure_every_time():
    """Every shift the application reports is RELATIVE to this one, so a
    reference built from a different random draw each run is a reference
    that moves under the numbers scaled against it."""
    from rdkit import Chem

    from openchem.chem.nmr_reference import tms_molecule

    assert Chem.MolToMolBlock(tms_molecule()) == Chem.MolToMolBlock(tms_molecule())


def test_every_calibration_compound_is_reproducible():
    from rdkit import Chem

    from openchem.chem.nmr_scaling import REFERENCE_COMPOUNDS, reference_molecule

    for compound in REFERENCE_COMPOUNDS:
        first = Chem.MolToMolBlock(reference_molecule(compound))
        second = Chem.MolToMolBlock(reference_molecule(compound))
        assert first == second, f"{compound.name} is not reproducible"


def test_cyclohexane_is_calibrated_on_its_CHAIR():
    """**THE ONE THAT IS NOT RIGID, AND THE REASON SEEDING ALONE WAS NOT THE
    FIX.**

    Ten of the eleven calibration compounds land on the same structure from
    any seed. Cyclohexane does not: chair at -3.5609 kcal/mol, twist-boat at
    +2.3688, and a single embedding gave the twist-boat about one time in
    three. The experimental shift it is fitted against -- 26.9 ppm for
    carbon -- is the chair's.

    **And the seed chosen for reproducibility, 0x5EED, produced the
    TWIST-BOAT.** Pinning the seed without taking the lowest-energy
    conformer would have locked the calibration onto the wrong geometry
    permanently, which is worse than the coin flip it replaced.

    Asserted against a WIDER search rather than a hardcoded energy: the
    claim is "the lowest one found", and a literal -3.5609 would be a number
    fitted to this force field on this machine.
    """
    from rdkit import Chem

    from openchem.chem.conformer_providers import RDKitConformerProvider
    from openchem.chem.nmr_scaling import REFERENCE_COMPOUNDS, reference_molecule

    compound = next(c for c in REFERENCE_COMPOUNDS if c.name == "Cyclohexane")
    wider = RDKitConformerProvider(random_seed=0).generate_conformers(
        Chem.MolFromSmiles(compound.smiles), num_conformers=40, optimize=True
    )
    energies = [energy for _mol, energy in wider]
    assert max(energies) - min(energies) > 1.0, (
        "cyclohexane stopped being the flexible case, so this proves nothing"
    )

    assert _mmff_energy(reference_molecule(compound)) == pytest.approx(min(energies), abs=1e-4)
