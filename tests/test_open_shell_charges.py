"""Charge models on radicals (item 13 of docs/OPEN_SHELL_AND_HYPERVALENT_COVERAGE_DESIGN.md): the preregistered rule, the shared open-shell predicate and what each consumer does with it.

The rule is held before it meets a result (`benchmarks/open_shell/charge_models_rule.py`, committed ahead of the ORCA run), so every verdict here is one of its lines.
"""

from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

import pytest
from rdkit import Chem

from openchem.chem.open_shell import SPIN_PROP, is_open_shell

_PATH = Path(__file__).parent.parent / "benchmarks" / "open_shell" / "charge_models_rule.py"
_spec = importlib.util.spec_from_file_location("charge_models_rule", _PATH)
rule = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = rule
_spec.loader.exec_module(rule)

# --- the metric ------------------------------------------------------------------------------------------------------------------------------

PAIR = rule.Pair("p", "C[CH2]", "CC", 2, ((0, 0), (1, 1)))


def _rows(radical_errors, parent_errors):
    return [rule.AtomRow(i, i, er, ep) for i, (er, ep) in enumerate(zip(radical_errors, parent_errors))]


def test_the_excess_is_the_radical_error_minus_the_parent_error_per_atom_and_e_is_the_largest():
    rows = rule.atom_rows(PAIR, {0: 0.30, 1: -0.10}, {0: 0.10, 1: -0.05}, {0: 0.20, 1: 0.10}, {0: 0.15, 1: 0.10})
    assert [round(r.error_radical, 6) for r in rows] == [0.2, 0.05]
    assert [round(r.error_parent, 6) for r in rows] == [0.05, 0.0]
    assert [round(r.excess, 6) for r in rows] == [0.15, 0.05]
    assert rule.verdict(rows) == (rule.FAIL, pytest.approx(0.15))


def test_the_boundary_is_inclusive_and_just_above_it_fails():
    assert rule.verdict(_rows([0.75], [0.70]))[0] == rule.PASS, "0.75 - 0.70 is 0.05 on paper and 0.050000000000000044 in binary"
    assert rule.verdict(_rows([0.05], [0.0]))[0] == rule.PASS
    assert rule.verdict(_rows([0.0501], [0.0]))[0] == rule.FAIL


def test_a_model_better_on_the_radical_than_on_its_parent_passes_and_says_nothing_about_accuracy():
    outcome, worst = rule.verdict(_rows([0.30], [0.80]))
    assert outcome == rule.PASS and worst < 0, "a negative excess is not a statement that the radical's charge is right"


@pytest.mark.parametrize("missing", [None, math.nan, math.inf])
def test_any_missing_or_non_finite_number_is_inconclusive_never_a_pass(missing):
    rows = rule.atom_rows(PAIR, {0: 0.1, 1: missing}, {0: 0.1, 1: 0.1}, {0: 0.1, 1: 0.1}, {0: 0.1, 1: 0.1})
    assert rule.verdict(rows) == (rule.INCONCLUSIVE, None)
    assert rule.verdict([]) == (rule.INCONCLUSIVE, None)
    assert rule.verdict(rule.atom_rows(PAIR, {0: 0.1}, {0: 0.1, 1: 0.1}, {0: 0.1, 1: 0.1}, {0: 0.1, 1: 0.1}))[0] == rule.INCONCLUSIVE, "an atom absent from a charge map is missing data"


# --- the pairs and their atom maps -----------------------------------------------------------------------------------------------------------


def _heavy(smiles: str) -> int:
    return Chem.MolFromSmiles(smiles).GetNumHeavyAtoms()


def test_every_preregistered_pair_has_a_valid_map_with_matching_elements():
    for pair in rule.PAIRS:
        rule.validate_map(pair, _heavy(pair.radical), _heavy(pair.parent))
        radical, parent = Chem.MolFromSmiles(pair.radical), Chem.MolFromSmiles(pair.parent)
        for r, p in pair.atom_map:
            assert radical.GetAtomWithIdx(r).GetSymbol() == parent.GetAtomWithIdx(p).GetSymbol(), f"{pair.name}: {r}->{p}"
        assert is_open_shell(radical) and not is_open_shell(parent), pair.name


@pytest.mark.parametrize(
    "atom_map, message",
    [((), "no atom map"), (((0, 0), (0, 1)), "two partners"), (((0, 0), (1, 0)), "two radical atoms"), (((0, 0), (1, 5)), "outside"), (((0, 0),), "every heavy atom")],
)
def test_a_missing_ambiguous_or_partial_map_is_refused(atom_map, message):
    with pytest.raises(ValueError, match=message):
        rule.validate_map(rule.Pair("x", "CC", "CC", 2, atom_map), 2, 2)


def test_the_descriptive_species_are_outside_the_statistic():
    drawn = {item.smiles for item in rule.DESCRIPTIVE}
    paired = {pair.radical for pair in rule.PAIRS}
    assert drawn.isdisjoint(paired) and "O=O" in drawn


# --- the open-shell predicate ----------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("smiles", ["[CH3]", "[OH]", "[CH2]", "[N]=O", "[O][O]", "O=O", "S=S"])
def test_the_predicate_holds_every_open_shell_drawing_including_O2_drawn_closed_shell(smiles):
    assert is_open_shell(Chem.MolFromSmiles(smiles))


@pytest.mark.parametrize("smiles", ["O", "CCO", "N#N", "c1ccccc1"])
def test_it_does_not_hold_closed_shell_molecules(smiles):
    assert not is_open_shell(Chem.MolFromSmiles(smiles))


def test_a_stated_multiplicity_above_one_makes_an_ordinary_drawing_open_shell_and_a_stated_singlet_carbene_stays_held():
    water = Chem.MolFromSmiles("O")
    water.SetProp(SPIN_PROP, "3")
    assert is_open_shell(water)
    carbene = Chem.MolFromSmiles("[CH2]")
    carbene.SetProp(SPIN_PROP, "1")
    assert is_open_shell(carbene), "drawn with unpaired electrons and unmeasured: the guard holds it"


# --- the measured verdicts reach every consumer ---------------------------------------------------------------------------------------------------

import json

from openchem.chem import geometry_charges as gc
from openchem.chem import open_shell_charges as osc
from openchem.chem.charge_evaluation import EEM, GASTEIGER, QEQ, evaluate_charges
from openchem.chem.conformer_providers import GenerationOptions, RDKitConformerProvider, search_conformers
from openchem.chem.dipole import compute_dipole_moment
from openchem.chem.electronic_properties import compute_orbital_electronegativity
from openchem.chem.surface_analysis import surface_areas

RESULT = json.loads((Path(__file__).parent.parent / "benchmarks" / "open_shell" / "charge_models_result.json").read_text())


def _conformer(smiles: str) -> Chem.Mol:
    return search_conformers(RDKitConformerProvider(random_seed=1), Chem.MolFromSmiles(smiles), True, GenerationOptions(max_embeddings=10, embedding_batch_size=5)).pool[0][0]


RADICALS = ["[CH3]", "C[CH2]", "O=O"]
IONESCU = (gc.EEM_IONESCU2013_E_MPA_631GS_GAS, gc.EEM_IONESCU2013_E_MPA_631GSS_GAS)


def test_the_stored_verdicts_are_the_ones_the_committed_result_measured():
    verdicts = RESULT["verdicts"]
    for model, excess in {**osc.FAILED_MODELS, **osc.PASSED_MODELS}.items():
        entry = verdicts[f"hirshfeld:{model}"]
        assert round(entry["E"], 3) == excess, model
        assert (entry["verdict"] == "FAIL") == (model in osc.FAILED_MODELS), model
    assert osc.LIMIT_E == rule.THRESHOLD_E
    assert set(osc.FAILED_MODELS) | set(osc.PASSED_MODELS) == set(rule.MEASURED_MODELS)
    assert (GASTEIGER, EEM, QEQ, *IONESCU) == tuple(rule.MEASURED_MODELS) or set((GASTEIGER, EEM, QEQ, *IONESCU)) == set(rule.MEASURED_MODELS), "the codes written out here are the models' own"


@pytest.mark.parametrize("smiles", RADICALS)
@pytest.mark.parametrize("model", [GASTEIGER, EEM, *IONESCU])
def test_a_model_that_failed_gives_no_charges_for_a_radical_and_says_why(smiles, model):
    mol = _conformer(smiles)
    if model == GASTEIGER or model == EEM:
        evaluation = evaluate_charges(mol, model)
        assert evaluation.charges is None and evaluation.refusal == osc.REFUSAL_CODE and "no spin-dependent term" in evaluation.message
    if model != GASTEIGER:
        dataset = gc.compute_geometry_charges(mol, "u", {"method": model})
        assert dataset.provenance.parameters["refusal"] == "REFUSE_UNPAIRED_ELECTRON" and dataset.inapplicable and "no spin-dependent term" in dataset.error


@pytest.mark.parametrize("smiles", RADICALS)
def test_qeq_passed_so_it_computes_and_carries_the_note(smiles):
    evaluation = evaluate_charges(_conformer(smiles), QEQ)
    assert evaluation.charges is not None and any("Spin is not modelled" in note for note in evaluation.notes)


@pytest.mark.parametrize("smiles", ["CCO", "O", "c1ccccc1", "N#N"])
def test_closed_shell_molecules_are_unchanged(smiles):
    mol = _conformer(smiles)
    for model in (GASTEIGER, EEM, QEQ):
        evaluation = evaluate_charges(mol, model)
        assert evaluation.charges is not None and not any("Spin" in note for note in evaluation.notes)
    for model in IONESCU:
        refused = gc.compute_geometry_charges(mol, "u", {"method": model}).provenance.parameters.get("refusal", "")
        assert refused != "REFUSE_UNPAIRED_ELECTRON"


@pytest.mark.parametrize(
    "model, smiles",
    [(gc.EEM_NEEMP2016_CCD_GEN_NPA, "[CH3]"), (gc.EEM_NEEMP2016_CCD_GEN_NPA, "O=O"), (gc.EEM_JIROUSKOVA2009_B3LYP_MK, "C[S]"), (gc.EEM_JIROUSKOVA2009_B3LYP_MK, "S=S")],
)
def test_the_typed_eem_models_keep_refusing_an_unpaired_electron_including_a_triplet_drawn_closed_shell(model, smiles):
    """Jiroukova's model covers only Cl, Br and S, so the radicals here contain sulfur: a radical without one is refused for its scope (a different, earlier refusal)."""
    dataset = gc.compute_geometry_charges(_conformer(smiles), "u", {"method": model})
    assert dataset.provenance.parameters["refusal"] == "REFUSE_UNPAIRED_ELECTRON"


@pytest.mark.parametrize("smiles", RADICALS)
def test_the_dipole_refuses_a_failed_model_and_carries_the_note_for_qeq(smiles):
    mol = _conformer(smiles)
    for model in (GASTEIGER, EEM):
        report = compute_dipole_moment(mol, "u", {"charge_model": model})
        assert report.inapplicable and "no spin-dependent term" in (report.error or "")
    qeq = compute_dipole_moment(mol, "u", {"charge_model": QEQ})
    assert not qeq.inapplicable and any("Spin is not modelled" in line for line in qeq.matched)


def test_orbital_electronegativity_and_the_surface_charge_split_do_not_use_gasteiger_on_a_radical():
    radical, closed = _conformer("C[CH2]"), _conformer("CC")
    for component in ("sigma", "pi"):
        refused = compute_orbital_electronegativity(radical, "u", {"component": component})
        assert refused.inapplicable and refused.provenance.parameters["refusal"] == osc.REFUSAL_CODE
    assert not compute_orbital_electronegativity(closed, "u", {"component": "sigma"}).inapplicable
    areas = surface_areas(radical)
    assert areas["asa_positive"] is None and areas["asa_negative"] is None and areas["asa"] > 0, "the geometry-only areas stay"
    assert surface_areas(closed)["asa_positive"] is not None


def test_the_always_on_and_ph_gasteiger_charges_refuse_a_radical():
    from openchem.chem.descriptor_providers import RDKitDescriptorProvider, compute_gasteiger_charge_at_ph

    radical = _conformer("[CH3]")
    datasets = {d.property_id: d for d in RDKitDescriptorProvider().compute_per_atom(radical, "u")}
    assert datasets["gasteiger_charge"].inapplicable and "no spin-dependent term" in datasets["gasteiger_charge"].error
    assert not datasets["crippen_logp_contrib"].inapplicable if hasattr(datasets["crippen_logp_contrib"], "inapplicable") else True
    refused = compute_gasteiger_charge_at_ph(radical, "u", {"pH": 7.4})
    assert refused.inapplicable and refused.provenance.parameters["refusal"] == osc.REFUSAL_CODE
    closed = {d.property_id: d for d in RDKitDescriptorProvider().compute_per_atom(_conformer("CC"), "u")}
    assert not closed["gasteiger_charge"].inapplicable and closed["gasteiger_charge"].values


def test_the_esp_pane_declines_gasteiger_on_a_radical_and_states_the_qeq_note(qapp):
    from test_qm_surfaces import FakeBackend, _FakeSurfaceService

    from openchem.chem.engine import ChemistryEngine
    from openchem.ui.widgets.esp_compare_widget import EspCompareWidget

    engine = ChemistryEngine()
    left = FakeBackend()
    widget = EspCompareWidget(engine, _FakeSurfaceService(), point_charge_backend=left, qm_backend=FakeBackend())
    try:
        molblock = engine.mol_to_molblock(_conformer("[CH3]"))
        widget.set_molecule("m", molblock)
        assert left.surfaces[-1] is None and "no spin-dependent term" in widget._point_charge_caption.text()
        widget._charge_model_combo.setCurrentIndex(widget._charge_model_combo.findData(QEQ))
        assert left.surfaces[-1] is not None and "Spin is not modelled" in widget._point_charge_caption.text()
    finally:
        widget.deleteLater()


# --- the reference tables the benchmark accepts -----------------------------------------------------------------------------------------------

_RUNNER_PATH = Path(__file__).parent.parent / "benchmarks" / "open_shell" / "charge_models.py"
_runner_spec = importlib.util.spec_from_file_location("charge_models_runner", _RUNNER_PATH)
runner = importlib.util.module_from_spec(_runner_spec)
sys.modules[_runner_spec.name] = runner
_runner_spec.loader.exec_module(runner)

CH3_OUTPUT = (Path(__file__).parent / "fixtures" / "orca" / "ch3_radical_charges_excerpt.out").read_text()


def test_the_hirshfeld_and_loewdin_tables_of_a_real_radical_output_are_read_in_atom_order_and_sum_to_the_net_charge():
    from openchem.chem.orca_engine import parse_hirshfeld_tables

    hirshfeld = parse_hirshfeld_tables(CH3_OUTPUT)[0]
    loewdin = runner.parse_loewdin(CH3_OUTPUT)
    assert [e for e, _ in hirshfeld] == [e for e, _ in loewdin] == ["C", "H", "H", "H"]
    assert hirshfeld[0][1] == pytest.approx(-0.081755) and loewdin[0][1] == pytest.approx(-0.044613)
    assert abs(sum(q for _, q in hirshfeld)) < runner.CHARGE_SUM_TOLERANCE and abs(sum(q for _, q in loewdin)) < runner.CHARGE_SUM_TOLERANCE


def test_a_closed_shell_loewdin_table_without_a_spin_column_is_read_and_a_missing_one_is_none():
    closed = "LOEWDIN ATOMIC CHARGES\n----------------------\n   0 O :   -0.200000\n   1 H :    0.100000\n   2 H :    0.100000\n\nnext"
    assert runner.parse_loewdin(closed) == [("O", -0.2), ("H", 0.1), ("H", 0.1)]
    assert runner.parse_loewdin("no table here") is None
