"""The ONE definition of which controls owe the user an explanation.

`tests/test_tooltip_coverage.py` and `tools/list_tooltips.py` both consume
`iter_documentable_controls` and neither has its own idea of the universe.
That is the point of the module: two implementations of "all interactive
controls" would drift, which is the failure class this repository has paid
for four times over -- `is_stripped_residue`, `filter_altlocs`,
`_single_copy`, and two privately written display gates.

IT REPORTS WHAT EXISTS AND WHAT THAT THING CURRENTLY CARRIES. It never
infers what a tooltip SHOULD say, so the guard can report
`MISSING_TOOLTIP` naming a control without inventing content for it -- the
same producer-declares / validator-checks-structure split as
`Provenance.parameters[TOTAL]`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, Literal

from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QAbstractButton,
    QComboBox,
    QDialogButtonBox,
    QDoubleSpinBox,
    QLineEdit,
    QSlider,
    QSpinBox,
    QTabBar,
    QTableWidget,
    QWidget,
    QWidgetAction,
)

from openchem.ui.widgets.help_tooltip import HelpTooltip, help_tooltip_for

#: Widget classes a user operates directly.
#:
#: `QAbstractButton` rather than `QPushButton` so checkboxes, radio buttons
#: and tool buttons come along -- naming the concrete leaves is how a
#: universe quietly stops covering half of itself.
_INTERACTIVE = (
    QAbstractButton,
    QComboBox,
    QSpinBox,
    QDoubleSpinBox,
    QLineEdit,
    QSlider,
)

Kind = Literal["widget", "action", "header"]
Status = Literal["tooltip", "alternate_help", "legacy_tooltip", "missing"]
Exclusion = Literal["dialog_button", "internal", "not_interactive", "opens_a_menu"]


@dataclass(frozen=True)
class DocumentableControl:
    """One rendering of one control, and what help it currently carries."""

    target: object
    kind: Kind
    #: What it CURRENTLY has, not what it ought to have.
    help_tooltip: HelpTooltip | None
    #: WHICH RENDERING this is -- `DockingPanel/searchSizeXSpin`.
    #:
    #: Separate from `help_id` deliberately: the id names the concept and
    #: may legitimately repeat across instances, this names the occurrence
    #: and may not. Squeezing instance identity into `object_name` would
    #: conflate a Qt detail with a semantic one, and `object_name` is
    #: frequently empty.
    instance_path: str
    #: `tooltip` -- a contract. `alternate_help` -- approved documentation
    #: by another route (`whatsThis`). `missing` -- NO SEMANTIC HELP AT ALL.
    #:
    #: Which is why `--missing` means "no semantic help" rather than "no
    #: tooltip": a control with good `whatsThis()` text is documented, and
    #: bolting a redundant tooltip beside it would make the two drift.
    status: Status
    widget_class: str
    object_name: str

    @property
    def help_id(self) -> str | None:
        return self.help_tooltip.help_id if self.help_tooltip else None


@dataclass(frozen=True)
class ExcludedControl:
    """Something skipped, and WHY.

    Recorded rather than silently dropped so that "why isn't this button
    covered?" has a deterministic answer from `list_tooltips.py --excluded`
    instead of requiring somebody to read the discovery code.
    """

    target: object
    reason: Exclusion
    instance_path: str
    widget_class: str


def _status(target) -> Status:
    if help_tooltip_for(target) is not None:
        return "tooltip"
    # `whatsThis()` is approved alternate documentation.
    #
    # `accessibleDescription()` deliberately is NOT -- and the wording
    # matters: accessible descriptions are useful and must never be deleted
    # to make this guard pass. "Spin box for search box width" is a correct
    # accessible description that explains no consequence; it is doing its
    # own job well and simply is not doing this one.
    if getattr(target, "whatsThis", None) and target.whatsThis().strip():
        return "alternate_help"
    # A raw `setToolTip` with no contract. THE MIGRATION DEBT, and a state
    # of its own rather than "missing": the user does get something, it
    # simply has no recorded semantics, no id and no source. Lumping it with
    # `missing` would overstate the gap and lose the distinction that makes
    # the debt burnable down.
    #
    # Keyed on `instance_path` rather than on a source call site, which is
    # what the plan for this originally proposed. A call site had to be
    # fingerprinted by AST because `file:line` moves and the tooltip STRING
    # is the very thing the migration rewrites; the control it lands on
    # survives both, is what the contract is actually about, and needs no
    # second scanner beside this one.
    if getattr(target, "toolTip", None) and target.toolTip().strip():
        # ... UNLESS QT WROTE IT. See `_tooltip_is_qt_s_own_echo`.
        if not _tooltip_is_qt_s_own_echo(target):
            return "legacy_tooltip"
    return "missing"


def _action_opens_a_menu(target) -> bool:
    """A menu TITLE, whose explanation is the menu it opens.

    `QMenu.menuAction()` is a `QAction` like any other and lands in the
    same walk, so `&File`, `Copy Structure As`, `2D Structure Display` and
    `Installed Plugins` all arrived asking for a contract. There is nothing
    honest to write on one: a title's meaning is the list of entries under
    it, and those entries carry their own contracts. Thirteen contracts
    reading "Opens the File menu" is exactly the restate-the-label
    degeneracy `test_no_contract_is_a_placeholder` exists to refuse.

    Derived from Qt -- an action either has a menu or it does not -- rather
    than from a list of menu names, which is the rot
    `inapplicable_calculators` is this repository's standing warning about.

    NARROW ON PURPOSE. It exempts the action that OPENS a menu and nothing
    inside one, so every command in the menu bar still owes a contract.
    `test_menu_entries_are_not_exempted_along_with_their_titles` is what
    holds that line.
    """
    return isinstance(target, QAction) and target.menu() is not None


def _tooltip_is_qt_s_own_echo(target) -> bool:
    """Did Qt synthesise this tooltip from the control's own label?

    **`QAction.toolTip()` NEVER RETURNS EMPTY.** With no tooltip ever set,
    Qt returns the action's own `text()` with the `&` accelerators removed
    and the `...` stripped -- so "&Open Project..." answers "Open Project",
    and a plain `toolTip().strip()` test cannot tell "nobody wrote one"
    from "somebody wrote one".

    Measured over the real window when the menu-bar batch was picked up:
    **all 83 menu actions** were being reported as `legacy_tooltip`, and
    not one of them carried a human-written string. That overstated the
    migration debt by 83 and, worse, hid 83 controls from `--missing`,
    which is the queue this migration is worked from. The state they were
    in was the exact degenerate case the whole contract layer exists to
    reject -- a tooltip that restates the label it is attached to.

    THE RULE IS ASKED OF QT, NOT REIMPLEMENTED. A throwaway `QAction` with
    the same `text()` reports exactly what Qt would synthesise, so this
    cannot drift when Qt changes `qt_strippedText`. Reproducing that
    function here would have been a second implementation of somebody
    else's private detail, and its edge cases are not the obvious ones:
    `...` is stripped ANYWHERE rather than only at the end ("Mid...dle"
    answers "Middle"), `&&` collapses to a literal `&`, and trailing
    whitespace goes.

    A tooltip deliberately set to exactly the synthesised string reads as
    absent here. That is the right answer either way: restating the label
    is not an explanation, and the degenerate-string floor already refuses
    it in a contract.
    """
    if not isinstance(target, QAction):
        return False
    probe = QAction(target.text())
    return target.toolTip() == probe.toolTip()


def _own_label(target) -> str:
    name = target.objectName() if hasattr(target, "objectName") else ""
    if name:
        return name
    text = target.text().strip() if hasattr(target, "text") else ""
    return text or type(target).__name__


def _describe(target, base: str) -> tuple[str, str]:
    """A path through the real widget hierarchy, not just `base/label`.

    The first version used the root's name as the whole prefix, which
    collapsed 411 controls onto 219 paths -- one of them covering 51
    separate checkboxes. An identity that cannot tell two controls apart
    makes the migration-debt set unsound, because a new bare tooltip on a
    control whose path already exists would not register as new.
    """
    parts = [_own_label(target)]
    parent = target.parentWidget() if hasattr(target, "parentWidget") else None
    while parent is not None:
        parts.append(_own_label(parent))
        parent = parent.parentWidget()
    if parts[-1] != base:
        parts.append(base)
    return "/".join(reversed(parts)), type(target).__name__


def _is_qt_internal(widget: QWidget) -> bool:
    """Qt's own scaffolding, by ITS naming convention rather than by a list.

    Qt reserves the `qt_` object-name prefix for widgets it builds inside
    its own controls -- a table view's corner button, a dock widget's float
    and close buttons, a scroll area's viewport. They are not things a user
    is meant to understand separately, and nobody in this application
    created them to be explained.

    Derived from the prefix rather than enumerated, so it cannot rot the
    way a list of widget names does.
    """
    return widget.objectName().startswith("qt_")


def _inside_dialog_button_box(widget: QWidget) -> bool:
    """Exempt by PARENT CHAIN, never by name.

    A standard OK/Cancel/Close needs no explanation, but a list of exempt
    widget NAMES is exactly what rotted `inapplicable_calculators` into 27
    wrong entries. Deriving the exemption from where the widget lives
    cannot go stale.
    """
    parent = widget.parentWidget()
    while parent is not None:
        if isinstance(parent, QDialogButtonBox):
            return True
        parent = parent.parentWidget()
    return False


def iter_documentable_controls(
    root: QWidget, *, path: str | None = None
) -> Iterator[DocumentableControl]:
    """Every control under `root` that owes the user an explanation.

    THREE SURFACES: interactive `QWidget`s, `QAction`s, and item-view
    HEADER items.

    `QAction` is in the universe because leaving it out was a large hole --
    `app/main_window.py` alone has 57 action sites, so a widgets-and-headers
    universe would declare the whole menu bar documented while covering none
    of it.

    NOT every `QTableWidgetItem`. A results table's cells are data, not
    controls; admitting them would make one docking run add nine
    "undocumented controls" and a batch table thousands, turning the
    inventory into a universe nobody can drive to zero. A body cell joins
    the day one carries an action or a semantic that needs explaining, with
    the reason recorded.

    Disabled or hidden does NOT exempt: the contract covers anything that
    can become enabled in a supported state, and a control's help must be
    there when it becomes usable.
    """
    base = path or type(root).__name__
    for control, _ in _walk(root, base):
        if control is not None:
            yield control


def iter_exclusions(root: QWidget, *, path: str | None = None) -> Iterator[ExcludedControl]:
    base = path or type(root).__name__
    for _, excluded in _walk(root, base):
        if excluded is not None:
            yield excluded


def _walk(root: QWidget, base: str):
    """Shared traversal, so included and excluded cannot disagree."""
    seen: set[int] = set()
    #: Siblings can still share a path -- three unnamed checkboxes in one
    #: layout are genuinely indistinguishable by hierarchy alone. An ordinal
    #: keeps `instance_path` an IDENTITY, which the migration-debt set
    #: depends on: two controls sharing one path would let a new bare
    #: tooltip hide behind an existing entry.
    #:
    #: Deterministic because `findChildren` returns children in construction
    #: order, so the same window yields the same ordinals every run.
    used: dict[str, int] = {}

    def unique(path: str) -> str:
        count = used.get(path, 0)
        used[path] = count + 1
        return path if count == 0 else f"{path}#{count + 1}"

    for widget in root.findChildren(QWidget):
        if id(widget) in seen:
            continue
        seen.add(id(widget))
        instance_path, class_name = _describe(widget, base)
        if not isinstance(widget, _INTERACTIVE):
            continue
        if _is_qt_internal(widget):
            yield None, ExcludedControl(widget, "internal", instance_path, class_name)
            continue
        if _inside_dialog_button_box(widget):
            yield None, ExcludedControl(widget, "dialog_button", instance_path, class_name)
            continue
        # Qt builds real controls INSIDE composite ones -- a QComboBox has
        # a QLineEdit, a QSpinBox has one too. They are implementation, not
        # separate things for a user to understand, and the outer control
        # already carries the explanation.
        if _is_internal_to_a_composite(widget):
            yield None, ExcludedControl(widget, "internal", instance_path, class_name)
            continue
        yield (
            DocumentableControl(
                target=widget,
                kind="widget",
                help_tooltip=help_tooltip_for(widget),
                instance_path=unique(instance_path),
                status=_status(widget),
                widget_class=class_name,
                object_name=widget.objectName(),
            ),
            None,
        )

    for action in root.findChildren(QAction):
        if id(action) in seen:
            continue
        seen.add(id(action))
        if action.isSeparator():
            continue
        instance_path, class_name = _describe(action, base)
        if _action_opens_a_menu(action):
            yield None, ExcludedControl(action, "opens_a_menu", instance_path, class_name)
            continue
        # A `QWidgetAction` is Qt's way of putting a WIDGET into a toolbar
        # or a menu -- it is a carrier, not a command. Measured: the one in
        # this window holds the `PanelRail`, whose own group buttons are
        # walked and documented individually. Documenting the wrapper as
        # well would be a contract for "the rail" sitting on top of
        # contracts for everything in it.
        if isinstance(action, QWidgetAction):
            yield None, ExcludedControl(action, "internal", instance_path, class_name)
            continue
        yield (
            DocumentableControl(
                target=action,
                kind="action",
                help_tooltip=help_tooltip_for(action),
                instance_path=unique(instance_path),
                status=_status(action),
                widget_class=class_name,
                object_name=action.objectName(),
            ),
            None,
        )

    for table in root.findChildren(QTableWidget):
        table_path, _ = _describe(table, base)
        for column in range(table.columnCount()):
            item = table.horizontalHeaderItem(column)
            if item is None:
                continue
            yield (
                DocumentableControl(
                    target=item,
                    kind="header",
                    help_tooltip=help_tooltip_for(item),
                    instance_path=unique(f"{table_path}/header[{column}]"),
                    status=_status(item),
                    widget_class=type(item).__name__,
                    object_name=item.text(),
                ),
                None,
            )


def _is_internal_to_a_composite(widget: QWidget) -> bool:
    """A control Qt built INSIDE one of its own composites.

    `QTabBar` is here for the same reason as the spin boxes and combo
    boxes, and it closes a hole `_is_qt_internal` cannot: a `QTabBar`
    builds two `QToolButton`s to scroll the tabs when they overflow, and
    names them `ScrollLeftButton` / `ScrollRightButton` -- WITHOUT the
    `qt_` prefix its own convention otherwise reserves. So the prefix rule
    excluded the tab bar and admitted its children, and three tab widgets
    put six Qt scroll arrows into the inventory as controls owing the user
    an explanation.

    Nothing of ours can be caught by it: a tab PAGE is a child of the
    stacked widget (`qt_tabwidget_stackedwidget`), never of the bar.
    Measured over the real window -- this rule excludes exactly those 6
    widgets and no others.

    THE TEMPTING GENERALISATION IS CATASTROPHIC AND WAS MEASURED BEFORE
    BEING REJECTED. "Anything under a `qt_`-named ancestor is Qt's own"
    reads as the principled version of this and would have excluded
    **200 of 243 widgets**, because every panel in the application lives
    inside a `QScrollArea`'s `qt_scrollarea_viewport`. It would have
    looked like a large coverage win.
    """
    parent = widget.parentWidget()
    while parent is not None:
        if isinstance(parent, (QComboBox, QSpinBox, QDoubleSpinBox, QTabBar)):
            return True
        parent = parent.parentWidget()
    return False
