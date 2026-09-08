"""The producer-declared chart channel: what it accepts and what it refuses.

The `spatial` annotations' guards, applied to a chart. Two halves, and the
second is the load-bearing one: a validator that only ever refuses grows
into a mass-spectrum validator one plausible bound at a time, so there is
an explicit test that structurally-fine nonsense is ACCEPTED.
"""

from __future__ import annotations

import ast
import math
from pathlib import Path

import pytest

from openchem.chem.report_adapter import report_from_fields
from openchem.domain.report import (
    ReportResult,
    Stick,
    StickChartAnnotation,
    valid_chart_annotation,
)

_REPORT_SOURCE = Path(__file__).resolve().parent.parent / "src" / "openchem" / "domain" / "report.py"


def _annotation(**overrides) -> StickChartAnnotation:
    fields = {
        "sticks": (Stick(278.0, 0.51), Stick(280.0, 1.0), Stick(282.0, 0.49)),
        "x_label": "m/z",
        "y_label": "Relative abundance",
        "x_descending": False,
    }
    fields.update(overrides)
    return StickChartAnnotation(**fields)


def test_a_scalar_result_declares_no_chart():
    """A formula or a pKa has no picture, and the default says so. If this
    ever needed an opt-out rather than an opt-in, the channel would be
    decoration."""
    report = ReportResult(molecule_uuid="u", report_id="logp", name="LogP")
    assert report.charts == ()


def test_a_well_formed_annotation_is_accepted():
    assert valid_chart_annotation(_annotation())


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"sticks": ()}, id="no sticks at all"),
        pytest.param({"sticks": (Stick(math.nan, 1.0),)}, id="nan x"),
        pytest.param({"sticks": (Stick(1.0, math.inf),)}, id="infinite y"),
        pytest.param({"sticks": ((1.0, 2.0),)}, id="a bare tuple, not a Stick"),
        pytest.param({"sticks": [Stick(1.0, 1.0)]}, id="a list, not a tuple"),
        pytest.param({"x_label": ""}, id="unlabelled x axis"),
        pytest.param({"y_label": "   "}, id="blank y axis"),
        pytest.param({"x_descending": 1}, id="direction that is not a bool"),
    ],
)
def test_malformed_annotations_are_refused_rather_than_repaired(overrides):
    """Failing closed. A consumer handed one of these must draw nothing and
    say so -- never sort, clamp or normalise it into shape, because a
    picture built from repaired nonsense reads as a result."""
    assert not valid_chart_annotation(_annotation(**overrides))


@pytest.mark.parametrize(
    "annotation",
    [None, "a chart", 42, object()],
    ids=["none", "a string", "a number", "some other object"],
)
def test_anything_that_is_not_an_annotation_is_refused(annotation):
    assert not valid_chart_annotation(annotation)


def test_the_validator_does_not_judge_the_chemistry():
    """**THE COMPLEMENT, AND THE REASON IT EXISTS.** Every one of these is
    scientifically odd and structurally impeccable, and the generic layer
    must accept all of them -- the moment it refuses one it has become a
    mass-spectrum validator, and the Lewis-site and reaction diagrams that
    will use this channel are not spectra.

    A plausibility bound here is the `half_angle_deg < 180` mistake:
    P(tBu)3 opens past the hemisphere, and a bound written from the common
    case refused a real Tolman measurement.
    """
    assert valid_chart_annotation(_annotation(sticks=(Stick(1e6, 1.0),)))
    # Intensities summing to 7.5 rather than to 1 or to 100.
    assert valid_chart_annotation(
        _annotation(sticks=(Stick(1.0, 2.5), Stick(2.0, 5.0)))
    )
    # Out of order on purpose: producer order is preserved and meaningful.
    assert valid_chart_annotation(
        _annotation(sticks=(Stick(9.0, 1.0), Stick(1.0, 0.5)))
    )


def test_a_negative_height_is_accepted_because_signed_quantities_are_real():
    """Requiring `y >= 0` reads as structural and is a claim about the
    chemistry. This application already computes signed per-atom values --
    Crippen LogP contributions run either way -- and a difference spectrum
    is the obvious second case. A mass spectrum's own non-negativity
    belongs to the mass-spectrum tests, where it is a statement about mass
    spectra."""
    assert valid_chart_annotation(_annotation(sticks=(Stick(1.0, -0.5),)))


def test_a_sticks_label_cannot_fall_out_of_step_with_its_stick():
    """Carried ON the stick rather than in a parallel list, so "labels
    aligned with points" is true by construction and there is no
    off-by-one for the validator to catch."""
    annotation = _annotation(sticks=(Stick(280.0, 1.0, "M+2"),))
    assert annotation.sticks[0].label == "M+2"
    assert valid_chart_annotation(annotation)


def test_the_domain_never_reads_the_units_to_decide_the_direction():
    """`x_descending` is the producer's declaration. A helper that inferred
    it from `x_units` would mirror either NMR or m/z silently, and a
    mirrored spectrum does not look broken -- it looks like a different
    compound. Asserted on the SOURCE, because no input can distinguish an
    honest implementation from one that happens to guess right."""
    source = _REPORT_SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "valid_chart_annotation":
            body = ast.dump(node)
            assert "x_units" not in body
            assert "y_units" not in body
            return
    raise AssertionError("valid_chart_annotation is not in domain/report.py any more")


def test_report_from_fields_carries_charts_through():
    """The adapter ends with `**rest`, which is how `spatial` already
    arrives -- so a producer declares a chart with no change to the
    thirteen call sites that go through it."""
    annotation = _annotation()
    report = report_from_fields(
        alert_id="elemental_analysis",
        name="Elemental Analysis",
        molecule_uuid="u",
        matched=["Formula: C7H4Br2O2"],
        category="identity",
        charts=(annotation,),
    )
    assert report.charts == (annotation,)
    assert report.facts, "the facts still arrive as well"
