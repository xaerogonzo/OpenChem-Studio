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

WHERE A PLACEHOLDER MAY GO, AND WHERE IT MAY NOT
--------------------------------------------------------------------------

**Adding a placeholder widget to a tab page that already contains content
widgets corrupts the heap.** Windows fatal exception `0xc0000374`, raised
inside the teardown `gc.collect()` -- and not in a test of the panel that
built it, but hundreds of tests later, first in
`test_main_window_docking_visualization.py` and then, once that was
addressed, in `test_regulatory_calculator.py`.

This is the rule that came out of it, and it is the only one supported by
the measurements:

    placeholder in a tab that is otherwise EMPTY        safe
    placeholder in a tab that already holds widgets     corrupts the heap

The three deferred tabs (1D Signals, IR, Surfaces) hold nothing until a
result arrives, so they get a real placeholder. The Hybrid tab says it
through `_hybrid_summary_label`, which already existed for notes, and the
three correlation tabs paint the message inside
`NmrCorrelationPlotWidget`. Neither adds a widget.

Measured, on a 12-second two-file reproduction
(`test_main_window_conformers.py` +
`test_main_window_docking_visualization.py`) once the arms were shown
reliable rather than trusted at n=1:

    placeholder in all 7 tabs, QWidget subclass    crashed 5 / 5
    placeholder in all 7 tabs, plain QLabel        crashed 0 / 5 here,
                                                   but the full suite
                                                   still died at 2229
    placeholder in the 3 empty tabs only           full suite green
    no placeholders at all                         full suite green

Three hypotheses were tested against the full suite and are WRONG, so
nobody need pay for them again: it is not the `dict[QWidget, ...]` that
held them (removing it changed nothing), not hiding the sibling content
(suppressing every visibility change changed nothing), and not the new
test file (removing it changed nothing).

**The mechanism is still not understood, and this docstring will not
pretend otherwise.** "Python-derived widget" is not the answer --
`WrappedLabel` and `CollapsibleSection` are Python-derived and live
happily in these same panels. Nor is it the widget class at all, since
the plain-`QLabel` arm still killed the full suite. What tracks the
crash exactly is WHERE the widget is added.

So this avoids the trigger rather than explaining it. If somebody works
out why, both the class form and the simpler "placeholder everywhere"
shape can come back; `tests/test_empty_states.py` asks each tab what it
shows rather than how, so it will not stand in the way.

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
