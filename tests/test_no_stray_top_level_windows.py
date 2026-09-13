"""A re-rendered section must never surface as its own window.

**THE FLASHING WHITE WINDOWS, NAMED BY A TRACE RATHER THAN A GUESS.**
Selecting a molecule in `MPMI.ocsproj` flashed small white windows.
`OPENCHEM_TRACE_WINDOWS` caught 1801 top-level shows in one
select-0-1-0 run, every one a parentless `CollapsibleSection`.

The mechanism is Qt's, and it needs two renders in one event-loop turn:
`QLayout.addChildWidget` does not show a new child, it QUEUES
`_q_showIfNotHidden`. The reader re-renders once per arriving result, so the
next render's `_clear_sections` ran `setParent(None)` on a section whose
queued show had not fired yet -- and when it did, the widget had no parent,
so "show" meant "open a window". `deleteLater` then closed it a moment later.

Asserted on the SYMPTOM, a visible top-level section, rather than on how the
clear is written.
"""

from __future__ import annotations

from PySide6.QtWidgets import QApplication, QWidget

from openchem.domain.report import Fact, FactCategory, StructureReport
from openchem.domain.structure_issue import Basis
from openchem.ui.widgets.collapsible_section import CollapsibleSection
from openchem.ui.widgets.fact_view import FactView

import conftest


def _report(label: str) -> StructureReport:
    fact = Fact(
        category=FactCategory.IDENTITY,
        label=label,
        value=1.0,
        display_value=f"{label} value",
        source="test",
        basis=Basis.DETERMINISTIC,
    )
    return StructureReport(molecule_uuid="m1", facts=(fact,))


def _stray_sections() -> list[QWidget]:
    return [
        w
        for w in QApplication.topLevelWidgets()
        if isinstance(w, CollapsibleSection) and not w.isHidden()
    ]


def test_rendering_twice_in_one_turn_opens_no_window(qapp):
    view = FactView()
    view.show()
    try:
        # Two renders before the loop runs: the arrival pattern of results.
        view.set_report(_report("first"), "Subject")
        view.set_report(_report("second"), "Subject")
        # Only the queued `_q_showIfNotHidden` calls; NOT the posted
        # deleteLater, which would hide the evidence along with the widget.
        qapp.processEvents()
        assert _stray_sections() == []
    finally:
        conftest.dispose(view)
