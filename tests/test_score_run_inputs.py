"""Which always-on properties and calculators a run must include for the user's scores to have a column (`domain/score_run_inputs.py`)."""

from __future__ import annotations

from openchem.bootstrap import build_service_container
from openchem.chem.descriptor_providers import RDKitDescriptorProvider
from openchem.domain.score_definition import ScoreDefinition
from openchem.domain.score_outputs import APPROVED
from openchem.domain.score_run_inputs import ScoreRunInputs, run_inputs_of

_OB = "calculator:oxygen_balance:Oxygen balance (CO basis)"
_SOL = "calculator:solubility:Predicted intrinsic solubility (mol/L)"


def _definition(inputs, score_id="user.s") -> ScoreDefinition:
    return ScoreDefinition(
        score_id=score_id, label="S", formula="x", result_unit="1", inputs=tuple(inputs), schema_version=1, owner="", created="2026-10-15", note="",
    )


def test_no_scores_read_nothing():
    assert run_inputs_of(()) == ScoreRunInputs()


def test_an_always_on_property_and_a_calculator_are_told_apart_and_the_calculator_is_its_id_and_not_its_fact_label():
    got = run_inputs_of([_definition([("a", "descriptor:tpsa"), ("b", _OB)])])
    assert got.descriptor_ids == ("tpsa",) and got.calculator_ids == ("oxygen_balance",) and got.scores == 1 and got.unreadable == ()


def test_two_facts_of_one_calculator_are_one_calculator():
    got = run_inputs_of([_definition([("a", _SOL), ("b", "calculator:solubility:Predicted intrinsic solubility (mg/mL)")])])
    assert got.calculator_ids == ("solubility",)


def test_what_several_scores_read_is_listed_once_and_sorted():
    got = run_inputs_of(
        [
            _definition([("p", "descriptor:tpsa"), ("l", "descriptor:mol_logp")], "user.a"),
            _definition([("l", "descriptor:mol_logp"), ("b", _OB)], "user.b"),
            _definition([("s", _SOL), ("b", _OB)], "user.c"),
        ]
    )
    assert got.descriptor_ids == ("mol_logp", "tpsa") and got.calculator_ids == ("oxygen_balance", "solubility") and got.scores == 3


def test_an_output_this_build_cannot_tick_is_named_and_not_dropped():
    got = run_inputs_of([_definition([("a", "geometry:dipole"), ("b", "descriptor:"), ("c", "calculator::x"), ("d", "tpsa")])])
    assert got.descriptor_ids == () and got.calculator_ids == ()
    assert got.unreadable == ("calculator::x", "descriptor:", "geometry:dipole", "tpsa")


def test_every_approved_output_names_something_the_application_can_tick():
    """A rename of a descriptor or a calculator would otherwise leave a score reading an id no picker offers, and the button would quietly tick nothing for it."""
    services = build_service_container()
    known_descriptors = set(RDKitDescriptorProvider().descriptor_ids())
    for output in APPROVED:
        got = run_inputs_of([_definition([("x", output.output_id)])])
        assert not got.unreadable, output.output_id
        for descriptor_id in got.descriptor_ids:
            assert descriptor_id in known_descriptors, output.output_id
        for calculator_id in got.calculator_ids:
            assert services.calculator_registry.get(calculator_id) is not None, output.output_id
