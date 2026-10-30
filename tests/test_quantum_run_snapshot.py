"""The ORCA runs the assistant may read (`openchem.domain.quantum_run_snapshot`) and the way they are told (`result_envelope.run_envelope`).

The results inside the runs are the real provider's: the SCF energy of `test_orca_engine`'s single-point output, and the vibrational analysis of the committed real `water_freq.out`. The
refusals asserted here are the ones a model could be misled by: a failed job read as a result, an infrared spectrum read as "no peaks", a number from an earlier structure read as current,
the structure sent to ORCA leaking into a reply, and a run changing under a reply that is already streaming.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest
import test_orca_engine as orca_tests
from rdkit import Chem
from rdkit.Chem import AllChem
from test_result_envelope import _entry

from openchem.chem.orca_engine import OrcaQuantumEngineProvider
from openchem.domain.common import CacheState, Provenance
from openchem.domain.descriptor import DescriptorValue
from openchem.domain.quantum_chemistry_run import OutputStatus, QuantumChemistryRun, RunStatus
from openchem.domain.quantum_run_snapshot import (
    DEFAULT_RUN_LIMIT,
    DETAIL_RUN_LIMIT,
    JobOutcome,
    RunEntry,
    classify_runs,
    entry_of,
    read_runs,
)
from openchem.domain.result_envelope import CAP_STEPS, FULL, READ_RUNS_NOTE, envelope_of, run_envelope, runs_view_envelope
from openchem.domain.scientific_result import NMRSpectrumResult
from openchem.domain.turn_snapshot import Freshness, TurnContext, build_turn_context

FIXTURES = Path(__file__).parent / "fixtures" / "orca"
MOL = "mol-1"
CURRENT_FP = "g" * 64
SECRET_MOLBLOCK = "SECRET-INPUT-COORDINATES-MARKER"
SECRET_CACHE_KEY = "SECRET-WAVEFUNCTION-CACHE-KEY"


def water():
    mol = Chem.AddHs(Chem.MolFromSmiles("O"))
    AllChem.EmbedMolecule(mol, randomSeed=7)
    return mol


def real_descriptors():
    provider = OrcaQuantumEngineProvider()
    descriptors, _conformer = provider.parse_output(orca_tests.SP_FIXTURE_OUTPUT, water(), MOL, "sp")
    return list(descriptors)


def real_vibrational():
    provider = OrcaQuantumEngineProvider()
    text = (FIXTURES / "water_freq.out").read_text(encoding="utf-8", errors="replace")
    return provider.parse_vibrational_spectrum(text, water(), MOL, "opt_freq")


def nmr_spectrum():
    return NMRSpectrumResult(
        spectrum_type="nmr_raw_shielding", name="NMR shielding", units="ppm", method="HF/def2-SVP", molecule_uuid=MOL,
        values={0: 323.1, 1: 31.4, 2: 31.5}, elements={0: "O", 1: "H", 2: "H"},
        provenance=Provenance(created_by="orca", method="orca", parameters={}), cache_state=CacheState.COMPLETED,
    )


def run(run_id="run-1", *, status=RunStatus.COMPLETED, fingerprint=CURRENT_FP, calculation_input="geometry", started=1000.0, **kw) -> QuantumChemistryRun:
    base = dict(
        run_id=run_id, molecule_uuid=MOL, calc_type="sp", method_basis="B3LYP def2-SVP", charge=0, multiplicity=1,
        calculation_input=calculation_input, input_fingerprint=fingerprint, input_molblock=SECRET_MOLBLOCK,
        started_at=started, completed_at=started + 12.5, status=status, surface_cache_key=SECRET_CACHE_KEY,
    )
    base.update(kw)
    return QuantumChemistryRun(**base)


def computed_run(run_id="run-1", **kw) -> QuantumChemistryRun:
    r = run(run_id, **kw)
    r.results["descriptors"] = real_descriptors()
    r.output_status["descriptors"] = OutputStatus.AVAILABLE
    return r


FINGERPRINTS = {"drawing": "d" * 64, "geometry": CURRENT_FP}


def turn(*runs: QuantumChemistryRun, fingerprints=None) -> TurnContext:
    fps = FINGERPRINTS if fingerprints is None else fingerprints
    return build_turn_context(
        project_uuid="p", molecule_uuid=MOL, display_name="Water", canonical_smiles="O", heavy_atoms=1, has_structure=True,
        conformer_count=1, fingerprints=fps, records=[], fresh=[], runs=classify_runs(runs, fps),
    )


# --- freshness -----------------------------------------------------------------------------------------------------------------------------


def test_a_run_on_the_structure_now_stored_is_current():
    entry = entry_of(computed_run(), FINGERPRINTS)
    assert entry.freshness is Freshness.CURRENT and entry.note == ""


def test_a_run_on_an_earlier_structure_is_historical_and_says_so():
    entry = entry_of(computed_run(fingerprint="x" * 64), FINGERPRINTS)
    assert entry.freshness is Freshness.HISTORICAL and "earlier structure" in entry.note


def test_the_kind_of_input_decides_which_fingerprint_it_is_compared_with():
    on_drawing = entry_of(computed_run(calculation_input="drawing", fingerprint=FINGERPRINTS["drawing"]), FINGERPRINTS)
    assert on_drawing.freshness is Freshness.CURRENT
    crossed = entry_of(computed_run(calculation_input="drawing", fingerprint=CURRENT_FP), FINGERPRINTS)
    assert crossed.freshness is Freshness.HISTORICAL


def test_an_ensemble_run_and_a_run_with_no_fingerprint_are_never_called_current():
    ensemble = entry_of(computed_run(calculation_input="ensemble"), FINGERPRINTS)
    assert ensemble.freshness is Freshness.UNVERIFIABLE and "ensemble fingerprint" in ensemble.note
    blank = entry_of(computed_run(fingerprint=""), FINGERPRINTS)
    assert blank.freshness is Freshness.UNVERIFIABLE and "no input fingerprint" in blank.note
    no_geometry = entry_of(computed_run(), {"drawing": "d" * 64})
    assert no_geometry.freshness is Freshness.UNVERIFIABLE


def test_runs_are_ordered_current_first_then_newest_first():
    entries = classify_runs(
        [
            computed_run("old-current", started=100.0),
            computed_run("old-history", started=500.0, fingerprint="x" * 64),
            computed_run("new-current", started=300.0),
            computed_run("unknown", started=900.0, fingerprint=""),
        ],
        FINGERPRINTS,
    )
    assert [e.run_id for e in entries] == ["new-current", "old-current", "old-history", "unknown"]


# --- outcome ---------------------------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "outcome", "usable"),
    [
        (RunStatus.COMPLETED, JobOutcome.COMPUTED, True),
        (RunStatus.COMPLETED_WITH_WARNINGS, JobOutcome.COMPUTED_WITH_WARNINGS, True),
        (RunStatus.FAILED, JobOutcome.FAILED, False),
        (RunStatus.CANCELLED, JobOutcome.CANCELLED, False),
        (RunStatus.RUNNING, JobOutcome.FAILED, False),
    ],
)
def test_each_way_a_run_can_end_is_its_own_outcome_and_only_a_finished_one_is_usable(status, outcome, usable):
    entry = entry_of(run(status=status), FINGERPRINTS)
    assert entry.outcome is outcome and entry.usable is usable


# --- frozen ----------------------------------------------------------------------------------------------------------------------------------


def test_a_run_changing_after_the_turn_began_changes_nothing_the_turn_holds():
    source = computed_run()
    entry = entry_of(source, FINGERPRINTS)
    source.status = RunStatus.FAILED
    source.warnings.append("added later")
    source.results["descriptors"] = []
    source.results["spectrum"] = nmr_spectrum()
    source.output_status["spectrum"] = OutputStatus.AVAILABLE
    assert entry.outcome is JobOutcome.COMPUTED and entry.warnings == ()
    assert len(entry.outputs["descriptors"]) == 1 and "spectrum" not in entry.outputs and "spectrum" not in entry.output_status
    with pytest.raises(dataclasses.FrozenInstanceError):
        entry.run_id = "other"  # type: ignore[misc]
    with pytest.raises(TypeError):
        entry.outputs["spectrum"] = ()  # type: ignore[index]


# --- reading ---------------------------------------------------------------------------------------------------------------------------------


def test_a_list_holds_the_current_runs_and_counts_the_rest():
    t = turn(computed_run("a"), computed_run("b", fingerprint="x" * 64), computed_run("c", fingerprint=""))
    view = read_runs(t)
    assert [e.run_id for e in view.entries] == ["a"] and view.not_current_left_out == 2 and view.detailed is False


def test_a_request_for_the_others_lists_them_with_their_freshness():
    t = turn(computed_run("a"), computed_run("b", fingerprint="x" * 64))
    view = read_runs(t, include_not_current=True)
    assert [(e.run_id, e.freshness) for e in view.entries] == [("a", Freshness.CURRENT), ("b", Freshness.HISTORICAL)]
    assert view.not_current_left_out == 0


def test_a_run_named_by_id_is_returned_in_full_whatever_its_freshness_and_an_unknown_id_is_said():
    t = turn(computed_run("a"), computed_run("b", fingerprint="x" * 64))
    view = read_runs(t, ["b", "ghost"])
    assert [e.run_id for e in view.entries] == ["b"] and view.not_found == ("ghost",) and view.detailed is True
    assert view.entries[0].freshness is Freshness.HISTORICAL


def test_a_long_history_is_cut_to_the_limit_and_says_how_many_were_left_out():
    t = turn(*[computed_run(f"r{i}", started=float(i)) for i in range(DEFAULT_RUN_LIMIT + 4)])
    view = read_runs(t)
    assert len(view.entries) == DEFAULT_RUN_LIMIT and view.truncated == 4
    assert read_runs(t, limit=0).entries == () and read_runs(t, limit=-3).truncated == DEFAULT_RUN_LIMIT + 4


def test_runs_named_by_id_are_returned_with_numbers_for_at_most_the_detail_limit():
    t = turn(*[computed_run(f"r{i}", started=float(i)) for i in range(DETAIL_RUN_LIMIT + 2)])
    view = read_runs(t, [f"r{i}" for i in range(DETAIL_RUN_LIMIT + 2)], limit=50)
    assert [e.run_id for e in view.entries] == [f"r{i}" for i in range(DETAIL_RUN_LIMIT)] and view.truncated == 2


def test_a_turn_with_no_runs_reads_as_none_and_never_raises():
    t = turn()
    assert read_runs(t).entries == () and read_runs(t, ["x"]).not_found == ("x",)


# --- what a model is told ---------------------------------------------------------------------------------------------------------------------


def text_of(payload) -> str:
    return json.dumps(payload, ensure_ascii=False)


def test_a_list_carries_every_header_and_no_number():
    entry = entry_of(computed_run(), FINGERPRINTS)
    payload = run_envelope(entry, FULL)
    assert payload["calculation"] == {
        "calc_type": "sp", "method_basis": "B3LYP def2-SVP", "charge": 0, "multiplicity": 1, "solvent": "", "provider": "orca",
    }
    assert payload["freshness"] == "current" and payload["outcome"] == "computed" and payload["status"] == "completed"
    assert payload["duration_seconds"] == 12.5 and payload["started_at"].endswith("+00:00")
    assert payload["outputs"]["descriptors"] == {"status": "available", "kind": "descriptor", "count": 1, "names": ["SCF Energy"]}
    assert "154.98" not in text_of(payload) and "results" not in payload["outputs"]["descriptors"]


def test_a_named_run_carries_its_numbers_with_their_units():
    payload = run_envelope(entry_of(computed_run(), FINGERPRINTS), FULL, detailed=True)
    [result] = payload["outputs"]["descriptors"]["results"]
    assert result["kind"] == "descriptor" and result["data"]["value"] == -154.988
    assert result["data"]["units"] == "Hartree" and result["data"]["descriptor_id"] == "orca.scf_energy"


def test_an_infrared_spectrum_is_its_modes_and_never_an_empty_list_of_peaks():
    spectrum = real_vibrational()
    assert spectrum.values == {} and len(spectrum.modes) == 3, "the premise: values are empty on purpose"
    r = computed_run(calc_type="opt_freq")
    r.results["vibrational_spectrum"] = spectrum
    r.output_status["vibrational_spectrum"] = OutputStatus.AVAILABLE
    detail = run_envelope(entry_of(r, FINGERPRINTS), FULL, detailed=True)["outputs"]["vibrational_spectrum"]["results"][0]["data"]
    assert detail["count"] == 3 and "peaks" not in detail and detail["imaginary_modes"] == 0
    assert [m[0] for m in detail["modes"]] == pytest.approx([1637.7, 3787.2, 3882.1], abs=0.1)
    assert detail["mode_columns"] == ["wavenumber_cm1", "ir_intensity_km_mol", "character"] and "cm^-1" in detail["units"]


def test_a_stored_infrared_spectrum_is_told_the_same_way_through_read_results():
    """The serialiser `read_results` uses was reading every vibrational spectrum as zero peaks, because the type is a spectrum with no per-atom values."""
    entry = _entry(real_vibrational())
    data = envelope_of(entry)["data"]
    assert data["count"] == 3 and "modes" in data and "peaks" not in data


def test_an_imaginary_mode_is_counted_and_its_warning_travels():
    spectrum = real_vibrational()
    flipped = dataclasses.replace(
        spectrum, modes=(dataclasses.replace(spectrum.modes[0], wavenumber_cm1=-85.0),) + spectrum.modes[1:], imaginary_warning="one imaginary mode: a saddle point, not a minimum"
    )
    r = computed_run(calc_type="opt_freq")
    r.results["vibrational_spectrum"] = flipped
    r.output_status["vibrational_spectrum"] = OutputStatus.AVAILABLE
    data = run_envelope(entry_of(r, FINGERPRINTS), FULL, detailed=True)["outputs"]["vibrational_spectrum"]["results"][0]["data"]
    assert data["imaginary_modes"] == 1 and data["modes"][0][0] == -85.0 and "saddle point" in data["imaginary_warning"]


def test_a_per_atom_spectrum_names_the_atoms_and_elements():
    r = computed_run(calc_type="nmr")
    r.results["spectrum"] = nmr_spectrum()
    r.output_status["spectrum"] = OutputStatus.AVAILABLE
    data = run_envelope(entry_of(r, FINGERPRINTS), FULL, detailed=True)["outputs"]["spectrum"]["results"][0]["data"]
    assert data["peak_columns"] == ["atom_index", "element", "value"] and data["peaks"][0] == [0, "O", 323.1] and data["units"] == "ppm"


@pytest.mark.parametrize("status", [RunStatus.FAILED, RunStatus.CANCELLED])
def test_a_job_that_did_not_finish_has_no_numbers_even_when_everything_is_asked_for(status):
    r = run(status=status, warnings=["ORCA ended before the SCF converged"])
    r.results["descriptors"] = real_descriptors()  # a record that should never exist for a failed job; it must still not be offered
    r.output_status["descriptors"] = OutputStatus.FAILED
    payload = run_envelope(entry_of(r, FINGERPRINTS), FULL, detailed=True)
    assert payload["outcome"] == status.value and payload["warnings"] == ["ORCA ended before the SCF converged"]
    assert "154.98" not in text_of(payload) and "results" not in payload["outputs"]["descriptors"]


def test_an_output_that_was_not_produced_or_does_not_apply_says_so_and_holds_no_value():
    r = computed_run(calc_type="nmr")
    r.output_status.update({"vibrational_spectrum": OutputStatus.NOT_PRODUCED, "spectrum": OutputStatus.INAPPLICABLE, "per_atom": OutputStatus.FAILED})
    outputs = run_envelope(entry_of(r, FINGERPRINTS), FULL, detailed=True)["outputs"]
    assert outputs["vibrational_spectrum"] == {"status": "not_produced"}
    assert outputs["spectrum"] == {"status": "inapplicable"} and outputs["per_atom"] == {"status": "failed"}


def test_the_structure_sent_to_orca_and_the_wavefunction_key_never_leave():
    r = computed_run()
    r.results["spectrum"] = nmr_spectrum()
    r.output_status["spectrum"] = OutputStatus.AVAILABLE
    for detailed in (False, True):
        for caps in CAP_STEPS:
            payload = text_of(run_envelope(entry_of(r, FINGERPRINTS), caps, detailed=detailed))
            assert SECRET_MOLBLOCK not in payload and SECRET_CACHE_KEY not in payload


def test_a_warning_is_bounded_and_a_long_one_says_it_was_cut():
    r = computed_run(status=RunStatus.COMPLETED_WITH_WARNINGS, warnings=["Spin-spin coupling output could not be parsed: " + "x" * 5000])
    [warning] = run_envelope(entry_of(r, FINGERPRINTS), FULL)["warnings"]
    assert len(warning) <= FULL.text and warning.endswith("…")


def test_a_kind_with_no_serialiser_is_named_and_its_numbers_are_not_offered():
    class TautomerLike:  # stands for the bundles (tautomer distribution, tautomer NMR) nobody has taught the envelope
        pass

    r = computed_run()
    r.results["tautomer_distribution"] = TautomerLike()
    r.output_status["tautomer_distribution"] = OutputStatus.AVAILABLE
    item = run_envelope(entry_of(r, FINGERPRINTS), FULL, detailed=True)["outputs"]["tautomer_distribution"]
    assert "unsupported" in item["results"][0] and "data" not in item["results"][0]


def test_a_plain_number_a_run_kept_is_offered_with_its_name_for_the_unit():
    r = computed_run()
    r.results["boltzmann_average_scf_energy_hartree"] = -76.0123456789
    item = run_envelope(entry_of(r, FINGERPRINTS), FULL, detailed=True)["outputs"]["boltzmann_average_scf_energy_hartree"]
    assert item["kind"] == "number" and item["results"] == [{"name": "boltzmann_average_scf_energy_hartree", "value": -76.0123}]


def test_what_a_producer_said_about_its_limits_comes_with_the_number():
    caveated = DescriptorValue(
        descriptor_id="orca.koopmans_hardness", name="Koopmans hardness", units="eV", category="quantum_chemistry", provider="orca", molecule_uuid=MOL, value=7.1,
        cache_state=CacheState.COMPLETED, provenance=Provenance(created_by="core", method="orca", parameters={"caveat": "Koopmans hardness is unreliable for this pair"}),
    )
    r = computed_run()
    r.results["descriptors"] = [caveated]
    item = run_envelope(entry_of(r, FINGERPRINTS), FULL, detailed=True)["outputs"]["descriptors"]["results"][0]
    assert item["caveats"] == ["Koopmans hardness is unreliable for this pair"]


def test_the_view_says_what_was_left_out_and_carries_the_standing_note():
    t = turn(computed_run("a"), computed_run("b", fingerprint="x" * 64))
    payload = runs_view_envelope(read_runs(t))
    assert [r["run_id"] for r in payload["runs"]] == ["a"] and payload["not_current_left_out"] == 1
    assert payload["note"] == READ_RUNS_NOTE and "Never state a value that is not in a run read here" in READ_RUNS_NOTE
    assert runs_view_envelope(read_runs(t, ["nope"]))["not_found"] == ["nope"]
