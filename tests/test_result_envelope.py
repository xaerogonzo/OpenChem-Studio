"""The result envelope: every number the assistant is told carries what gives it meaning.

Run against REAL results from the registry wherever one exists (per-atom, report, structure set,
pH curve, trajectory), because an envelope tested only on hand-built results proves that it reads the
shapes its author imagined. The two kinds with no calculator to run (the always-on descriptor, a
computed alert) are built directly, and the failure shapes are built the way
`DescriptorService._publish_failed` builds them.

**THE SPECTRUM IS THE ONE KIND THAT CANNOT COME FROM THE REGISTRY ON EVERY MACHINE.** The only
registry calculator that makes one without ORCA is `nmr_database`, and it refuses "Database not built"
wherever the shift index has not been built into the data root. It had been built on the machine this
was written on, so the whole file was green there and three spectrum tests failed on CI's clean runner
(measured: the same call under an empty `OPENCHEM_DATA_ROOT` returns that refusal). The shared fixture
therefore uses the suite's `synthetic_nmr_spectrum` on the real aspirin, and a separate test reads the
real database result where the machine has one.
"""

from __future__ import annotations

import json
import math

import pytest
from conftest import synthetic_nmr_spectrum
from rdkit import Chem

from openchem.chem.calculation_input import INPUT_PREFIX
from openchem.chem.engine import ChemistryEngine
from openchem.cli import calculation as cli
from openchem.domain import result_envelope as env
from openchem.domain.common import (
    ATOM_BASIS,
    CATEGORICAL_SCALE,
    RUN_CALC_TYPE,
    RUN_CHARGE,
    RUN_ID,
    RUN_METHOD_BASIS,
    RUN_MULTIPLICITY,
    RUN_PROVIDER,
    RUN_SETTINGS,
    TOTAL,
    CacheState,
    Provenance,
    ScientificResult,
    declare_total,
    decline_total,
)
from openchem.domain.descriptor import DescriptorValue
from openchem.domain.refusal_kinds import (
    INPUT_REQUIRED,
    MissingInput,
    RefusalKind,
    refusal_parameters,
)
from openchem.domain.report import Fact, FactCategory, Basis, ReportResult
from openchem.domain.result_store import ResultIdentity, StoredResult
from openchem.domain.run_lifecycle import RunOutcome, RunState
from openchem.domain.scientific_result import AlertResult, PerAtomDataset
from openchem.domain.turn_snapshot import Freshness, Outcome, ResultsView, classify_results

MOL = "mol-1"
FP = {"drawing": "draw-NOW", "geometry": "geom-NOW"}
ASPIRIN = "CC(=O)Oc1ccccc1C(=O)O"

HEADER_KEYS = {
    "result_id", "name", "calculator", "kind", "freshness", "freshness_note", "outcome", "status",
    "input", "method", "parameters", "caveats",
}


def _stored(result, producer="calc", fingerprint="draw-NOW", calculation_input="drawing", result_id=None):
    from openchem.domain.result_store import result_id_of

    identity = ResultIdentity(
        molecule_uuid=MOL, result_id=result_id or result_id_of(result), calculation_input=calculation_input,
        input_fingerprint=fingerprint, producer=producer,
    )
    return StoredResult(identity=identity, result=result, application_version="9.9")


def _entry(result, *, fresh=True, **kw):
    stored = _stored(result, **kw)
    return classify_results([stored], [stored] if fresh else [], FP)[0]


@pytest.fixture(scope="module")
def real():
    """One real result of each kind a calculator can produce, from the registry, on aspirin."""
    engine = ChemistryEngine()
    registry = cli.build_registry()
    model, _info = cli.build_model(engine, ASPIRIN, conformer=True, seed=1)

    def run(calculator_id):
        definition = registry.get(calculator_id)
        outcome = cli.run_calculator(registry, engine, model, calculator_id, {p.name: p.default for p in definition.parameters})
        assert outcome.result is not None, (calculator_id, outcome)
        return outcome.result

    return {
        "per_atom": run("crippen_logp_contrib"),
        "report": run("elemental_analysis"),
        "spectrum": synthetic_nmr_spectrum(Chem.AddHs(Chem.MolFromSmiles(ASPIRIN)), MOL),
        "structure_set": run("tautomers"),
        "ph_curve": run("hbond_vs_ph"),
        "trajectory": run("molecular_dynamics"),
    }


@pytest.fixture(scope="module")
def every_kind(real):
    built = dict(real)
    built["descriptor"] = DescriptorValue(
        descriptor_id="mol_wt", name="Molecular Weight", units="g/mol", category="physicochemical", provider="rdkit",
        molecule_uuid=MOL, value=180.159, cache_state=CacheState.COMPLETED,
    )
    built["alert"] = AlertResult(
        alert_id="pains", name="PAINS", molecule_uuid=MOL, matched=["catechol_A(92)"],
        cache_state=CacheState.COMPLETED,
    )
    return built


def _refusal(code, kind=None, inapplicable=False, missing=()):
    return PerAtomDataset(
        property_id="p", name="P", units="", method="m", molecule_uuid=MOL, values={}, cache_state=CacheState.FAILED,
        error="The long explanation of why.", error_summary="Needs a density", inapplicable=inapplicable,
        provenance=Provenance(created_by="core", method="p", parameters=refusal_parameters(code, kind, tuple(missing))),
    )


def _numeric_leaves(value, path=()):
    if isinstance(value, bool):
        return
    if isinstance(value, (int, float)):
        yield path, value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from _numeric_leaves(item, path + (key,))
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            yield from _numeric_leaves(item, path + (index,))


# --- the contract every kind keeps ------------------------------------------------------------


def test_exactly_the_eight_stored_kinds_are_supported_and_each_is_exercised(every_kind):
    assert set(every_kind) == set(env.SUPPORTED_KINDS)
    assert {env.kind_of(result) for result in every_kind.values()} == set(env.SUPPORTED_KINDS)


@pytest.mark.parametrize("kind", env.SUPPORTED_KINDS)
def test_every_kind_has_the_whole_header_and_is_json_plain(every_kind, kind):
    envelope = env.envelope_of(_entry(every_kind[kind]))
    assert HEADER_KEYS <= set(envelope), HEADER_KEYS - set(envelope)
    assert envelope["kind"] == kind and envelope["freshness"] == "current" and envelope["outcome"] == "computed"
    assert envelope["input"]["kind"] == "drawing" and envelope["input"]["fingerprint"] == "draw-NOW"
    assert envelope["method"]["application_version"] == "9.9" and "data" in envelope
    json.dumps(envelope)


@pytest.mark.parametrize("kind", env.SUPPORTED_KINDS)
def test_no_number_is_offered_without_a_statement_of_its_units(every_kind, kind):
    """The structural rule: wherever a block carries values, the block says what they are in."""
    envelope = env.envelope_of(_entry(every_kind[kind]))
    data = envelope["data"]
    if kind in ("per_atom", "spectrum", "ph_curve", "trajectory", "descriptor"):
        assert "units" in data and isinstance(data["units"], str), kind
    if kind in ("report", "ph_curve"):
        for fact in data.get("facts", []):
            assert "units" in fact and "value" in fact and isinstance(fact["value"], str), fact
    if kind in ("alert", "structure_set"):
        assert not [path for path, _ in _numeric_leaves(data) if path[0] not in ("count", "truncated", "total_available")]


@pytest.mark.parametrize("kind", env.SUPPORTED_KINDS)
def test_outside_data_the_only_numbers_are_settings_a_conformer_index_and_a_unit_named_energy(every_kind, kind):
    """`parameters` are the settings the run used, named as the calculator names them (their meaning is
    on the calculator's card); the conformer energy names its unit in its key."""
    envelope = env.envelope_of(_entry(every_kind[kind]))
    outside = {k: v for k, v in envelope.items() if k != "data"}
    allowed = {("input", "conformer_index"), ("input", "conformer_energy_kcal_mol")}
    assert not [path for path, _ in _numeric_leaves(outside) if path[0] != "parameters" and path not in allowed]


# --- kinds ----------------------------------------------------------------------------------------


def test_a_real_per_atom_result_says_which_atoms_and_how_to_read_the_total(real):
    envelope = env.envelope_of(_entry(real["per_atom"], calculation_input="drawing"))
    data = envelope["data"]
    assert data["count"] == len(real["per_atom"].values) and data["atom_basis"]
    assert data["values"][0][0] == min(real["per_atom"].values)
    assert "min" in data["statistics_over_all_values"] and ("declared_total" in data or "no_total" in data)
    assert "atom_index_space" in data


def test_a_long_per_atom_result_is_a_sample_plus_statistics_over_everything():
    values = {i: float(i) for i in range(500)}
    result = PerAtomDataset(property_id="p", name="P", units="e", method="m", molecule_uuid=MOL, values=values)
    data = env.envelope_of(_entry(result))["data"]
    assert data["count"] == 500 and len(data["values"]) == 60 and data["truncated"] == 440
    assert data["statistics_over_all_values"] == {"min": 0.0, "max": 499.0, "mean": 249.5}
    assert data["units"] == "e"


def test_a_categorical_dataset_offers_no_statistics_because_its_numbers_are_ids():
    result = PerAtomDataset(
        property_id="p", name="Rings", units="", method="m", molecule_uuid=MOL, values={0: 1, 1: 1, 2: 2},
        provenance=Provenance(created_by="core", method="m", parameters={"scale": CATEGORICAL_SCALE}),
    )
    data = env.envelope_of(_entry(result))["data"]
    assert data["categorical"] is True and "statistics_over_all_values" not in data


def test_a_declared_total_is_passed_on_and_a_declined_one_gives_its_reason():
    declared = PerAtomDataset(
        property_id="p", name="LogP", units="", method="m", molecule_uuid=MOL, values={0: 0.5},
        provenance=Provenance(created_by="core", method="m", parameters={TOTAL: declare_total(1.31, "LogP (Crippen)")}),
    )
    declined = PerAtomDataset(
        property_id="p", name="Ecc", units="", method="m", molecule_uuid=MOL, values={0: 5},
        provenance=Provenance(created_by="core", method="m", parameters={TOTAL: decline_total("a graph distance has no sum")}),
    )
    assert env.envelope_of(_entry(declared))["data"]["declared_total"]["label"] == "LogP (Crippen)"
    assert env.envelope_of(_entry(declined))["data"]["no_total"] == "a graph distance has no sum"


def test_the_atom_basis_a_producer_declared_is_carried():
    result = PerAtomDataset(
        property_id="p", name="X", units="", method="m", molecule_uuid=MOL, values={0: 1.0},
        provenance=Provenance(created_by="core", method="m", parameters={ATOM_BASIS: "explicit_h"}),
    )
    assert env.envelope_of(_entry(result))["data"]["atom_basis"] == "explicit_h"


def test_a_geometry_result_says_which_conformer_and_never_reads_as_the_drawing():
    result = PerAtomDataset(
        property_id="p", name="Q", units="e", method="m", molecule_uuid=MOL, values={0: 0.1},
        provenance=Provenance(created_by="core", method="m", parameters={
            INPUT_PREFIX + "source": "automatic_lowest_energy", INPUT_PREFIX + "conformer_index": 3,
            INPUT_PREFIX + "conformer_energy": -12.5, INPUT_PREFIX + "force_field": "MMFF94",
            INPUT_PREFIX + "parameters": {"pH": 7.4},
        }),
    )
    envelope = env.envelope_of(_entry(result, calculation_input="geometry", fingerprint="geom-NOW"))
    assert envelope["input"] == {
        "kind": "geometry", "fingerprint": "geom-NOW", "source": "automatic_lowest_energy",
        "conformer_index": 3, "conformer_energy_kcal_mol": -12.5, "force_field": "MMFF94",
    }
    assert envelope["parameters"] == {"pH": 7.4}


def test_a_report_carries_its_facts_with_units_evidence_and_the_reports_own_caveats(real):
    envelope = env.envelope_of(_entry(real["report"]))
    data = envelope["data"]
    assert data["count"] == len(real["report"].facts) and data["facts"]
    assert all({"label", "value", "units", "basis", "source"} <= set(f) for f in data["facts"])


def test_a_reports_assumptions_and_limitations_are_caveats_not_dropped():
    report = ReportResult(
        report_id="r", name="R", molecule_uuid=MOL, assumptions=("assumes neutral",), limitations=("organic only",),
        facts=(Fact(FactCategory.COMPOSITION if hasattr(FactCategory, "COMPOSITION") else list(FactCategory)[0],
                    "Mass", 180.159, "180.159", "RDKit", Basis.DETERMINISTIC, units="g/mol"),),
    )
    caveats = env.envelope_of(_entry(report))["caveats"]
    assert "assumes neutral" in caveats and "organic only" in caveats


def test_fact_evidence_is_capped_but_limitations_never_are():
    fact = Fact(list(FactCategory)[0], "X", 1, "1", "s", Basis.HEURISTIC, evidence=tuple(f"e{i}" for i in range(9)),
                limitations=tuple(f"l{i}" for i in range(7)))
    report = ReportResult(report_id="r", name="R", molecule_uuid=MOL, facts=(fact,))
    rendered = env.envelope_of(_entry(report))["data"]["facts"][0]
    assert rendered["evidence"] == ["e0", "e1", "e2"] and len(rendered["limitations"]) == 7


def test_a_report_with_many_facts_says_how_many_were_left_out():
    fact = Fact(list(FactCategory)[0], "X", 1, "1", "s", Basis.DETERMINISTIC)
    report = ReportResult(report_id="r", name="R", molecule_uuid=MOL, facts=tuple(fact for _ in range(100)))
    data = env.envelope_of(_entry(report))["data"]
    assert data["count"] == 100 and len(data["facts"]) == 40 and data["truncated"] == 60


def test_a_spectrum_lists_its_peaks_with_their_element_and_units(real):
    data = env.envelope_of(_entry(real["spectrum"]))["data"]
    assert data["units"] and data["peak_columns"] == ["atom_index", "element", "value"]
    assert all(len(peak) == 3 and isinstance(peak[1], str) for peak in data["peaks"])


def test_the_real_database_spectrum_reads_the_same_way_where_the_machine_has_the_database():
    """The arm that needs the NMR shift index in the data root. Skipped, and says so, where it is not built."""
    engine = ChemistryEngine()
    registry = cli.build_registry()
    model, _info = cli.build_model(engine, ASPIRIN, conformer=True, seed=1)
    definition = registry.get("nmr_database")
    outcome = cli.run_calculator(registry, engine, model, "nmr_database", {p.name: p.default for p in definition.parameters})
    if outcome.result is None or outcome.result.cache_state is not CacheState.COMPLETED:
        pytest.skip("the NMR shift database is not built on this machine, so nmr_database refuses")
    envelope = env.envelope_of(_entry(outcome.result))
    assert HEADER_KEYS <= set(envelope) and envelope["kind"] == "spectrum" and envelope["outcome"] == "computed"
    data = envelope["data"]
    assert data["units"] and data["peak_columns"] == ["atom_index", "element", "value"] and data["peaks"]


def test_a_structure_set_gives_counts_and_labels_and_says_what_it_leaves_out(real):
    data = env.envelope_of(_entry(real["structure_set"]))["data"]
    assert data["count"] == len(real["structure_set"].entries) and "labels" in data and "not included" in data["note"]


def test_a_ph_curve_gives_its_range_series_statistics_and_a_sample(real):
    data = env.envelope_of(_entry(real["ph_curve"]))["data"]
    assert data["points"] == len(real["ph_curve"].ph_values) and data["x_range"][0] <= data["x_range"][1]
    assert data["series"] and all("sampled_points" in s and "min" in s for s in data["series"].values())


def test_a_trajectory_gives_a_summary_with_units_in_its_keys(real):
    data = env.envelope_of(_entry(real["trajectory"]))["data"]
    assert data["frames"] == len(real["trajectory"].frames) and "time_range_fs" in data and "energy_kcal_mol" in data


# --- what is not offered ----------------------------------------------------------------------------


def test_a_refused_result_has_its_refusal_and_no_data():
    result = _refusal(INPUT_REQUIRED, RefusalKind.NEEDS_INPUT, missing=[MissingInput("loading_density_g_cm3", "g/cm3")])
    envelope = env.envelope_of(_entry(result))
    assert envelope["outcome"] == "refused" and envelope["status"] == "needs_input" and "data" not in envelope
    assert envelope["refusal"] == {
        "code": INPUT_REQUIRED, "kind": "needs_input", "summary": "Needs a density",
        "detail": "The long explanation of why.",
        "missing_inputs": [{"parameter": "loading_density_g_cm3", "units": "g/cm3", "problem": "missing"}],
    }


def test_a_failed_result_has_no_data_and_is_not_a_low_value():
    result = PerAtomDataset(property_id="p", name="P", units="e", method="m", molecule_uuid=MOL, values={},
                            cache_state=CacheState.FAILED, error="boom")
    envelope = env.envelope_of(_entry(result))
    assert envelope["outcome"] == "failed" and "data" not in envelope and envelope["refusal"]["detail"] == "boom"


def test_a_result_for_an_earlier_structure_says_so_in_its_header_and_its_caveats():
    result = PerAtomDataset(property_id="p", name="P", units="e", method="m", molecule_uuid=MOL, values={0: 1.0})
    envelope = env.envelope_of(_entry(result, fresh=False, fingerprint="draw-BEFORE"))
    assert envelope["freshness"] == "historical" and "earlier structure" in envelope["freshness_note"]
    assert any("earlier structure" in caveat for caveat in envelope["caveats"])


def test_a_kind_nobody_taught_the_serialiser_is_unsupported_and_offers_no_numbers():
    from dataclasses import dataclass

    @dataclass(frozen=True, kw_only=True)
    class Ninth(ScientificResult):
        result_id: str = "ninth"
        secret: float = 42.0

    stored = _stored(Ninth(), result_id="ninth")
    envelope = env.envelope_of(classify_results([stored], [stored], FP)[0])
    assert envelope["kind"] == "unsupported" and "data" not in envelope and "no serialiser" in envelope["unsupported"]
    assert 42.0 not in [leaf for _path, leaf in _numeric_leaves(envelope)]


def test_numbers_are_six_significant_figures_and_non_finite_ones_are_named():
    result = PerAtomDataset(property_id="p", name="P", units="e", method="m", molecule_uuid=MOL,
                            values={0: 1 / 3, 1: math.nan, 2: math.inf})
    values = dict(env.envelope_of(_entry(result))["data"]["values"])
    assert values[0] == 0.333333 and values[1] == "nan" and values[2] == "inf"


def test_long_text_is_cut_and_says_so():
    long_name = "x" * 1000
    result = PerAtomDataset(property_id="p", name=long_name, units="e", method="m", molecule_uuid=MOL, values={0: 1.0})
    name = env.envelope_of(_entry(result))["name"]
    assert len(name) == 400 and name.endswith("…")


# --- size ---------------------------------------------------------------------------------------------


def test_each_cap_step_is_smaller_and_the_header_survives_the_smallest():
    result = PerAtomDataset(property_id="p", name="P", units="e", method="m", molecule_uuid=MOL,
                            values={i: float(i) for i in range(2000)})
    sizes = [len(json.dumps(env.envelope_of(_entry(result), caps))) for caps in env.CAP_STEPS]
    assert sizes == sorted(sizes, reverse=True) and sizes[0] > sizes[-1]
    smallest = env.envelope_of(_entry(result), env.CAP_STEPS[-1])
    assert HEADER_KEYS <= set(smallest) and smallest["data"]["units"] == "e" and smallest["data"]["count"] == 2000


# --- the views --------------------------------------------------------------------------------------------


def test_a_results_view_lists_results_and_what_is_missing_and_warns_against_inventing():
    entry = _entry(PerAtomDataset(property_id="p", name="P", units="e", method="m", molecule_uuid=MOL, values={0: 1.0}))
    view = ResultsView(turn_id="t", molecule_uuid=MOL, entries=(entry,), not_run=("pka",), only_not_current=("logd",), truncated=2)
    out = env.results_view_envelope(view)
    assert out["not_run"] == ["pka"] and out["only_not_current"] == ["logd"] and out["left_out_for_length"] == 2
    assert out["results"][0]["result_id"] == "p" and "never zero" in out["note"]
    json.dumps(out)


def test_a_completed_runs_outcome_carries_the_result_it_produced():
    stored = _stored(PerAtomDataset(property_id="p", name="P", units="e", method="m", molecule_uuid=MOL, values={0: 1.0}))
    out = env.outcome_envelope(RunOutcome("r1", "calc", RunState.COMPLETED, "completed", status="ready", stored=stored))
    assert out["state"] == "completed" and out["has_number"] is True
    assert out["result"]["freshness"] == "current" and out["result"]["data"]["units"] == "e"


def test_a_refused_runs_outcome_carries_the_refusal_and_not_a_number():
    stored = _stored(_refusal(INPUT_REQUIRED, RefusalKind.NEEDS_INPUT))
    out = env.outcome_envelope(RunOutcome("r1", "calc", RunState.REFUSED, "declined", status="needs_input", stored=stored))
    assert out["has_number"] is False and out["result"]["outcome"] == "refused" and "data" not in out["result"]


def test_an_outcome_with_no_result_is_just_its_state_and_message():
    out = env.outcome_envelope(RunOutcome("r1", "calc", RunState.PREVIEWED, "needs a person"))
    assert "result" not in out and out["state"] == "previewed" and out["message"] == "needs a person"


# --- the settings a result was run with --------------------------------------------------------------------


def _qc_descriptor(parameters):
    return DescriptorValue(
        descriptor_id="orca.scf_energy", name="SCF Energy", units="Hartree", category="quantum_chemistry",
        provider="orca", molecule_uuid=MOL, value=-154.987654, cache_state=CacheState.COMPLETED,
        provenance=Provenance(created_by="core", method="orca", parameters=parameters),
    )


def test_a_service_runs_settings_are_shown_without_the_prefix_and_the_producers_working_is_not():
    envelope = env.envelope_of(_entry(_qc_descriptor({
        "orca_version": "6.1.1", "caveat": "no diffuse functions",
        RUN_CALC_TYPE: "sp", RUN_METHOD_BASIS: "B3LYP def2-SVP", RUN_CHARGE: -1, RUN_MULTIPLICITY: 2,
        RUN_PROVIDER: "orca", RUN_ID: "run-1",
    })))
    assert envelope["parameters"] == {
        "calc_type": "sp", "method_basis": "B3LYP def2-SVP", "charge": -1, "multiplicity": 2,
    }
    # In the order the panel shows its fields, not however a dict happened to be built.
    assert list(envelope["parameters"]) == ["calc_type", "method_basis", "charge", "multiplicity"]
    json.dumps(envelope, allow_nan=False)


def test_a_result_with_no_recorded_settings_has_none_rather_than_a_guess():
    assert env.envelope_of(_entry(_qc_descriptor({"orca_version": "6.1.1"})))["parameters"] == {}


def test_a_producers_recorded_caveat_is_a_caveat_and_not_a_setting():
    """The Koopmans hardness that inverts ammonia and phosphine, a Fukui f+ taken on an unbound anion: the
    producer records the warning in its provenance, and before this a model was sent the number without it,
    because a descriptor and a per-atom dataset have no `assumptions` field to carry one."""
    envelope = env.envelope_of(_entry(_qc_descriptor({
        "orca_version": "6.1.1", "caveat": "no diffuse functions", RUN_CALC_TYPE: "sp",
    })))
    assert envelope["caveats"] == ["no diffuse functions"]
    assert "caveat" not in envelope["parameters"]
    json.dumps(envelope, allow_nan=False)


def test_a_result_with_no_recorded_caveat_has_none():
    assert env.envelope_of(_entry(_qc_descriptor({"orca_version": "6.1.1"})))["caveats"] == []


@pytest.mark.parametrize("recorded", ["", "   ", None, 3, ["a caveat"], {"a": "caveat"}])
def test_only_a_non_empty_string_is_taken_for_a_caveat(recorded):
    """A project saved by something else can hold anything under the key; a number is not a warning."""
    assert env.envelope_of(_entry(_qc_descriptor({"caveat": recorded})))["caveats"] == []


def test_a_recorded_caveat_comes_after_the_freshness_note_and_a_runaway_one_is_cut():
    long_caveat = "diffuse " * 400
    envelope = env.envelope_of(_entry(_qc_descriptor({"caveat": long_caveat}), fresh=False))
    assert len(envelope["caveats"]) == 2
    assert envelope["caveats"][0] == envelope["freshness_note"] != ""
    assert len(envelope["caveats"][1]) == env.RECORDED_CAVEAT_LIMIT and envelope["caveats"][1].endswith("…")
    smallest = env.envelope_of(_entry(_qc_descriptor({"caveat": long_caveat})), env.CAP_STEPS[-1])["caveats"]
    assert len(smallest[0]) == env.RECORDED_CAVEAT_LIMIT


def test_a_producers_caveat_longer_than_a_header_caveat_arrives_whole_at_every_cap():
    """The Fukui caveat is 492 characters with no warning on and 1320 with all of them, and its last sentence says the calculation is not
    validated. Cut at the 400 a header caveat gets, that sentence never reached a model; the caps shrink rows, not what a number means."""
    recorded = " ".join(f"Sentence {n} says something a reader needs about the number, in about as many words as a real caveat does." for n in range(11))
    assert env.FULL.text < len(recorded) < env.RECORDED_CAVEAT_LIMIT
    for caps in env.CAP_STEPS:
        assert env.envelope_of(_entry(_qc_descriptor({"caveat": recorded})), caps)["caveats"] == [recorded]


def test_a_registry_dialogs_dict_wins_over_a_run_setting_of_the_same_name():
    envelope = env.envelope_of(_entry(_qc_descriptor({
        INPUT_PREFIX + "parameters": {"charge": 3}, RUN_CHARGE: -1, RUN_CALC_TYPE: "sp",
    })))
    assert envelope["parameters"] == {"charge": 3, "calc_type": "sp"}


def test_recorded_settings_are_bounded_and_say_what_was_left_out():
    settings = {
        "method_basis": "B3LYP " + "x" * 5000, "window": list(range(500)), "ratio": 0.123456789,
        "bad": math.nan, "nested": {"a": 1},
    }
    settings.update({f"s{i:03d}": i for i in range(100)})
    result = _qc_descriptor({INPUT_PREFIX + "parameters": settings})

    envelope = env.envelope_of(_entry(result))
    shown = envelope["parameters"]
    assert len(shown) == env.MAX_SETTINGS
    assert len(shown["method_basis"]) == 400 and shown["method_basis"].endswith("…")
    assert len(shown["window"]) == env.FULL.items
    assert shown["ratio"] == 0.123456789  # a setting is not a measurement: no rounding
    assert shown["bad"] == "nan" and shown["nested"] == "{'a': 1}"
    assert f"{len(settings) - env.MAX_SETTINGS} further recorded settings were left out for length" in envelope["caveats"]
    json.dumps(envelope, allow_nan=False)

    # Settings are part of what a number means: shrinking the reply cuts their text, never their names.
    smallest = env.envelope_of(_entry(result), env.CAP_STEPS[-1])["parameters"]
    assert len(smallest) == env.MAX_SETTINGS and len(smallest["method_basis"]) == 60


# --- drift guards ------------------------------------------------------------------------------------------


def test_the_run_vocabulary_is_the_one_the_spectra_already_carry():
    """`QuantumChemistryService._stamped` wrote these literal keys first (all but `run_id`, which only
    the descriptors carry); panels and tests read them, so a rename here is not a local change."""
    assert RUN_SETTINGS == ("run_calc_type", "run_method_basis", "run_charge", "run_multiplicity")
    assert (RUN_PROVIDER, RUN_ID) == ("run_provider", "run_id")


def test_the_provenance_keys_read_here_are_the_ones_the_calculation_path_writes():
    assert env.INPUT_SOURCE_KEY == INPUT_PREFIX + "source"
    assert env.INPUT_PARAMETERS_KEY == INPUT_PREFIX + "parameters"
    assert env.INPUT_CONFORMER_INDEX_KEY == INPUT_PREFIX + "conformer_index"
    assert env.INPUT_CONFORMER_ENERGY_KEY == INPUT_PREFIX + "conformer_energy"
    assert env.INPUT_FORCE_FIELD_KEY == INPUT_PREFIX + "force_field"
