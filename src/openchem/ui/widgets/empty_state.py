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

WHY THE FOUR TABS SAY IT FOUR DIFFERENT WAYS
--------------------------------------------------------------------------

Three deferred tabs (1D Signals, IR, Surfaces) get a real placeholder;
Hybrid uses the `_hybrid_summary_label` it already had; the correlation
tabs PAINT the message inside `NmrCorrelationPlotWidget`; the Log tab is
a `QPlainTextEdit` using Qt's native `setPlaceholderText`.

That variety was originally a WORKAROUND for a heap corruption that
appeared whenever widgets were added to this panel, and this docstring
used to state a rule ("prefer a change that adds no widget") that was
**wrong**. The real cause was the test suite's teardown `gc.collect()`
destroying MainWindows; adding widgets merely shuffled the heap enough to
change whether the corrupting free landed on something fatal. CLAUDE.md
has the measurements under "SOLVED: the teardown collect was DESTROYING
MainWindows".

The four mechanisms stayed anyway, because each is the better drawing on
its own merits: a message painted where the peaks would be is where
somebody is looking, and a widget that already exists needs no second one
beside it. There is no longer any reason to avoid adding a placeholder
where one genuinely reads better.

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
