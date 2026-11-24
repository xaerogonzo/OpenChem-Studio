"""Unpaired electrons (docs/OPEN_SHELL_AND_HYPERVALENT_COVERAGE_DESIGN.md): what was measured wrong, held to an independent answer.

Every expectation here is either an arithmetic fact (electron parity), another program's own verdict (real ORCA 6.1.1 on a methyl radical and on NO at
multiplicity 1: 'multiplicity (1) is odd and number of electrons (9) is odd -> impossible'), or a textbook Hueckel result recomputed below by a second,
independent diagonalisation. A control (a closed-shell molecule) must not move in each group.
"""

from __future__ import annotations

import numpy as np
import pytest
from rdkit import Chem, RDLogger
from rdkit.Chem import AllChem

from openchem.chem import hansen, joback
from openchem.chem.engine import ChemistryEngine
from openchem.chem.huckel import compute_huckel_analysis, compute_pi_electron_density, open_shell_refusal, solve_huckel
from openchem.chem.open_shell import default_multiplicity, electron_count, multiplicity_problem, spin_note, unpaired_electrons
from openchem.chem.quantum_run_request import RunChoice, RunRefusal, prepare_run
from openchem.domain.conformer import ConformerModel
from openchem.domain.molecule import MoleculeModel
from openchem.domain.refusal_kinds import RefusalKind, refusal_kind_of

RDLogger.DisableLog("rdApp.*")
ENGINE = ChemistryEngine()


def mol(smiles: str) -> Chem.Mol:
    return Chem.MolFromSmiles(smiles)


# --- the spin the structure states --------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "smiles, unpaired, multiplicity",
    [("[CH3]", 1, 2), ("[OH]", 1, 2), ("[N]=O", 1, 2), ("[O][O]", 2, 3), ("[CH2]", 2, 3), ("[O]", 2, 3), ("CC1(C)CCCC(C)(C)N1[O]", 1, 2), ("CCO", 0, 1), ("O=O", 0, 3), ("S=S", 0, 3), ("S=O", 0, 3), ("N#N", 0, 1), ("[O-]O", 0, 1)],
)
def test_the_default_multiplicity_is_unpaired_electrons_plus_one(smiles, unpaired, multiplicity):
    assert unpaired_electrons(mol(smiles)) == unpaired
    assert default_multiplicity(mol(smiles)) == multiplicity


def test_a_drawn_singlet_carbene_is_not_told_from_a_triplet_one():
    """Measured: RDKit reads a molfile's singlet (RAD 1) and triplet (RAD 3) as two radical electrons and writes the triplet back, so the multiplicity is NOT in the structure."""
    block = "\n  t\n\n  1  0  0  0  0  0  0  0  0  0999 V2000\n    0.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\nM  RAD  1   1   {r}\nM  END\n"
    singlet = Chem.MolFromMolBlock(block.format(r=1), removeHs=False)
    triplet = Chem.MolFromMolBlock(block.format(r=3), removeHs=False)
    assert Chem.MolToMolBlock(singlet) == Chem.MolToMolBlock(triplet)
    assert default_multiplicity(singlet) == 3  # the high-spin default, which is why it is a default and not a fact


def test_the_engine_gives_a_model_its_default_multiplicity():
    for smiles, expected in (("[O][O]", 3), ("[CH3]", 2), ("CCO", 1)):
        model = MoleculeModel(display_name=smiles)
        ENGINE.set_structure_from_smiles(model, smiles)
        assert ENGINE.default_multiplicity(model) == expected


# --- electrons that cannot have the multiplicity ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("smiles, charge, multiplicity", [("[CH3]", 0, 1), ("[N]=O", 0, 1), ("CCO", 0, 2), ("[O][O]", 0, 2), ("[CH3]", 0, 12), ("[H]", 0, 3)])
def test_an_impossible_pair_is_named(smiles, charge, multiplicity):
    """The first two are the pairs real ORCA refused (exit 55); the rest are the same arithmetic."""
    assert multiplicity_problem(mol(smiles), charge, multiplicity)


@pytest.mark.parametrize("smiles, charge, multiplicity", [("[CH3]", 0, 2), ("[N]=O", 0, 2), ("[O][O]", 0, 3), ("[O][O]", 0, 1), ("CCO", 0, 1), ("CCO", 0, 3), ("[O][O-]", -1, 2)])
def test_a_possible_pair_is_not(smiles, charge, multiplicity):
    assert multiplicity_problem(mol(smiles), charge, multiplicity) == ""


def test_the_electron_count_includes_implicit_hydrogens_and_the_charge():
    assert electron_count(mol("[CH3]"), 0) == 9
    assert electron_count(mol("[O][O-]"), -1) == 17
    assert electron_count(Chem.AddHs(mol("[CH3]")), 0) == 9


def conformer_molecule(smiles: str) -> MoleculeModel:
    molecule = MoleculeModel(display_name=smiles)
    ENGINE.set_structure_from_smiles(molecule, smiles)
    three_d = Chem.AddHs(mol(smiles))
    AllChem.EmbedMolecule(three_d, randomSeed=7)
    molecule.conformers.append(ConformerModel(molblock=Chem.MolToMolBlock(three_d), method="rdkit_etkdg", energy=0.0))
    return molecule


def run(smiles: str, multiplicity: int, charge: int = 0):
    return prepare_run(ENGINE, conformer_molecule(smiles), RunChoice(calc_type="opt", method_basis="B3LYP def2-SVP", charge=charge, multiplicity=multiplicity))


@pytest.mark.parametrize("smiles", ["[CH3]", "[N]=O"])
def test_a_run_ORCA_would_refuse_is_refused_before_it_is_queued(smiles):
    result = run(smiles, 1)
    assert isinstance(result, RunRefusal)
    assert "multiplicity 1" in result.message


def test_the_same_radical_at_its_own_multiplicity_is_prepared_with_no_note():
    result = run("[CH3]", 2)
    assert not isinstance(result, RunRefusal)
    assert result.conformer_note == ""


def test_a_closed_shell_run_is_unchanged():
    result = run("CCO", 1)
    assert not isinstance(result, RunRefusal)
    assert result.conformer_note == ""
    assert isinstance(run("CCO", 2), RunRefusal)


def test_a_closed_shell_calculation_on_a_drawn_triplet_is_prepared_and_says_so():
    """Not refused (a person may want it) but not silent: real ORCA ran O2 at multiplicity 1 and finished, 0.0632 Eh (39.7 kcal/mol) above multiplicity 3."""
    result = run("[O][O]", 1)
    assert not isinstance(result, RunRefusal)
    assert "closed-shell" in result.conformer_note and "multiplicity 3" in result.conformer_note
    assert spin_note(mol("[O][O]"), 3) == ""


# --- the group-contribution methods ------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("smiles", ["C[CH2]", "C=C[CH2]", "[CH2]c1ccccc1", "[CH3]", "CC1(C)CCCC(C)(C)N1[O]"])
def test_joback_and_hansen_refuse_unpaired_electrons(smiles):
    """Measured before: Joback gave ethyl radical {-CH3, =CH2} (a vinyl CH2 the molecule does not have) and allyl radical two =CH2 groups; Hansen gave benzyl radical ethylbenzene's ACCH2- group."""
    assert joback.fragment(mol(smiles)).refusal is joback.JobackRefusal.OPEN_SHELL
    assert hansen.fragment(mol(smiles)).refusal is hansen.HansenRefusal.OPEN_SHELL
    assert refusal_kind_of("OPEN_SHELL") is RefusalKind.LIMIT
    assert "closed-shell" in joback.refusal_text(joback.fragment(mol(smiles)))
    assert "closed-shell" in hansen.refusal_text(hansen.fragment(mol(smiles)))


def test_the_closed_shell_controls_keep_their_groups():
    assert dict(joback.fragment(mol("Cc1ccccc1")).counts) == {"-CH3": 1, "ring=CH-": 5, "ring=C<": 1}
    assert dict(hansen.fragment(mol("Cc1ccccc1")).first) == {"acch3": 1, "ach": 5}
    assert dict(joback.fragment(mol("CCc1ccccc1")).counts) == {"-CH3": 1, "-CH2-": 1, "ring=CH-": 5, "ring=C<": 1}


# --- Hueckel -----------------------------------------------------------------------------------------------------------------------------------


def reference_pi_energy(edges: list[tuple[int, int]], size: int, electrons: int) -> float:
    """A second diagonalisation, written separately: sum of occupation times x over the sorted eigenvalues."""
    matrix = np.zeros((size, size))
    for a, b in edges:
        matrix[a, b] = matrix[b, a] = 1.0
    levels = sorted(np.linalg.eigvalsh(matrix), reverse=True)
    total, left = 0.0, electrons
    for level in levels:
        put = min(2, left)
        total += put * level
        left -= put
    return total


def test_benzyl_radical_has_seven_pi_centres_and_the_textbook_energy():
    """Measured before: pi system of 6 (the benzene ring), total 8.00 beta and a 2.00 gap, the radical carbon left out. Seven centres and seven electrons give 8.72 beta (the textbook value)."""
    edges = [(i, (i + 1) % 6) for i in range(6)] + [(0, 6)]
    expected = reference_pi_energy(edges, 7, 7)
    assert expected == pytest.approx(8.72, abs=0.005)
    result = solve_huckel(mol("[CH2]c1ccccc1"))
    assert len(result.atom_indices) == 7
    assert result.total_pi_energy == pytest.approx(expected)
    assert result.homo == pytest.approx(0.0, abs=1e-9)  # the non-bonding orbital holds the unpaired electron


def test_allyl_radical_is_the_textbook_three_centre_case():
    result = solve_huckel(mol("C=C[CH2]"))
    assert result.total_pi_energy == pytest.approx(reference_pi_energy([(0, 1), (1, 2)], 3, 3))
    assert result.total_pi_energy == pytest.approx(2 * 2**0.5)


def test_hueckel_refuses_a_radical_that_is_not_a_carbon_centre_and_gives_the_reason():
    for smiles in ("[N]=O", "[O][O]", "CC1(C)CCCC(C)(C)N1[O]", "[CH2]"):
        assert open_shell_refusal(mol(smiles))
        report = compute_huckel_analysis(mol(smiles), "u")
        assert report.provenance.parameters["refusal"] == "OPEN_SHELL"
        dataset = compute_pi_electron_density(mol(smiles), "u")
        assert dataset.provenance.parameters["refusal"] == "OPEN_SHELL"
        assert dataset.values == {}


def test_hueckel_controls_do_not_move():
    assert solve_huckel(mol("Cc1ccccc1")).total_pi_energy == pytest.approx(8.0)
    assert solve_huckel(mol("c1ccccc1")).total_pi_energy == pytest.approx(8.0)
    assert not open_shell_refusal(mol("[CH2]c1ccccc1"))
    assert not open_shell_refusal(mol("Cc1ccccc1"))


# --- the Quantum Chemistry panel ----------------------------------------------------------------------------------------------------------------


def test_selecting_a_molecule_sets_the_panel_multiplicity_from_its_unpaired_electrons(qapp):
    """The multiplicity stayed at 1 whatever was selected (the charge was always derived). A closed-shell drawing still gives 1."""
    from test_quantum_chemistry_panel import _dispose_panel, _make_panel

    from openchem.domain.project import ProjectModel

    panel, engine, _service = _make_panel()
    try:
        project = ProjectModel(name="spin")
        for smiles in ("CCO", "[CH3]", "[O][O]"):
            model = MoleculeModel(display_name=smiles)
            engine.set_structure_from_smiles(model, smiles)
            project.molecules.append(model)
        panel.set_project(project)
        seen = []
        for index in range(3):
            panel._molecule_combo.setCurrentIndex(index)
            seen.append(panel._multiplicity_spin.value())
        assert seen == [1, 2, 3]
    finally:
        _dispose_panel(panel)


# --- ground states drawn closed-shell, and <S**2> ---------------------------------------------------------------------------------------------


def test_a_closed_shell_drawn_triplet_says_so_when_run_as_a_singlet():
    assert "triplet" in spin_note(mol("O=O"), 1)
    assert spin_note(mol("O=O"), 3) == ""
    assert spin_note(mol("N#N"), 1) == ""  # the control: N2 is a singlet (triplet is +147.5 kcal/mol in real ORCA)


def test_orca_reports_s_squared_only_for_an_unrestricted_run():
    from openchem.chem.orca_engine import OrcaQuantumEngineProvider

    base = "FINAL SINGLE POINT ENERGY      -150.1449\n"
    unrestricted = base + "Expectation value of <S**2>     :     2.006490\nIdeal value S*(S+1) for S=1.0   :     2.000000\nDeviation                       :     0.006490\n"
    provider = OrcaQuantumEngineProvider()
    water = Chem.AddHs(mol("O"))
    AllChem.EmbedMolecule(water, randomSeed=1)

    def ids(text):
        return {d.descriptor_id: d for d in provider.parse_output(text, water, "u", "sp")[0]}

    found = ids(unrestricted)["orca.s_squared"]
    assert found.value == 2.00649 and found.provenance.parameters["ideal_s_squared"] == 2.0 and found.provenance.parameters["excess"] == 0.00649
    assert "orca.s_squared" not in ids(base)


def test_psi4_refuses_an_impossible_electron_count_before_running():
    from openchem.chem.psi4_engine import Psi4QuantumEngineProvider

    methyl = Chem.AddHs(mol("[CH3]"))
    AllChem.EmbedMolecule(methyl, randomSeed=1)
    with pytest.raises(ValueError, match="multiplicity 1"):
        Psi4QuantumEngineProvider().build_input(methyl, 0, 1, "B3LYP def2-SVP", "sp")


# --- OS1: the drawing's multiplicity stays with the structure ---------------------------------------------------------------------------------


CARBENE = "\n  t\n\n  1  0  0  0  0  0  0  0  0  0999 V2000\n    0.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\nM  RAD  1   1   {r}\nM  END\n"


def test_the_multiplicity_is_read_from_the_molfile_text():
    from openchem.chem.open_shell import spin_from_molblock

    assert [spin_from_molblock(CARBENE.format(r=r)) for r in (1, 2, 3)] == [1, 2, 3]
    assert spin_from_molblock(Chem.MolToMolBlock(mol("CCO"))) is None
    assert spin_from_molblock(None) is None
    # two atoms: a triplet O2 drawn as two doublets is multiplicity 3
    assert spin_from_molblock(Chem.MolToMolBlock(mol("[O][O]"))) == 3


def test_a_singlet_carbene_stays_a_singlet_through_the_structure_the_model_stores():
    singlet, triplet = MoleculeModel(display_name="s"), MoleculeModel(display_name="t")
    ENGINE.set_structure_from_molblock(singlet, CARBENE.format(r=1))
    ENGINE.set_structure_from_molblock(triplet, CARBENE.format(r=3))
    assert ENGINE.default_multiplicity(singlet) == 1
    assert ENGINE.default_multiplicity(triplet) == 3
    assert singlet.canonical_smiles == triplet.canonical_smiles  # identity is unchanged: the spin is not in the SMILES
    assert singlet.molblock != triplet.molblock


def test_the_singlet_survives_the_project_file_and_an_undoable_edit():
    from openchem.commands.molecule_commands import EditStructureCommand
    from openchem.events.base import EventBus

    molecule = MoleculeModel(display_name="s")
    ENGINE.set_structure_from_molblock(molecule, CARBENE.format(r=1))
    assert ENGINE.default_multiplicity(MoleculeModel.from_dict(molecule.to_dict())) == 1
    before = molecule.molblock
    command = EditStructureCommand(ENGINE, molecule, Chem.MolToMolBlock(mol("CCO")), EventBus())
    command.redo()
    assert ENGINE.default_multiplicity(molecule) == 1 and molecule.canonical_smiles == "CCO"
    command.undo()
    assert molecule.molblock == before and ENGINE.default_multiplicity(molecule) == 1


def test_a_run_of_a_drawn_singlet_at_multiplicity_1_carries_no_note():
    result = run_from_molblock(CARBENE.format(r=1), 1)
    assert not isinstance(result, RunRefusal) and result.conformer_note == ""
    triplet = run_from_molblock(CARBENE.format(r=3), 1)
    assert "closed-shell" in triplet.conformer_note


def run_from_molblock(molblock: str, multiplicity: int):
    molecule = MoleculeModel(display_name="c")
    ENGINE.set_structure_from_molblock(molecule, molblock)
    three_d = Chem.AddHs(Chem.MolFromMolBlock(molblock, removeHs=False))
    AllChem.EmbedMolecule(three_d, randomSeed=7)
    molecule.conformers.append(ConformerModel(molblock=Chem.MolToMolBlock(three_d), method="rdkit_etkdg", energy=0.0))
    return prepare_run(ENGINE, molecule, RunChoice(calc_type="sp", method_basis="B3LYP def2-SVP", charge=0, multiplicity=multiplicity))


def test_a_singlet_code_on_a_lone_atom_survives_the_stored_molblock():
    """RDKit writes no RAD line for a bond-less O or H (the radical rides in the atom line's valence field), so the singlet code used to vanish and the default said triplet (Ketcher-measured, tests/test_ketcher_radical_roundtrip.py)."""
    block = "\n  t\n\n  1  0  0  0  0  0  0  0  0  0999 V2000\n    0.0000    0.0000    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\nM  RAD  1   1   {r}\nM  END\n"
    singlet, triplet = MoleculeModel(display_name="s"), MoleculeModel(display_name="t")
    ENGINE.set_structure_from_molblock(singlet, block.format(r=1))
    ENGINE.set_structure_from_molblock(triplet, block.format(r=3))
    assert (ENGINE.default_multiplicity(singlet), ENGINE.default_multiplicity(triplet)) == (1, 3)
    assert "M  RAD  1   1   1" in singlet.molblock
    assert Chem.MolFromMolBlock(singlet.molblock, removeHs=False).GetAtomWithIdx(0).GetNumRadicalElectrons() == 2  # still read as an atom, not water
