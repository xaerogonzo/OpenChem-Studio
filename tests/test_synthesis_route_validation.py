"""The route validator (`openchem.chem.route_validation`, design note 0d, moved from the spike in Stage 1 slice 6) on the planner's REAL saved route trees (AiZynthFinder 4.4.1, `benchmarks/synthesis/fixtures/`), parsed into `Route`s by the real parser, and on synthetic mutations of them. Each outcome can fail on its own, and a check that could not be made is `not_assessable`, never a pass. No planner is run here."""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path

import pytest

from openchem.chem.aizynth_planner import _Unrepresentable, route_from_tree
from openchem.chem.route_validation import validate_route
from openchem.domain.synthesis_route import Check, MappingStatus, Route, RouteMolecule, RouteStep, StockStatus

_FIXTURES = Path(__file__).parent.parent / "benchmarks" / "synthesis" / "fixtures"


def _fixture(name: str) -> dict:
    return json.loads((_FIXTURES / f"{name}_it100.json").read_text(encoding="utf-8"))


@pytest.fixture
def aspirin_tree() -> dict:
    """The planner's first aspirin route: one step, salicylic acid and acetic anhydride, both in stock, every atom mapped."""
    return copy.deepcopy(_fixture("aspirin")["routes"][0])


def parsed(tree: dict, rank: int = 1) -> Route:
    return route_from_tree(copy.deepcopy(tree), rank)


def _reaction(tree: dict) -> dict:
    return tree["children"][0]


# --- real routes -----------------------------------------------------------------------------------------------------------


def test_every_route_with_a_reaction_the_planner_returned_for_the_fixture_targets_validates():
    seen = 0
    for name in ("aspirin", "paracetamol", "caffeine", "s_ibuprofen", "sildenafil", "ibuprofen", "strychnine"):
        for tree in _fixture(name)["routes"]:
            try:
                route = parsed(tree)
            except _Unrepresentable:
                continue  # the bare target, which has no step to validate
            seen += 1
            result = validate_route(route)
            assert (result.molecules, result.reactions, result.mapping, result.conservation) == (Check.PASS, Check.PASS, MappingStatus.COMPLETE, Check.PASS), (name, result.diagnostics)
            assert result.fully_validated
    assert seen >= 50  # the fixtures hold real routes, not a handful


def test_the_aspirin_route_reads_with_its_leaving_atoms_counted_and_its_stock_known(aspirin_tree):
    result = validate_route(parsed(aspirin_tree))

    assert result.stock is StockStatus.ALL_IN_STOCK
    assert result.unmapped_right_atoms == 4  # acetic anhydride's other half (O, C, CH3, O), which has no partner on the product side
    assert result.missing == () and result.diagnostics == ()


def test_stereochemistry_in_a_step_is_kept_when_comparing_the_sides_to_the_molecules():
    tree = _fixture("s_ibuprofen")["routes"][0]
    assert "@" in _reaction(tree)["metadata"]["mapped_reaction_smiles"] and validate_route(parsed(tree)).fully_validated


def test_a_tree_with_no_reaction_is_not_a_route_at_all_so_there_is_nothing_to_validate():
    with pytest.raises(_Unrepresentable, match="no reaction"):
        parsed(_fixture("strychnine")["routes"][0])  # the planner's tree for an unsolved target can be the bare target


def test_a_multi_step_route_is_checked_step_by_step_and_a_fault_names_its_step():
    tree = copy.deepcopy(_fixture("sildenafil")["routes"][0])  # three steps
    assert validate_route(parsed(tree)).fully_validated

    def deepest(node: dict) -> dict:
        for reaction in node.get("children", []):
            for child in reaction.get("children", []):
                if child.get("children"):
                    return deepest(child)
            return reaction
        return node

    first_run = deepest(tree)  # the reaction run first, which is step 1 in forward order
    first_run["metadata"]["mapped_reaction_smiles"] = "C(C>>CC"
    result = validate_route(parsed(tree))

    assert result.reactions is Check.FAIL
    assert any(d.startswith("step 1: the reaction SMILES does not parse") for d in result.diagnostics)
    assert not any(d.startswith("step 2") or d.startswith("step 3") for d in result.diagnostics)


# --- synthetic mutations: each outcome can fail on its own -------------------------------------------------------------------


def test_a_molecule_that_does_not_parse_fails_the_molecule_outcome(aspirin_tree):
    aspirin_tree["children"][0]["children"][0]["smiles"] = "C(C"

    result = validate_route(parsed(aspirin_tree))

    assert result.molecules is Check.FAIL and not result.fully_validated
    assert any(d == "molecule does not parse: 'C(C'" for d in result.diagnostics)


def test_a_reaction_smiles_that_does_not_parse_fails_the_reaction_outcome(aspirin_tree):
    _reaction(aspirin_tree)["metadata"]["mapped_reaction_smiles"] = "C(C>>CC"

    result = validate_route(parsed(aspirin_tree))

    assert result.reactions is Check.FAIL and result.mapping is MappingStatus.ABSENT and result.conservation is Check.NOT_ASSESSABLE


@pytest.mark.parametrize("odd", ["C", "C>>C>>C", "C>C>C", ">>", "C>>", ">>C"])
def test_an_oddly_shaped_reaction_smiles_never_raises_and_is_never_a_pass(aspirin_tree, odd):
    _reaction(aspirin_tree)["metadata"]["mapped_reaction_smiles"] = odd

    result = validate_route(parsed(aspirin_tree))

    assert result.reactions is Check.FAIL and not result.fully_validated and result.conservation is Check.NOT_ASSESSABLE


def test_a_reaction_whose_sides_are_not_its_molecules_is_inconsistent(aspirin_tree):
    _reaction(aspirin_tree)["children"][0]["smiles"] = "CCO"  # the tree says the precursor is ethanol; the reaction says acetic anhydride

    result = validate_route(parsed(aspirin_tree))

    assert result.reactions is Check.FAIL and "the reaction's sides are not the molecules the step connects" in " ".join(result.diagnostics)
    assert result.mapping is MappingStatus.COMPLETE  # the mapping itself is untouched: only the consistency failed


def test_a_step_with_no_reaction_smiles_cannot_be_assessed_and_is_listed_as_missing(aspirin_tree):
    del _reaction(aspirin_tree)["metadata"]["mapped_reaction_smiles"]

    result = validate_route(parsed(aspirin_tree))

    # the planner did not give enough to check: neither a pass nor a fail, and conservation is not assessable, never passed
    assert result.reactions is Check.NOT_ASSESSABLE and result.mapping is MappingStatus.ABSENT and result.conservation is Check.NOT_ASSESSABLE
    assert "step.reaction_smiles" in result.missing and "step 1: the planner gave no reaction SMILES" in result.diagnostics
    assert not result.fully_validated


def test_a_failed_reaction_outranks_a_step_that_could_not_be_assessed():
    tree = copy.deepcopy(_fixture("sildenafil")["routes"][0])
    reactions: list[dict] = []

    def collect(node: dict) -> None:
        for reaction in node.get("children", []):
            reactions.append(reaction)
            for child in reaction.get("children", []):
                collect(child)

    collect(tree)
    del reactions[0]["metadata"]["mapped_reaction_smiles"]  # unassessable
    reactions[1]["metadata"]["mapped_reaction_smiles"] = "C(C>>CC"  # failed

    assert validate_route(parsed(tree)).reactions is Check.FAIL


def test_stripping_every_map_number_is_absent_not_a_conservation_failure(aspirin_tree):
    reaction = _reaction(aspirin_tree)
    reaction["metadata"]["mapped_reaction_smiles"] = re.sub(r":\d+\]", "]", reaction["metadata"]["mapped_reaction_smiles"])

    result = validate_route(parsed(aspirin_tree))

    assert result.mapping is MappingStatus.ABSENT and result.conservation is Check.NOT_ASSESSABLE
    assert result.reactions is Check.PASS  # the molecules are still the ones the step connects


def test_a_product_atom_left_unmapped_makes_the_mapping_partial_and_conservation_not_assessable(aspirin_tree):
    reaction = _reaction(aspirin_tree)
    reaction["metadata"]["mapped_reaction_smiles"] = reaction["metadata"]["mapped_reaction_smiles"].replace("[CH3:1]", "C", 1)  # the acetyl methyl on the product side loses its number

    result = validate_route(parsed(aspirin_tree))

    assert result.mapping is MappingStatus.PARTIAL and result.conservation is Check.NOT_ASSESSABLE and not result.fully_validated


def test_a_number_repeated_on_one_side_is_a_partial_mapping(aspirin_tree):
    reaction = _reaction(aspirin_tree)
    left, right = reaction["metadata"]["mapped_reaction_smiles"].split(">>")
    reaction["metadata"]["mapped_reaction_smiles"] = left + ">>" + right.replace("[CH3:16]", "[CH3:1]", 1)  # map 1 now appears twice on the right

    assert validate_route(parsed(aspirin_tree)).mapping is MappingStatus.PARTIAL


def test_a_mapped_atom_whose_element_changes_across_the_step_fails_conservation_with_the_sides_still_the_molecules(aspirin_tree):
    reaction = _reaction(aspirin_tree)
    left, right = reaction["metadata"]["mapped_reaction_smiles"].split(">>")
    # swap the numbers of a carbon and an oxygen on the right: the molecules are unchanged (so the sides are still the nodes) but map 1 now pairs a carbon with an oxygen
    swapped = right.replace("[CH3:1]", "[CH3:@]", 1).replace("[O:3]", "[O:1]", 1).replace("[CH3:@]", "[CH3:3]", 1)
    reaction["metadata"]["mapped_reaction_smiles"] = left + ">>" + swapped

    result = validate_route(parsed(aspirin_tree))

    assert result.reactions is Check.PASS and result.mapping is MappingStatus.COMPLETE and result.conservation is Check.FAIL
    assert any(d.startswith("step 1: map 1 changes element") for d in result.diagnostics) and not result.fully_validated


def test_a_stereocentre_flipped_on_one_side_is_not_the_molecule_it_claims_to_connect():
    tree = copy.deepcopy(_fixture("s_ibuprofen")["routes"][0])
    reaction = _reaction(tree)
    left, right = reaction["metadata"]["mapped_reaction_smiles"].split(">>")
    reaction["metadata"]["mapped_reaction_smiles"] = left.replace("[C@H:9]", "[C@@H:9]") + ">>" + right

    assert validate_route(parsed(tree)).reactions is Check.FAIL


def test_a_mapped_product_atom_with_no_partner_on_the_right_fails_conservation(aspirin_tree):
    reaction = _reaction(aspirin_tree)
    left, right = reaction["metadata"]["mapped_reaction_smiles"].split(">>")
    reaction["metadata"]["mapped_reaction_smiles"] = left + ">>" + right.replace("[CH3:1]", "C", 1)  # the number that should find its partner is gone from the right

    result = validate_route(parsed(aspirin_tree))

    assert result.conservation is Check.FAIL and any("0 partners" in d for d in result.diagnostics)


# --- stock and the missing-information list ----------------------------------------------------------------------------------


def test_a_precursor_not_in_stock_is_reported_and_does_not_unvalidate_the_route():
    tree = _fixture("ibuprofen")["routes"][0]
    result = validate_route(parsed(tree))

    assert result.stock is StockStatus.SOME_NOT_IN_STOCK and result.fully_validated  # stock is a snapshot match, not a validity outcome


def test_a_missing_stock_flag_is_not_provided_never_assumed_true_and_outranks_a_false_one(aspirin_tree):
    del _reaction(aspirin_tree)["children"][0]["in_stock"]

    result = validate_route(parsed(aspirin_tree))

    assert result.stock is StockStatus.NOT_PROVIDED and "molecule.in_stock" in result.missing
    mixed = copy.deepcopy(aspirin_tree)
    _reaction(mixed)["children"][1]["in_stock"] = False
    assert validate_route(parsed(mixed)).stock is StockStatus.NOT_PROVIDED


def test_missing_planner_metadata_is_listed_field_by_field(aspirin_tree):
    metadata = _reaction(aspirin_tree)["metadata"]
    for key in ("policy_probability", "template_hash", "policy_name"):
        del metadata[key]

    result = validate_route(parsed(aspirin_tree))

    assert result.missing == ("step.policy_name", "step.policy_probability", "step.template_id")
    assert result.fully_validated  # absent metadata is reported, it does not unvalidate a route that checks out


def test_a_hand_built_route_with_nothing_but_its_molecules_is_checked_as_far_as_it_can_be():
    route = Route(target_smiles="CCO", rank=1, steps=(RouteStep(product="CCO", reactants=("CC=O",)),), starting_materials=(RouteMolecule(smiles="CC=O"),))

    result = validate_route(route)

    assert result.molecules is Check.PASS and result.reactions is Check.NOT_ASSESSABLE and result.mapping is MappingStatus.ABSENT
    assert result.stock is StockStatus.NOT_PROVIDED and not result.fully_validated
    assert result.missing == ("molecule.in_stock", "step.policy_name", "step.policy_probability", "step.reaction_smiles", "step.template_id")


def test_the_report_is_always_internally_consistent_whatever_is_done_to_a_real_route(aspirin_tree):
    """`ValidationReport` refuses a conservation verdict without a complete mapping; the validator must never trip that."""
    reaction = _reaction(aspirin_tree)
    base = reaction["metadata"]["mapped_reaction_smiles"]
    for text in (base, re.sub(r":\d+\]", "]", base), base.replace("[CH3:1]", "C", 1), "C>>C", "", None):
        tree = copy.deepcopy(aspirin_tree)
        if text is None:
            del _reaction(tree)["metadata"]["mapped_reaction_smiles"]
        else:
            _reaction(tree)["metadata"]["mapped_reaction_smiles"] = text
        result = validate_route(parsed(tree))
        assert result.conservation is Check.NOT_ASSESSABLE or result.mapping is MappingStatus.COMPLETE


# --- agreement with the spike's validator, which the frozen quality benchmark still runs -------------------------------------


def _spike():
    import importlib.util
    import sys

    spec = importlib.util.spec_from_file_location("synthesis_spike_validator_for_agreement", _FIXTURES.parent / "route_validator.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _same_outcomes(tree: dict) -> None:
    spike = _spike().validate_route(copy.deepcopy(tree))
    ours = validate_route(parsed(tree))
    assert (ours.molecules, ours.mapping, ours.conservation, ours.stock) == (spike.molecules, spike.mapping, spike.conservation, spike.stock)
    assert ours.unmapped_right_atoms == spike.unmapped_right_atoms


def test_it_agrees_with_the_spike_validator_on_every_real_route_the_fixtures_hold():
    compared = 0
    for name in ("aspirin", "paracetamol", "caffeine", "s_ibuprofen", "sildenafil", "ibuprofen"):
        for tree in _fixture(name)["routes"]:
            _same_outcomes(tree)
            compared += 1
    assert compared >= 40


def test_it_agrees_with_the_spike_on_what_each_mapping_mutation_does(aspirin_tree):
    base = _reaction(aspirin_tree)["metadata"]["mapped_reaction_smiles"]
    left, right = base.split(">>")
    for text in (re.sub(r":\d+\]", "]", base), base.replace("[CH3:1]", "C", 1), left + ">>" + right.replace("[CH3:1]", "C", 1), "C(C>>CC"):
        tree = copy.deepcopy(aspirin_tree)
        _reaction(tree)["metadata"]["mapped_reaction_smiles"] = text
        _same_outcomes(tree)
