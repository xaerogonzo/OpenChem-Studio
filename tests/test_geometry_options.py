"""The Geometry calculator's options: energy unit, relaxing a copy, the lowest-of-N conformer, the radius scale.

What is guarded, each a way a plausible-looking number could be wrong:

* a unit change CONVERTS the stored energy -- it never computes a second, different one;
* relaxing happens on a COPY: the molecule handed in is byte-for-byte the same afterwards;
* the lowest-of-N claim says how many candidates there were, repeats exactly, and never reports
  an energy above the geometry that was supplied;
* the defaults leave every number as it was, so no existing project changes meaning;
* the method version keeps an older result beside a new one instead of replaying it.
"""

from __future__ import annotations

import math

import pytest
from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.chem.geometry_analysis import (
    NoConformerError,
    compute_geometry_analysis,
    force_field_energies,
)
from openchem.chem.geometry_options import (
    KJ_PER_KCAL,
    UNIT_KJ,
    geometry_options,
    geometry_parameters,
)
from openchem.chem.geometry_preparation import (
    geometry_fingerprint,
    lowest_energy_conformer,
    optimised_copy,
)
from openchem.domain.calculator import DRAWING, GEOMETRY


def _raw(smiles: str = "CC(C)Cc1ccc(cc1)C(C)C(=O)O", seed: int = 3) -> Chem.Mol:
    """An embedded conformer that has NOT been relaxed, so relaxing it visibly moves it."""
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    assert AllChem.EmbedMolecule(mol, randomSeed=seed) == 0
    return mol


def _drawing(smiles: str = "CC(C)Cc1ccc(cc1)C(C)C(=O)O") -> Chem.Mol:
    """What a calculator that asked for a geometry but had none is handed: the 2D drawing."""
    mol = Chem.MolFromSmiles(smiles)
    AllChem.Compute2DCoords(mol)
    return mol


def _facts(report) -> dict:
    return {fact.label: fact for fact in report.facts}


def _run(mol, **parameters):
    return compute_geometry_analysis(mol, "uuid", parameters)


# --- the options themselves -------------------------------------------------------------------------


def test_the_defaults_are_the_behaviour_there_was_before_the_options_existed():
    options = geometry_options({})

    assert (options.energy_unit, options.conformer_policy, options.optimise_mmff, options.optimise_projection) == (
        "kcal_per_mol", "never", False, False,
    )
    assert options.radius_scale == 1.0 and options.optimisation_limit == "normal"


@pytest.mark.parametrize(
    "stored", [{"energy_unit": "joules"}, {"conformer_policy": "sometimes"}, {"optimisation_limit": "ludicrous"}, {"radius_scale": 99}, {"radius_scale": "x"}, {"conformer_count": "many"}],
)
def test_a_value_this_build_does_not_offer_reads_as_the_default_rather_than_failing(stored):
    assert geometry_options(stored) == geometry_options({})


def test_the_conformer_count_is_clamped():
    assert geometry_options({"conformer_count": 0}).conformer_count == 1
    assert geometry_options({"conformer_count": 10_000}).conformer_count == 200


def test_every_choice_is_stored_as_a_code_and_labelled_separately():
    for parameter in geometry_parameters():
        if parameter.kind == "choice":
            assert parameter.choice_labels is not None and len(parameter.choice_labels) == len(parameter.choices)
            assert parameter.default in parameter.choices
            assert not set(parameter.choices) & set(parameter.choice_labels) or parameter.choices == parameter.choice_labels


# --- the energy unit converts, it does not recompute -----------------------------------------------------


def test_kilojoules_are_the_same_energy_times_the_calorie():
    mol = _raw()
    kcal = _facts(_run(mol))
    kj = _facts(_run(mol, energy_unit=UNIT_KJ))

    for label in ("MMFF94 energy", "UFF energy", "Dreiding energy"):
        assert kj[label].value == pytest.approx(kcal[label].value * KJ_PER_KCAL, rel=1e-12)
        assert kj[label].units == "kJ/mol" and kcal[label].units == "kcal/mol"


def test_the_default_energies_are_exactly_what_the_calculator_gave_before():
    mol = _raw()
    facts = _facts(_run(mol))
    direct = force_field_energies(mol)

    assert facts["MMFF94 energy"].value == pytest.approx(direct["mmff94"], rel=1e-12)
    assert facts["UFF energy"].value == pytest.approx(direct["uff"], rel=1e-12)
    assert facts["Dreiding energy"].value == pytest.approx(direct["dreiding"], rel=1e-12)


# --- relaxing happens on a copy ----------------------------------------------------------------------------------


def test_relaxing_never_moves_the_molecule_it_was_handed():
    mol = _raw()
    before = geometry_fingerprint(mol)

    _run(mol, optimise_mmff=True, optimise_projection=True)
    optimised_copy(mol)

    assert geometry_fingerprint(mol) == before


def test_optimising_before_the_mmff_energy_lowers_it_and_says_so():
    mol = _raw()
    plain = _facts(_run(mol))["MMFF94 energy"].value
    relaxed = _facts(_run(mol, optimise_mmff=True))

    assert "MMFF94 energy (optimised)" in relaxed and "MMFF94 energy" not in relaxed
    assert relaxed["MMFF94 energy (optimised)"].value < plain - 1.0
    assert "Geometry relaxed for" in relaxed


def test_the_other_energies_stay_on_the_geometry_as_given_when_only_the_mmff_one_is_relaxed():
    mol = _raw()
    plain = _facts(_run(mol))
    relaxed = _facts(_run(mol, optimise_mmff=True))

    assert relaxed["UFF energy"].value == plain["UFF energy"].value
    assert relaxed["Dreiding energy"].value == plain["Dreiding energy"].value


def test_the_stricter_the_limit_the_lower_the_energy_never_higher():
    mol = _raw()
    energies = [
        _facts(_run(mol, optimise_mmff=True, optimisation_limit=limit))["MMFF94 energy (optimised)"].value
        for limit in ("loose", "normal", "strict", "very_strict")
    ]

    assert all(later <= earlier + 1e-6 for earlier, later in zip(energies, energies[1:]))


def test_optimising_before_the_projection_changes_what_the_shadow_is_measured_on():
    mol = _raw()
    plain = _run(mol)
    relaxed = _run(mol, optimise_projection=True)

    assert plain.provenance.parameters["measured_geometry"] == plain.provenance.parameters["input_geometry"]
    assert relaxed.provenance.parameters["measured_geometry"] != relaxed.provenance.parameters["input_geometry"]
    assert _facts(relaxed)["Min projection area"].value != _facts(plain)["Min projection area"].value


def test_the_axes_are_drawn_only_on_the_geometry_that_is_on_screen():
    """An arrow from a relaxed copy's frame would sit in the wrong place on the displayed structure."""
    mol = _raw()

    assert _run(mol).spatial
    assert not _run(mol, optimise_projection=True).spatial
    assert _run(mol, optimise_mmff=True).spatial, "relaxing for the energy alone does not change what is measured"


# --- the conformer policy ------------------------------------------------------------------------------------------


def test_a_two_d_structure_is_still_refused_by_default():
    report = _run(_drawing())

    assert report.cache_state.name == "FAILED" and "3D one" in report.error


def test_if_2d_generates_a_conformer_for_a_drawing_and_says_how():
    report = _run(_drawing(), conformer_policy="if_2d", conformer_count=8)
    facts = _facts(report)

    assert report.cache_state.name != "FAILED"
    assert "Conformer used" in facts
    assert "Lowest of" in facts["Conformer used"].display_value
    assert "global minimum" in " ".join(facts["Conformer used"].limitations)


def test_if_2d_leaves_a_real_conformer_alone():
    mol = _raw()
    report = _run(mol, conformer_policy="if_2d")

    assert "Conformer used" not in _facts(report)
    assert report.provenance.parameters["measured_geometry"] == geometry_fingerprint(mol)


def test_always_may_not_do_worse_than_the_geometry_it_was_given():
    mol = _raw()
    supplied = optimised_copy(mol, "normal").energy
    found = lowest_energy_conformer(mol, 8, "normal")

    assert found is not None and found.energy <= supplied + 1e-9
    assert found.candidates == 9 and found.generated == 8, "eight generated, plus the one supplied"


def test_always_repeats_exactly():
    mol = _raw()

    first = _facts(_run(mol, conformer_policy="always", conformer_count=6))
    second = _facts(_run(mol, conformer_policy="always", conformer_count=6))

    assert first["MMFF94 energy"].value == second["MMFF94 energy"].value
    assert first["Conformer used"].display_value == second["Conformer used"].display_value


def test_the_provenance_records_the_search_it_ran():
    report = _run(_drawing(), conformer_policy="if_2d", conformer_count=5)
    recorded = report.provenance.parameters

    assert recorded["conformer_policy"] == "if_2d" and recorded["conformer_count"] == 5
    assert recorded["conformers_tried"] >= recorded["conformers_ranked"] >= 1
    assert recorded["search_seed"] and recorded["method"] == "geometry-v2"


def test_a_structure_that_cannot_be_given_a_conformer_is_a_refusal_not_a_crash(monkeypatch):
    from openchem.chem import geometry_analysis

    monkeypatch.setattr(geometry_analysis, "lowest_energy_conformer", lambda *a, **k: None)

    report = _run(_drawing(), conformer_policy="if_2d")

    assert report.cache_state.name == "FAILED" and "could be generated" in report.error


# --- the radius scale -------------------------------------------------------------------------------------------------


def test_scaling_the_radii_scales_a_lone_atoms_shadow_by_the_square():
    helium = Chem.MolFromSmiles("[He]")
    AllChem.EmbedMolecule(helium, randomSeed=42)
    base = _facts(_run(helium))["Min projection area"].value
    doubled = _facts(_run(helium, radius_scale=2.0))["Min projection area"].value

    assert doubled == pytest.approx(4 * base, rel=1e-9)
    assert _facts(_run(helium, radius_scale=2.0))["Min projection area"].limitations[-1] == "Van der Waals radii scaled by 2."


def test_the_radius_scale_does_not_change_the_energies_or_the_centroid_radii():
    mol = _raw()
    base, scaled = _facts(_run(mol)), _facts(_run(mol, radius_scale=1.5))

    for label in ("MMFF94 energy", "Max radius (from centroid)"):
        assert scaled[label].value == base[label].value


# --- the shadow facts ---------------------------------------------------------------------------------------------------


def test_the_new_size_facts_are_reported_with_units_and_a_definition():
    facts = _facts(_run(_raw("c1ccccc1")))

    for label in ("Size perpendicular to the min projection", "Size perpendicular to the max projection"):
        assert facts[label].units == "A" and facts[label].value > 0
        assert "surface to surface" in facts[label].limitations[0]
    assert facts["Min projection area"].value < facts["Max projection area"].value


def test_benzenes_minimum_is_below_what_the_principal_planes_gave():
    """18.75 A^2 searched; 20.07 A^2 on the principal planes (measured 2026-10-10)."""
    assert _facts(_run(_raw("c1ccccc1", seed=0xC0FFEE)))["Min projection area"].value < 19.5


# --- the method version ------------------------------------------------------------------------------------------------


def _stored(report, fingerprint="fp"):
    from openchem.domain.result_store import SessionResultStore, StoredResult
    from openchem.services.result_identity import make_identity

    identity = make_identity(
        molecule_uuid="m", result=report, calculation_input=GEOMETRY, input_fingerprint=fingerprint, producer="core"
    )
    store = SessionResultStore("project")
    store.put(StoredResult(identity=identity, result=report))
    return store, identity


def test_a_new_geometry_result_carries_the_new_method():
    from openchem.domain.result_store import CURRENT_METHOD_VERSIONS, GEOMETRY_METHOD

    _store, identity = _stored(_run(_raw()))

    assert identity.method_version == GEOMETRY_METHOD == CURRENT_METHOD_VERSIONS["geometry_analysis"] == "geometry-v2"


def test_a_result_saved_before_the_search_loads_as_the_previous_method_and_says_so():
    from openchem.domain.result_store import LEGACY_METHOD_VERSIONS, SessionResultStore

    store, _identity = _stored(_run(_raw()))
    saved = store.to_dict()
    (entry,) = saved["molecules"]["m"]["results"]
    entry.pop("method_version")  # what a project saved before methods were recorded looks like

    (restored,) = SessionResultStore.from_dict(saved, "project").fresh_results("m", {GEOMETRY: "fp"})

    legacy, label = LEGACY_METHOD_VERSIONS["geometry_analysis"]
    assert restored.identity.method_version == legacy
    assert restored.result.name == label and "previous method" in label


def test_the_old_and_new_methods_never_share_a_slot_and_only_the_new_is_replayed():
    from openchem.domain.result_store import SessionResultStore, StoredResult

    store, identity = _stored(_run(_raw()))
    saved = store.to_dict()
    saved["molecules"]["m"]["results"][0].pop("method_version")
    reloaded = SessionResultStore.from_dict(saved, "project")
    reloaded.put(StoredResult(identity=identity, result=_run(_raw())))

    replayed = {s.identity.method_version for s in reloaded.fresh_results("m", {GEOMETRY: "fp"})}
    kept = {entry.get("method_version", "") for entry in reloaded.to_dict()["molecules"]["m"]["results"]}

    assert replayed == {"geometry-v2"}, "the old measurement must not be replayed as if it were the new one"
    assert kept == {"geometry-v2", "legacy-principal-planes-v1"}, "and it must not be thrown away either"
