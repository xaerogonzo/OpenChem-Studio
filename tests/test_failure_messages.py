"""A failure has TWO jobs, and one string could not do both.

Every FAILED branch in the Properties panel wrote `error` into the value
cell AND into its tooltip, so a producer had one string with which to be
both a table cell and an explanation. The shape descriptors' reason is a
sentence and the pkasolver one is 344 characters, and the panel's value
column at the dock's 280 px minimum shows about forty -- so the cell read
"Needs a real 3D conformer - generate one first" and stopped, with the
half that says what to press off the edge of the panel.

`error` keeps its meaning (the FULL explanation) and `error_summary` is
the new, optional cell form. The split is guarded here; where each string
lands on screen is guarded in `test_property_panel.py`, and the geometry
it no longer disturbs in `test_property_panel_long_values.py`.
"""

from __future__ import annotations

import pytest
from rdkit import Chem

from openchem.chem.descriptor_providers import (
    _NEEDS_CONFORMER_ERROR,
    _NEEDS_CONFORMER_SUMMARY,
    _PKA_NOT_INSTALLED_MESSAGE,
    _PKA_NOT_INSTALLED_SUMMARY,
    RDKitDescriptorProvider,
)
from openchem.domain.common import CacheState, describe_failure

#: The Windows console codepages a result string can land in. Measured
#: rather than assumed, and the obvious single choice is wrong in both
#: directions:
#:
#:     char                    cp1252   cp437   cp850
#:     A-ring, sup-2, degree       ok      ok      ok
#:     sup-3                       ok   RAISE      ok
#:     em dash                     ok   RAISE   RAISE
#:     triangle U+25B8          RAISE   RAISE   RAISE
#:
#: So cp1252 alone -- which `test_regulatory_calculator` uses -- does NOT
#: reject an em dash, and a blanket "must be pure ASCII" rule would fail
#: the 62 shipped result lines that legitimately carry an angstrom sign.
#: Requiring all three is the rule the constraint actually implies.
CONSOLE_CODEPAGES = ("cp1252", "cp437", "cp850")


def _raises_on(text: str) -> list[str]:
    """Which of the three codepages this string would raise on."""
    bad = []
    for codepage in CONSOLE_CODEPAGES:
        try:
            text.encode(codepage)
        except UnicodeEncodeError:
            bad.append(codepage)
    return bad


# ---------------------------------------------------------------------
# The pairing rule
# ---------------------------------------------------------------------


def test_a_producer_that_declares_nothing_gets_the_reason_in_both_places():
    """THE DEGRADATION PATH. Every unmigrated producer depends on it."""
    assert describe_failure("Something went wrong.") == (
        "Something went wrong.",
        "Something went wrong.",
    )


def test_a_declared_summary_becomes_the_cell_and_the_reason_stays_the_hover():
    assert describe_failure("The long reason.", "Short") == ("Short", "The long reason.")


def test_a_failure_with_nothing_to_say_still_says_something():
    """A blank cell is indistinguishable from a value that never arrived."""
    assert describe_failure(None) == ("Failed", "")
    assert describe_failure("") == ("Failed", "")
    assert describe_failure("   ") == ("Failed", "")


@pytest.mark.parametrize("blank", [None, "", "   "])
def test_a_blank_summary_is_treated_as_no_summary(blank):
    """Fail closed. A summary that is whitespace is a producer that meant
    to write one and did not, and promoting it would blank the cell while
    leaving the tooltip full -- the failure invisible on screen."""
    assert describe_failure("The reason.", blank) == ("The reason.", "The reason.")


def test_a_summary_with_no_reason_behind_it_is_promoted_rather_than_left_hollow():
    """The hover would otherwise carry LESS than the cell it expands,
    which reads as "there is nothing more to say" when the truth is that
    the producer forgot the detail."""
    assert describe_failure(None, "Needs a 3D conformer") == (
        "Needs a 3D conformer",
        "Needs a 3D conformer",
    )


def test_the_summary_is_not_graded_against_its_reason():
    """STRUCTURAL ONLY, the same line `valid_total_declaration` draws.

    A summary longer than its detail is a producer writing a poor
    contract, and this function must still hand both along -- deciding
    whether a summary fairly condenses a reason is a claim about PROSE,
    and a validator that graded it would be the tooltip layer's forbidden
    grader wearing a different hat. Width is handled by eliding, which is
    measured and needs no threshold.
    """
    cell, hover = describe_failure("Short.", "A very much longer summary indeed.")
    assert cell == "A very much longer summary indeed."
    assert hover == "Short."


# ---------------------------------------------------------------------
# The shipped producer strings
# ---------------------------------------------------------------------


def test_the_two_long_reasons_ship_a_cell_form_as_well():
    """The two failures whose reason cannot fit a cell are the two that
    declare a summary. Asserted as a RELATIONSHIP rather than as pinned
    prose, so rewording either is free and dropping one is not."""
    for summary, reason in (
        (_NEEDS_CONFORMER_SUMMARY, _NEEDS_CONFORMER_ERROR),
        (_PKA_NOT_INSTALLED_SUMMARY, _PKA_NOT_INSTALLED_MESSAGE),
    ):
        assert summary.strip()
        assert len(summary) < len(reason)
        assert describe_failure(reason, summary) == (summary, reason)


def test_the_shape_descriptors_really_carry_both_strings():
    """FOUND BY MUTATION: a constant existing is not a constant REACHING.

    `test_the_two_long_reasons_ship_a_cell_form_as_well` reads the module
    constants and checks they relate, and passes perfectly happily when
    the provider stops attaching `error_summary` to the values it
    produces -- so the panel falls back to the reason, the cell goes back
    to a clipped sentence, and every other guard in this file stays
    green. This is the repository's own "shipped is not reachable" in
    miniature: the string was declared and unwired.

    Observational, through the real provider, on the reported molecule.
    """
    provider = RDKitDescriptorProvider()
    benzene = Chem.MolFromSmiles("c1ccccc1")
    failed = {
        d.descriptor_id: d for d in provider.compute(benzene, "mol-1")
        if d.cache_state is CacheState.FAILED
    }
    assert "radius_of_gyration" in failed, (
        "setup: the shape descriptors did not refuse a molecule with no "
        "3D conformer, so this guard has nothing to walk"
    )
    for descriptor_id, descriptor in failed.items():
        assert descriptor.error_summary, (
            f"{descriptor_id} failed without a cell form, so the panel "
            "falls back to the full reason and clips it again"
        )
        cell, hover = describe_failure(descriptor.error, descriptor.error_summary)
        assert cell == _NEEDS_CONFORMER_SUMMARY
        assert hover == _NEEDS_CONFORMER_ERROR
        assert cell != hover


def test_every_shipped_failure_message_survives_a_windows_console():
    """OBSERVATIONAL: it runs the real provider and reads what it produced.

    **`DescriptorValue.error` HAD NO SWEEP COVERAGE AT ALL.**
    `benchmarks/report_lines/sweep.py` instruments `report_adapter._split`,
    so it enumerates the 499 lines that reach `AlertResult.matched` and
    never touches the `error` field -- which is exactly where the shipped
    non-ASCII string was. Measured on the old wording, which carried an em
    dash and a U+25B8 triangle:

        em dash    raises on cp437 and cp850
        triangle   raises on cp1252 TOO

    so it was unprintable on every Windows console codepage rather than
    only the DOS ones. `regulatory/calculator.py` records the same rule
    for `matched` lines, and was hit three times in one session.

    Benzene from SMILES has no real 3D conformer, which is the reported
    reproduction and the case that produces these failures.
    """
    provider = RDKitDescriptorProvider()
    benzene = Chem.MolFromSmiles("c1ccccc1")
    failures = [
        d for d in provider.compute(benzene, "mol-1")
        if d.cache_state is CacheState.FAILED
    ]
    assert failures, (
        "setup: no descriptor failed, so this guard walked an empty "
        "population -- the shape descriptors are supposed to refuse a "
        "molecule with no 3D conformer"
    )
    for descriptor in failures:
        for field in ("error", "error_summary"):
            text = getattr(descriptor, field, None)
            if not text:
                continue
            bad = _raises_on(text)
            assert not bad, (
                f"{descriptor.descriptor_id}.{field} raises on "
                f"{', '.join(bad)}: {text!r}"
            )


def test_the_probe_would_reject_the_wording_this_replaced():
    """THE CONTROL. A codepage check that cannot say NO is worth nothing,
    and this one walks strings that are already ASCII -- so without an arm
    that fails, it would pass against a rule that checked nothing. The
    string is the one that shipped."""
    shipped_before = (
        "Needs a real 3D conformer — generate one first with "
        "Structure ▸ Generate Conformers...."
    )
    assert _raises_on(shipped_before) == list(CONSOLE_CODEPAGES)
