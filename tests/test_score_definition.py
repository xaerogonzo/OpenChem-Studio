"""A score's definition: reading it back, the rules it must meet, its label, its digest (`domain/score_definition.py`).

The label rules are the ones that matter to a person who is not looking at the formula: a score must never read as a number the application computes
(`name_collision`), and the suffix that says so is never part of the text that can be edited (`display_label`). The rest is the shape of the data.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import replace

import pytest

from openchem.domain.score_constants import Constant
from openchem.domain.score_definition import (
    DISPLAY_SUFFIX,
    FORMAT_DEFAULTS,
    FORMAT_REFUSE,
    MAX_LABEL,
    MAX_NOTE,
    MAX_OWNER,
    ON_MISSING_DEFAULT,
    ON_MISSING_REFUSE,
    SCHEMA_VERSION,
    SCORE_ID_PREFIX,
    DamagedDefinition,
    NewerDefinition,
    ScoreDefinition,
    check_computation,
    check_score_definition,
    name_collision,
    new_score_id,
    normalise_name,
    output_names,
    policy_for,
    slugify,
)
from openchem.domain.score_formula import FormulaError, Problem


def _definition(**changes) -> ScoreDefinition:
    base = ScoreDefinition(
        score_id="user.my_score",
        label="My blend",
        formula="ramp(psa, hi, 60) * ramp(logp, 5, 2)",
        result_unit="1",
        inputs=(("psa", "descriptor:tpsa"), ("logp", "descriptor:mol_logp")),
        constants=(Constant("hi", 140.0, "Å^2"),),
        owner="Alex",
        created="2026-10-14",
        note="a first try",
    )
    return replace(base, **changes)


# --- reading and writing --------------------------------------------------------------------------------------------------------


def test_a_definition_round_trips_through_json_unchanged():
    definition = _definition()
    again = ScoreDefinition.from_dict(json.loads(json.dumps(definition.to_dict())))
    assert again == definition and again.digest == definition.digest


def test_the_stored_form_names_every_field():
    assert set(_definition().to_dict()) == {
        "score_id", "label", "schema_version", "formula", "result_unit", "inputs", "constants", "on_missing", "owner", "created", "note",
    }


def test_the_label_is_stored_without_the_suffix_and_shown_with_it():
    definition = _definition()
    assert definition.label == "My blend" and DISPLAY_SUFFIX not in definition.to_dict()["label"]
    assert definition.display_label == "My blend (user-defined, unvalidated)"
    assert DISPLAY_SUFFIX == "(user-defined, unvalidated)"


def test_optional_fields_default_when_a_file_omits_them():
    data = _definition().to_dict()
    for key in ("owner", "created", "note", "constants"):
        del data[key]
    again = ScoreDefinition.from_dict(data)
    assert (again.owner, again.created, again.note, again.constants) == ("", "", "", ())


@pytest.mark.parametrize(
    "mutate, why",
    [
        (lambda d: "not an object", "an object"),
        (lambda d: {**d, "schema_version": True}, "schema_version"),
        (lambda d: {**d, "schema_version": 0}, "schema_version"),
        (lambda d: {**d, "schema_version": "1"}, "schema_version"),
        (lambda d: {k: v for k, v in d.items() if k != "schema_version"}, "schema_version"),
        (lambda d: {k: v for k, v in d.items() if k != "score_id"}, "score_id"),
        (lambda d: {**d, "label": 5}, "label"),
        (lambda d: {**d, "formula": None}, "formula"),
        (lambda d: {**d, "result_unit": 1}, "result_unit"),
        (lambda d: {**d, "on_missing": []}, "on_missing"),
        (lambda d: {**d, "owner": 3}, "owner"),
        (lambda d: {**d, "note": ["x"]}, "note"),
        (lambda d: {**d, "created": 20261014}, "created"),
        (lambda d: {**d, "inputs": "psa"}, "inputs"),
        (lambda d: {k: v for k, v in d.items() if k != "inputs"}, "inputs"),
        (lambda d: {**d, "inputs": [["psa"]]}, "[name, output id]"),
        (lambda d: {**d, "inputs": [["psa", 3]]}, "[name, output id]"),
        (lambda d: {**d, "inputs": [["a", "b", "c"]]}, "[name, output id]"),
        (lambda d: {**d, "constants": {"hi": 1}}, "constants"),
        (lambda d: {**d, "constants": ["hi"]}, "not an object"),
        (lambda d: {**d, "constants": [{"name": "hi", "value": 1}]}, "text name and a text unit"),
        (lambda d: {**d, "constants": [{"name": "hi", "value": "1", "unit": "1"}]}, "finite number"),
        (lambda d: {**d, "constants": [{"name": "hi", "value": True, "unit": "1"}]}, "finite number"),
        (lambda d: {**d, "constants": [{"name": "hi", "value": math.nan, "unit": "1"}]}, "finite number"),
        (lambda d: {**d, "constants": [{"name": "hi", "value": math.inf, "unit": "1"}]}, "finite number"),
    ],
)
def test_a_definition_that_is_not_one_is_damaged_and_says_why(mutate, why):
    with pytest.raises(DamagedDefinition, match=why):
        ScoreDefinition.from_dict(mutate(_definition().to_dict()))


def test_a_newer_definition_is_told_apart_from_a_damaged_one_and_whatever_else_it_holds():
    with pytest.raises(NewerDefinition, match="newer version"):
        ScoreDefinition.from_dict({"schema_version": SCHEMA_VERSION + 1, "anything": "else"})
    assert not issubclass(NewerDefinition, DamagedDefinition) and not issubclass(DamagedDefinition, NewerDefinition)


# --- the digest -----------------------------------------------------------------------------------------------------------------


def test_the_digest_is_sixteen_hex_digits_and_stable():
    digest = _definition().digest
    assert re.fullmatch(r"[0-9a-f]{16}", digest) and _definition().digest == digest


@pytest.mark.parametrize(
    "change",
    [
        {"formula": "ramp(psa, hi, 61) * ramp(logp, 5, 2)"},
        {"result_unit": "%"},
        {"inputs": (("psa", "descriptor:tpsa"), ("lp", "descriptor:mol_logp"))},
        {"inputs": (("psa", "descriptor:labute_asa"), ("logp", "descriptor:mol_logp"))},
        {"constants": (Constant("hi", 141.0, "Å^2"),)},
        {"constants": (Constant("hi", 140.0, "nm^2"),)},
        {"constants": (Constant("high", 140.0, "Å^2"),)},
        {"schema_version": SCHEMA_VERSION + 1},
        {"on_missing": "zero"},
    ],
)
def test_what_changes_the_number_changes_the_digest(change):
    assert _definition(**change).digest != _definition().digest


@pytest.mark.parametrize("change", [{"label": "Other"}, {"owner": "Sam"}, {"note": "changed"}, {"created": "2020-01-01"}, {"score_id": "user.other"}])
def test_what_does_not_change_the_number_does_not_change_the_digest(change):
    assert _definition(**change).digest == _definition().digest


# --- the rules a definition must meet --------------------------------------------------------------------------------------------


def test_a_good_definition_checks_and_returns_its_formula():
    formula = check_score_definition(_definition())
    assert formula.text == "ramp(psa, hi, 60) * ramp(logp, 5, 2)"


@pytest.mark.parametrize(
    "change, why",
    [
        ({"score_id": "my_score"}, "user\\."),
        ({"score_id": "user."}, "user\\."),
        ({"score_id": "user.My_Score"}, "user\\."),
        ({"score_id": "user.1abc"}, "user\\."),
        ({"score_id": "user." + "a" * 41}, "user\\."),
        ({"schema_version": SCHEMA_VERSION + 1}, "is format 3"),
        ({"schema_version": FORMAT_DEFAULTS}, "no defaults is format 1"),
        ({"on_missing": "zero"}, "policies are"),
        ({"label": ""}, "empty"),
        ({"label": "  "}, "empty"),
        ({"label": " padded"}, "spaces"),
        ({"label": "padded "}, "spaces"),
        ({"label": "x" * (MAX_LABEL + 1)}, f"at most {MAX_LABEL}"),
        ({"label": "two\nlines"}, "cannot be shown"),
        ({"label": "tab\there"}, "cannot be shown"),
        ({"label": "!!! ???"}, "letter or digit"),
        ({"owner": "x" * (MAX_OWNER + 1)}, "owner"),
        ({"owner": "a\nb"}, "owner"),
        ({"note": "x" * (MAX_NOTE + 1)}, "note"),
        ({"note": "bell\x07"}, "note"),
        ({"created": "14/10/2026"}, "YYYY-MM-DD"),
        ({"created": "2026-1-4"}, "YYYY-MM-DD"),
        ({"inputs": (), "constants": (), "formula": "1 + 1"}, "at least one"),
    ],
)
def test_a_field_that_is_not_usable_is_refused_with_the_definition_code(change, why):
    with pytest.raises(FormulaError, match=why) as caught:
        check_score_definition(_definition(**change))
    assert caught.value.problem is Problem.DEFINITION


# --- the second policy: a default for an input nobody calculated -----------------------------------------------------------------------


def _with_defaults(**defaults) -> ScoreDefinition:
    return _definition(on_missing=ON_MISSING_DEFAULT, schema_version=FORMAT_DEFAULTS, defaults=tuple(defaults.items()))


def test_a_definition_with_no_default_is_the_first_policy_and_format_one_as_every_earlier_one_was():
    definition = _definition()
    assert definition.defaults == () and definition.on_missing == ON_MISSING_REFUSE == "refuse" and definition.schema_version == FORMAT_REFUSE == 1
    assert "defaults" not in definition.to_dict(), "a definition without defaults is byte-for-byte what an earlier build wrote"
    assert policy_for(()) == ("refuse", 1) and policy_for([]) == ("refuse", 1)


def test_a_default_makes_the_definition_the_second_policy_and_format_two():
    assert policy_for([("logp", 1.0)]) == (ON_MISSING_DEFAULT, FORMAT_DEFAULTS) == ("default", 2)
    check_score_definition(_with_defaults(logp=1.0))


def test_a_default_is_stored_and_read_back_unchanged():
    definition = _with_defaults(logp=2.5, psa=0.0)
    stored = definition.to_dict()
    assert stored["defaults"] == [["logp", 2.5], ["psa", 0.0]] and stored["on_missing"] == "default" and stored["schema_version"] == 2
    again = ScoreDefinition.from_dict(json.loads(json.dumps(stored)))
    assert again == definition and again.digest == definition.digest and again.defaults == (("logp", 2.5), ("psa", 0.0))


def test_the_digest_of_a_definition_without_defaults_is_the_digest_it_always_had_and_a_default_changes_it():
    assert _definition().digest == _definition(defaults=()).digest
    assert _with_defaults(logp=1.0).digest != _definition().digest
    assert _with_defaults(logp=1.0).digest != _with_defaults(logp=2.0).digest
    assert _with_defaults(logp=1.0).digest != _with_defaults(psa=1.0).digest


@pytest.mark.parametrize(
    "definition, why",
    [
        (_definition(on_missing=ON_MISSING_DEFAULT, schema_version=FORMAT_DEFAULTS), "needs at least one"),
        (_definition(defaults=(("logp", 1.0),)), "needs none"),
        (_definition(on_missing=ON_MISSING_DEFAULT, schema_version=FORMAT_REFUSE, defaults=(("logp", 1.0),)), "is format 1"),
        (_definition(on_missing=ON_MISSING_REFUSE, schema_version=FORMAT_DEFAULTS), "no defaults is format 1"),
        (_definition(on_missing=ON_MISSING_DEFAULT, schema_version=FORMAT_DEFAULTS, defaults=(("ghost", 1.0),)), "not one of the inputs"),
        (_definition(on_missing=ON_MISSING_DEFAULT, schema_version=FORMAT_DEFAULTS, defaults=(("logp", 1.0), ("logp", 2.0))), "two defaults"),
        (_definition(on_missing=ON_MISSING_DEFAULT, schema_version=FORMAT_DEFAULTS, defaults=(("logp", math.nan),)), "finite number"),
        (_definition(on_missing=ON_MISSING_DEFAULT, schema_version=FORMAT_DEFAULTS, defaults=(("logp", math.inf),)), "finite number"),
        (_definition(on_missing=ON_MISSING_DEFAULT, schema_version=FORMAT_DEFAULTS, defaults=(("logp", True),)), "finite number"),
    ],
)
def test_defaults_and_the_policy_must_say_the_same_thing(definition, why):
    with pytest.raises(FormulaError, match=why) as caught:
        check_score_definition(definition)
    assert caught.value.problem is Problem.DEFINITION
    assert caught.value.field == ("" if "format" in why else "inputs"), "a problem with a default belongs to the inputs box; one with the format belongs to nothing the person types"


@pytest.mark.parametrize(
    "mutate, why",
    [
        (lambda d: {**d, "defaults": "logp"}, "defaults is not a list"),
        (lambda d: {**d, "defaults": [["logp"]]}, r"\[input name, number\]"),
        (lambda d: {**d, "defaults": [[1, 2.0]]}, r"\[input name, number\]"),
        (lambda d: {**d, "defaults": [["a", 1, 2]]}, r"\[input name, number\]"),
        (lambda d: {**d, "defaults": [["logp", "1"]]}, "finite number"),
        (lambda d: {**d, "defaults": [["logp", True]]}, "finite number"),
        (lambda d: {**d, "defaults": [["logp", math.nan]]}, "finite number"),
        (lambda d: {**d, "defaults": [["logp", math.inf]]}, "finite number"),
    ],
)
def test_a_default_that_is_not_one_is_damaged_and_says_why(mutate, why):
    with pytest.raises(DamagedDefinition, match=why):
        ScoreDefinition.from_dict(mutate(_with_defaults(logp=1.0).to_dict()))


def test_an_integer_default_is_read_as_a_float():
    data = _with_defaults(logp=1.0).to_dict()
    data["defaults"] = [["logp", 1]]
    assert ScoreDefinition.from_dict(data).defaults == (("logp", 1.0),) and isinstance(ScoreDefinition.from_dict(data).defaults[0][1], float)


def test_a_definition_in_a_format_after_this_one_is_kept_and_not_read_whatever_it_holds():
    with pytest.raises(NewerDefinition):
        ScoreDefinition.from_dict({**_with_defaults(logp=1.0).to_dict(), "schema_version": SCHEMA_VERSION + 1, "defaults": "something new"})


def test_a_note_may_have_line_breaks_and_is_otherwise_free_text():
    check_score_definition(_definition(note="line one\nline two Å β"))


def test_the_inputs_the_constants_the_syntax_and_the_units_keep_their_own_codes():
    cases = [
        (_definition(inputs=(("psa", "descriptor:tpsa"), ("logp", "descriptor:nothing"))), Problem.OUTPUT),
        (_definition(inputs=(("psa", "descriptor:num_hbd"), ("logp", "calculator:hbond_sites:Donors"))), Problem.OUTPUT),
        (_definition(inputs=(("psa", "descriptor:esol_logs"), ("logp", "calculator:solubility:Predicted intrinsic solubility (mol/L)")), constants=(), formula="psa + logp"), Problem.CONSENSUS),
        (_definition(constants=(Constant("hi", math.nan, "Å^2"),)), Problem.CONSTANT),
        (_definition(formula="ramp(psa, hi, 60) *"), Problem.SYNTAX),
        (_definition(formula="ramp(psa, hi, 60) * ramp(logp, 5, 2) * nothing"), Problem.NAME),
        (_definition(formula="ramp(psa, hi, 60)"), Problem.INPUTS),
        (_definition(result_unit="%"), Problem.UNIT),
        (_definition(result_unit="furlong"), Problem.UNIT),
        (_definition(result_unit=""), Problem.UNIT),
    ]
    for definition, problem in cases:
        with pytest.raises(FormulaError) as caught:
            check_score_definition(definition)
        assert caught.value.problem is problem, (definition.formula, caught.value.problem, caught.value.message)


def test_a_result_unit_error_names_the_result_unit():
    with pytest.raises(FormulaError, match="the result unit 'furlong'"):
        check_score_definition(_definition(result_unit="furlong"))


# --- the label may not look like a name the application provides ------------------------------------------------------------------


@pytest.mark.parametrize(
    "label, reserved, collides",
    [
        ("CNS MPO", ["cns_mpo"], "cns_mpo"),  # equal once punctuation and case are gone
        ("My CNS-MPO score", ["cns_mpo"], "cns_mpo"),  # contains it
        ("mpo", ["cns_mpo"], "cns_mpo"),  # contained by it
        ("Lipinski", ["Lipinski rule of five"], "Lipinski rule of five"),  # contained by a display name
        ("Ångström", ["angstrom"], "angstrom"),  # accents
        ("Polar surface", ["polar_surface_area"], "polar_surface_area"),
        ("pKa blend", ["pka"], "pka"),  # a short name still blocks when it is three characters
        ("QED variant", ["qed"], "qed"),
        ("Fine name", ["cns_mpo", "logd"], None),
        ("ab", ["ab"], None),  # shorter than three characters blocks nothing
        ("Zebra", [], None),
    ],
)
def test_name_collision(label, reserved, collides):
    assert name_collision(label, reserved) == collides


def test_a_label_close_to_a_registry_name_is_refused_naming_it():
    with pytest.raises(FormulaError, match="too close to 'cns_mpo'") as caught:
        check_score_definition(_definition(label="CNS MPO v2"), ["cns_mpo", "logd"])
    assert caught.value.problem is Problem.DEFINITION
    check_score_definition(_definition(label="CNS MPO v2"), ["logd"])


def test_a_label_close_to_an_approved_outputs_name_is_refused_without_the_caller_saying_so():
    for label in ("TPSA", "My tpsa", "mol wt", "Oxygen balance (CO basis)", "Predicted intrinsic solubility (mol/L) again"):
        with pytest.raises(FormulaError, match="too close to"):
            check_score_definition(_definition(label=label))


def test_the_approved_outputs_names_are_read_from_the_table():
    names = output_names()
    assert "tpsa" in names and "mol_wt" in names and "Oxygen balance (CO basis)" in names
    assert not any(name.startswith(("descriptor:", "calculator:")) for name in names)
    assert len(names) == len(set(names))


def test_check_computation_does_not_look_at_the_label():
    definition = _definition(label="TPSA")
    check_computation(definition)
    with pytest.raises(FormulaError):
        check_score_definition(definition)


def test_normalise_name_drops_case_accents_and_punctuation():
    assert normalise_name("  CNS-MPO (v2)!  ") == "cnsmpov2"
    assert normalise_name("Ångström") == "angstrom"
    assert normalise_name("!!!") == ""


# --- ids ------------------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "label, slug",
    [
        ("My blend", "my_blend"),
        ("  Spaces   and -- punctuation!! ", "spaces_and_punctuation"),
        ("Ångström score", "angstrom_score"),
        ("2nd try", "score_2nd_try"),
        ("!!!", "score"),
        ("评分", "score"),
        ("", "score"),
        ("x" * 100, "x" * 40),
    ],
)
def test_slugify(label, slug):
    assert slugify(label) == slug


def test_a_new_id_is_user_dot_the_slug_and_never_one_in_use():
    assert new_score_id("My blend", []) == "user.my_blend"
    taken = {"user.my_blend", "user.my_blend_2"}
    assert new_score_id("My blend", taken) == "user.my_blend_3"
    assert new_score_id("Another", taken) == "user.another"


def test_a_new_id_always_fits_the_id_rule_even_when_the_slug_is_at_its_longest():
    rule = re.compile(r"user\.[a-z][a-z0-9_]{0,39}")
    taken: set[str] = set()
    for _ in range(12):
        new = new_score_id("x" * 80, taken)
        assert rule.fullmatch(new), new
        taken.add(new)
    assert len(taken) == 12 and SCORE_ID_PREFIX == "user."


# --- the limits are these numbers, and the edge of each is the last thing accepted ---------------------------------------------------


def test_the_limits_are_these_numbers():
    """Pinned as numbers: a test that reads a limit by name moves with a mutant that moves it (slice 1's lesson, met again)."""
    from openchem.domain.score_definition import (
        MAX_DEFINITIONS,
        MIN_NAME_CHARACTERS,
        ON_MISSING_REFUSE,
    )

    assert (MAX_LABEL, MAX_OWNER, MAX_NOTE, MAX_DEFINITIONS, MIN_NAME_CHARACTERS) == (80, 80, 500, 100, 3)
    assert ON_MISSING_REFUSE == "refuse" and _definition().on_missing == "refuse" and _definition().to_dict()["on_missing"] == "refuse"


def test_a_label_an_owner_and_a_note_of_exactly_the_limit_are_accepted():
    check_score_definition(_definition(label="x" * 80))
    check_score_definition(_definition(owner="o" * 80))
    check_score_definition(_definition(note="n" * 500))
    for change in ({"label": "x" * 81}, {"owner": "o" * 81}, {"note": "n" * 501}):
        with pytest.raises(FormulaError):
            check_score_definition(_definition(**change))


def test_the_digest_of_a_definition_without_defaults_is_the_literal_origin_master_computes_for_it():
    """Computed by `origin/master`'s `score_definition` (loaded from git) for this very definition before defaults existed: a definition made then keeps its digest."""
    assert _definition().digest == "e8bde0269b3e3ffe"


def test_a_default_is_hashed_at_the_precision_it_is_declared():
    assert _with_defaults(logp=3.5).digest != _with_defaults(logp=3.6).digest != _with_defaults(logp=3.0).digest != _with_defaults(logp=3.0000001).digest
