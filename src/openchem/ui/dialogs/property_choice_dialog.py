"""Choose which always-on properties or structural-alert catalogs a project run includes.

Properties has one box for each ("Include always-on properties", "Include structural
alerts") and that is all a run needs when the answer is "all of them" or "none". The Batch
panel let you tick ONE of the 36 descriptors or ONE of the five alert catalogs, so a
project table of just logP and TPSA was possible there and was not here. This dialog is
that picker, for either list.

**NOTHING CHOSEN BEFORE MEANS EVERYTHING IS TICKED**, the way a box that is simply ticked
means "all". A previous choice survives by id: an id that no longer names anything is
dropped, never reported. "Nothing ticked" is refused by the dialog rather than accepted
and then run as "everything" (or as nothing): the way to leave them out is the box.

The filter hides rows and never unticks them, so ticks made before filtering still run
(the Batch panel's rule). **All shown** and **None shown** act on the rows the filter
leaves visible, which is what a select-all means once a list can be filtered.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

#: One row to offer: (id, label shown, tooltip).
Choice = tuple[str, str, str]

#: What the tree's items carry, under `Qt.ItemDataRole.UserRole`: the id of a leaf.
_ID_ROLE = Qt.ItemDataRole.UserRole


class PropertyChoiceDialog(QDialog):
    """A filterable, grouped checklist over ids. `chosen()` is what was left ticked."""

    def __init__(
        self,
        title: str,
        intro: str,
        groups: Mapping[str, Sequence[Choice]],
        chosen: set[str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setObjectName("propertyChoiceDialog")
        self._building = True
        offered = {identifier for rows in groups.values() for identifier, _label, _tip in rows}
        survivors = (chosen & offered) if chosen is not None else None
        self._total = len(offered)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(intro, self))
        self._filter = QLineEdit(self)
        self._filter.setPlaceholderText("Filter the list (ticks are kept)")
        self._filter.setClearButtonEnabled(True)
        self._filter.textChanged.connect(self._on_filter_changed)
        layout.addWidget(self._filter)

        self._tree = QTreeWidget(self)
        self._tree.setHeaderHidden(True)
        self._tree.setRootIsDecorated(True)
        self._tree.setMinimumHeight(260)
        for group, rows in groups.items():
            parent_item = QTreeWidgetItem(self._tree, [group])
            # Two-state to click, partial only as a DISPLAY (`_sync_group`): a clickable tristate
            # cycles through "partly" and a handler cannot tell that from the person choosing it,
            # and Qt's auto-tristate would also tick the rows the filter is hiding.
            parent_item.setFlags(parent_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            for identifier, label, tooltip in rows:
                leaf = QTreeWidgetItem(parent_item, [label])
                leaf.setFlags(leaf.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                leaf.setData(0, _ID_ROLE, identifier)
                if tooltip:
                    leaf.setToolTip(0, tooltip)
                leaf.setCheckState(
                    0,
                    Qt.CheckState.Checked
                    if survivors is None or not survivors or identifier in survivors
                    else Qt.CheckState.Unchecked,
                )
            parent_item.setExpanded(True)
        for group_index in range(self._tree.topLevelItemCount()):
            self._sync_group(self._tree.topLevelItem(group_index))
        self._tree.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self._tree)

        row = QHBoxLayout()
        self._all_button = QPushButton("All shown", self)
        self._all_button.clicked.connect(self._tick_shown)
        self._none_button = QPushButton("None shown", self)
        self._none_button.clicked.connect(self._untick_shown)
        row.addWidget(self._all_button)
        row.addWidget(self._none_button)
        row.addStretch(1)
        self._count = QLabel("", self)
        row.addWidget(self._count)
        layout.addLayout(row)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self
        )
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)
        self._building = False
        self._refresh()

    # -- reading ---------------------------------------------------------------------------

    def _leaves(self):
        for top in range(self._tree.topLevelItemCount()):
            group = self._tree.topLevelItem(top)
            for index in range(group.childCount()):
                yield group.child(index)

    def chosen(self) -> set[str]:
        """The ids ticked, shown or hidden by the filter."""
        return {
            str(leaf.data(0, _ID_ROLE))
            for leaf in self._leaves()
            if leaf.checkState(0) is Qt.CheckState.Checked
        }

    def shown_count(self) -> int:
        return sum(1 for leaf in self._leaves() if not leaf.isHidden())

    # -- acting ----------------------------------------------------------------------------------

    # Bound methods, never lambdas closing over `self` (see MoleculeScopeDialog).
    def _tick_shown(self, _checked: bool = False) -> None:
        self._set_shown(Qt.CheckState.Checked)

    def _untick_shown(self, _checked: bool = False) -> None:
        self._set_shown(Qt.CheckState.Unchecked)

    def _set_shown(self, state: Qt.CheckState) -> None:
        self._building = True
        for leaf in self._leaves():
            if not leaf.isHidden():
                leaf.setCheckState(0, state)
        for top in range(self._tree.topLevelItemCount()):
            self._sync_group(self._tree.topLevelItem(top))
        self._building = False
        self._refresh()

    @staticmethod
    def _sync_group(group: QTreeWidgetItem) -> None:
        """A group reads ticked, unticked or partly ticked from ALL its rows, shown or not."""
        states = {group.child(i).checkState(0) for i in range(group.childCount())}
        if states == {Qt.CheckState.Checked}:
            group.setCheckState(0, Qt.CheckState.Checked)
        elif states == {Qt.CheckState.Unchecked}:
            group.setCheckState(0, Qt.CheckState.Unchecked)
        else:
            group.setCheckState(0, Qt.CheckState.PartiallyChecked)

    def _on_item_changed(self, item: QTreeWidgetItem, _column: int = 0) -> None:
        if self._building:
            return
        self._building = True
        try:
            group = item.parent()
            if group is None:
                # Ticking a heading ticks the rows the filter shows and leaves hidden ones alone.
                if item.checkState(0) is not Qt.CheckState.PartiallyChecked:
                    for index in range(item.childCount()):
                        leaf = item.child(index)
                        if not leaf.isHidden():
                            leaf.setCheckState(0, item.checkState(0))
                self._sync_group(item)
            else:
                self._sync_group(group)
        finally:
            self._building = False
        self._refresh()

    def _on_filter_changed(self, text: str) -> None:
        needle = text.strip().casefold()
        for top in range(self._tree.topLevelItemCount()):
            group = self._tree.topLevelItem(top)
            visible = 0
            for index in range(group.childCount()):
                leaf = group.child(index)
                match = not needle or needle in leaf.text(0).casefold() or needle in group.text(0).casefold()
                leaf.setHidden(not match)
                visible += 1 if match else 0
            # A group with no match is hidden, not shown empty.
            group.setHidden(visible == 0)
        self._refresh()

    def _refresh(self) -> None:
        ticked = len(self.chosen())
        self._count.setText(f"{ticked} of {self._total} ticked")
        self._buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(ticked > 0)
