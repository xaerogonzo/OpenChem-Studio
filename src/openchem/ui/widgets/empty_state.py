"""The widget that says why a surface is empty, and what would fill it.

Before this existed there was **no empty-state text anywhere in `ui/`** --
a search for any placeholder string across the whole package found two
files, neither of them a panel. So a tab with no data for the current
molecule showed nothing, and there was no way to tell apart:

    the calculation has not been run
    the calculation ran and produced nothing
    the calculation failed
    this tab is not for the kind of job you ran

All four look identical when they are all blank, and Alex hit exactly
that: *"A lot of the different quantum settings are just... blank. Even if
intentional, it's bad and a confusing design."*

**An empty state is two sentences, and the second one is the point.** The
headline says what is missing; the action says the one thing that would
fill it. A placeholder that only says "No data" has told the reader
something they could already see.

ADDING WIDGETS TO THE QUANTUM CHEMISTRY PANEL CORRUPTS THE HEAP
--------------------------------------------------------------------------

Windows fatal exception `0xc0000374`, raised inside the teardown
`gc.collect()` -- and never in a test of that panel, but hundreds of
tests later, wherever the next collection happens to land.

**That panel is already the suite's worst leaker.** CLAUDE.md's own
census: `test_quantum_chemistry_panel.py` accounts for 104 of the 138
objects destroyed outside the test that made them. Every widget added to
its tree enlarges a graph that is already outliving itself, and past some
margin the teardown collect goes over.

Measured, and the shape of the result is what matters more than any one
number:

    +7 placeholder widgets across its tab pages    full suite dead
    +3 placeholder widgets (empty tabs only)       full suite green
    +1 CollapsibleSection in its main layout       full suite dead
    reparenting an existing widget into a tab      full suite green
    a much larger composite added to a TOOLBAR     full suite green

So it is not about tab pages, which an earlier version of this docstring
claimed on thinner evidence. The rail -- a bigger widget than any of
these -- was added outside this panel and cost nothing.

**The working rule: in `QuantumChemistryPanel`, prefer a change that adds
no widget at all.** All three mechanisms here follow it. The three
deferred tabs are genuinely empty and can afford one placeholder each;
Hybrid uses the `_hybrid_summary_label` it already had; the correlation
tabs PAINT their message inside `NmrCorrelationPlotWidget`; and the Log
tab is the existing `QPlainTextEdit`, reparented, using Qt's native
`setPlaceholderText`.

Three hypotheses were tested against the full suite and are WRONG, so
nobody need pay for them again: it is not the `dict[QWidget, ...]` that
held the placeholders (removing it changed nothing), not hiding the
sibling content (suppressing every visibility change changed nothing),
and not the new test file (removing it changed nothing).

**The mechanism is still not understood.** "Python-derived widget" is not
the answer -- `WrappedLabel` and `CollapsibleSection` are Python-derived
and live happily elsewhere. The honest statement is that this panel sits
near a limit nobody has characterised, and the cheap way past it is not
to spend the margin.

Fixing the leak itself is the real answer and is not attempted here;
CLAUDE.md records that closing that file's leaks costs 155 seconds on
every run. `tests/test_empty_states.py` asks each tab what it SHOWS
rather than how, so whoever does fix it can simplify all of this freely.

The marker is a Qt property, the same idiom `property_panel.py` uses to
carry a calculator id on a button: it needs no custom class, and it is
what `is_empty_state` reads.
"""

from __future__ import annotations

from html import escape

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QWidget

#: Marks a label as a placeholder rather than content.
EMPTY_STATE_PROPERTY = "openchem_empty_state"
#: The plain text behind the rendered rich text, for tests and copying --
#: `QLabel.text()` gives back the HTML source, which is not what either
#: wants to read.
EMPTY_STATE_TEXT_PROPERTY = "openchem_empty_state_text"


def empty_state(headline: str, action: str = "", parent: QWidget | None = None) -> QLabel:
    """A centred "nothing here yet, and here is why" label.

    Deliberately quiet, secondary text rather than an error: an empty tab
    is the normal state of most tabs most of the time. Styling it as a
    problem would be its own dishonesty, and this app already had the
    opposite failure of painting ordinary results in alert red.
    """
    label = QLabel(parent)
    label.setWordWrap(True)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setTextFormat(Qt.TextFormat.RichText)
    label.setMargin(24)
    label.setProperty(EMPTY_STATE_PROPERTY, True)
    set_empty_state_message(label, headline, action)
    return label


def set_empty_state_message(label: QLabel, headline: str, action: str = "") -> None:
    """Rewrite a placeholder's two lines.

    `escape` because these strings are rendered as rich text and a
    chemical name can legitimately contain `<` or `&` -- (E)-but-2-ene
    reaching a `<` would silently swallow the rest of the sentence.
    """
    parts = [f'<b style="color:#555555">{escape(headline)}</b>']
    if action:
        parts.append(f'<span style="color:#777777">{escape(action)}</span>')
    label.setText("<br><br>".join(parts))
    label.setProperty(EMPTY_STATE_TEXT_PROPERTY, f"{headline}\n{action}".strip())


def is_empty_state(widget: QWidget) -> bool:
    return bool(widget.property(EMPTY_STATE_PROPERTY))


def empty_state_text(widget: QWidget) -> str:
    """The placeholder's plain text, both lines."""
    return str(widget.property(EMPTY_STATE_TEXT_PROPERTY) or "")
