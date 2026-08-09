from __future__ import annotations

import logging
import os
from collections.abc import Callable

from PySide6.QtCore import QPoint, QSize, Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QFormLayout,
    QLabel,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from openchem.chem.calculation_input import canonical_conformer
from openchem.chem.engine import ChemistryEngine
from openchem.domain.calculator import (
    CalculationRequest,
    CalculatorDefinition,
    RegistryExecution,
    ServiceExecution,
)
from openchem.domain.common import CacheState
from openchem.domain.project import ProjectModel
from openchem.domain.scientific_result import PerAtomDataset, SpectrumResult
from openchem.chem.report_adapter import report_from_alert
from openchem.domain.report import ReportResult
from openchem.domain.structure_issue import Severity
from openchem.events.base import EventBus
from openchem.events.events import (
    AlertComputed,
    DescriptorComputed,
    ReportComputed,
    MoleculeChanged,
    MoleculeSelected,
    PerAtomDataComputed,
    PhCurveComputed,
    SpectrumComputed,
    StructureSetComputed,
)
from openchem.services.calculator_registry import CalculatorRegistry
from openchem.services.descriptor_service import DescriptorService
from openchem.ui.dialogs.calculator_inspector_dialog import CalculatorInspectorDialog
from openchem.ui.dialogs.calculator_settings_dialog import CalculatorSettingsDialog
from openchem.ui.dialogs.nmr_view_dialog import NmrViewDialog
from openchem.ui.widgets.substance_card import SubstanceCard, card_data_from_report
from openchem.ui.widgets.collapsible_section import CollapsibleSection as _CollapsibleSection
from openchem.ui.widgets.collapsible_section import ExplicitHeightLabel as _ExplicitHeightLabel
from openchem.ui.widgets.collapsible_section import WrappedLabel as _WrappedLabel
from openchem.ui.widgets.fact_view import FactView

# Preferred display order -- any category not listed here (e.g. a future
# plugin-supplied one) is appended alphabetically after these, not dropped.
_CATEGORY_ORDER = [
    "physicochemical",
    "identity",
    "naming",
    "charge",
    "logp",
    "logd",
    "molar_refractivity",
    "structures",
    "markush",
    "quantum",
    "electronic",
    "alignment",
    "dynamics",
    "topology",
    "geometry",
    "surface",
    "substructure",
    "interactions",
    "stereochemistry",
    "medicinal_chemistry",
    "pka",
    # Directly after pKa on purpose. Somebody reading "how basic is this"
    # is standing exactly where the Bronsted answer stops being the whole
    # answer, and carbon monoxide is the case that proves it.
    "lewis",
    "admet",
    "shape",
]
_CATEGORY_LABELS = {
    "physicochemical": "Physicochemical",
    "identity": "Identity",
    "naming": "Naming",
    "charge": "Charge",
    "logp": "LogP",
    "logd": "LogD (pH-dependent)",
    "molar_refractivity": "Molar Refractivity",
    "structures": "Structure Generators",
    "quantum": "Quantum (Huckel)",
    "electronic": "Electronic Properties",
    "alignment": "3D Alignment",
    "dynamics": "Dynamics",
    "markush": "Markush Enumeration",
    "topology": "Topology",
    "geometry": "Geometry (3D)",
    "surface": "Surface Area",
    "substructure": "Substructure Search",
    "interactions": "Interactions",
    "stereochemistry": "Stereochemistry",
    "medicinal_chemistry": "Medicinal Chemistry",
    "pka": "pKa",
    "lewis": "Lewis Acid/Base",
    "admet": "ADMET / Toxicity",
    "shape": "Shape",
    # Without these two the panel falls back to `category.title()`, which
    # rendered the NMR section as "Nmr". Found during a documentation
    # sweep: the guide had to describe a heading that was a formatting
    # accident rather than a name anybody chose.
    "nmr": "NMR",
    "regulatory": "Regulatory",
}
_DEFAULT_EXPANDED = {"physicochemical", "identity"}

# Sections are collapsed/expanded up front, computation is NOT deferred
# until a section opens -- every descriptor here finishes in well under a
# millisecond (confirmed live for the full ~30-descriptor RDKit batch), so
# a lazy-per-category compute path would add real service-layer complexity
# (splitting one provider's `compute()` by category, or threading a
# category filter through DescriptorService) to solve a performance
# problem that doesn't exist. Collapsing is purely a decluttering aid.


# THE COLOUR VOCABULARY. Red means failed, dangerous or invalid -- nothing
# else. It previously meant "this result has content", which is why a
# molecular weight, a Szeged index and an elemental analysis all arrived in
# alert red and the app read as though it were constantly complaining.
#
# Counted while fixing it: **20 of the 25 `alert_id`s in this codebase are
# reports rather than alert catalogs.** Only pains, brenk,
# mutagenicity_alerts, herg_risk_factors and a regulatory screen WITH
# findings are warnings.
#
# Colour never carries meaning on its own -- each state has a glyph too,
# for colour-blind readers and for anyone reading a copied plain-text
# export where the styling is gone.
_FAILURE_STYLE = "color: #c62828;"  # red: it did not work, or it is invalid
_WARNING_STYLE = "color: #ef6c00;"  # amber: it worked, and you should look
_SUCCESS_STYLE = "color: #2e7d32;"  # green: checked, nothing flagged
_INFORMATION_STYLE = "color: #666666;"  # neutral: it is simply a value

_FAILURE_GLYPH = "✕ "  # ballot X
_WARNING_GLYPH = "△ "  # white up-pointing triangle
_SUCCESS_GLYPH = "✓ "  # check mark

#: Plain BMP glyphs, not emoji. Qt's emoji rendering on Windows falls back
#: per font and can produce a tofu box where a symbol was intended; these
#: three are in every shipped UI font. Verified by painting, not assumed --
#: see `test_property_panel.py`.


def _format_value(value: object) -> tuple[str, str]:
    """Returns (text, stylesheet) for a descriptor's value -- dispatches on
    the Python type of the value itself (bool vs. number vs. text) rather
    than a separate declared "display_type" field, so no per-category
    branching accumulates here as new descriptors are added."""
    if value is None:
        return "", ""
    if isinstance(value, bool):
        return (_SUCCESS_GLYPH + "Pass", _SUCCESS_STYLE) if value else (_FAILURE_GLYPH + "Fail", _FAILURE_STYLE)
    if isinstance(value, float):
        return f"{value:.4g}", ""
    return str(value), ""


def _make_copyable(label: QLabel) -> None:
    """Let the mouse select this label's text.

    A `QLabel` is not selectable by default, so every number in this panel
    used to be look-only -- you could read a partial charge but not paste
    it into a notebook, an issue or a message. Five other surfaces already
    reach `ui/result_clipboard.py`; this panel reached nothing.

    `LinksAccessibleByMouse` is preserved because fact links depend on it.
    """
    label.setTextInteractionFlags(
        label.textInteractionFlags() | Qt.TextInteractionFlag.TextSelectableByMouse
    )


def _without_glyphs(text: str) -> str:
    """Strip the status glyphs for anything leaving the GUI.

    Two reasons, and the second one is a rule this project learned the
    hard way. A glyph is DECORATION -- somebody pasting a result into a
    paper wants "Pass", not "✓ Pass", and the word already carries the
    meaning the glyph duplicates on screen.

    And these three are non-ASCII. `regulatory/calculator.py`'s docstring
    records that result text reaches Qt, logs and console streams, and
    that a Windows cp1252 stream RAISES on a tick -- hit three times in
    one session, which is why `test_naming_result_lines_stay_ascii`
    exists. Producing them at render time and dropping them at the exit is
    what keeps the glyphs on screen without putting them in the pipe.
    """
    for glyph in (_FAILURE_GLYPH, _WARNING_GLYPH, _SUCCESS_GLYPH):
        text = text.replace(glyph, "")
    return text


def _is_catalog(alert) -> bool:
    from openchem.chem.report_adapter import is_catalog

    return is_catalog(alert)


def _present_alert(alert) -> tuple[str, str, str]:
    """How one `AlertResult` should read: (text, stylesheet, tooltip).

    Pulled out of the panel so the decision is testable on its own and so
    the four states are visible together rather than spread through an
    if-chain in a Qt slot.

    THE ORDER MATTERS. `cache_state` is checked BEFORE `matched`, because a
    failure carries no matches -- and an empty `matched` used to fall
    straight through to a green "Clean". Geometry without a 3D conformer
    therefore reported success while discarding the message that said what
    to do about it, which is the worst of both: wrong, and silent.
    """
    if alert.cache_state is CacheState.FAILED:
        reason = alert.error or "Failed"
        return _FAILURE_GLYPH + reason, _FAILURE_STYLE, reason
    if alert.cache_state in (CacheState.QUEUED, CacheState.RUNNING):
        return alert.cache_state.value.capitalize() + "...", _INFORMATION_STYLE, ""

    if not alert.matched:
        # "Clean" is a verdict, and only a catalog is entitled to give one.
        # An elemental analysis with nothing to say has not cleared the
        # molecule of anything.
        if alert.severity is Severity.WARNING:
            return _SUCCESS_GLYPH + "Clean", _SUCCESS_STYLE, "Checked, nothing flagged."
        return "Nothing to report.", _INFORMATION_STYLE, ""

    joined = "\n".join(alert.matched)
    if alert.severity is Severity.ERROR:
        return _FAILURE_GLYPH + joined, _FAILURE_STYLE, joined
    if alert.severity is Severity.WARNING:
        return (
            f"{_WARNING_GLYPH}{len(alert.matched)} alert(s): {', '.join(alert.matched)}",
            _WARNING_STYLE,
            joined,
        )
    # INFO: a report. One line per line -- comma-joining them produced the
    # "8 alert(s): Formula: CHNO, Mass: 43.025, Exact mass: ..." run that
    # made a composition table look like a toxicity finding.
    return joined, _INFORMATION_STYLE, joined


def _summarise(result: object) -> str:
    """A one-line "what arrived" for a result whose detail lives in a
    dialog. Enough to show the run happened and produced something, with
    the shape of it, so "nothing noticeable happens" cannot recur.
    """
    values = getattr(result, "values", None)
    if isinstance(values, dict) and values:
        numbers = [v for v in values.values() if isinstance(v, (int, float))]
        if numbers:
            return (
                f"{len(values)} atoms, {min(numbers):.4g} to {max(numbers):.4g}"
                f"{' ' + result.units if getattr(result, 'units', '') else ''}"
            )
        return f"{len(values)} atoms"
    structures = getattr(result, "structures", None)
    if structures is not None:
        return f"{len(structures)} structures"
    points = getattr(result, "points", None)
    if points is not None:
        return f"{len(points)} points"
    return "Ready"


#: Qt property carrying which calculator a section button opens.
_CALCULATOR_ID_PROPERTY = "openchem_calculator_id"
#: ... and which report a "Details..." button opens.
logger = logging.getLogger("openchem.ui")

#: Set `OPENCHEM_INSTRUMENT_PANEL=1` to dump this panel's row geometry.
#:
#: WHY IT EXISTS IN THE SHIPPED CODE rather than as a scratch script.
#: The report-row truncation was chased through four fixes and one
#: instrumentation run, every one of which passed in an out-of-app
#: harness and failed in the app. The harness said there was no clipping
#: while the app clipped, no horizontal scrollbar while the app had one,
#: and a full-width label while the app still truncated. **A harness
#: nobody uses is not evidence about the panel a user sees**, and the
#: only way to stop paying for that is to be able to measure inside the
#: running application.
#:
#: Off unless the variable is set, so it costs a single `os.environ`
#: read at import and nothing at runtime.
_INSTRUMENT = bool(os.environ.get("OPENCHEM_INSTRUMENT_PANEL"))

#: How long to wait before dumping. The layout needs to settle -- read
#: too early and you measure a transient mid-relayout state, which has
#: already produced one false "reproduction" of this bug.
_INSTRUMENT_DELAY_MS = 1500

_REPORT_ID_PROPERTY = "openchem_report_id"

#: Pixels of headroom left above a revealed row, so it lands inside the
#: viewport rather than flush against its bottom edge.
_REVEAL_MARGIN = 24

#: How a wide row's name is drawn, now that it is a caption above its
#: value rather than a `QFormLayout` label beside it. Muted and small so
#: the value stays the thing being read.
_WIDE_ROW_CAPTION_STYLE = "color: #555; font-size: 11px;"

#: The panel refuses to be narrower than this.
#:
#: IT IS PART OF THE SAME FIX AND NOT A SEPARATE OPINION. A minimum on
#: the value is a minimum on the CONTENT, and a scroll area whose content
#: cannot fit scrolls SIDEWAYS -- which is worse than the wrapping it
#: replaced, and is what the first version of this shipped as a "fix":
#: the value read correctly at six lines while the panel needed a
#: horizontal scrollbar at every width below 360.
#:
#: So the panel's own minimum has to be at least the value's, with room
#: for the label column's indent and the vertical scrollbar. Measured
#: across the widths the dock produces, on a six-line result whose
#: longest line needs 187 px:
#:
#:     arm                       170   240   300   360   460
#:     shipped                    24L   12L   10L    6L    6L
#:     value>=140, no panel min   10L    6L   10L    6L    6L
#:     value>=200, panel>=240      6L    6L    6L    6L    6L   <- no h-scroll
#:
#: Six lines is the right answer at every width -- the value has six
#: lines in it. The middle row is why the panel minimum is needed rather
#: than just a smaller value minimum: without it there is a dead zone
#: around 300 px where the field column is too narrow to fit the text and
#: too wide to trigger the wrap.
#:
#: 280 AND NOT 240, AND THE DIFFERENCE IS THE VERTICAL SCROLLBAR. 240 was
#: derived against one short section, which never grew one -- so the
#: viewport was the whole panel. The real panel always scrolls, and the
#: scrollbar plus frame take 24 px off the width the content actually
#: gets. Shipped at 240 it produced exactly the horizontal scrollbar this
#: constant exists to prevent, confirmed by driving the app:
#:
#:     panel min  value min  content  viewport  h-scroll
#:         240       200       224      216      YES
#:         260       200       236      236      no
#:         280       200       256      256      no
#:
#: The requirement is panel >= 248. 280 leaves headroom for a wider
#: scrollbar at another DPI or theme, which 260 does not.
#:
#: The lesson generalises: a scroll area's VIEWPORT is not its width, and
#: a harness whose content is too short to scroll measures the wrong one.
_PANEL_MIN_WIDTH = 280


def _starved(widget: QWidget) -> str:
    """`STARVED` when a widget is shorter than the minimum it asks for.

    A layout given less than its minimum does not refuse: it shrinks its
    items anyway, so a starved ANCESTOR is what makes a field 14 px tall
    while that field's own numbers all look correct. Naming the level the
    shortfall first appears at is the whole point of the ancestor walk.
    """
    return "STARVED" if widget.height() < widget.minimumSizeHint().height() else "ok"


def _dump_height_budget(panel: QWidget) -> None:
    """Walk out from each section to the panel, printing who is starved.

    WHY THIS AND NOT MORE FIELD COLUMNS. The recorded measurements all
    describe the field -- it asks for 144 px and is given 14 -- and four
    fixes were designed around that field. But the same run shows a plain
    `formula` row dropping from 16 px to 14 the moment the report row is
    added, and nothing about a report row can make an unrelated scalar
    shorter. Only a container short of space can, by shrinking everything
    in it. This finds that container.
    """
    from PySide6.QtWidgets import QScrollArea

    scroll = panel.findChild(QScrollArea)
    if scroll is not None:
        content = scroll.widget()
        logger.warning(
            "scroll: viewport %dx%d | content %dx%d minSizeH %d %s | widgetResizable %s",
            scroll.viewport().width(),
            scroll.viewport().height(),
            content.width(),
            content.height(),
            content.minimumSizeHint().height(),
            _starved(content),
            scroll.widgetResizable(),
        )
    logger.warning(
        "%-24s %-8s %-8s %-9s %-9s %-9s %-8s",
        "section", "height", "minSizeH", "content h", "content m", "form min", "verdict",
    )
    for category, section in getattr(panel, "_sections", {}).items():
        if section.isHidden() or not section.is_expanded():
            continue
        form = section.content_layout()
        logger.warning(
            "%-24s %-8d %-8d %-9d %-9d %-9d %-8s",
            category[:24],
            section.height(),
            section.minimumSizeHint().height(),
            section.content.height(),
            section.content.minimumSizeHint().height(),
            form.minimumSize().height(),
            _starved(section.content),
        )


def _force_relayout(panel: QWidget) -> None:
    """Invalidate every layout in the panel and let them re-run.

    THE ARM THAT TELLS TWO CAUSES APART. The section is 113 px tall while
    asking 225, and there are only two ways that happens: the layout ran
    against minimums that were smaller AT THE TIME and nothing re-ran it,
    or something is capping the height and a re-run changes nothing. This
    destroys nothing and moves nothing permanently -- it only re-asks.
    """
    from PySide6.QtWidgets import QApplication

    for child in panel.findChildren(QWidget):
        layout = child.layout()
        if layout is not None:
            layout.invalidate()
    if panel.layout() is not None:
        panel.layout().invalidate()
    # THREE ROUNDS, NOT ONE. `invalidate()` POSTS a LayoutRequest rather
    # than laying out, delivering it can post more, and the first version
    # of this probe pumped once -- which cannot tell "the relayout does
    # not help" from "the relayout never finished".
    for _ in range(3):
        QApplication.sendPostedEvents()
        QApplication.processEvents()
    for child in panel.findChildren(QWidget):
        layout = child.layout()
        if layout is not None:
            layout.activate()
    QApplication.processEvents()


def _force_section_minimums(panel: QWidget) -> None:
    """Pin every starved section to the height it asks for.

    Not a candidate fix -- a control. If the rows render at their full
    height once the section is simply given the height it already asks
    for, then every number in the chain is right and only the geometry is
    wrong. If they still do not, the minimum is not what is being ignored
    and no amount of relayout would have helped.
    """
    from PySide6.QtWidgets import QApplication

    for section in getattr(panel, "_sections", {}).values():
        if section.isHidden() or not section.is_expanded():
            continue
        wanted = section.minimumSizeHint().height()
        if section.height() < wanted:
            section.setMinimumHeight(wanted)
    QApplication.processEvents()


def _dump_ancestors(field: QWidget, panel: QWidget) -> None:
    """From one field up to the panel: height against the height asked for.

    Each level also reports what its own LAYOUT would answer, because a
    vertical `QBoxLayout` holding a height-for-width item does not use
    that item's minimum -- it substitutes `heightForWidth`. Printing
    `totalMinimumSize` beside `totalHeightForWidth` is what makes that
    substitution visible instead of inferred.
    """
    logger.warning("ancestors of the report row's field:")
    widget: QWidget | None = field
    while widget is not None:
        layout = widget.layout()
        if layout is None:
            extra = "no layout"
        else:
            extra = "layout: hfw=%s totalMin=%d totalHint=%d totalHfw=%s" % (
                layout.hasHeightForWidth(),
                layout.totalMinimumSize().height(),
                layout.totalSizeHint().height(),
                layout.totalHeightForWidth(widget.width()) if layout.hasHeightForWidth() else "-",
            )
        logger.warning(
            "    %-20s h=%-5d minSizeH=%-5d sizeHint=%-5d maxH=%-9d hfw=%-5s %-8s | %s",
            type(widget).__name__[:20],
            widget.height(),
            widget.minimumSizeHint().height(),
            widget.sizeHint().height(),
            widget.maximumHeight(),
            widget.heightForWidth(widget.width()) if widget.hasHeightForWidth() else "-",
            _starved(widget),
            extra,
        )
        if widget is panel:
            break
        widget = widget.parentWidget()


def _dump_container_items(panel: QWidget) -> None:
    """What the sections container's own layout thinks each section needs.

    The container is 990 px tall and asks for 990, so by its own numbers
    it has room to give every section its minimum -- and one section is
    given half. A layout consults the ITEM, so the item is what has to be
    asked.
    """
    container = getattr(panel, "_sections_container", None)
    layout = container.layout() if container is not None else None
    if layout is None:
        return
    logger.warning(
        "sections container: h=%d layout hfw=%s totalMin=%d",
        container.height(),
        layout.hasHeightForWidth(),
        layout.totalMinimumSize().height(),
    )
    for index in range(layout.count()):
        item = layout.itemAt(index)
        widget = item.widget()
        if widget is None or widget.isHidden():
            continue
        logger.warning(
            "    item %-18s geom_h=%-5d minSize=%-5d sizeHint=%-5d hfw=%-5s hfw(w)=%s",
            type(widget).__name__[:18],
            item.geometry().height(),
            item.minimumSize().height(),
            item.sizeHint().height(),
            item.hasHeightForWidth(),
            item.heightForWidth(container.width()) if item.hasHeightForWidth() else "-",
        )


def _dump_panel_metrics(panel: QWidget) -> None:
    """Log what every form row's FIELD widget reports about itself.

    The columns are the ones that decide whether a wrapped value gets the
    height and width it needs -- and comparing an ALERT row against a
    REPORT row holding the same text is the specific comparison the
    truncation bug needs, so the kind of each row is named.
    """
    from PySide6.QtWidgets import QFormLayout

    logger.warning("panel width=%d  (OPENCHEM_INSTRUMENT_PANEL)", panel.width())
    logger.warning(
        "%-28s %-7s %-7s %-9s %-9s %-7s %-7s %-9s",
        "row (label -> field kind)", "width", "height", "sizeHint", "minSizeH",
        "hasHfW", "hfw(w)", "minWidth",
    )
    for category, section in getattr(panel, "_sections", {}).items():
        form = section.content_layout()
        for row in range(form.rowCount()):
            label_item = form.itemAt(row, QFormLayout.ItemRole.LabelRole)
            field_item = form.itemAt(row, QFormLayout.ItemRole.FieldRole)
            # A wide row occupies SpanningRole and has no field at all,
            # so a dump that only reads FieldRole silently omits exactly
            # the rows this instrumentation exists for.
            if field_item is None:
                field_item = form.itemAt(row, QFormLayout.ItemRole.SpanningRole)
            if field_item is None:
                continue
            field = field_item.widget()
            if field is None or not field.isVisibleTo(panel):
                continue
            label = label_item.widget() if label_item is not None else None
            name = getattr(label, "text", lambda: "")() or category
            kind = type(field).__name__
            width = field.width()
            logger.warning(
                "%-28s %-7d %-7d %-9d %-9d %-7s %-7d %-9d",
                f"{name[:18]} -> {kind[:8]}",
                width,
                field.height(),
                field.sizeHint().height(),
                field.minimumSizeHint().height(),
                field.hasHeightForWidth(),
                field.heightForWidth(width) if field.hasHeightForWidth() else -1,
                field.minimumWidth(),
            )
            # WHAT THE LAYOUT ACTUALLY ASKS. A layout consults the ITEM,
            # never the widget: `QWidgetItem.hasHeightForWidth` reads the
            # SIZE POLICY flag, not the `hasHeightForWidth()` override the
            # line above prints. The two can disagree, and every recorded
            # measurement of this row so far has printed the widget's.
            logger.warning(
                "      item: hfw=%-6s minSize=%-5d sizeHint=%-5d hfw(w)=%-5d | policy hfw=%s v=%s",
                field_item.hasHeightForWidth(),
                field_item.minimumSize().height(),
                field_item.sizeHint().height(),
                field_item.heightForWidth(width) if field_item.hasHeightForWidth() else -1,
                field.sizePolicy().hasHeightForWidth(),
                field.sizePolicy().verticalPolicy().name,
            )
            # A container hides the widget that actually holds the text.
            for child in field.findChildren(QLabel):
                logger.warning(
                    "%-28s %-7d %-7d %-9d %-9d %-7s %-7d %-9d",
                    "    inside -> QLabel",
                    child.width(),
                    child.height(),
                    child.sizeHint().height(),
                    child.minimumSizeHint().height(),
                    child.hasHeightForWidth(),
                    child.heightForWidth(child.width()) if child.hasHeightForWidth() else -1,
                    child.minimumWidth(),
                )


def _add_wide_row(section, name: str, field: QWidget) -> None:
    """Add a value that can be long, spanning BOTH form columns.

    This replaces the `WrapLongRows` + minimum-width pair that used to
    give long values the full width. That mechanism worked by making the
    field's minimum too wide to sit beside its label, so Qt wrapped the
    row -- which meant the form's height depended on its width, which
    made the form height-for-width, which is what truncated report rows
    (see `ExplicitHeightLabel`). Asking for a spanning row outright says
    the same thing with no width-dependent height in it.

    **It also removes the minimum width, and with it the sideways
    scroll.** That minimum existed only to TRIGGER the wrap, and a
    minimum on the value is a minimum on the CONTENT: below about 360 px
    the panel scrolled horizontally instead of wrapping. Nothing needs
    to be forced wide now, so nothing can overflow.

    The caption is a plain label with wrapping OFF, deliberately -- a
    wrapped one would be height-for-width and would put the whole
    problem back one level down.
    """
    holder = QWidget(section.content)
    box = QVBoxLayout(holder)
    box.setContentsMargins(0, 0, 0, 0)
    box.setSpacing(0)
    caption = QLabel(name, holder)
    caption.setWordWrap(False)
    caption.setStyleSheet(_WIDE_ROW_CAPTION_STYLE)
    box.addWidget(caption)
    field.setParent(holder)
    box.addWidget(field)
    section.content_layout().addRow(holder)


class PropertyPanel(QWidget):
    """Categorized, collapsible descriptor view.

    Subscribes to DescriptorComputed/AlertComputed and re-renders with no
    manual refresh — the outline's "live property panel" requirement. Never
    calls RDKit directly; descriptors arrive fully computed via events from
    DescriptorService.

    Phase 18: each category also gets one "Open [Calculator]..." button per
    `CalculatorRegistry` entry registered for it -- clicking one opens that
    calculator's settings dialog (if it has parameters), runs it via
    `DescriptorService.run_calculator`, and opens a `CalculatorInspectorDialog`
    once the matching result arrives. Holds `calculator_registry`/
    `descriptor_service`/`chemistry_engine` references and a `ProjectModel`
    (via `set_project`, same pattern `DockingPanel`/`QuantumChemistryPanel`
    already use) to drive this directly -- unlike the purely event-reactive
    descriptor rendering, opening a calculator is a user-initiated action
    that needs the real `MoleculeModel`, not just its uuid.
    """

    def __init__(
        self,
        event_bus: EventBus,
        calculator_registry: CalculatorRegistry,
        descriptor_service: DescriptorService,
        chemistry_engine: ChemistryEngine,
        parent: QWidget | None = None,
        on_add_structure: Callable[[str, str], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self._calculator_registry = calculator_registry
        self._descriptor_service = descriptor_service
        self._chemistry_engine = chemistry_engine
        # Adding a generated structure (a chosen stereoisomer, tautomer,
        # resonance form) as a new molecule needs the undo stack, which
        # MainWindow owns -- so it injects the callback rather than this
        # panel reaching upward for it.
        self._on_add_structure = on_add_structure
        self._project: ProjectModel | None = None
        self._selected_molecule_uuid: str | None = None
        # Set right before DescriptorService.run_calculator() and cleared
        # once the matching result arrives -- distinguishes "the user just
        # asked for this calculator" from an eager-batch PerAtomDataComputed
        # for the same property_id (crippen_logp_contrib/crippen_mr_contrib
        # are computed both ways, deliberately the same value either way --
        # see compute_crippen_logp_contrib_calculator's docstring), which
        # must not silently pop the inspector open on its own.
        self._pending_calculator_id: str | None = None
        #: The row `_reveal_pending_result` scrolls to on the next turn
        #: of the event loop, once its geometry has settled.
        self._reveal_target: QWidget | None = None
        # Keyed on (provider, descriptor_id) rather than bare descriptor_id:
        # two providers (e.g. a plugin and the built-in one) could otherwise
        # pick the same short name and silently collide.
        self._value_labels: dict[tuple[str, str], QLabel] = {}
        self._alert_labels: dict[tuple[str, str], QLabel] = {}
        #: Results whose detail lives in a dialog -- per-atom datasets,
        #: spectra, structure sets, pH curves. Before these existed a
        #: batch run computed them, published them, and rendered nothing
        #: whatsoever, which is exactly what "I can hit run on several
        #: things and nothing noticeable happens" was describing.
        self._result_labels: dict[str, QLabel] = {}
        #: Fact-based reports, kept so "Details..." can open one after the
        #: fact. Plain data keyed by string -- never a dict keyed by a
        #: QWidget, which hashes on a C++ pointer Qt frees with the parent.
        self._reports: dict[str, ReportResult] = {}
        self._report_labels: dict[str, QLabel] = {}
        self._sections: dict[str, _CollapsibleSection] = {}
        # Which section each row currently lives in -- lets
        # _on_descriptor_computed detect a category change and re-parent the
        # row instead of leaving it stuck in whatever section it first drew
        # in (see the category-bucketing bug this guards against).
        self._row_sections: dict[tuple[str, str], _CollapsibleSection] = {}

        self._sections_container = QWidget(self)
        self._sections_layout = QVBoxLayout(self._sections_container)
        self._sections_layout.setContentsMargins(0, 0, 0, 0)
        self._sections_layout.addStretch()

        # Held rather than left a local: `_reveal_pending_result` scrolls a
        # freshly-arrived row into view through it.
        self._scroll_area = scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(self._sections_container)
        # See `_PANEL_MIN_WIDTH`: a minimum on the values is a minimum on
        # the content, and content the panel cannot fit makes it scroll
        # SIDEWAYS. The dock gave this panel 170 px in the running app,
        # which is narrower than a single result line.
        self.setMinimumWidth(_PANEL_MIN_WIDTH)

        # Panel-wide rather than per-section: a selection routinely spans
        # categories ("charges and SASA and the ring systems"), and a Run
        # button inside one section could not express that.
        self._calculator_ticks: dict[str, QCheckBox] = {}
        #: Ticked calculators currently in flight, so one cannot be
        #: queued twice from repeated clicks.
        self._running_calculator_ids: set[str] = set()
        self._run_selected_button = QPushButton("Run selected", self)
        self._run_selected_button.setEnabled(False)
        self._run_selected_button.clicked.connect(self._on_run_selected)
        self._clear_selection_button = QPushButton("Clear", self)
        self._clear_selection_button.setEnabled(False)
        self._clear_selection_button.clicked.connect(self._on_clear_selection)
        # A PLAIN QLabel, deliberately, where every other multi-line label
        # in this panel is a `_WrappedLabel`.
        #
        # `_WrappedLabel`'s `MinimumExpanding` vertical policy is
        # load-bearing INSIDE the scroll area -- it is what stops the
        # calculator buttons being squeezed to 13px (see its docstring).
        # In this top-level row it does the exact opposite: the row claims
        # the stretch and pushes the sections off the bottom of the panel.
        # Measured on a bare Qt reproduction at 900x950: **461px tall with
        # the policy, 20px without**, moving the scroll area's top from
        # y=478 to y=37.
        #
        # One line, with the full text on hover, because this is transient
        # status and not a result.
        self._batch_status = QLabel("", self)
        self._batch_status.setWordWrap(False)
        self._batch_status.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._batch_status.setStyleSheet(_INFORMATION_STYLE)

        batch_row = QHBoxLayout()
        batch_row.addWidget(self._run_selected_button)
        batch_row.addWidget(self._clear_selection_button)
        batch_row.addWidget(self._batch_status, 1)

        # A PERSISTENT header, not a result row. What the app should call
        # a structure changes with what kind of thing it is, and that
        # answer belongs above the properties rather than among them.
        self._substance_card = SubstanceCard(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self._substance_card)
        layout.addLayout(batch_row)
        layout.addWidget(scroll_area)

        # Right-click anywhere to copy. Selecting text with the mouse works
        # too (see `_make_copyable`), but a panel of forty short values is
        # awkward to drag across, and "copy the whole thing" is what people
        # actually want when pasting into a notebook or an issue.
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)

        # Eagerly create a section (with its "Open..." buttons) for every
        # registered calculator category, even one with no matching scalar
        # descriptor to otherwise trigger section creation (pKa has none) --
        # the registry is static (registered once at bootstrap), so this
        # only ever needs to run once. Skips a category that's entirely
        # ServiceExecution-backed (Docking, QuantumChemistry, Phase 21) --
        # those run through their own panel, not through a settings-dialog
        # -> run_calculator() -> inspector flow this panel drives, so an
        # eager section for them here would just be an empty, unusable
        # section (or a button that raises CalculatorRegistry.compute()'s
        # ValueError if it somehow got one).
        for category in calculator_registry.categories():
            if any(
                isinstance(d.execution, RegistryExecution) for d in calculator_registry.by_category(category)
            ):
                self._section_for(category)

        event_bus.subscribe(MoleculeSelected, self._on_molecule_selected)
        event_bus.subscribe(MoleculeChanged, self._on_molecule_changed)
        event_bus.subscribe(DescriptorComputed, self._on_descriptor_computed)
        event_bus.subscribe(AlertComputed, self._on_alert_computed)
        event_bus.subscribe(ReportComputed, self._on_report_computed)
        event_bus.subscribe(PerAtomDataComputed, self._on_per_atom_data_computed)
        event_bus.subscribe(SpectrumComputed, self._on_spectrum_computed)
        event_bus.subscribe(StructureSetComputed, self._on_structure_set_computed)
        event_bus.subscribe(PhCurveComputed, self._on_ph_curve_computed)

    def set_project(self, project: ProjectModel | None) -> None:
        self._project = project

    def _on_molecule_selected(self, event: MoleculeSelected) -> None:
        self._selected_molecule_uuid = event.molecule_uuid
        self._pending_calculator_id = None
        # The backstop. `_finish_batch_run` clears ids as results arrive by
        # matching the result's own id against the calculator's, which is
        # only best-effort: nothing guarantees a calculator names its result
        # after itself. Clearing on molecule change means the worst case is
        # "cannot re-run until you switch molecule", not "stuck forever".
        self._running_calculator_ids.clear()
        self._batch_status.setText("")
        self._value_labels.clear()
        self._alert_labels.clear()
        self._result_labels.clear()
        self._reports.clear()
        self._report_labels.clear()
        self._row_sections.clear()
        for section in self._sections.values():
            section.clear_rows()
        self._substance_card.clear()
        self._request_substance_perception()

    def _section_for(self, category: str) -> _CollapsibleSection:
        section = self._sections.get(category)
        if section is not None:
            return section
        expanded = category in _DEFAULT_EXPANDED
        title = _CATEGORY_LABELS.get(category, category.replace("_", " ").title() or "Other")
        section = _CollapsibleSection(title, expanded, self._sections_container)
        self._sections[category] = section
        for definition in self._calculator_registry.by_category(category):
            if not isinstance(definition.execution, RegistryExecution):
                # ServiceExecution-backed (Docking, QuantumChemistry) --
                # registered for discovery only, run from their own panel.
                continue
            button = QPushButton(f"Open {definition.display_name}...", section.content)
            # A BOUND METHOD, never a lambda that captures `self`.
            #
            # PySide6 holds a connected plain callable STRONGLY and holds a
            # bound method of a QObject weakly, so
            # `connect(lambda ...: self._open_calculator(d))` roots the
            # panel for the life of the process -- past refcounting and
            # past the cyclic collector, which cannot see through the
            # internal map the callable is kept in. Measured on a minimal
            # case: three buttons with a self-capturing lambda leak their
            # widget; the same widget with a bound method is freed by
            # refcounting alone.
            #
            # Which calculator a button means travels on the button
            # instead, resolved back through the registry -- the single
            # source of truth for what is registered anyway.
            button.setProperty(_CALCULATOR_ID_PROPERTY, definition.calculator_id)
            button.clicked.connect(self._on_calculator_button_clicked)

            # The tick box runs this calculator as part of a batch. The
            # engine has always been able to run several at once --
            # `run_calculator` dispatches to `QThreadPool.globalInstance()`
            # with no serialisation -- so this is the affordance, not new
            # machinery.
            row = QWidget(section.content)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            tick = QCheckBox(row)
            tick.setToolTip("Include in 'Run selected'")
            tick.setProperty(_CALCULATOR_ID_PROPERTY, definition.calculator_id)
            tick.toggled.connect(self._on_selection_toggled)
            self._calculator_ticks[definition.calculator_id] = tick
            row_layout.addWidget(tick)
            row_layout.addWidget(button, 1)
            section.add_calculator_widget(row)
        self._add_service_execution_hint(section, category)
        self._add_cross_theory_hint(section, category)
        self._reorder_sections()
        return section

    #: Category -> (category it should point at, the sentence to show).
    #: ONE entry, and deliberately not generalised into a registry field.
    #: There is exactly one pair of acid-base theories in this application
    #: and inventing a mechanism for a single case is the premature
    #: generalisation this project has declined twice before. A second
    #: entry here is the signal to reconsider, not the first.
    _CROSS_THEORY_HINTS = {
        "pka": (
            "lewis",
            "pKa answers whether this gives up a PROTON. Something can be a "
            "negligible Bronsted base and still a strong Lewis base -- carbon "
            "monoxide is both -- so see the Lewis Acid/Base section too.",
        ),
    }

    def _add_cross_theory_hint(self, section: _CollapsibleSection, category: str) -> None:
        """Point the pKa section at the Lewis one.

        Not the same relationship as `_add_service_execution_hint`, which
        says "a more accurate version of this calculation exists". This one
        says "this calculation answers a narrower QUESTION than you may
        think it does", which is a different and more easily missed error.
        """
        target = self._CROSS_THEORY_HINTS.get(category)
        if target is None:
            return
        other, message = target
        # Silent when nothing implements the other theory, so a stripped or
        # plugin-reduced registry cannot leave a pointer to nowhere.
        if not self._calculator_registry.by_category(other):
            return
        hint = _ExplicitHeightLabel(message, section.content)
        hint.setStyleSheet("color: #666666; font-style: italic;")
        section.add_calculator_widget(hint)

    def _add_service_execution_hint(self, section: _CollapsibleSection, category: str) -> None:
        """Phase 23: a section whose runnable calculators are all
        `prediction_basis == "empirical"` gets a one-line pointer to the
        matching `"ab_initio"` calculator, when one exists. Concretely: the
        NMR section's clickable row is the instant SMARTS estimate, and
        nothing on screen previously hinted that a real ORCA NMR
        calculation exists at all -- a user could reasonably believe they
        had just run the ab initio one (Alex did).

        The ab initio counterpart lives in a DIFFERENT category
        (`orca.nmr` is in `"quantum_chemistry"`, so its own panel keeps its
        natural grouping), so the match is on the dotted-calculator_id
        convention established in Phase 21: `orca.nmr` / `orca.nmr_coupling`
        both carry `nmr` as their id suffix. Registry-driven rather than
        hardcoding "NMR", so a future empirical/ab-initio pair following
        the same naming gets this for free.
        """
        runnable = [
            d for d in self._calculator_registry.by_category(category)
            if isinstance(d.execution, RegistryExecution)
        ]
        if not runnable or any(d.prediction_basis != "empirical" for d in runnable):
            return
        ab_initio = [
            d
            for c in self._calculator_registry.categories()
            for d in self._calculator_registry.by_category(c)
            if d.prediction_basis == "ab_initio"
            and isinstance(d.execution, ServiceExecution)
            and category in d.calculator_id.split(".")[-1].split("_")
        ]
        if not ab_initio:
            return
        panel_name = ab_initio[0].execution.panel_name
        hint = _ExplicitHeightLabel(
            f"Estimate above is empirical (instant). For a real ab initio "
            f"calculation, use the {panel_name}.",
            section.content,
        )
        hint.setStyleSheet("color: #666666; font-style: italic;")
        section.add_calculator_widget(hint)

    def _reorder_sections(self) -> None:
        # Re-inserts every known section in preferred order (listed
        # categories first, any unlisted ones appended alphabetically) --
        # cheap to just rebuild since there are only ever a handful of
        # sections, and this only runs when a brand-new category shows up
        # for the first time, not on every descriptor.
        while self._sections_layout.count():
            self._sections_layout.takeAt(0)
        ordered = sorted(
            self._sections,
            key=lambda cat: (
                _CATEGORY_ORDER.index(cat) if cat in _CATEGORY_ORDER else len(_CATEGORY_ORDER),
                cat,
            ),
        )
        for category in ordered:
            self._sections_layout.addWidget(self._sections[category])
        self._sections_layout.addStretch()

    def _on_descriptor_computed(self, event: DescriptorComputed) -> None:
        descriptor = event.descriptor
        if descriptor.molecule_uuid != self._selected_molecule_uuid:
            return
        section = self._section_for(descriptor.category or "other")
        row_key = (descriptor.provider, descriptor.descriptor_id)
        label = f"{descriptor.name} ({descriptor.units})" if descriptor.units else descriptor.name

        value_label = self._value_labels.get(row_key)
        if value_label is None:
            value_label = QLabel(section.content)
            value_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            _make_copyable(value_label)
            section.content_layout().addRow(label, value_label)
            self._value_labels[row_key] = value_label
        elif self._row_sections.get(row_key) is not section:
            # A row's category can legitimately change between events (e.g.
            # a placeholder published before the real category was known) --
            # move it to the right section instead of leaving it stuck
            # wherever it was first drawn. `takeRow` (not `removeRow`, which
            # deletes the widgets) removes the row without destroying
            # `value_label`, so it can be re-added under the new section.
            old_section = self._row_sections.get(row_key)
            if old_section is not None:
                taken = old_section.content_layout().takeRow(value_label)
                if taken.labelItem is not None and taken.labelItem.widget() is not None:
                    taken.labelItem.widget().deleteLater()
            section.content_layout().addRow(label, value_label)
        self._row_sections[row_key] = section

        if descriptor.cache_state.value == "failed":
            value_label.setText(descriptor.error or "Failed")
            value_label.setStyleSheet(_FAILURE_STYLE)
            value_label.setToolTip(descriptor.error or "")
        elif descriptor.cache_state.value in ("queued", "running"):
            value_label.setText(descriptor.cache_state.value.capitalize() + "...")
            value_label.setStyleSheet(_INFORMATION_STYLE)
            value_label.setToolTip("")
        else:
            text, style = _format_value(descriptor.value)
            value_label.setText(text)
            value_label.setStyleSheet(style)
            value_label.setToolTip("")

    def _finish_batch_run(self, result_id: str) -> None:
        """A ticked calculator's result arrived, so it is no longer running.

        Matches the result's own id against the calculator id. Most
        calculators name their result after themselves (`lewis_sites`,
        `gasteiger_charge`, `huckel_analysis`), but nothing enforces it, so
        this is best-effort and `_on_molecule_selected` is the backstop.
        """
        was_running = result_id in self._running_calculator_ids
        self._running_calculator_ids.discard(result_id)
        # The status used to be written once on dispatch and never
        # revisited, so it read "Running 2 with default settings: ..."
        # indefinitely -- including in the screenshot where both results
        # were already on screen behind it.
        if was_running and not self._running_calculator_ids:
            self._batch_status.setText("Finished.")

    def _show_result(self, result_id: str, name: str, category: str, result: object) -> None:
        """Render a result whose detail belongs in a dialog.

        Called for EVERY such result, not only the one the user clicked a
        button for. That distinction is the bug: `_on_run_selected`
        deliberately leaves `_pending_calculator_id` unset (six stacked
        inspectors is not a saving), and every handler below used to
        return early without it -- so a batch run produced no visible
        change anywhere in the panel.

        The row is a summary plus a link, not the data itself. A hundred
        per-atom values do not belong in a form row, and the Calculator
        Inspector already renders them properly.
        """
        section = self._section_for(category or "other")
        label = self._result_labels.get(result_id)
        if label is None:
            label = _ExplicitHeightLabel("", section.content)
            _make_copyable(label)
            _add_wide_row(section, name, label)
            self._result_labels[result_id] = label
        if getattr(result, "cache_state", None) is CacheState.FAILED:
            reason = getattr(result, "error", None) or "Failed"
            label.setText(_FAILURE_GLYPH + reason)
            label.setStyleSheet(_FAILURE_STYLE)
            label.setToolTip(reason)
            return
        summary = _summarise(result)
        label.setText(summary)
        label.setStyleSheet(_INFORMATION_STYLE)
        label.setToolTip("Open the calculator's button above to see the detail.")

    def _category_of(self, calculator_id: str) -> str:
        """Which section a result belongs in.

        `PerAtomDataset` and `SpectrumResult` carry no category of their
        own -- only `AlertResult` does -- so it comes from the registry,
        which is the single source of truth for what a calculator is and
        where it lives.
        """
        definition = self._calculator_registry.get(calculator_id)
        return definition.category if definition is not None else "other"

    def _on_alert_computed(self, event: AlertComputed) -> None:
        alert = event.alert
        self._finish_batch_run(alert.alert_id)
        if alert.molecule_uuid != self._selected_molecule_uuid:
            return
        # Phase 19: routed via alert.category (PAINS -> medicinal_chemistry,
        # BRENK -> admet) now that a second alert catalog exists.
        section = self._section_for(alert.category)
        row_key = ("core", alert.alert_id)

        value_label = self._alert_labels.get(row_key)
        if value_label is None:
            value_label = _ExplicitHeightLabel("", section.content)
            _make_copyable(value_label)
            _add_wide_row(section, alert.name, value_label)
            self._alert_labels[row_key] = value_label

        text, style, tooltip = _present_alert(alert)
        value_label.setText(text)
        value_label.setStyleSheet(style)
        value_label.setToolTip(tooltip)
        self._reveal(alert.alert_id, section, value_label.parentWidget())
        # An unmigrated result is still a report; it just has to be
        # reconstructed from its strings. Held so "Details..." works for
        # it exactly as it does for a migrated one.
        if not _is_catalog(alert):
            self._reports[alert.alert_id] = report_from_alert(alert)

    def _on_molecule_changed(self, event: MoleculeChanged) -> None:
        """Re-perceive when the STRUCTURE changes, not only when the
        selection does.

        Found by running the app. Selecting the empty starter molecule
        leaves nothing to perceive, and pasting a structure into it fires
        `MoleculeChanged` rather than `MoleculeSelected` -- so the header
        read "No structure selected" while the properties below it showed
        Mwt 58.44 and formula ClNa. Every test builds a molecule that
        already has its molblock and publishes a selection, which is the
        one order in which this cannot happen.
        """
        if event.molecule_uuid != self._selected_molecule_uuid:
            return
        self._request_substance_perception()

    def _selected_molecule_name(self) -> str:
        """What the app calls the selected molecule, or "".

        **Independent of the classification**, deliberately. The card reads
        the two from different sources so that a structure nothing can name
        still gets its header -- "Organometallic / (not named) / C10H10Fe"
        is worth far more than collapsing the card because one source came
        up empty.
        """
        if self._project is None or self._selected_molecule_uuid is None:
            return ""
        molecule = self._project.find_molecule(self._selected_molecule_uuid)
        # `display_name`, read directly. The first version was
        # `getattr(molecule, "name", "")`, and the DEFAULT hid the typo:
        # every card rendered "(not named)" for a molecule the project
        # explorer was calling "New molecule" three inches away, with
        # nothing raising.
        return molecule.display_name if molecule is not None else ""

    def _request_substance_perception(self) -> None:
        """Run the one calculator the header is made of.

        Auto-run because the card is a HEADER: a persistent identity
        strip that only appears once somebody thinks to tick a box is not
        a header, it is a result. This is the only calculator dispatched
        without being asked for, and it is cheap -- graph perception, no
        conformer, no external tool.
        """
        if self._project is None or self._selected_molecule_uuid is None:
            return
        molecule = self._project.find_molecule(self._selected_molecule_uuid)
        if molecule is None:
            return
        # **A new molecule has no molblock yet, and this is the only
        # calculator that runs without being asked.** Found by launching
        # the app: selecting the empty starter molecule logged
        # `InvalidStructureError: Molecule ... has no molblock` as a
        # calculator FAILURE, once per selection. Every other calculator
        # waits for a click, so nothing had ever dispatched against a
        # structure that does not exist yet.
        if not molecule.molblock:
            return
        definition = self._calculator_registry.get("substance_analysis")
        if definition is None or not isinstance(definition.execution, RegistryExecution):
            return
        self._descriptor_service.run_calculator(
            molecule,
            CalculationRequest(
                calculator_id="substance_analysis",
                molecule_uuid=molecule.uuid,
                parameters={p.name: p.default for p in definition.parameters},
            ),
        )

    def _on_report_computed(self, event: ReportComputed) -> None:
        """A calculator produced facts rather than a list of strings.

        Rendered as one row per fact, in the calculator's own section --
        which is what `AlertResult` could never do, because a string list
        has no labels to make rows out of. "Details..." opens the whole
        thing in a `FactView` with search, the depth filter, provenance
        and export.
        """
        report = event.report
        self._finish_batch_run(report.report_id)
        if report.molecule_uuid != self._selected_molecule_uuid:
            return
        self._reports[report.report_id] = report
        if report.report_id == "substance_analysis":
            self._substance_card.set_data(
                card_data_from_report(report, name=self._selected_molecule_name())
            )
        section = self._section_for(report.category)

        label = self._report_row(section, report.report_id, report.name)
        if report.cache_state is CacheState.FAILED:
            label.setText(_FAILURE_GLYPH + (report.error or "Failed"))
            label.setStyleSheet(_FAILURE_STYLE)
        elif not report.facts:
            label.setText("Nothing to report.")
            label.setStyleSheet(_INFORMATION_STYLE)
        else:
            label.setText("\n".join(f"{f.label}: {f.display_value}" for f in report.facts[:6]))
            label.setStyleSheet(_INFORMATION_STYLE)
            if len(report.facts) > 6:
                label.setToolTip(f"{len(report.facts)} facts. Open Details for all of them.")
        # Every branch, including the failures -- a run that failed is
        # exactly the case where being shown the answer matters most, and
        # the early returns this replaced meant a FAILED report scrolled
        # nowhere and read as nothing having happened.
        self._reveal(report.report_id, section, label.parentWidget())

    def _report_row(self, section, report_id: str, name: str):
        """The label for one report, created once and reused.

        Paired with a "Details..." button that opens the report in a
        `FactView` -- the same widget the Atom Inspector uses, so search,
        the depth filter, evidence, limitations and export come along
        without this panel implementing any of it.

        THIS ROW USED TO TRUNCATE TO ONE LINE, and nothing on the row
        was ever the cause. Measured in the running app, the field
        asked for 144 px of height and was given 14 -- but so was the
        plain `formula` row above it, which dropped from 16 px to 14
        the moment this row appeared. An unrelated scalar cannot be
        shortened by a report row; only a
        container short of space can shorten both.

        The shortfall is at the SECTION: it is given 113 px while asking
        225, because a vertical `QBoxLayout` holding a height-for-width
        item substitutes that item's `heightForWidth` for its minimum,
        and one `WrappedLabel` inside makes every ancestor layout
        height-for-width carrying.

        EIGHT FIXES HAVE BEEN TRIED, four of them against this row, and
        all eight failed. Do not design a ninth here -- the numbers on
        this row are correct.

        THIS ROW TRUNCATED FOR NINE ATTEMPTED FIXES, four of them aimed
        at this row, whose numbers were correct the whole time.
        `QBoxLayout.setGeometry` OVERWRITES a height-for-width item's
        minimum with its `heightForWidth` before distributing space, so
        no minimum stated anywhere on the chain could win. The fix is to
        leave the chain with no height-for-width in it at all, which
        takes all three of `ExplicitHeightLabel`, `DontWrapRows` and
        `_add_wide_row` -- see `docs/ARCHITECTURE.md`'s Known TODO.

        The value is a `_ExplicitHeightLabel` and NOT a `_WrappedLabel`
        for that reason, and one `_WrappedLabel` anywhere in this section
        would put the truncation back.
        """
        existing = self._report_labels.get(report_id)
        if existing is not None:
            return existing
        row = QWidget(section.content)
        row_layout = QVBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(2)
        value = _ExplicitHeightLabel("", row)
        _make_copyable(value)
        row_layout.addWidget(value)
        details = QPushButton("Details...", row)
        details.setMaximumWidth(80)
        # The payload rides on the button; a lambda capturing self is held
        # STRONGLY by PySide6 and would root this panel for the process.
        details.setProperty(_REPORT_ID_PROPERTY, report_id)
        details.clicked.connect(self._on_details_clicked)
        # UNDER the value, not beside it. Beside it, the button took 80 px
        # plus spacing off a field column that was already the narrow half
        # of a 280 px dock, leaving the text about 22 px -- a
        # one-word-per-line ribbon. The row spans the full width now, so
        # the value gets all of it and the button costs a row of its own
        # rather than two thirds of the line.
        row_layout.addWidget(details, 0, Qt.AlignmentFlag.AlignRight)
        _add_wide_row(section, name, row)
        self._report_labels[report_id] = value
        # Triggered HERE rather than at construction: at startup the
        # panel is empty and every row it could measure does not exist
        # yet. A report row is exactly the case under investigation.
        if _INSTRUMENT:
            # A BOUND METHOD, not a lambda capturing self. `singleShot`
            # releases its callable after firing so this one would not
            # leak permanently, but PySide6 holds a plain callable
            # STRONGLY and this codebase has already paid for that once
            # -- see CLAUDE.md and tests/test_qt_object_disposal.py.
            QTimer.singleShot(_INSTRUMENT_DELAY_MS, self._dump_metrics)
        return value

    def _dump_metrics(self) -> None:
        """Log this panel's row geometry. Only reachable with
        `OPENCHEM_INSTRUMENT_PANEL` set -- see `_INSTRUMENT`."""
        _dump_panel_metrics(self)
        _dump_height_budget(self)
        _dump_container_items(self)
        for report_id, value in self._report_labels.items():
            container = value.parentWidget()
            if container is not None:
                logger.warning("--- report row %r ---", report_id)
                _dump_ancestors(container, self)
        if os.environ.get("OPENCHEM_INSTRUMENT_RELAYOUT"):
            logger.warning("=== ARM 1: relayout, pumped to completion ===")
            _force_relayout(self)
            _dump_panel_metrics(self)
            _dump_height_budget(self)
            logger.warning("=== ARM 2: pin starved sections to their own minimum ===")
            _force_section_minimums(self)
            _dump_panel_metrics(self)
            _dump_height_budget(self)

    def _on_details_clicked(self, _checked: bool = False) -> None:
        button = self.sender()
        if button is None:
            return
        report = self._reports.get(button.property(_REPORT_ID_PROPERTY))
        if report is None:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(report.name)
        dialog.resize(520, 620)
        view = FactView(dialog)
        view.set_report(report, report.name)
        layout = QVBoxLayout(dialog)
        layout.addWidget(view)
        dialog.exec()

    def _on_per_atom_data_computed(self, event: PerAtomDataComputed) -> None:
        dataset = event.dataset
        self._finish_batch_run(dataset.property_id)
        if dataset.molecule_uuid == self._selected_molecule_uuid:
            self._show_result(
                dataset.property_id, dataset.name,
                self._category_of(dataset.property_id), dataset,
            )
        if (
            self._pending_calculator_id is not None
            and dataset.property_id == self._pending_calculator_id
            and dataset.molecule_uuid == self._selected_molecule_uuid
        ):
            self._pending_calculator_id = None
            self._open_inspector(dataset)

    def _on_spectrum_computed(self, event: SpectrumComputed) -> None:
        # Phase 22: a RegistryExecution-backed calculator (e.g. the
        # empirical SMARTS NMR estimator) can produce a SpectrumResult
        # instead of a PerAtomDataset -- matched by spectrum_type against
        # _pending_calculator_id the same way property_id is matched
        # above (the two calculators that use this path name their
        # calculator_id and spectrum_type identically).
        spectrum = event.spectrum
        self._finish_batch_run(spectrum.spectrum_type)
        if spectrum.molecule_uuid == self._selected_molecule_uuid:
            self._show_result(
                spectrum.spectrum_type, spectrum.name,
                self._category_of(spectrum.spectrum_type), spectrum,
            )
        if (
            self._pending_calculator_id is not None
            and spectrum.spectrum_type == self._pending_calculator_id
            and spectrum.molecule_uuid == self._selected_molecule_uuid
        ):
            self._pending_calculator_id = None
            self._open_inspector(spectrum)

    def _on_structure_set_computed(self, event: StructureSetComputed) -> None:
        # Phase 27: a structure-generating calculator (stereoisomers,
        # tautomers, resonance, Markush) produces a StructureSetResult.
        # Matched on set_id the same way the spectrum path matches
        # spectrum_type. Every generator's set_id is deliberately equal to
        # its registered calculator_id so no mapping table is needed -- they
        # were aligned before shipping rather than bridged afterwards.
        structure_set = event.structure_set
        self._finish_batch_run(structure_set.set_id)
        if structure_set.molecule_uuid == self._selected_molecule_uuid:
            self._show_result(
                structure_set.set_id, getattr(structure_set, 'name', structure_set.set_id),
                self._category_of(structure_set.set_id), structure_set,
            )
        if (
            self._pending_calculator_id is not None
            and structure_set.set_id == self._pending_calculator_id
            and structure_set.molecule_uuid == self._selected_molecule_uuid
        ):
            self._pending_calculator_id = None
            self._open_inspector(structure_set)

    def _on_ph_curve_computed(self, event: PhCurveComputed) -> None:
        # Phase 28. Matched on curve_id, which every pH calculator sets
        # equal to its registered calculator_id -- same convention the
        # structure-set and spectrum paths use.
        curve = event.curve
        self._finish_batch_run(curve.curve_id)
        if curve.molecule_uuid == self._selected_molecule_uuid:
            self._show_result(
                curve.curve_id, getattr(curve, 'name', curve.curve_id),
                self._category_of(curve.curve_id), curve,
            )
        if (
            self._pending_calculator_id is not None
            and curve.curve_id == self._pending_calculator_id
            and curve.molecule_uuid == self._selected_molecule_uuid
        ):
            self._pending_calculator_id = None
            self._open_inspector(curve)

    def _on_calculator_button_clicked(self, _checked: bool = False) -> None:
        """Resolve the button that was pressed back to its calculator.

        Deliberately reads the sender rather than closing over the
        definition -- see `_section_for` for why a capturing lambda cannot
        be used here.
        """
        button = self.sender()
        if button is None:
            return
        calculator_id = button.property(_CALCULATOR_ID_PROPERTY)
        definition = self._calculator_registry.get(calculator_id) if calculator_id else None
        if definition is not None:
            self._open_calculator(definition)

    # --- running several at once -------------------------------------------

    def _selected_calculator_ids(self) -> list[str]:
        return [cid for cid, tick in self._calculator_ticks.items() if tick.isChecked()]

    def _on_selection_toggled(self, _checked: bool = False) -> None:
        count = len(self._selected_calculator_ids())
        self._run_selected_button.setEnabled(count > 0)
        self._clear_selection_button.setEnabled(count > 0)
        self._run_selected_button.setText(
            f"Run selected ({count})" if count else "Run selected"
        )

    def _on_clear_selection(self, _checked: bool = False) -> None:
        for tick in self._calculator_ticks.values():
            tick.setChecked(False)
        self._batch_status.setText("")

    def _on_run_selected(self, _checked: bool = False) -> None:
        """Dispatch every ticked calculator for the selected molecule.

        **Default parameters, no dialogs.** Each calculator that has
        settings would otherwise open its own, and answering six dialogs to
        avoid clicking six buttons is not a saving. Somebody who needs
        non-default settings still has the per-calculator button, which is
        exactly what it is for.

        Results arrive through the existing `PerAtomDataComputed` /
        `AlertComputed` events like any other run, so nothing downstream
        knows this happened. `_pending_calculator_id` is deliberately NOT
        set: it exists to pop an inspector open when a result lands, and
        six inspectors stacking up is not what anybody asked for.
        """
        if self._project is None or self._selected_molecule_uuid is None:
            self._batch_status.setText("Select a molecule first.")
            return
        molecule = self._project.find_molecule(self._selected_molecule_uuid)
        if molecule is None:
            return

        started: list[str] = []
        for calculator_id in self._selected_calculator_ids():
            definition = self._calculator_registry.get(calculator_id)
            if definition is None or not isinstance(definition.execution, RegistryExecution):
                continue
            # Same calculator ticked and already running is the one
            # re-entrancy worth guarding: the pool would happily run it
            # twice and publish two results for one molecule.
            if calculator_id in self._running_calculator_ids:
                continue
            self._running_calculator_ids.add(calculator_id)
            parameters = {p.name: p.default for p in definition.parameters}
            self._descriptor_service.run_calculator(
                molecule,
                CalculationRequest(
                    calculator_id=calculator_id,
                    molecule_uuid=molecule.uuid,
                    parameters=parameters,
                ),
            )
            started.append(definition.display_name)

        if not started:
            self._batch_status.setText("Those are already running.")
            return
        self._batch_status.setText(
            f"Running {len(started)} with default settings: {', '.join(started[:4])}"
            + ("..." if len(started) > 4 else "")
        )

    # --- copying out ---------------------------------------------------------

    def _on_context_menu(self, position) -> None:
        menu = QMenu(self)
        menu.addAction("Copy all properties").triggered.connect(self._on_copy_all)
        menu.exec(self.mapToGlobal(position))

    def _on_copy_all(self, _checked: bool = False) -> None:
        QGuiApplication.clipboard().setText(self.as_text())

    def as_text(self) -> str:
        """Everything currently on screen, as plain text.

        Walks the SECTIONS rather than the three label dictionaries, so the
        output carries the same headings and the same order the reader is
        looking at. Reading it out of the dicts would silently reorder it
        and drop the groupings, which is most of what makes it legible.
        """
        lines: list[str] = []
        for category in sorted(
            self._sections,
            key=lambda cat: (
                _CATEGORY_ORDER.index(cat) if cat in _CATEGORY_ORDER else len(_CATEGORY_ORDER),
                cat,
            ),
        ):
            section = self._sections[category]
            form = section.content_layout()
            rows: list[str] = []
            for row in range(form.rowCount()):
                label_item = form.itemAt(row, QFormLayout.ItemRole.LabelRole)
                field_item = form.itemAt(row, QFormLayout.ItemRole.FieldRole)
                if label_item is None or field_item is None:
                    continue
                name_widget = label_item.widget()
                value_widget = field_item.widget()
                if name_widget is None or value_widget is None:
                    continue
                value = _without_glyphs(value_widget.text()).replace("\n", "; ")
                rows.append(f"  {name_widget.text()}: {value}")
            if rows:
                lines.append(_CATEGORY_LABELS.get(category, category.title()))
                lines.extend(rows)
                lines.append("")
        return "\n".join(lines).rstrip()

    def _open_calculator(self, definition: CalculatorDefinition) -> None:
        # Says so, rather than returning silently. Clicking an "Open..."
        # button with nothing selected used to do NOTHING AT ALL -- no
        # dialog, no message, no log line -- which is indistinguishable
        # from a broken button and is the same complaint as "I can hit run
        # on several things and nothing noticeable happens".
        if self._project is None or self._selected_molecule_uuid is None:
            self._batch_status.setText("Select a molecule first.")
            return
        molecule = self._project.find_molecule(self._selected_molecule_uuid)
        if molecule is None:
            self._batch_status.setText("That molecule is no longer in the project.")
            return
        parameters: dict[str, object] = {}
        if definition.parameters:
            dialog = CalculatorSettingsDialog(definition, self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            parameters = dialog.parameters()
        self._pending_calculator_id = definition.calculator_id
        self._descriptor_service.run_calculator(
            molecule,
            CalculationRequest(calculator_id=definition.calculator_id, molecule_uuid=molecule.uuid, parameters=parameters),
        )

    def _reveal(self, calculator_id: str, section, row: QWidget | None) -> None:
        """Bring an explicitly-requested ROW result onto the screen.

        **THIS IS WHY THE ADMET CALCULATOR "PRODUCED NOTHING".** It
        produced everything: the sidecar ran, the model returned its
        endpoints and the row was rendered correctly -- about 900 px below
        the top of a panel whose viewport is 372 px, inside a section that
        is collapsed by default and sits near the bottom of twenty-odd
        others. Confirmed by driving the app and scrolling down to find
        `hERG blockade: 0.82` sitting there.

        Four of the six result shapes already answer a button press
        unmissably: a per-atom dataset, a spectrum, a structure set and a
        pH curve all open a dialog when they match
        `_pending_calculator_id`. The two that render INLINE -- an alert
        and a report -- had no such handling, so the louder the result the
        better it was hidden. That asymmetry, not the sidecar, is the bug.

        Deliberately NOT a dialog. A row-shaped result belongs in its row;
        popping a window for it would stack windows during a batch run and
        would answer a different question from the one the user asked.
        """
        if self._pending_calculator_id != calculator_id:
            return
        self._pending_calculator_id = None
        section.set_expanded(True)
        self._reveal_target = row
        # Deferred by one turn because the row was created or re-texted a
        # moment ago and its geometry is not settled: asked now,
        # `ensureWidgetVisible` scrolls to where the row used to be. A
        # BOUND METHOD, never a lambda capturing self -- PySide6 holds a
        # plain callable strongly (see tests/test_qt_object_disposal.py).
        QTimer.singleShot(0, self._reveal_pending_result)

    def _reveal_pending_result(self) -> None:
        """Put the row's TOP near the top of the viewport.

        **NOT `ensureWidgetVisible`, for two measured reasons.**

        It moves BOTH axes, and a row a little wider than the viewport
        makes it scroll right as well -- in the app that left every label
        clipped on its left edge ("bb_permeant", "unctional Groups"). A
        properties panel scrolled sideways is the failure this project
        already calls worse than the one being fixed. Setting the vertical
        bar alone cannot do that.

        And it scrolls the MINIMUM distance, measured against a height
        that is not settled yet: an `ExplicitHeightLabel` fixes its height
        from its width during the layout pass, so a moment after the row
        is added it is still short. The result was the caption arriving
        flush against the bottom edge with its values below the fold --
        the same invisibility this whole fix is about. Anchoring the row's
        TOP does not depend on its final height at all, so it is right
        whenever it runs.
        """
        row = self._reveal_target
        self._reveal_target = None
        if row is None:
            return
        container = self._scroll_area.widget()
        if container is None:
            return
        top = row.mapTo(container, QPoint(0, 0)).y()
        self._scroll_area.verticalScrollBar().setValue(max(0, top - _REVEAL_MARGIN))

    def _open_inspector(self, result: PerAtomDataset | SpectrumResult) -> None:
        if self._project is None:
            return
        molecule = self._project.find_molecule(result.molecule_uuid)
        if molecule is None:
            return
        best = canonical_conformer(molecule)
        conformer_molblock = best.molblock if best is not None else None
        # A spectrum goes to the dedicated NMR view (Phase 23c): grouped
        # signals, integrations and multiplicities have nowhere to live in
        # the generic inspector's one-colour-per-atom layout.
        if isinstance(result, SpectrumResult):
            dialog = NmrViewDialog(self._chemistry_engine, molecule, result, conformer_molblock, parent=self)
        else:
            dialog = CalculatorInspectorDialog(
                self._chemistry_engine,
                molecule,
                result,
                conformer_molblock,
                self,
                on_add_structure=self._on_add_structure,
            )
        dialog.exec()
