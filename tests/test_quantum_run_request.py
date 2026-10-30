"""`openchem.chem.quantum_run_request`: the rules for "may this molecule be run as asked, and with what", called directly and not through the panel.

`tests/test_quantum_run_button.py` holds the Run button to these rules through the real panel. These hold the function itself: the order of its refusals, what a prepared run carries, and what `start` hands
the service, so the second caller (an assistant's card, in the next slice) can rely on them without a widget.
"""

from __future__ import annotations

import dataclasses

import pytest
from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.chem.calculation_input import canonical_conformer, geometry_fingerprint
from openchem.chem.engine import ChemistryEngine
from openchem.chem.fukui import conformer_average_message, open_shell_message
from openchem.chem.quantum_run_request import (
    COSTLY_CALC_TYPES,
    NO_CONFORMER,
    NO_USABLE_CONFORMER,
    PreparedRun,
    RunChoice,
    RunRefusal,
    chosen_conformer,
    chosen_conformer_note,
    prepare_run,
    slot_of,
    start,
)
from openchem.domain.calculator import ENSEMBLE, GEOMETRY
from openchem.domain.conformer import ConformerModel
from openchem.domain.molecule import MoleculeModel

ENGINE = ChemistryEngine()


def butane(count: int = 3) -> MoleculeModel:
    molecule = MoleculeModel(display_name="Butane")
    ENGINE.set_structure_from_smiles(molecule, "CCCC")
    mol_3d = Chem.AddHs(Chem.MolFromSmiles("CCCC"))
    AllChem.EmbedMultipleConfs(mol_3d, numConfs=count, randomSeed=42)
    for conf_id in range(count):
        molecule.conformers.append(ConformerModel(molblock=Chem.MolToMolBlock(mol_3d, confId=conf_id), method="rdkit_etkdg", energy=float(conf_id)))
    return molecule


def choice(**kw) -> RunChoice:
    base = dict(calc_type="sp", method_basis="B3LYP def2-SVP", charge=0, multiplicity=1)
    base.update(kw)
    return RunChoice(**base)


def refusal(molecule, **kw) -> str:
    result = prepare_run(ENGINE, molecule, choice(**kw))
    assert isinstance(result, RunRefusal), result
    return result.message


class _Service:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def request_calculation(self, **kwargs) -> None:
        self.calls.append(("single", kwargs))

    def request_boltzmann_nmr(self, **kwargs) -> None:
        self.calls.append(("ensemble", kwargs))


# --- the order of the refusals ------------------------------------------------------------------------------------------------------------------


def test_the_refusals_are_in_the_order_a_person_fixes_them():
    assert refusal(None) == "Select a molecule with a structure first."
    assert refusal(MoleculeModel(display_name="empty")) == "Select a molecule with a structure first."
    no_conformer = MoleculeModel(display_name="x")
    ENGINE.set_structure_from_smiles(no_conformer, "O")
    assert refusal(no_conformer, method_basis="  ") == NO_CONFORMER, "a missing conformer is said before a missing method"
    flat = butane(1)
    flat.conformers[:] = [ConformerModel(molblock=flat.molblock, method="drawing")]
    assert refusal(flat, method_basis="") == NO_USABLE_CONFORMER, "an unusable conformer is said before a missing method"
    assert refusal(butane(), method_basis="   ") == "Enter a method/basis (e.g. 'B3LYP def2-SVP')."
    assert refusal(butane(), calc_type="fukui", multiplicity=2, average_conformers=True) == open_shell_message(2), "spin before averaging"
    assert refusal(butane(), calc_type="fukui", average_conformers=True) == conformer_average_message()


def test_an_average_that_cannot_be_resolved_names_the_conformer_and_is_refused():
    molecule = butane(3)
    molecule.conformers[2] = ConformerModel(molblock=molecule.molblock, method="drawing")
    assert refusal(molecule, average_conformers=True) == "Cannot average over the conformers: Conformer 3 has no 3D coordinates."


def test_averaging_one_conformer_is_a_single_run_and_never_a_fukui_refusal():
    molecule = butane(1)
    prepared = prepare_run(ENGINE, molecule, choice(calc_type="fukui", average_conformers=True))
    assert isinstance(prepared, PreparedRun) and prepared.ensemble is None


# --- what a prepared run carries ---------------------------------------------------------------------------------------------------------------


def test_a_prepared_single_run_carries_the_identity_of_the_conformer_every_calculation_uses():
    molecule = butane(3)
    prepared = prepare_run(ENGINE, molecule, choice(charge=1, multiplicity=2))
    canonical = canonical_conformer(molecule)
    assert isinstance(prepared, PreparedRun)
    assert prepared.molecule_uuid == molecule.uuid and prepared.structure_identity == molecule.canonical_smiles != ""
    assert prepared.fingerprint == geometry_fingerprint(canonical) and prepared.conformer_molblock == canonical.molblock
    assert prepared.source_slot == molecule.conformers.index(canonical) + 1 and prepared.conformer_note == "" and prepared.ensemble is None
    assert prepared.mol.GetNumAtoms() == 14 and prepared.mol.GetConformer().Is3D()
    assert (prepared.choice.charge, prepared.choice.multiplicity) == (1, 2)
    with pytest.raises(dataclasses.FrozenInstanceError):
        prepared.fingerprint = "other"  # type: ignore[misc]


def test_a_chosen_conformer_is_the_one_run_and_the_one_noted():
    molecule = butane(3)
    other = next(c for c in molecule.conformers if c is not canonical_conformer(molecule))
    prepared = prepare_run(ENGINE, molecule, choice(conformer_id=other.conformer_id))
    slot = molecule.conformers.index(other) + 1
    assert prepared.fingerprint == geometry_fingerprint(other) and prepared.source_slot == slot
    assert prepared.conformer_note.startswith(f"Computed on conformer {slot}, not the one every calculation uses")
    assert prepare_run(ENGINE, molecule, choice(calc_type="opt", conformer_id=other.conformer_id)).conformer_note == "", "an optimization replaces its source: not noted"


def test_a_choice_that_names_no_stored_conformer_falls_back_to_automatic():
    molecule = butane(3)
    prepared = prepare_run(ENGINE, molecule, choice(conformer_id="gone"))
    assert prepared.fingerprint == geometry_fingerprint(canonical_conformer(molecule)) and prepared.conformer_note == ""


def test_averaging_ignores_a_chosen_conformer_as_the_greyed_box_does():
    molecule = butane(3)
    other = next(c for c in molecule.conformers if c is not canonical_conformer(molecule))
    assert chosen_conformer(molecule, choice(conformer_id=other.conformer_id, average_conformers=True)) is None
    assert chosen_conformer(molecule, choice(conformer_id=other.conformer_id)) is other
    assert chosen_conformer(molecule, choice()) is None


def test_an_average_carries_every_conformer_and_an_identity_of_the_set():
    molecule = butane(3)
    prepared = prepare_run(ENGINE, molecule, choice(calc_type="nmr", average_conformers=True))
    assert prepared.ensemble is not None and len(prepared.ensemble.mols) == 3 and prepared.ensemble.fingerprint
    assert prepared.ensemble.fingerprint != prepared.fingerprint


def test_only_a_costly_calculation_asks_for_the_cost_to_be_accepted():
    molecule = butane(2)
    assert COSTLY_CALC_TYPES == {"led"}
    for calc_type in ("sp", "opt", "opt_freq", "nmr", "nmr_coupling", "delta_scf", "fukui"):
        assert prepare_run(ENGINE, molecule, choice(calc_type=calc_type)).asks_cost is False
    assert prepare_run(ENGINE, molecule, choice(calc_type="led")).asks_cost is True


def test_the_slot_of_a_fingerprint_is_its_one_based_position_or_zero():
    molecule = butane(3)
    assert [slot_of(molecule, geometry_fingerprint(c)) for c in molecule.conformers] == [1, 2, 3]
    assert slot_of(molecule, "not a stored conformer") == 0


def test_the_note_is_for_another_conformer_only_and_never_for_an_optimization():
    molecule = butane(3)
    automatic = canonical_conformer(molecule)
    other = next(c for c in molecule.conformers if c is not automatic)
    assert chosen_conformer_note(molecule, None, "sp") == "" and chosen_conformer_note(molecule, automatic, "sp") == ""
    assert chosen_conformer_note(molecule, other, "sp") != "" and chosen_conformer_note(molecule, other, "nmr") != ""
    assert chosen_conformer_note(molecule, other, "opt") == "" and chosen_conformer_note(molecule, other, "opt_freq") == ""


# --- what the service is handed ----------------------------------------------------------------------------------------------------------------


def test_start_hands_the_service_a_single_job_the_arguments_the_panel_always_sent():
    molecule = butane(3)
    prepared = prepare_run(ENGINE, molecule, choice(calc_type="opt", method_basis="PBE0 def2-TZVP CPCM(Water)", provider_id="psi4"))
    service = _Service()
    start(service, prepared)
    [(kind, kwargs)] = service.calls
    assert kind == "single" and set(kwargs) == {
        "mol", "molecule_uuid", "calc_type", "charge", "multiplicity", "method_basis", "provider_id", "input_fingerprint", "calculation_input", "structure_identity", "source_slot",
    }
    assert kwargs["calc_type"] == "opt" and kwargs["method_basis"] == "PBE0 def2-TZVP CPCM(Water)" and kwargs["provider_id"] == "psi4"
    assert kwargs["input_fingerprint"] == prepared.fingerprint and kwargs["calculation_input"] == GEOMETRY and kwargs["mol"] is prepared.mol
    assert kwargs["source_slot"] == prepared.source_slot and kwargs["structure_identity"] == molecule.canonical_smiles


def test_start_hands_the_service_an_average_with_the_identity_of_the_set():
    molecule = butane(3)
    prepared = prepare_run(ENGINE, molecule, choice(calc_type="nmr", average_conformers=True, charge=-1))
    service = _Service()
    start(service, prepared)
    [(kind, kwargs)] = service.calls
    assert kind == "ensemble" and set(kwargs) == {
        "mols", "molecule_uuid", "calc_type", "charge", "multiplicity", "method_basis", "provider_id", "input_fingerprint", "calculation_input", "structure_identity",
    }
    assert kwargs["calculation_input"] == ENSEMBLE and kwargs["input_fingerprint"] == prepared.ensemble.fingerprint
    assert len(kwargs["mols"]) == 3 and kwargs["charge"] == -1 and kwargs["structure_identity"] == molecule.canonical_smiles


def test_preparing_starts_nothing_and_changes_nothing():
    molecule = butane(3)
    before = ([c.conformer_id for c in molecule.conformers], molecule.molblock, molecule.canonical_smiles)
    prepare_run(ENGINE, molecule, choice(average_conformers=True))
    assert before == ([c.conformer_id for c in molecule.conformers], molecule.molblock, molecule.canonical_smiles)
