"""A table cell that sorts by its value rather than its printed text.

Extracted from `ui/panels/batch_panel.py`, which defined it privately and
was then not the only table that needed it -- the per-atom comparison in
`ui/dialogs/batch_analysis_dialog.py` has exactly the same problem with
exactly the same cause. Same reason `collapsible_section.py` came out of
`property_panel.py`: a widget two things need does not belong inside one
of them.

`batch_panel` still imports `_SortableItem` and `_SORT_ROLE` from here
under their old names, so nothing that referenced them had to change.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTableWidgetItem

#: Where the sortable value lives. A private role rather than `EditRole`,
#: which Qt may render or hand to an editor.
SORT_ROLE = Qt.ItemDataRole.UserRole + 1


class SortableItem(QTableWidgetItem):
    """A cell that sorts by its VALUE rather than by its printed text.

    `QTableWidget.setSortingEnabled` sorts through `QTableWidgetItem.__lt__`,
    whose default compares `DisplayRole` -- a string. So a molecular-weight
    column sorts "1000" before "200", and a LogP column sorts "-1.03" before
    "-0.5" before "1.31" only by accident of digit order. Storing the float
    under a private role is not enough on its own: without this override,
    Qt never looks at it.

    Mixed types are compared as strings rather than raising. A column can
    legitimately hold floats for most rows and the infinity that marks a
    failed cell, and `float('inf') < 'text'` is a TypeError that would
    propagate out of a header click.
    """

    def __init__(self, text: str = "", sort_value: object | None = None) -> None:
        super().__init__(text)
        # The optional second argument is the common case -- text and sort
        # key set together. Callers that need a sort key unrelated to the
        # text (a failed cell sorting to one end) still set the role
        # directly, which is why this does not force one.
        if sort_value is not None:
            self.setData(SORT_ROLE, sort_value)

    def __lt__(self, other: QTableWidgetItem) -> bool:
        mine = self.data(SORT_ROLE)
        theirs = other.data(SORT_ROLE)
        try:
            return mine < theirs
        except TypeError:
            return str(mine) < str(theirs)
