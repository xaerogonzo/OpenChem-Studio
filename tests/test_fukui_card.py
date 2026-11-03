"""The assistant asking for Fukui functions (`orca.fukui`; `docs/AI_CALCULATION_BRIDGE.md`, section 23).

Two layers: the shared rules (`prepare_fukui`, which counts the jobs with the same functions the engine writes its input from) and the host (a card that states the cost, the scope and the stage, and refuses a
species Fukui functions are not defined for before any card exists). The service is a recording double; nothing here runs ORCA (a real run is `benchmarks/visual/ai_fukui_dispatch.json`).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from test_calculation_host_orca import approve, prepare, world  # noqa: E402,F401

from openchem.chem.quantum_run_request import PreparedFukui, RunChoice, RunRefusal, prepare_fukui  # noqa: E402
from openchem.domain.calculation_bridge import ProblemCode  # noqa: E402
from openchem.domain.run_lifecycle import RunState  # noqa: E402

FUKUI = "orca.fukui"
BASIS = "B3LYP def2-SVP"
DIFFUSE = "B3LYP def2-SVPD"


# --- the shared rules --------------------------------------------------------------------------------------------------------------------------


def test_a_neutral_closed_shell_species_is_the_three_states_and_the_cation_search():
    """Water: ten electrons, so the HOMO is orbital 4 and the oxygen's 1s is the only core orbital, which leaves the HOMO-1, -2 and -3 to search."""
    prepared = prepare_fukui("O", 0, 1, BASIS)
    assert isinstance(prepared, PreparedFukui) and (prepared.jobs, prepared.cation_search_jobs, prepared.search_not_run) == (6, 3, "")
    text = prepared.card_text()
    assert "6 real ORCA single point(s) in one job at B3LYP def2-SVP" in text and "the neutral, the cation and the anion" in text
    assert "3 more cation start(s)" in text and "about 2.5 times" in text and "Settings > Quantum chemistry can switch them off" in text and "\n" not in text


def test_with_the_search_off_it_is_three_jobs_and_the_card_does_not_mention_one():
    prepared = prepare_fukui("O", 0, 1, BASIS, cation_search=False)
    assert (prepared.jobs, prepared.cation_search_jobs) == (3, 0) and "more cation" not in prepared.card_text() and "other cation states" not in prepared.card_text()


def test_an_anion_gets_its_dianion_and_a_basis_with_diffuse_functions_adds_starts():
    """Hydroxide: its own state (charge -1) and the dianion are anionic, the N-1 state is neutral, so at a basis with diffuse functions two states get two more starts each (6 + 4)."""
    assert prepare_fukui("[OH-]", -1, 1, BASIS).jobs == 6
    assert prepare_fukui("[OH-]", -1, 1, DIFFUSE).jobs == 10
    leaves_it_out = prepare_fukui("[OH-]", -1, 1, BASIS, anion_f_plus=False)
    assert leaves_it_out.jobs == 5 and "has it left out" in leaves_it_out.card_text() and "f- alone" in leaves_it_out.card_text()
    kept = prepare_fukui("[OH-]", -1, 1, BASIS).card_text()
    assert "itself an anion" in kept and "dianion" in kept and "run last" in kept
    assert "itself an anion" not in prepare_fukui("O", 0, 1, BASIS).card_text()


def test_a_species_with_no_valence_orbital_below_its_homo_says_why_the_search_did_not_run():
    prepared = prepare_fukui("[H][H]", 0, 1, BASIS)
    assert (prepared.jobs, prepared.cation_search_jobs) == (3, 0) and prepared.search_not_run
    assert f"The search for other cation states was not run: {prepared.search_not_run}." in prepared.card_text()


def test_an_open_shell_or_unpairable_species_is_refused_in_the_words_the_panel_uses():
    from openchem.chem.fukui import open_shell_message

    assert prepare_fukui("O", 0, 2, BASIS) == RunRefusal(open_shell_message(2))
    odd = prepare_fukui("[CH3]", 0, 1, BASIS)
    assert isinstance(odd, RunRefusal) and "9 electrons" in odd.message and "cannot all be paired" in odd.message
    assert "cannot all be paired" in prepare_fukui("O", 1, 1, BASIS).message
    unreadable = prepare_fukui("not a smiles", 0, 1, BASIS)
    assert isinstance(unreadable, RunRefusal) and "could not be read" in unreadable.message


# --- the card ---------------------------------------------------------------------------------------------------------------------------


def test_a_card_says_the_cost_the_scope_and_the_stage_and_starts_nothing(world):
    result = prepare(world, FUKUI, {"method_basis": "PBE0 def2-TZVP"})
    assert result.ok
    text = "\n".join(result.preparation.preview)
    assert "What it would cost (approving accepts it): This will run" in text and "real ORCA single point(s) in one job at PBE0 def2-TZVP" in text
    assert "Stage: experimental. Not validated: it failed two preregistered checks" in text
    assert "Quantum Chemistry panel's Run button" in text
    assert world.starter.calls == [] and world.host.pending() == (result.preparation,)


def test_the_cards_job_count_follows_the_settings_the_run_will_read(world):
    from openchem.app.settings import FUKUI_CATION_SEARCH

    on = "\n".join(prepare(world, FUKUI).preparation.preview)
    world.services.quantum_chemistry_service._settings.set(FUKUI_CATION_SEARCH.key, False)
    off = "\n".join(prepare(world, FUKUI).preparation.preview)
    assert "more cation start(s)" in on and "more cation start(s)" not in off and "single point(s)" in off


def test_an_open_shell_request_is_refused_before_a_card_exists(world):
    result = prepare(world, FUKUI, {"multiplicity": 2})
    assert [p.code for p in result.problems] == [ProblemCode.INVALID_STRUCTURE] and "closed-shell species (multiplicity 1)" in result.problems[0].message
    assert world.host.pending() == ()


def test_an_electron_count_that_cannot_be_paired_is_refused_before_a_card_exists(world):
    result = prepare(world, FUKUI, {"charge": 1})
    assert [p.code for p in result.problems] == [ProblemCode.INVALID_STRUCTURE] and "cannot all be paired" in result.problems[0].message and world.host.pending() == ()


def test_fukui_without_orca_is_not_ready(world):
    world.services.quantum_chemistry_service._settings.set("orca/executable_path", "")
    assert [p.code for p in prepare(world, FUKUI).problems] == [ProblemCode.NOT_READY]


def test_approving_hands_the_panel_the_settings_the_card_showed_and_the_conformer_it_is_bound_to(world):
    preparation = prepare(world, FUKUI, {"charge": 0, "multiplicity": 1, "method_basis": "PBE0 def2-TZVP"}).preparation
    assert preparation.calculation_input == "geometry"
    assert approve(world, preparation.run_id) is RunState.RUNNING
    [(molecule_uuid, choice, fingerprint)] = world.starter.calls
    assert molecule_uuid == world.molecule.uuid and fingerprint == preparation.input_fingerprint
    assert choice == RunChoice(calc_type="fukui", method_basis="PBE0 def2-TZVP", charge=0, multiplicity=1)
