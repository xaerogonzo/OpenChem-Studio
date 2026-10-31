"""`openchem.chem.quantum_run_request`: the rules for "may this molecule be run as asked, and with what", called directly and not through the panel.

`tests/test_quantum_run_button.py` holds the Run button to these rules through the real panel. These hold the function itself: the order of its refusals, what a prepared run carries, and what `start` hands
the service, so the second caller (an assistant's card, in the next slice) can rely on them without a widget.
"""

from __future__ import annotations

import dataclasses

import pytest
from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.chem import bond_dissociation as bd
from openchem.chem.calculation_input import canonical_conformer, geometry_fingerprint
from openchem.chem.engine import ChemistryEngine
from openchem.chem.fukui import conformer_average_message, open_shell_message
from openchem.chem.quantum_run_request import (
    COSTLY_CALC_TYPES,
    COST_ESTIMATE_CAVEAT,
    NO_CONFORMER,
    NO_USABLE_CONFORMER,
    TWO_PARTNERS_MESSAGE,
    PreparedBondDissociation,
    PreparedRun,
    RunChoice,
    RunRefusal,
    bond_choices,
    chosen_conformer,
    chosen_conformer_note,
    led_cost_message,
    led_cost_of_smiles,
    prepare_bond_dissociation,
    prepare_bond_dissociation_for,
    prepare_run,
    review_cost,
    review_led,
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


# --- the cost of a job that asks first: one set of rules and words for the panel's dialog and an assistant's card ---------------------------------


def _pair_molecule(z_shift: float = 0.0) -> MoleculeModel:
    from test_orca_led import _pair

    molecule = MoleculeModel(display_name="Ammonia borane")
    ENGINE.set_structure_from_smiles(molecule, "N.B")
    molecule.conformers.append(ConformerModel(molblock=Chem.MolToMolBlock(_pair(z_shift)), method="rdkit_etkdg"))
    return molecule


def test_only_a_job_that_asks_first_is_reviewed():
    prepared = prepare_run(ENGINE, butane(2), choice(calc_type="sp"))
    assert review_cost(prepared).kind == "ok"


def test_one_species_is_refused_as_not_two_partners_whoever_asks():
    prepared = prepare_run(ENGINE, butane(2), choice(calc_type="led"))
    review = review_cost(prepared)
    assert (review.kind, review.title, review.message) == ("two_partners", "Two partners needed", TWO_PARTNERS_MESSAGE) and review.refuses


def test_two_partners_that_overlap_are_refused_with_the_geometrys_reason():
    prepared = prepare_run(ENGINE, _pair_molecule(1.5), choice(calc_type="led"))
    review = review_cost(prepared)
    assert review.kind == "geometry" and review.refuses and "overlap" in review.message and review.title == "This geometry cannot be decomposed"


def test_a_sensible_pair_is_ok_and_a_costly_one_is_a_cost_to_accept():
    assert review_cost(prepare_run(ENGINE, _pair_molecule(0.0), choice(calc_type="led"))).kind == "ok"
    big = Chem.AddHs(Chem.MolFromSmiles("c1ccc2ccccc2c1.c1ccc2ccccc2c1"))
    review = review_led(big)
    assert review.kind == "expensive" and not review.refuses and COST_ESTIMATE_CAVEAT in review.message and "basis functions, DLPNO-CCSD(T)" in review.message


def test_a_card_is_told_the_cost_of_a_structure_before_any_conformer_exists():
    refusal, text = led_cost_of_smiles("N.B")
    assert refusal == "" and "basis functions, DLPNO-CCSD(T)" in text and COST_ESTIMATE_CAVEAT in text
    assert led_cost_of_smiles("CCCC") == (TWO_PARTNERS_MESSAGE, "")
    assert led_cost_of_smiles("")[0] and led_cost_of_smiles("not a smiles")[0]


def test_the_cost_text_counts_the_hydrogens_orca_is_handed():
    from openchem.chem.orca_led import estimate_led_cost_for

    _refusal, text = led_cost_of_smiles("N.B")
    bare = estimate_led_cost_for(Chem.MolFromSmiles("N.B"))
    assert led_cost_message(estimate_led_cost_for(Chem.AddHs(Chem.MolFromSmiles("N.B")))) == text and bare.atoms < 8


# --- proton affinity: the button's rules, shared with an assistant's card -------------------------------------------------------------------------


def test_proton_affinity_needs_a_structure_to_run_on():
    from openchem.chem.quantum_run_request import PreparedProtonAffinity, prepare_proton_affinity, prepare_proton_affinity_for

    assert prepare_proton_affinity("") == RunRefusal("Select a molecule with a structure first.")
    assert prepare_proton_affinity_for(None) == RunRefusal("Select a molecule with a structure first.")
    assert prepare_proton_affinity_for(MoleculeModel(display_name="empty")) == RunRefusal("Select a molecule with a structure first.")
    drawn = MoleculeModel(display_name="Ammonia")
    ENGINE.set_structure_from_smiles(drawn, "N")
    prepared = prepare_proton_affinity_for(drawn)
    assert isinstance(prepared, PreparedProtonAffinity) and prepared.smiles == drawn.canonical_smiles and prepared.jobs == 2 and not prepared.asks_cost


def test_proton_affinity_says_why_a_base_is_refused_and_what_it_could_not_do(monkeypatch):
    from openchem.chem import quantum_run_request as module

    assert module.prepare_proton_affinity("C[N+](C)(C)C").message.startswith("Proton affinity does not apply:")

    def broken(smiles):
        raise RuntimeError("no embedding")

    monkeypatch.setattr(module, "ProtonAffinitySequence", broken)
    assert module.prepare_proton_affinity("N") == RunRefusal("Proton affinity could not start: no embedding")


def test_a_long_run_or_an_unmeasured_base_asks_and_a_small_measured_one_does_not():
    from openchem.chem.quantum_run_request import prepare_proton_affinity

    assert not prepare_proton_affinity("N").asks_cost
    long_run = prepare_proton_affinity("c1ccncc1")
    assert long_run.jobs == 5 and long_run.asks_cost and "5 ORCA geometry optimizations" in long_run.question()
    unmeasured = prepare_proton_affinity("CCl")
    assert unmeasured.asks_cost and unmeasured.question().startswith("This molecule is outside what the benchmark measured")


# --- bond dissociation: the bonds a run computes, stated before it starts --------------------------------------------------------------------------


def test_bond_dissociation_defaults_to_every_bond_class_up_to_the_most_one_run_takes():
    prepared = prepare_bond_dissociation("CCO")
    assert isinstance(prepared, PreparedBondDissociation) and prepared.atoms == (0, 1, 2) and prepared.left_out == () and prepared.jobs == 5
    assert prepared.labels == ("CH3-H, bonded to C", "CH2-H, bonded to C, O", "O-H, bonded to C") and prepared.scope_warnings == ()
    # Which bond is the WEAKEST is what the run finds, so the default is the dialog's own: the first MAX_BONDS classes, in the order it shows them.
    many = prepare_bond_dissociation("CCCCCCO")
    assert len(many.atoms) == bd.MAX_BONDS and many.left_out == ("O-H, bonded to C",)
    assert many.atoms == tuple(b["atom"] for b in bd.describe_bonds("CCCCCCO")[: bd.MAX_BONDS])


def test_a_card_says_which_bonds_are_left_out_and_where_to_choose_them():
    text = prepare_bond_dissociation("CCCCCCO").card_text()
    assert "The bonds it would compute: CH3-H, bonded to C;" in text and "at most 6" in text and "it leaves out: O-H, bonded to C" in text
    assert "Bond dissociation button, where the bonds are chosen" in text and "weakest bond computed" in text
    assert "22 ORCA jobs" in text and "minutes to hours" in text
    # Nothing is left out of a molecule one run can take whole, so nothing is said about it.
    assert "leaves out" not in prepare_bond_dissociation("CCO").card_text()


def test_explicit_bonds_are_the_ones_computed_and_the_rest_are_left_out():
    prepared = prepare_bond_dissociation("CCO", [2])
    assert prepared.atoms == (2,) and prepared.labels == ("O-H, bonded to C",) and prepared.left_out == ("CH3-H, bonded to C", "CH2-H, bonded to C, O")
    assert prepared.jobs == 3


def test_a_molecule_outside_what_was_measured_comes_back_with_its_warning_and_the_question_says_so():
    prepared = prepare_bond_dissociation("CCl")
    assert prepared.scope_warnings and "outside what the benchmark measured" in prepared.question() and "Cl:" in prepared.question()


@pytest.mark.parametrize(
    ("smiles", "message"),
    [
        ("", "Select a molecule with a structure first."),
        ("C[N+](C)(C)C", "Bond dissociation does not apply: a charged or zwitterionic structure"),
        ("O=C=O", "Bond dissociation does not apply: no bond between a heavy atom and a hydrogen"),
    ],
)
def test_a_molecule_the_protocol_cannot_compute_is_refused_with_its_reason(smiles, message):
    refusal = prepare_bond_dissociation(smiles)
    assert isinstance(refusal, RunRefusal) and refusal.message.startswith(message)


def test_more_bonds_than_one_run_takes_is_refused_when_asked_for_explicitly():
    refusal = prepare_bond_dissociation("CCCCCCO", list(range(7)))
    assert isinstance(refusal, RunRefusal) and "at most 6" in refusal.message


def test_the_bond_choices_are_the_dialogs_list_or_the_sentence_that_says_why_not():
    assert [b["atom"] for b in bond_choices("CCO")] == [0, 1, 2]
    assert isinstance(bond_choices(""), RunRefusal) and bond_choices("C[N+](C)(C)C").message.startswith("Bond dissociation does not apply")


def test_bond_dissociation_for_a_molecule_needs_a_structure():
    assert prepare_bond_dissociation_for(None).message == "Select a molecule with a structure first."
    assert isinstance(prepare_bond_dissociation_for(MoleculeModel(display_name="blank")), RunRefusal)
