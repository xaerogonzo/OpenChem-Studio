"""The producer-declared chart channel: what it accepts and what it refuses.

The `spatial` annotations' guards, applied to a chart. Two halves, and the
second is the load-bearing one: a validator that only ever refuses grows
into a mass-spectrum validator one plausible bound at a time, so there is
an explicit test that structurally-fine nonsense is ACCEPTED.
"""

from __future__ import annotations

import ast
import math
import typing
from pathlib import Path

import pytest

from openchem.chem.report_adapter import report_from_fields
from openchem.domain.report import (
    LineChartAnnotation,
    LineSeries,
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


# --- the second kind: a continuous curve -------------------------------------


def _line(series_points, **overrides):
    fields = {
        "series": tuple(
            LineSeries(points=points, name=name)
            for name, points in series_points
        ),
        "x_label": "pH",
        "y_label": "Fraction",
        "x_descending": False,
    }
    fields.update(overrides)
    return LineChartAnnotation(**fields)


_CURVE = (("HA", ((0.0, 1.0), (7.0, 0.5), (14.0, 0.0))),)


def test_a_well_formed_curve_is_accepted():
    assert valid_chart_annotation(_line(_CURVE))


def test_the_union_holds_both_kinds_and_dispatch_is_by_isinstance():
    """A third kind must cost a `|` and nothing else.

    `spatial` shipped as three from the start; this channel shipped as
    one and the note on `ChartAnnotation` promised the second would be
    additive. Asserted so a later consumer written around a bare
    `StickChartAnnotation` is caught here rather than by a chart that
    silently fails to draw.
    """
    from openchem.domain.report import ChartAnnotation

    from openchem.domain.report import DepictionAnnotation

    assert StickChartAnnotation in typing.get_args(ChartAnnotation)
    assert LineChartAnnotation in typing.get_args(ChartAnnotation)
    assert DepictionAnnotation in typing.get_args(ChartAnnotation)


@pytest.mark.parametrize(
    "points",
    [
        ((0.0, 1.0), (7.0, 0.5), (14.0, 0.0)),
        ((14.0, 0.0), (7.0, 0.5), (0.0, 1.0)),
        ((0.0, 1.0), (7.0, 0.5), (7.0, 0.4), (14.0, 0.0)),
    ],
    ids=["ascending", "descending", "duplicate-x"],
)
def test_a_monotonic_series_is_accepted_in_either_direction(points):
    """NON-DECREASING or NON-INCREASING, never strict.

    Two values at one x is a real thing to have -- two measurements at
    one pH, a step in a titration -- and a producer may hand over a curve
    running either way, so requiring strict increase would refuse both.
    """
    assert valid_chart_annotation(_line((("s", points),)))


def test_a_scrambled_series_is_REFUSED_where_a_scrambled_stick_list_is_not():
    """The one deliberate break from the sibling kind, and the geometry is why.

    Sticks are drawn independently at their own positions, so order
    affects only which of two sharing an x a hit test resolves to -- and
    `StickChartAnnotation` preserves producer order for exactly that
    reason. A line is a POLYLINE: consecutive points are joined, so order
    is not metadata about the picture, it IS the picture.

    Asserted as a PAIR so the difference is visible in one place. The
    same x values, one kind accepting and the other refusing.
    """
    scrambled = ((0.0, 1.0), (14.0, 0.0), (7.0, 0.5))
    assert not valid_chart_annotation(_line((("s", scrambled),)))

    assert valid_chart_annotation(
        StickChartAnnotation(
            sticks=tuple(Stick(x, y) for x, y in scrambled),
            x_label="m/z",
            y_label="Relative abundance",
            x_descending=False,
        )
    ), "the stick kind is unmoved -- it never required order and still does not"


def test_a_named_series_holding_nothing_is_refused():
    """A legend entry with no curve under it reads as "this is zero here".

    `sticks` requires at least one member because `charts == ()` is
    already how a producer says it has no chart; a series is the same
    contradiction one level down. A producer with nothing to say for a
    series omits the series.
    """
    assert not valid_chart_annotation(_line((("HA", ()),)))
    assert not valid_chart_annotation(_line((("HA", ((0.0, 1.0),)), ("A-", ()))))


def test_series_are_NOT_required_to_share_an_x_grid():
    """The refusal this DECLINES, and the reason it was tempting.

    The five pH calculators all sample `ph_grid`, so a shared-grid rule
    would pass on every producer that exists today and refuse the first
    legitimate overlay -- a computed curve against a measured one,
    sampled where the instrument sampled. A bound written from the common
    case is the `half_angle_deg < 180` mistake, which refused a real
    Tolman measurement.
    """
    assert valid_chart_annotation(
        _line((
            ("computed", ((0.0, 1.0), (1.0, 0.5), (2.0, 0.2))),
            ("measured", ((0.3, 0.9), (1.7, 0.3))),
        ))
    )


def test_a_structurally_fine_curve_that_says_nothing_useful_is_ACCEPTED():
    """The load-bearing half, and the reason this file exists.

    A validator that only ever refuses grows into a domain validator one
    plausible bound at a time. None of this is checked: that fractions
    lie in [0, 1], that they sum to one, that pH is between 0 and 14,
    that y is monotonic, or that the curve resembles a titration. They
    are chemistry claims and the producers' own tests hold them.
    """
    assert valid_chart_annotation(
        _line((("nonsense", ((-500.0, 1e9), (0.0, -1e9), (500.0, 0.0))),)),
        )


def test_nan_is_refused_and_is_not_a_way_to_write_a_gap():
    """Recorded as well as enforced.

    The next reader wanting a discontinuous curve will find the validator
    refusing NaN with no supported way to express one, and the tempting
    repair is to weaken the check. A series per segment is the cheap
    answer and needs nothing new.
    """
    assert not valid_chart_annotation(_line((("s", ((0.0, 1.0), (1.0, math.nan))),)))
    assert not valid_chart_annotation(_line((("s", ((0.0, 1.0), (math.inf, 0.5))),)))

    segments = _line((("s (0-1)", ((0.0, 1.0), (1.0, 0.5))),
                      ("s (2-3)", ((2.0, 0.4), (3.0, 0.1)))))
    assert valid_chart_annotation(segments), "two segments express the gap"


def test_a_boolean_is_not_a_coordinate():
    """`isinstance(True, int)` is True in Python.

    A producer handing over a flag where a coordinate belongs would
    otherwise pass every numeric check and plot at 1.0 -- a picture built
    from a type error, which reads as a result.
    """
    assert not valid_chart_annotation(_line((("s", ((0.0, 1.0), (True, 0.5))),)))


def test_the_axis_rules_are_the_SAME_for_both_kinds():
    """One concept, one implementation.

    Both branches ask `_valid_axes`, so the two cannot drift apart on
    what an axis IS -- the drift this repository has paid for whenever
    one concept had two implementations.
    """
    assert not valid_chart_annotation(_line(_CURVE, x_label="  "))
    assert not valid_chart_annotation(_line(_CURVE, y_label=""))
    assert not valid_chart_annotation(_line(_CURVE, x_descending="yes"))
