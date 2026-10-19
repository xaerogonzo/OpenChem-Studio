"""The route validator of the synthesis spike (`benchmarks/synthesis/route_validator.py`, design note 0d) on the planner's REAL saved route trees (AiZynthFinder 4.4.1, `benchmarks/synthesis/fixtures/`) and on synthetic mutations of them. No planner is run here."""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest

_BENCH = Path(__file__).parent.parent / "benchmarks" / "synthesis"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


v = _load("synthesis_route_validator_under_test", _BENCH / "route_validator.py")


def _fixture(name: str) -> dict:
    return json.loads((_BENCH / "fixtures" / f"{name}_it100.json").read_text(encoding="utf-8"))


@pytest.fixture
def aspirin_route() -> dict:
    """The planner's first aspirin route: one step, salicylic acid and acetic anhydride, both in stock, every atom mapped."""
    return copy.deepcopy(_fixture("aspirin")["routes"][0])


def _reaction(route: dict) -> dict:
    return route["children"][0]


# --- real routes -----------------------------------------------------------------------------------------------------------


def test_every_route_with_a_reaction_the_planner_returned_for_the_fixture_targets_validates():
    seen = 0
    for name in ("aspirin", "paracetamol", "caffeine", "s_ibuprofen", "sildenafil", "ibuprofen", "strychnine"):
        for route in _fixture(name)["routes"]:
            result = v.validate_route(route)
            if result.steps == 0:
                continue
            seen += 1
            assert (result.molecules, result.reactions, result.mapping, result.conservation) == (v.PASS, v.PASS, v.COMPLETE, v.PASS), (name, result.diagnostics)
            assert result.fully_validated
    assert seen >= 50  # the fixtures hold real routes, not a handful


def test_the_aspirin_route_reads_as_one_step_with_its_leaving_atoms_counted_and_its_stock_known(aspirin_route):
    result = v.validate_route(aspirin_route)

    assert result.steps == 1 and result.stock == v.ALL_IN_STOCK
    assert result.unmapped_right_atoms == 4  # acetic anhydride's other half (O, C, CH3, O), which has no partner on the product side
    assert result.missing == [] and result.diagnostics == []


def test_stereochemistry_in_a_step_is_kept_when_comparing_the_sides_to_the_nodes():
    route = _fixture("s_ibuprofen")["routes"][0]
    assert "@" in _reaction(route)["metadata"]["mapped_reaction_smiles"] and v.validate_route(route).fully_validated


def test_a_target_already_in_stock_has_no_step_to_validate():
    route = _fixture("strychnine")["routes"][0]  # the planner's tree for an unsolved target can be the bare target
    result = v.validate_route(route)

    assert result.steps == 0 and result.mapping == v.ABSENT and result.conservation == v.NOT_ASSESSABLE
    assert not result.fully_validated and "the tree has no reaction" in result.diagnostics


# --- synthetic mutations: each outcome can fail on its own -------------------------------------------------------------------


def test_a_molecule_that_does_not_parse_fails_the_molecule_outcome_only(aspirin_route):
    aspirin_route["children"][0]["children"][0]["smiles"] = "C(C"

    result = v.validate_route(aspirin_route)

    assert result.molecules == v.FAIL and not result.fully_validated
    assert any("does not parse" in d for d in result.diagnostics)


def test_a_reaction_smiles_that_does_not_parse_fails_the_reaction_outcome(aspirin_route):
    _reaction(aspirin_route)["metadata"]["mapped_reaction_smiles"] = "C(C>>CC"

    result = v.validate_route(aspirin_route)

    assert result.reactions == v.FAIL and result.mapping == v.ABSENT and result.conservation == v.NOT_ASSESSABLE


def test_a_reaction_whose_sides_are_not_its_nodes_is_inconsistent(aspirin_route):
    _reaction(aspirin_route)["children"][0]["smiles"] = "CCO"  # the tree says the precursor is ethanol; the reaction says acetic anhydride

    result = v.validate_route(aspirin_route)

    assert result.reactions == v.FAIL and "not the molecule nodes it connects" in " ".join(result.diagnostics)
    assert result.mapping == v.COMPLETE  # the mapping itself is untouched: only the consistency failed


def test_a_route_with_no_mapped_reaction_is_unmapped_and_conservation_is_not_assessable_never_passed(aspirin_route):
    del _reaction(aspirin_route)["metadata"]["mapped_reaction_smiles"]

    result = v.validate_route(aspirin_route)

    assert result.mapping == v.ABSENT and result.conservation == v.NOT_ASSESSABLE
    assert result.reactions == v.FAIL and "reaction.metadata.mapped_reaction_smiles" in result.missing
    assert not result.fully_validated


def test_stripping_every_map_number_is_absent_not_a_conservation_failure(aspirin_route):
    reaction = _reaction(aspirin_route)
    import re

    reaction["metadata"]["mapped_reaction_smiles"] = re.sub(r":\d+\]", "]", reaction["metadata"]["mapped_reaction_smiles"])

    result = v.validate_route(aspirin_route)

    assert result.mapping == v.ABSENT and result.conservation == v.NOT_ASSESSABLE


def test_a_product_atom_left_unmapped_makes_the_mapping_partial_and_conservation_not_assessable(aspirin_route):
    reaction = _reaction(aspirin_route)
    smiles = reaction["metadata"]["mapped_reaction_smiles"]
    reaction["metadata"]["mapped_reaction_smiles"] = smiles.replace("[CH3:1]", "C", 1)  # the acetyl methyl on the product side loses its number

    result = v.validate_route(aspirin_route)

    assert result.mapping == v.PARTIAL and result.conservation == v.NOT_ASSESSABLE and not result.fully_validated


def test_a_mapped_atom_whose_element_changes_across_the_step_fails_conservation(aspirin_route):
    reaction = _reaction(aspirin_route)
    smiles = reaction["metadata"]["mapped_reaction_smiles"]
    left, right = smiles.split(">>")
    reaction["metadata"]["mapped_reaction_smiles"] = left + ">>" + right.replace("[CH3:1]", "[NH2:1]", 1)  # a carbon on the left becomes nitrogen on the right

    result = v.validate_route(aspirin_route)

    assert result.mapping == v.COMPLETE and result.conservation == v.FAIL
    assert any("changes element" in d for d in result.diagnostics) and not result.fully_validated


def test_a_mapped_product_atom_with_no_partner_on_the_right_fails_conservation(aspirin_route):
    reaction = _reaction(aspirin_route)
    left, right = reaction["metadata"]["mapped_reaction_smiles"].split(">>")
    reaction["metadata"]["mapped_reaction_smiles"] = left + ">>" + right.replace("[CH3:1]", "C", 1)  # the number that should find its partner is gone from the right

    result = v.validate_route(aspirin_route)

    assert result.conservation == v.FAIL and any("0 partners" in d for d in result.diagnostics)


# --- stock and the missing-information list ----------------------------------------------------------------------------------


def test_a_precursor_not_in_stock_is_reported_and_does_not_unvalidate_the_route():
    route = _fixture("ibuprofen")["routes"][0]
    result = v.validate_route(route)

    assert result.stock == v.SOME_NOT_IN_STOCK and result.fully_validated  # stock is a snapshot match, not a validity outcome


def test_a_missing_stock_flag_is_not_provided_never_assumed_true(aspirin_route):
    del _reaction(aspirin_route)["children"][0]["in_stock"]

    result = v.validate_route(aspirin_route)

    assert result.stock == v.NOT_PROVIDED and "molecule.in_stock" in result.missing


def test_missing_planner_metadata_is_listed_field_by_field(aspirin_route):
    metadata = _reaction(aspirin_route)["metadata"]
    for key in ("policy_probability", "template", "template_hash"):
        del metadata[key]

    result = v.validate_route(aspirin_route)

    assert result.missing == ["reaction.metadata.policy_probability", "reaction.metadata.template", "reaction.metadata.template_hash"]
    assert result.fully_validated  # absent metadata is reported, it does not unvalidate a route that checks out
