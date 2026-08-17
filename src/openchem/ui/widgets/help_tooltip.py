"""A semantic help contract for a control, of which the tooltip is one
rendering.

THE INVARIANT IS "HAS A DOCUMENTED CONTRACT", NOT "HAS TOOLTIP TEXT". That
distinction is the whole design: a guard that only checks for a non-empty
string degenerates into `tooltip = "Options."`, and 179 hand-written
strings with nothing tying them to meaning rot the moment the UI moves.
The producer declares what a control MEANS and the validator checks the
STRUCTURE of that declaration, never the prose -- the same split
`CalculatorDefinition.applies_to` and `Provenance.parameters[TOTAL]`
already use in this codebase, for the same reason.

WHY THIS EXISTS AT ALL. A user asked what the docking pose table's
"RMSD l.b." column meant, and nothing in the application answered: 66
`setToolTip` call sites against 179 constructions of interactive Qt
classes, with the Docking panel carrying one and the Alignment panel none.

`HelpTooltip` knows nothing about Qt, deliberately -- it is constructible
and comparable with no `QApplication`, which is what makes the metadata
unit-testable and `tools/list_tooltips.py` easy to test. Only
`apply_help_tooltip` and `help_tooltip_for` touch Qt.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from PySide6.QtCore import Qt

#: Where a `QTableWidgetItem` keeps its contract.
#:
#: A `QTableWidgetItem` is **not a `QObject`** -- verified, because the
#: whole item surface depends on it:
#:
#:     QTableWidgetItem is a QObject?   False
#:       has setProperty?               False
#:       has setData?                   True
#:
#: So items cannot carry Qt properties and need their own storage. A
#: module-level dict keyed on object identity was rejected: table items are
#: replaced and destroyed constantly, so such a map leaks and goes stale
#: against freed items -- this project's own wrapper-invalidation trap in a
#: new place.
HELP_TOOLTIP_ROLE = int(Qt.ItemDataRole.UserRole) + 7

#: Qt property name for the surfaces that ARE `QObject`s. Namespaced so it
#: cannot collide with Qt's own properties, a plugin's, or a third-party
#: widget's.
_PROPERTY = "_openchem.help_tooltip"

#: `<surface>.<concept>`, lowercase ASCII, dot-separated.
_HELP_ID = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")

#: A trailing `_1` / `_27`: one concept rendered many times, given one id
#: per rendering. See `validate` for why this shape and not a bare `.1`.
_INSTANCE_SUFFIX = re.compile(r"^.+_\d+$")

#: Segments that mean somebody encoded a WIDGET rather than a CONCEPT.
_WIDGET_WORDS = frozenset({
    "qwidget", "qpushbutton", "qcombobox", "qspinbox", "qdoublespinbox",
    "qcheckbox", "qlineedit", "qtablewidgetitem", "qaction", "qlabel",
    "button", "spinbox", "combobox", "checkbox", "widget", "panel", "dialog",
})


class HelpTooltipError(ValueError):
    """A contract that cannot be right whatever the repository contains."""


@dataclass(frozen=True)
class HelpTooltip:
    """What a control means, and where that meaning came from.

    Three kinds of statement live in `text`, and only one of them wants a
    source -- keeping the middle one source-free is what stops
    `docs/sources.toml` becoming a dumping ground for application
    semantics:

        an external scientific fact       carries `source_key`
        OpenChem behaviour or semantics   carries neither
        an interpretation warning drawn
        from documented behaviour         carries `help_anchor`
    """

    #: The rendered tooltip.
    text: str

    #: 1 action + result. 2 a scientific parameter: what it controls plus at
    #: least one APPLICABLE qualifier (unit, range, default, or behavioural
    #: consequence). 3 interpretation-sensitive: definition, units or
    #: reference frame where applicable, and the interpretation limit.
    #:
    #: Tier 2 requires "at least one applicable" rather than all four on
    #: purpose. A method or model choice has no numeric unit and no useful
    #: range, and demanding the full set produces `Default: N/A` padding
    #: written to satisfy a rule rather than a reader.
    tier: Literal[1, 2, 3]

    #: A stable SEMANTIC identifier -- `docking.rmsd_lower_bound`.
    #:
    #: It names a control DEFINITION, not an instance: any number of runtime
    #: controls may share one `help_id` when they mean the same thing, and
    #: `DocumentableControl.instance_path` tells the renderings apart. Ten
    #: generated parameter rows that mean one thing share one id rather than
    #: sprouting `quantum.charge.1`, `quantum.charge.2`, which reads as
    #: precision and is noise.
    #:
    #: Never renamed because the UI moved, and never reused for a different
    #: concept: reusing one silently turns every earlier reference into a
    #: statement about something else.
    help_id: str

    #: Grouping only. NEVER validated against anything, and no consumer may
    #: treat it as a documentation identity -- that is `help_anchor`'s job,
    #: and a field with two jobs is a pair that can disagree.
    topic: str | None = None

    #: A `<!-- help:... -->` anchor in `docs/`. Optional even at tier 3:
    #: requiring one would hide a documentation project inside the tooltip
    #: project. Checked by the guard when present.
    help_anchor: str | None = None

    #: A key in `docs/sources.toml`. Checked by the guard when present.
    source_key: str | None = None

    def validate(self) -> None:
        """Everything checkable WITHOUT the repository.

        Deliberately does not resolve anchors or source keys: those are
        repository-level facts and belong to the guard, which has
        `openchem.help` and the registry in hand. Keeping this pure is what
        lets the contract be tested with no `QApplication` and no `docs/`.
        """
        if self.tier not in (1, 2, 3):
            raise HelpTooltipError(f"tier must be 1, 2 or 3, not {self.tier!r}")
        if not self.text or not self.text.strip():
            raise HelpTooltipError(f"{self.help_id!r} has no text")
        if not _HELP_ID.match(self.help_id or ""):
            raise HelpTooltipError(
                f"help_id {self.help_id!r} is not <surface>.<concept> in lowercase ASCII"
            )
        segments = self.help_id.split(".")
        for segment in segments:
            if segment in _WIDGET_WORDS:
                raise HelpTooltipError(
                    f"help_id {self.help_id!r} names a widget ({segment!r}) rather than a "
                    "concept -- it must survive the UI being reorganised"
                )
        # `_1`, not `.1`: a bare numeric segment cannot reach here at all
        # (the pattern requires each segment to start with a letter), so
        # checking for one would be a branch nothing can enter. The form
        # that IS reachable -- and is what a sweep meeting ten identical
        # rows actually produces -- is `quantum.charge_1`, `quantum.charge_2`.
        if _INSTANCE_SUFFIX.match(segments[-1]):
            raise HelpTooltipError(
                f"help_id {self.help_id!r} ends in an instance number. A help_id names a "
                "control DEFINITION: repeated renderings share one id unless they genuinely "
                "differ in meaning, and instance_path is what tells them apart."
            )


def apply_help_tooltip(target, tooltip: HelpTooltip) -> None:
    """Attach `tooltip` to `target` and render it as the Qt tooltip.

    `target`, not `QWidget`, because the pose-table headers are
    `QTableWidgetItem`s and a widget-only contract would have reported 100%
    coverage while the columns that prompted this work sat outside its
    universe.

    Three surfaces, two storage mechanisms, one call:

        QWidget            Qt property   (it is a QObject)
        QAction            Qt property   (it is a QObject)
        QTableWidgetItem   item data     (it is NOT)
    """
    tooltip.validate()
    if hasattr(target, "setProperty"):
        target.setProperty(_PROPERTY, tooltip)
    elif hasattr(target, "setData"):
        target.setData(HELP_TOOLTIP_ROLE, tooltip)
    else:  # pragma: no cover - a surface nothing in this app produces
        raise HelpTooltipError(f"cannot attach a help contract to {type(target).__name__}")
    target.setToolTip(tooltip.text)


def help_tooltip_for(target) -> HelpTooltip | None:
    """The contract on `target`, or None.

    THE ONE READER. `tooltip_inventory` goes through this and nothing
    reaches into either storage mechanism directly -- two readers of one
    fact is the divergence the single discovery layer exists to prevent.
    """
    value = None
    if hasattr(target, "property"):
        value = target.property(_PROPERTY)
    elif hasattr(target, "data"):
        value = target.data(HELP_TOOLTIP_ROLE)
    return value if isinstance(value, HelpTooltip) else None
