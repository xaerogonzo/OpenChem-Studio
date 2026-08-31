"""The ligand reaches Vina at the declared preparation pH.

`_convert_ligand_to_pdbqt` used to call a bare `mol.addh()` -- pybel's wrapper
for `AddHydrogens(polaronly=False, correctForPH=False, pH=7.4)`, i.e. the pH is
accepted and ignored -- while `_convert_receptor_to_pdbqt` had been moved to the
pH-correct call. The asymmetry is not cosmetic. Open Babel types a neutral
tertiary amine's nitrogen `NA`, a hydrogen-bond ACCEPTOR, where the pH 7.4
ammonium is `N` plus an `HD` polar hydrogen, a DONOR.

**These guards run without Vina.** The defect is entirely in the PDBQT handed
to it, so the file that gets written is the whole subject.

WHAT IS AND IS NOT CLAIMED. That the ligand is represented at the same DECLARED
pH as the receptor -- not that one scalar determines every protonation state.
And nothing here claims a docking result improves; that is a separate,
benchmark-shaped question, and this contract holds either way.
"""

from __future__ import annotations

import collections
import pathlib
import tempfile

import pytest
from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.chem.docking_providers import DEFAULT_PREPARATION_PH, VinaDockingProvider

FENTANYL = "CCC(=O)N(c1ccccc1)C1CCN(CCc2ccccc2)CC1"


def _embed(smiles: str) -> Chem.Mol:
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    # A fixed seed so a fixture cannot change meaning between runs; this
    # project has recorded a threshold fitted to one embedding once already.
    AllChem.EmbedMolecule(mol, randomSeed=0xC0FFEE)
    AllChem.MMFFOptimizeMolecule(mol)
    return mol


def _pdbqt(smiles: str, ph: float = DEFAULT_PREPARATION_PH) -> str:
    """The real preparation path's own output, never a reimplementation of it."""
    from openbabel import pybel

    provider = VinaDockingProvider()
    with tempfile.TemporaryDirectory() as scratch:
        out = pathlib.Path(scratch) / "ligand.pdbqt"
        provider._convert_ligand_to_pdbqt(pybel, _embed(smiles), out, ph)
        return out.read_text(encoding="utf-8")


def _atom_types(pdbqt_text: str) -> dict[str, int]:
    """AutoDock types, which are what Vina scores -- not elements."""
    return dict(
        collections.Counter(
            line.split()[-1]
            for line in pdbqt_text.splitlines()
            if line.startswith(("ATOM", "HETATM"))
        )
    )


# --------------------------------------------------------------------------
# The defect itself
# --------------------------------------------------------------------------


def test_a_basic_amine_reaches_vina_as_a_donor_not_an_acceptor():
    """The whole defect in one assertion.

    Fentanyl's piperidine nitrogen is the atom that anchors every opioid
    ligand. Prepared without pH correction it is typed `NA` -- an ACCEPTOR --
    and the receptor's anchor carboxylate is an acceptor too, so the intended
    donor contribution is absent from Vina's directional hydrogen-bond term.
    """
    types = _atom_types(_pdbqt(FENTANYL))
    assert types.get("HD", 0) == 1, f"no polar hydrogen on the amine: {types}"
    assert "NA" not in types, f"a nitrogen is still typed as an acceptor: {types}"
    assert types.get("N", 0) == 2, types


def test_the_amide_nitrogen_is_not_protonated_along_with_the_amine():
    """Fentanyl has TWO nitrogens and only one of them is basic.

    The narrow half of the guard above: exactly one polar hydrogen, so
    "protonate every nitrogen" cannot pass. This is the class this project
    fixed in `pka_providers` last week -- Dimorphite-DL's amine rule has no
    exclusion for an adjacent carbonyl, so a TERTIARY amide falls through to
    it. Open Babel's own pH model gets it right, which is why it can be the
    runtime path.
    """
    assert _atom_types(_pdbqt(FENTANYL)).get("HD", 0) == 1


# --------------------------------------------------------------------------
# The negative controls, which are the load-bearing half
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name,smiles", [("toluene", "Cc1ccccc1"), ("diethyl ether", "CCOCC")])
def test_a_non_ionizable_ligand_is_unchanged_by_preparation(name, smiles):
    """Nothing to ionize, so nothing may change.

    Without this, "add a hydrogen to everything" satisfies the donor guard
    above while corrupting every neutral ligand in the catalogue.
    """
    assert _atom_types(_pdbqt(smiles, 1.0)) == _atom_types(_pdbqt(smiles, 12.0)), name
    assert "HD" not in _atom_types(_pdbqt(smiles)), name


def test_an_existing_donor_does_not_gain_a_duplicate_hydrogen():
    """Ethanol's hydroxyl is already a donor and is not ionized in range.

    It must come through with exactly ONE polar hydrogen at every pH -- a
    second one would be an invented donor, which scores as a favourable
    contact that does not exist.
    """
    for ph in (1.0, DEFAULT_PREPARATION_PH, 12.0):
        assert _atom_types(_pdbqt("CCO", ph)).get("HD", 0) == 1, ph


# --------------------------------------------------------------------------
# The contract is pH, not fentanyl
# --------------------------------------------------------------------------


def test_the_declared_ph_governs_an_acid():
    """Acetic acid is neutral at pH 1 and a carboxylate at 7.4.

    Without this pair the suite would only establish "Open Babel happens to
    fix fentanyl", where the shipped claim is a pH-preparation contract.
    """
    assert _atom_types(_pdbqt("CC(=O)O", 1.0)).get("HD", 0) == 1
    assert "HD" not in _atom_types(_pdbqt("CC(=O)O", 7.4))


def test_the_declared_ph_governs_a_base():
    """Methylamine is an ammonium at 7.4 and a neutral amine at 12 -- where
    the nitrogen goes back to being typed `NA`, the acceptor typing this
    whole change is about."""
    at_74 = _atom_types(_pdbqt("CN", 7.4))
    at_12 = _atom_types(_pdbqt("CN", 12.0))
    assert at_74.get("HD", 0) == 3 and "NA" not in at_74, at_74
    assert at_12.get("HD", 0) == 2 and at_12.get("NA", 0) == 1, at_12


@pytest.mark.parametrize(
    "name,smiles,expected_present,expected_absent",
    [
        # A basic aliphatic amine protonates; a pyridine (pKa ~5.2) does not,
        # and stays a genuine acceptor. Asserting BOTH is what stops "every
        # nitrogen becomes a donor" from passing.
        ("aliphatic amine", "CCCN", ("HD", "N"), ("NA",)),
        ("pyridine", "c1ccncc1", ("NA",), ("HD",)),
        ("neutral amide", "CC(N)=O", ("HD", "N", "OA"), ("NA",)),
        ("phenol", "Oc1ccccc1", ("HD", "OA"), ()),
        ("carboxylate", "CC(=O)O", ("OA",), ("HD",)),
    ],
)
def test_atom_typing_spot_checks(name, smiles, expected_present, expected_absent):
    """The mechanism is TYPING, not formal charge.

    The 16-molecule agreement below is about the CHARGE STATE; what Vina
    scores is the AutoDock type, and the two are not the same claim. These
    pin the preparation contract per functional group.
    """
    types = _atom_types(_pdbqt(smiles))
    for expected in expected_present:
        assert expected in types, f"{name}: expected {expected} in {types}"
    for forbidden in expected_absent:
        assert forbidden not in types, f"{name}: {forbidden} should be absent from {types}"


def test_ligand_stereochemistry_survives_preparation():
    """A PDBQT conversion can preserve coordinates while losing stereochemical
    assignment, and [source:tenbrink2009] treats stereoisomeric state as one of
    the docking-state variables alongside protonation.

    Read back from the written 3D coordinates rather than from a label, since
    the label is exactly what a lossy conversion drops.
    """
    from openbabel import pybel

    smiles = "C[C@H](N)C(=O)O"
    before = _embed(smiles)
    Chem.AssignStereochemistryFrom3D(before)
    original = Chem.FindMolChiralCenters(before, useLegacyImplementation=False)
    assert original, "the fixture has no stereocentre, so it cannot show this"

    provider = VinaDockingProvider()
    with tempfile.TemporaryDirectory() as scratch:
        out = pathlib.Path(scratch) / "ligand.pdbqt"
        provider._convert_ligand_to_pdbqt(pybel, before, out, DEFAULT_PREPARATION_PH)
        after_mol = Chem.MolFromPDBBlock(
            "\n".join(
                line
                for line in out.read_text(encoding="utf-8").splitlines()
                if line.startswith(("ATOM", "HETATM"))
            ),
            removeHs=False,
            sanitize=False,
        )
    assert after_mol is not None
    Chem.AssignStereochemistryFrom3D(after_mol)
    assert Chem.FindMolChiralCenters(after_mol, useLegacyImplementation=False) == original


# --------------------------------------------------------------------------
# The cross-check: two implementations, one published reference
# --------------------------------------------------------------------------

#: Literature charge states at pH 7.4. The REFERENCE for both implementations
#: below -- neither of them is the oracle, because two implementations can
#: agree while sharing an assumption. Same corpus as
#: `tests/test_protonation_microspecies.py`, which is where it was validated.
LITERATURE_CHARGE_STATES = [
    ("caffeine", "Cn1cnc2c1c(=O)n(C)c(=O)n2C", 0),
    ("DMF", "CN(C)C=O", 0),
    ("DEET", "CCN(CC)C(=O)c1cccc(C)c1", 0),
    ("N-methylpyrrolidone", "CN1CCCC1=O", 0),
    ("atropine", "CN1C2CCC1CC(C2)OC(=O)C(CO)c1ccccc1", 1),
    ("lidocaine", "CCN(CC)CC(=O)Nc1c(C)cccc1C", 1),
    ("nicotine", "CN1CCC[C@H]1c1cccnc1", 1),
    ("propranolol", "CC(C)NCC(O)COc1cccc2ccccc12", 1),
    ("fentanyl", FENTANYL, 1),
    ("aspirin", "CC(=O)Oc1ccccc1C(=O)O", -1),
    ("ibuprofen", "CC(C)Cc1ccc(cc1)C(C)C(=O)O", -1),
]


@pytest.mark.parametrize("name,smiles,expected", LITERATURE_CHARGE_STATES)
def test_open_babel_reproduces_the_published_charge_state(name, smiles, expected):
    """The runtime path against the literature, which is the reference."""
    from openbabel import pybel

    mol = pybel.readstring("smi", smiles)
    mol.OBMol.AddHydrogens(False, True, DEFAULT_PREPARATION_PH)
    assert mol.OBMol.GetTotalCharge() == expected, name


@pytest.mark.parametrize("name,smiles,expected", LITERATURE_CHARGE_STATES)
def test_the_projects_own_protonation_agrees_with_the_runtime_path(name, smiles, expected):
    """An INDEPENDENT project-side cross-check, not an oracle.

    `dominant_microspecies` is validated against the same literature states and
    carries the tertiary-amide correction. It is deliberately NOT the runtime
    implementation: it returns a mol built from SMILES and so has no conformer,
    and adopting it would discard the 3D geometry the panel selected. Keeping
    it as a second opinion means a divergence in EITHER becomes visible.
    """
    from openchem.chem.pka_providers import dominant_microspecies

    ours = dominant_microspecies(Chem.MolFromSmiles(smiles), DEFAULT_PREPARATION_PH)
    assert ours.formal_charge == expected, name
