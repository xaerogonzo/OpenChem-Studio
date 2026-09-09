"""The quantitative-limit model, and the compatibility it must not break.

Stage 6a. `Rule` gained a field that every existing ruleset does not use,
so the guards here are in two halves: that a limit can be expressed at all,
and that the 91 rules shipped before it existed are untouched.

**THE SPLIT THIS MODEL EXISTS FOR IS STRUCTURAL.** `Rule` already separates
`LegalSource` -- the regulation in its own words -- from
`MachineInterpretation`, our reading of it. `SourceLimitFact` and
`QuantitativeLimit` are that same split one level down, as two objects
rather than one flat record with `source_*` prefixes, so a reader can tell
a transcription from a reading FROM THE TYPE.
"""

from __future__ import annotations

import dataclasses

import pytest

from openchem.chem.regulatory.loader import SHIPPED_ROOT, load_ruleset
from openchem.chem.regulatory.types import (
    NORMALIZED_UNITS,
    LimitPrecision,
    LimitType,
    QuantitativeLimit,
    Rule,
    SourceLimitFact,
)


def _fact(**overrides) -> SourceLimitFact:
    values = {"value": "10", "unit": "ppm", "raw_notation": "", "qualifier": ""}
    values.update(overrides)
    return SourceLimitFact(**values)


def _shipped_rules() -> list[Rule]:
    rules: list[Rule] = []
    for path in sorted(SHIPPED_ROOT.glob("*.json")):
        rules.extend(load_ruleset(path).rules)
    return rules


# --- the compatibility boundary ------------------------------------------


def test_every_shipped_rule_loads_with_no_quantitative_limits():
    """The real compatibility boundary, asserted over the whole population.

    THE SETUP IS ASSERTED FIRST: an empty shipped set would satisfy the
    claim vacuously, and this project has recorded a population walk
    collapsing to zero and reading as a clean pass.
    """
    rules = _shipped_rules()

    assert len(rules) > 80, f"only {len(rules)} shipped rules were loaded"
    assert all(rule.quantitative_limits == () for rule in rules)


def test_a_rule_built_without_the_field_is_identical_to_one_built_with_an_empty_tuple():
    """Additive means additive: the default is not merely empty, it is the
    same object a caller that never heard of this field produces."""
    from openchem.chem.regulatory.types import (
        Domain,
        Jurisdiction,
        LegalSource,
        MachineInterpretation,
        MatchType,
    )

    common = {
        "rule_id": "probe",
        "display_name": "Probe",
        "domain": Domain.OCCUPATIONAL_EXPOSURE,
        "jurisdiction": Jurisdiction.US,
        "match_type": MatchType.IDENTITY,
        "legal": LegalSource(authority="a", instrument="b", section="c"),
        "interpretation": MachineInterpretation(),
    }

    assert Rule(**common) == Rule(**common, quantitative_limits=())


def test_the_loader_reads_a_limit_back_out_of_a_ruleset(tmp_path):
    """A limit survives the JSON the build step writes.

    Through `load_ruleset` rather than by constructing the dataclass, so
    this exercises the deserialiser a shipped file goes through.
    """
    import json

    path = tmp_path / "probe.json"
    path.write_text(
        json.dumps(
            {
                "ruleset_id": "probe",
                "domain": "occupational_exposure",
                "jurisdiction": "us",
                "rules": [
                    {
                        "rule_id": "probe.chlorine",
                        "domain": "occupational_exposure",
                        "jurisdiction": "us",
                        "quantitative_limits": [
                            {
                                "source": {
                                    "value": "(C)1",
                                    "unit": "ppm",
                                    "raw_notation": "(C)",
                                    "qualifier": "skin",
                                },
                                "limit_type": "ceiling",
                                "precision": "approximate",
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    limit = load_ruleset(path).rules[0].quantitative_limits[0]

    assert limit.source.value == "(C)1"
    assert limit.source.raw_notation == "(C)"
    assert limit.source.qualifier == "skin"
    assert limit.limit_type is LimitType.CEILING
    assert limit.precision is LimitPrecision.APPROXIMATE
    assert limit.normalized_value is None


# --- source fact against interpretation ----------------------------------


def test_a_reader_can_tell_a_transcription_from_a_reading_by_the_TYPE():
    """Not by a comment, and not by a field-name prefix.

    A flat object carrying `source_value` beside `normalized_value` puts
    the whole burden on naming discipline; two types put it on the
    compiler. `SourceLimitFact` holds only what the regulation printed.
    """
    printed = {f.name for f in dataclasses.fields(SourceLimitFact)}
    read = {f.name for f in dataclasses.fields(QuantitativeLimit)}

    assert printed == {"value", "unit", "raw_notation", "qualifier"}
    assert "limit_type" not in printed, "a classification is not a transcription"
    assert "normalized_value" not in printed
    assert "source" in read, "the reading must carry the thing it is a reading OF"


def test_the_notation_that_produced_the_reading_survives_it():
    """If `(C)` is what makes a limit a CEILING, the `(C)` is kept.

    Otherwise an auditor can see the interpretation and not the token that
    justified it -- and `raw_notation` is DISTINCT from `qualifier`, which
    is the source's footnote and a different thing entirely.
    """
    limit = QuantitativeLimit(
        source=_fact(
            value="(C)1",
            raw_notation="(C)",
            qualifier="May be absorbed through the skin.",
        ),
        limit_type=LimitType.CEILING,
    )

    assert limit.source.raw_notation == "(C)"
    assert limit.source.qualifier != limit.source.raw_notation
    assert "(C)" in limit.source.value


# --- what the model refuses ----------------------------------------------


@pytest.mark.parametrize(
    ("overrides", "why"),
    [
        ({"normalized_value": float("nan")}, "NaN"),
        ({"normalized_value": float("inf")}, "infinity"),
        ({"normalized_value": -1.0}, "a negative exposure limit"),
    ],
)
def test_a_nonsensical_normalized_value_is_refused_at_construction(overrides, why):
    """Not left for a builder to catch later.

    A NaN limit is a number every later comparison silently answers False
    to, which is indistinguishable from a substance that is under its
    limit.
    """
    with pytest.raises(ValueError):
        QuantitativeLimit(
            source=_fact(),
            limit_type=LimitType.TWA_8H,
            normalized_unit="ppm",
            normalization_method="probe",
            **overrides,
        )


def test_a_normalized_unit_comes_from_a_closed_vocabulary():
    """Or `mg/m3`, `mg/m^3` and `mg per cubic meter` become three unrelated
    units the moment a second regulator is read. The SOURCE unit stays
    verbatim and is deliberately not drawn from this set."""
    with pytest.raises(ValueError, match="not a normalized unit"):
        QuantitativeLimit(
            source=_fact(),
            limit_type=LimitType.TWA_8H,
            normalized_value=1.0,
            normalized_unit="parts per million",
            normalization_method="probe",
        )

    accepted = QuantitativeLimit(
        source=_fact(unit="parts of vapor per million parts of air"),
        limit_type=LimitType.TWA_8H,
        normalized_value=1.0,
        normalized_unit="ppm",
        normalization_method="probe",
    )
    assert accepted.source.unit not in NORMALIZED_UNITS


def test_a_normalized_value_must_say_why_the_conversion_is_valid():
    """ppm to mg/m3 is not a unit conversion -- it needs the substance's
    molar mass AND stated temperature and pressure. A derived number
    without its justification is the unexplained value this project has
    spent whole branches removing."""
    with pytest.raises(ValueError, match="why the conversion is valid"):
        QuantitativeLimit(
            source=_fact(),
            limit_type=LimitType.TWA_8H,
            normalized_value=29.0,
            normalized_unit="mg/m3",
        )


def test_absence_is_expressible_and_is_not_zero():
    """A row with no numeric PEL is a different statement from a PEL of
    zero, and this project already has the rule -- `n/a` is not 0. The
    model must be able to hold a source fact with no normalized value at
    all rather than defaulting one in."""
    limit = QuantitativeLimit(source=_fact(value="", unit=""), limit_type=LimitType.OTHER)

    assert limit.normalized_value is None
    assert limit.normalized_value != 0


def test_a_substance_can_carry_more_than_one_limit():
    """A TUPLE, never one optional limit. A substance can have a TWA *and*
    a ceiling, and a model assuming one substance means one number would
    need rewriting the first time a source prints two."""
    from openchem.chem.regulatory.types import (
        Domain,
        Jurisdiction,
        LegalSource,
        MachineInterpretation,
        MatchType,
    )

    rule = Rule(
        rule_id="probe",
        display_name="Probe",
        domain=Domain.OCCUPATIONAL_EXPOSURE,
        jurisdiction=Jurisdiction.US,
        match_type=MatchType.IDENTITY,
        legal=LegalSource(authority="a", instrument="b", section="c"),
        interpretation=MachineInterpretation(),
        quantitative_limits=(
            QuantitativeLimit(source=_fact(value="1"), limit_type=LimitType.TWA_8H),
            QuantitativeLimit(
                source=_fact(value="(C)5", raw_notation="(C)"),
                limit_type=LimitType.CEILING,
            ),
        ),
    )

    assert {limit.limit_type for limit in rule.quantitative_limits} == {
        LimitType.TWA_8H,
        LimitType.CEILING,
    }


def test_the_limit_types_stay_semantically_distinct():
    """A ceiling and a peak are not synonyms, and an 8-hour average is not
    either of them. Collapsing any two would make every reported number
    ambiguous about what it is a limit ON."""
    assert len({member.value for member in LimitType}) == len(list(LimitType))
    assert LimitType.CEILING is not LimitType.PEAK
    assert {"twa_8h", "stel", "ceiling", "peak", "other"} == {
        member.value for member in LimitType
    }


def test_precision_has_three_values_because_a_source_may_say_nothing():
    """Table Z-1's footnote (b) makes the SAME COLUMN carry two epistemic
    statuses -- a mg/m3 entry is exact alone and approximate beside a ppm
    entry. A two-valued flag would force a guess on every source that is
    silent, which is how an unstated precision becomes a claimed one."""
    assert {member.value for member in LimitPrecision} == {
        "exact",
        "approximate",
        "unstated",
    }
    assert (
        QuantitativeLimit(source=_fact(), limit_type=LimitType.TWA_8H).precision
        is LimitPrecision.UNSTATED
    )
