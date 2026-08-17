from __future__ import annotations

import logging
import os
from collections.abc import Callable
from typing import NamedTuple

from PySide6.QtCore import QPoint, QRect, QSize, Qt, QTimer
from PySide6.QtGui import QFontMetrics, QGuiApplication
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
    GEOMETRY,
    CalculationRequest,
    CalculatorDefinition,
    RegistryExecution,
    ServiceExecution,
)
from openchem.domain.common import CacheState
from openchem.domain.project import ProjectModel
from openchem.domain.scientific_result import PerAtomDataset, SpectrumResult
from openchem.ui.visualization import declared_total, label_decimals
from openchem.ui.widgets.help_tooltip import HelpTooltip, apply_help_tooltip
from openchem.chem.report_adapter import report_from_alert
from openchem.domain.report import ReportResult
from openchem.domain.structure_issue import Severity
from openchem.events.base import EventBus
from openchem.events.events import (
    AlertComputed,
    CalculationFinished,
    DescriptorComputed,
    ReportComputed,
    MoleculeChanged,
    MoleculeSelected,
    PerAtomDataComputed,
    PhCurveComputed,
    SpectrumComputed,
    StructureSetComputed,
    TrajectoryComputed,
)
from openchem.services.calculator_registry import CalculatorRegistry
from openchem.services.descriptor_service import DescriptorService
from openchem.ui.dialogs.calculator_inspector_dialog import CalculatorInspectorDialog
from openchem.ui.dialogs.spatial_result_dialog import SpatialResultDialog
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
    "lipophilicity",
    "structures",
    "quantum",
    "electronic",
    "topology",
    "geometry",
    "surface",
    "substructure",
    "stereochemistry",
    "medicinal_chemistry",
    # Before pKa rather than after, because the pH-solubility curve is read
    # THROUGH pKa and somebody arriving at "how soluble is this" should meet
    # the answer before the machinery behind it.
    "solubility",
    "pka",
    # Directly after pKa on purpose. Somebody reading "how basic is this"
    # is standing exactly where the Bronsted answer stops being the whole
    # answer, and carbon monoxide is the case that proves it.
    "lewis",
    "admet",
    "shape",
]
#: **26 SECTIONS HELD 49 BUTTONS, AND ELEVEN OF THEM HELD EXACTLY ONE.**
#: Finding a calculator meant scrolling twenty-six headings, most
#: concealing a single item -- counted in `docs/NAVIGATION_AUDIT.md`, and
#: the strongest single number behind "this is extremely difficult
#: software to use".
#:
#: The merge is a taxonomy decision, so each one is justified where it is
#: not obvious:
#:
#: - `structure` (Substance & Bonding) joined `identity`. Both answer
#:   "what IS this", and the old pair rendered as "Structure" beside
#:   "Structure Generators" -- two headings a page apart, one of which
#:   was `category.title()` rather than a name anybody chose.
#: - `logp` + `logd` became `lipophilicity`. `logd` was NOT a singleton
#:   and is merged anyway, because logP contributions in one section and
#:   logD in another is the split that made no sense to begin with.
#: - `molar_refractivity` went to `electronic`, NOT to lipophilicity with
#:   the rest of the Crippen family. Molar refractivity is molar
#:   POLARIZABILITY by Lorentz-Lorenz, so it belongs beside the two
#:   polarizability calculators; filing it under lipophilicity would have
#:   put a heading on the section that was not true of its contents.
#:
#: **A HEADING MAY NOT CONTAIN `&`, AND MUST BE SHORT.** The section
#: header is a `QToolButton`, which eats `&` as a mnemonic -- "Lipophilicity
#: & Refractivity" rendered as "Lipophilicity  Refractivity", with the
#: ampersand simply gone -- and elides when too long, which turned
#: "Identity & Composition" into "Identity ...mposition". Both were caught
#: by looking at the running app after a merge that every test passed.
#: - `alignment`, `dynamics` and `interactions` joined `geometry`: a
#:   superposition, a trajectory and a contact map are all things you can
#:   only ask of a 3D structure.
#: - `stereocenters` moved OUT of `geometry` to sit with
#:   `stereo_descriptors`. A CIP label and the centre it labels belong
#:   together, and this is the one move that gives a singleton a partner
#:   rather than absorbing it.
#: - `regulatory` joined `admet`. Costs nothing in the fact view: those
#:   Facts carry `FactCategory.REGULATORY` themselves, so only the
#:   section changed.
#:
#: `nmr` IS STILL A SINGLETON AND DELIBERATELY SO. `nmr_database` has no
#: registry sibling -- the ORCA NMR jobs are ServiceExecution and live in
#: their own panel -- and filing a spectroscopic measurement under a
#: structural heading to flatten a count would be worse than the count.
#: `test_no_category_holds_a_single_calculator` asserts the exception BY
#: NAME, so a second one cannot arrive quietly.
_CATEGORY_LABELS = {
    "physicochemical": "Physicochemical",
    "identity": "Identity",
    "naming": "Naming",
    "charge": "Charge",
    "lipophilicity": "Lipophilicity",
    "structures": "Structure Generators",
    "quantum": "Quantum (Huckel)",
    "electronic": "Electronic Properties",
    "topology": "Topology",
    "geometry": "Geometry (3D)",
    "surface": "Surface Area",
    "substructure": "Substructure Search",
    "stereochemistry": "Stereochemistry",
    "medicinal_chemistry": "Medicinal Chemistry",
    "solubility": "Solubility",
    "pka": "pKa",
    "lewis": "Lewis Acid/Base",
    "admet": "ADMET / Regulatory",
    "shape": "Shape",
    # Without these the panel falls back to `category.title()`, which
    # rendered the NMR section as "Nmr". Found during a documentation
    # sweep: the guide had to describe a heading that was a formatting
    # accident rather than a name anybody chose.
    "nmr": "NMR",
    # These two hold no buttons at all -- both are ServiceExecution, run
    # from their own panels, and the section exists only to carry the
    # hint that says so. They were relying on `category.title()` giving
    # the right answer by luck, which is the same accident as "Nmr" with
    # a happier outcome.
    "docking": "Docking",
    "quantum_chemistry": "Quantum Chemistry",
}
def _category_label(category: str) -> str:
    """What a section is called, in the ONE place that decides.

    **THERE WERE TWO OF THESE AND THEY DISAGREED.** The heading fell back
    to `category.replace("_", " ").title()` and the "Copy all" text fell
    back to `category.title()`, so an unlabelled `medicinal_chemistry`
    would show as "Medicinal Chemistry" on screen and copy as
    "Medicinal_Chemistry" -- two names for one section, in one panel.

    Latent rather than shipped: measured across all four sources that can
    reach `_section_for` (the registry, both descriptor spec tables, a
    calculator's result, and a provider's alerts), every category in the
    app today HAS a chosen label, so neither fallback runs. It is unified
    because a divergence that only appears for the next category added is
    the kind this document is about.

    The fallback stays for plugins, which may register a category nobody
    here has named. It reads `my_tools` as "My Tools", which is right;
    what it cannot do is acronyms, and `nmr` becoming "Nmr" is exactly
    how this finding was noticed.
    """
    return _CATEGORY_LABELS.get(category) or category.replace("_", " ").title() or "Other"


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


#: The attribute each result type carries its payload in -> the noun for a
#: count of it. ORDERED, because a subclass can carry more than one: an
#: `NMRSpectrumResult` has `values`, `ranges` AND `couplings`, and `values`
#: is the one its view renders, so the first match is the right one.
#:
#: **THE PREVIOUS VERSION PROBED FOR NAMES NO RESULT TYPE HAS EVER HAD.**
#: It asked for `structures` and `points`; `StructureSetResult` calls it
#: `entries` and `PhCurveResult` calls it `ph_values`. Both probes missed
#: on every result, so nine calculators rendered as the bare word "Ready"
#: -- the calculator ran, the payload was there, and the panel said
#: nothing about it. Measured on aspirin: 11 of 26 dialog-detail
#: calculators, `major_microspecies` and `tautomers` among them.
#:
#: Same failure as the `inapplicable_calculators` blocklist: a name
#: written once, against a shape nobody re-checked. `test_summarise.py`
#: derives this table's correctness FROM the dataclasses, so a renamed
#: field fails there instead of silently reverting to "Ready".
#: The noun is SINGULAR and pluralised at the point of use -- "1
#: structures" is the kind of blemish that makes a panel read as
#: unfinished, and every one of these counts can legitimately be 1
#: (a molecule with one tautomer, a single-frame trajectory).
_PAYLOAD_FIELDS: tuple[tuple[str, str], ...] = (
    ("values", "atom"),
    ("entries", "structure"),
    ("ph_values", "pH point"),
    ("frames", "frame"),
)


def _counted(count: int, noun: str) -> str:
    """`3 structures`, `1 structure`. Every noun in `_PAYLOAD_FIELDS`
    pluralises regularly, so there is nothing to look up."""
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def _summarise(result: object) -> str:
    """A one-line "what arrived" for a result whose detail lives in a
    dialog. Enough to show the run happened and produced something, with
    the shape of it, so "nothing noticeable happens" cannot recur.

    **An EMPTY payload says so rather than falling through to "Ready".**
    `stereocenters` on a molecule with none is a real answer, and "Ready"
    is indistinguishable from the panel having failed to render one. The
    row is captioned with the result's own name, so "None found." reads
    as "Stereocenters: None found."

    **A DECLARED TOTAL LEADS** -- it is the number the row was opened for.
    This read "21 atoms, -1.019 to 0.5437" for a LogP contribution: true,
    and not what anybody wanted to know, with the molecule's own LogP
    nowhere on the row. It now reads
    "LogP (Crippen) 3.62 - 21 atoms, -1.02 to 0.54", which is the same
    number the dialog behind it shows, at the same precision.

    **THE RANGE STAYS, AND THAT DEPENDED ON A FIX THAT LANDED SEPARATELY.**
    A first version dropped it, because carrying both overflowed a section
    that was starved -- 145 px against a 192 px minimum, so the row was
    handed 34 px whatever it asked for. That starvation was a
    height-for-width flag re-armed by a style change
    (`ExplicitHeightLabel.changeEvent`), fixed on master while this was in
    flight. Re-measured on the merge with `{"do": "dump"}`:

        total + count            row 47/47   section 192/192   ok
        total + count + range    row 63/63   section 208/208   ok

    Both now get what they ask for, so the constraint that removed the
    range no longer exists and the row carries everything it used to plus
    the total. A result that declares no total keeps the old wording
    exactly.
    """
    total = declared_total(result)
    places = label_decimals(result)
    for attribute, noun in _PAYLOAD_FIELDS:
        payload = getattr(result, attribute, None)
        if payload is None:
            continue
        if not payload:
            return "None found."
        if isinstance(payload, dict):
            numbers = [v for v in payload.values() if isinstance(v, (int, float))]
            if numbers:
                units = getattr(result, "units", "")
                units_suffix = f" {units}" if units else ""
                span = (
                    f"{min(numbers):.{places}f} to {max(numbers):.{places}f}{units_suffix}"
                )
                if total is None:
                    return f"{_counted(len(payload), noun)}, {span}"
                total_units = f" {total['units']}" if total["units"] else ""
                return (
                    f"{total['label']} {total['value']:.{places}f}{total_units}"
                    f" - {_counted(len(payload), noun)}, {span}"
                )
        return _counted(len(payload), noun)
    return "Ready"


#: Qt property carrying which calculator a section button opens.
_CALCULATOR_ID_PROPERTY = "openchem_calculator_id"


#: One concept rendered once per registered calculator, so ONE contract.
#:
#: This is the case the "a help_id names a DEFINITION, not an instance"
#: rule exists for. Sixty tick boxes all mean "include this calculator when
#: I press Run selected"; giving them sixty ids would read as precision and
#: be noise, and `DocumentableControl.instance_path` already tells the
#: renderings apart.
_BATCH_SELECTION_HELP = HelpTooltip(
    text=(
        "Include this calculator when you press 'Run selected'.\n\n"
        "Ticking several runs them together — they are dispatched to a thread "
        "pool rather than queued, so the total is roughly the slowest rather "
        "than the sum. Ticking nothing and pressing a calculator's own button "
        "runs just that one."
    ),
    tier=1,
    help_id="properties.batch_selection",
    topic="properties",
    help_anchor="properties",
)


def calculator_help(definition: CalculatorDefinition) -> HelpTooltip:
    """A contract for one calculator's button, DERIVED from its registration.

    Generated rather than hand-written, and the difference is not effort:
    `CalculatorDefinition.description` is already the authoritative
    statement of what a calculator does, so writing sixty tooltips beside
    it would be sixty chances to disagree with the registry. This cannot
    drift -- it IS the registry, rendered.

    Each calculator is its own concept, so each gets its own `help_id`.
    That is the opposite call from the tick boxes above, and for the
    opposite reason: those sixty controls mean one thing, these sixty mean
    sixty things.

    **The input representation is the part worth saying out loud.** Eight
    registered calculators return a DIFFERENT NUMBER for the same molecule
    depending on whether they are handed the drawing or a conformer, purely
    because a conformer carries explicit hydrogens -- so which one this
    calculator gets is a fact about its answer, not an implementation
    detail. See `CALCULATION_INPUTS`.
    """
    if definition.calculation_input == GEOMETRY:
        basis = (
            "Runs on a real 3D conformer when one exists, falling back to the "
            "structure as drawn. Its answer can differ between the two."
        )
    else:
        basis = (
            "Runs on the structure as drawn, not on a 3D conformer — so explicit "
            "hydrogens in a conformer cannot change its answer."
        )
    return HelpTooltip(
        text=f"{definition.description.strip()}\n\n{basis}",
        # Tier 2: it is a scientific parameter of the session rather than a
        # plain action, and the basis sentence is the applicable qualifier.
        tier=2,
        help_id=f"calculator.{definition.calculator_id}",
        topic=definition.category,
        help_anchor="properties",
    )
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

#: An elided calculator button never shrinks below this, so it stays a
#: button rather than a sliver at any panel width.
_ELIDED_BUTTON_MIN_WIDTH = 80

#: How narrow a row caption may be squeezed before the panel would rather
#: overflow. It is a FLOOR, not a width: `_ElidingCaptionLabel` caps only
#: its `minimumSizeHint`, so a wide panel still shows the full text.
#:
#: **DERIVED FROM THE PANEL'S OWN MINIMUM, not chosen for looks.** At the
#: 280 px `_PANEL_MIN_WIDTH` the scroll viewport is 256 and the section
#: spends 18 on content margins, so the form has 238 to live in; its
#: field column and spacing take 44 of that, leaving 194 as the widest a
#: caption column may be before the content is wider than the viewport
#: and every row is clipped at the right edge. 120 sits well inside that
#: with room for the field column to grow, and still shows about
#: eighteen characters -- enough to tell one row from another, with the
#: full string in the tooltip and recoverable from "Copy all".
_ELIDED_CAPTION_MIN_WIDTH = 120

#: How many pixels of reported overflow are measurement noise rather than
#: a clip.
#:
#: **MEASURED, and it is the `intra` term that needs it.**
#: `QFontMetrics.boundingRect` over-reports a single line by one pixel
#: against what `QLabel` actually paints, so two `'✓ Pass'` value
#: labels report `intra 1` while rendering complete -- confirmed by
#: magnifying the running app. The geometry terms were exact in the same
#: run: every widget came in at `right -2` or better once the content fit
#: the viewport.
#:
#: 2 is that 1 px with a pixel of headroom, and it is far below the thing
#: being guarded against: the reported symptom was a whole character, and
#: the measured defect was 14 px.
_OVERFLOW_TOLERANCE = 2

#: The longest a calculator's display name may be before its button
#: elides at the panel's minimum width.
#:
#: **MEASURED, in the running app, not chosen.** The button is 208 px at
#: the 280 px panel minimum, leaving 192 px for text. With the old
#: `Open {name}...` wrapper -- 46 px of every button -- SEVEN names
#: elided; without it, one. The survivor was "NMR Shifts (experimental
#: database)" at 197 px against 192.
#:
#: A CHARACTER COUNT IS A PROXY FOR A PIXEL WIDTH and an imperfect one,
#: because the font is proportional: "Accessible Surface Area (per atom)"
#: and the old NMR name are both 34 characters and differ by 5 px. A
#: pixel assertion is deliberately NOT used -- CI is Linux with different
#: fonts, and a guard that fails there for a reason nobody can reproduce
#: locally gets deleted rather than fixed.
#:
#: 34 is the widest name measured to fit, and it fits by NOTHING:
#: "Accessible Surface Area (per atom)..." needs exactly the 192 px
#: available. It is kept at that length rather than mangled, because it
#: is the standard term for the quantity and eliding is graceful -- the
#: full name stays in the tooltip. The guard's job is to stop the NEXT
#: name being longer than anything that has been shown to fit.
_MAX_CALCULATOR_NAME = 34

#: Room the button's own frame and padding take off its width before
#: there is anywhere to put text.
_ELIDED_BUTTON_PADDING = 16

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


def _dump_width_budget(panel: QWidget) -> None:
    """Name whatever makes the panel's content wider than its viewport.

    A scroll area sizes its content to `max(viewport, minimum)`, so ONE
    widget with a large minimum width pushes every row past the right
    edge and the text is clipped there -- measured at content 287 against
    a 256 viewport. Heights were the whole story for the report row, so
    the height dump was built first; this is the same question sideways.
    """
    from PySide6.QtWidgets import QFormLayout, QScrollArea

    scroll = panel.findChild(QScrollArea)
    viewport = scroll.viewport().width() if scroll is not None else 0
    logger.warning("width budget (viewport %d px) -- anything wider is overflow:", viewport)
    for category, section in getattr(panel, "_sections", {}).items():
        if section.isHidden() or not section.is_expanded():
            continue
        form = section.content_layout()
        logger.warning(
            "  %-22s section min %-5d content min %-5d form min %-5d",
            category[:22],
            section.minimumSizeHint().width(),
            section.content.minimumSizeHint().width(),
            form.minimumSize().width(),
        )
        for row in range(form.rowCount()):
            item = form.itemAt(row, QFormLayout.ItemRole.SpanningRole) or form.itemAt(
                row, QFormLayout.ItemRole.FieldRole
            )
            widget = item.widget() if item is not None else None
            if widget is None or widget.isHidden():
                continue
            for child in [widget, *widget.findChildren(QLabel)]:
                wanted = child.minimumSizeHint().width()
                if wanted > viewport:
                    logger.warning(
                        "      OVERFLOW %-14s min %-5d  %r",
                        type(child).__name__[:14],
                        wanted,
                        (child.text()[:48] if hasattr(child, "text") else ""),
                    )
        # WHICH DESCENDANT SETS THE SECTION'S MINIMUM. The per-row loop
        # above asks whether any single widget beats the VIEWPORT, and it
        # reported nothing while the section's minimum was 272 against a
        # 256 viewport -- because the demand is 254 from a row plus the
        # section's own 18 px of content margins, and no individual
        # widget crosses the line on its own. Ranking is what names the
        # contributor; a threshold cannot, because the threshold is the
        # thing in question.
        ranked = sorted(
            (
                (child.minimumSizeHint().width(), child)
                for child in section.content.findChildren(QWidget)
                if child.isVisibleTo(section.content)
            ),
            key=lambda pair: pair[0],
            reverse=True,
        )
        for wanted, child in ranked[:5]:
            logger.warning(
                "      sets-min %-5d %-20s wrap=%-5s %r",
                wanted,
                type(child).__name__[:20],
                (child.wordWrap() if isinstance(child, QLabel) else "-"),
                (_painted_text(child)[:44]),
            )


class RenderedOverflow(NamedTuple):
    """One widget whose painted text leaves the scroll viewport.

    `left`/`right` are pixels PAST each viewport edge, so a fitting
    widget is `(<=0, <=0)`. `intra` is separate and is the width the
    text needs at the width the widget was GIVEN, minus that width --
    non-zero means the clip happens INSIDE the widget, which no amount
    of moving it would fix.
    """

    widget: QWidget
    text: str
    left: int
    right: int
    intra: int
    path: str

    def describe(self, viewport_width: int) -> str:
        return (
            f"{type(self.widget).__name__} {self.text[:44]!r} "
            f"overflowed left {self.left} px / right {self.right} px "
            f"/ intra {self.intra} px | viewport width {viewport_width} "
            f"| path: {self.path}"
        )


def _painted_text(widget: QWidget) -> str:
    """The text a widget actually draws, or `""` for a pure container.

    **Containers are deliberately excluded from the overflow walk.** A
    holder wider than the viewport with every child inside it clips
    nothing, and reporting it would bury the one widget that does --
    which is the false-positive this walk exists to avoid. A container's
    demand is the OTHER question and shows up in `_dump_width_budget`.
    """
    getter = getattr(widget, "text", None)
    if not callable(getter):
        return ""
    try:
        return str(getter() or "")
    except (TypeError, RuntimeError):
        # A Qt method needing arguments, or a freed C++ object.
        return ""


def _ancestry_path(widget: QWidget, top: QWidget) -> str:
    """`A > B > C`, so a failure names WHERE the offender sits.

    A bare "QLabel overflowed by 17 px" is not actionable in a panel
    holding a hundred labels; the chain is what points at the row.
    """
    names: list[str] = []
    node: QWidget | None = widget
    while node is not None and node is not top:
        names.append(type(node).__name__)
        node = node.parentWidget()
    names.append(type(top).__name__)
    return " > ".join(reversed(names))


def rendered_overflow(
    panel: QWidget, tolerance: int = _OVERFLOW_TOLERANCE
) -> list[RenderedOverflow]:
    """Every descendant whose PAINTED text leaves the scroll viewport.

    **THIS IS THE ORACLE, AND `_dump_width_budget` IS NOT.** That one
    asks which widget's `minimumSizeHint().width()` exceeds the viewport
    -- minimum-width PRESSURE, which explains why a layout was forced
    wide. A widget can have a perfectly reasonable minimum hint and
    still be LAID OUT past the edge, and it is the laid-out geometry a
    reader loses characters to. The two are kept separate because they
    answer different questions and only this one is the symptom.

    **`horizontalScrollBar().maximum() == 0` IS NOT THE ORACLE EITHER.**
    That assertion has been in the suite since the wide-row work and
    passes while the running app clips, which is what made this
    function necessary.

    **BOTH EDGES.** Left-edge clipping is not hypothetical in this
    panel: `_reveal_row` records `"bb_permeant"` and `"unctional
    Groups"` from a run that had scrolled right.

    Returns findings rather than logging them, so the live dump and the
    headless guard share ONE implementation. Computing overflow twice is
    how a dump and a test come to disagree about the same panel.
    """
    areas = panel.findChildren(QScrollArea)
    if len(areas) != 1:
        # The walk assumes ONE boundary owner. More than one means a
        # nested scrollable arrived, and a child legitimately wider than
        # its own scrollable parent is not overflow -- so the assumption
        # has to fail loudly rather than quietly mis-measure.
        raise AssertionError(
            f"expected exactly one QScrollArea in the panel, found {len(areas)} -- "
            "a nested scrollable invalidates this measurement"
        )
    viewport = areas[0].viewport()
    bounds = viewport.rect()

    findings: list[RenderedOverflow] = []
    for child in viewport.findChildren(QWidget):
        # **`isVisibleTo`, NOT `isHidden` AND NOT `isVisible`.** A widget
        # inside a COLLAPSED section has `isHidden() == False` -- the flag
        # is on the section's content, not on the child -- and it has
        # never been laid out, so it still carries a default geometry that
        # reads as a huge overflow. Measured before this filter existed:
        # 56 findings at "right 384 px", every one of them a label in a
        # collapsed section, against a real overflow of 14. `isVisible()`
        # is the opposite mistake and this file already records it: it is
        # False for every child of a window nobody showed, so under a test
        # harness it answers "none of them".
        if not child.isVisibleTo(viewport):
            continue
        text = _painted_text(child)
        if not text:
            continue
        mapped = QRect(child.mapTo(viewport, QPoint(0, 0)), child.size())
        left = bounds.left() - mapped.left()
        right = mapped.right() - bounds.right()

        # What the text NEEDS at the width it was given. A single
        # unbreakable token longer than the widget clips inside it, and
        # no amount of repositioning the widget would show it.
        #
        # **LABELS ONLY.** A `QPushButton`'s `contentsRect` is not its text
        # rectangle -- the style adds its own padding -- so the comparison
        # is meaningless there, and `_ElidingPushButton` elides on purpose
        # anyway. Measured: the 80 px "Details..." button reports `intra 40`
        # under the test platform's wider font while rendering correctly for
        # a user, which is a false positive that would make this probe
        # untrustworthy exactly where it needs to be believed. The geometry
        # terms above still cover buttons.
        inner = child.contentsRect().width() if isinstance(child, QLabel) else 0
        intra = 0
        if inner > 0:
            flags = Qt.TextFlag.TextWordWrap if getattr(child, "wordWrap", None) and child.wordWrap() else Qt.TextFlag.TextSingleLine
            needed = QFontMetrics(child.font()).boundingRect(
                QRect(0, 0, inner, 0), int(flags), text
            ).width()
            intra = needed - inner

        if left > tolerance or right > tolerance or intra > tolerance:
            findings.append(
                RenderedOverflow(child, text, left, right, intra, _ancestry_path(child, viewport))
            )
    return findings


def _dump_rendered_overflow(panel: QWidget) -> None:
    """Log `rendered_overflow`, plus the viewport width it judged against.

    The viewport width is logged on its own line even when nothing
    overflows, because "content adapts to the viewport" and "the
    viewport shrank to fit the content" look identical in a findings
    list and are opposite outcomes.
    """
    areas = panel.findChildren(QScrollArea)
    width = areas[0].viewport().width() if len(areas) == 1 else -1
    try:
        findings = rendered_overflow(panel)
    except AssertionError as exc:
        logger.warning("rendered overflow: NOT MEASURABLE -- %s", exc)
        return
    logger.warning(
        "rendered overflow (viewport %d px): %d finding(s)", width, len(findings)
    )
    for finding in findings:
        logger.warning("    %s", finding.describe(width))


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
            name = _caption_text(label) or category
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


def _mnemonic_safe(text: str) -> str:
    """Escape `&` so a QAbstractButton shows it instead of eating it.

    **"Substance & Bonding" rendered as "Substance  Bonding"** -- the
    ampersand simply gone, with the gap left behind, and `B` quietly
    underlined as an accelerator nobody asked for. Qt reads `&` in any
    button or menu label as a mnemonic marker, and `&&` is its escape.

    Seen in the running app, on the one calculator of 49 whose name
    contains an ampersand. The section headings hit the identical bug and
    were reworded instead, because those are our own words and shorter is
    better there anyway; a calculator name is chemistry vocabulary, so it
    gets escaped rather than bent to suit a Qt convention.
    """
    return text.replace("&", "&&")


class _ElidingPushButton(QPushButton):
    """An "Open [Calculator]..." button that may be narrower than its label.

    **A `QPushButton` REFUSES TO BE NARROWER THAN ITS TEXT**, and one of
    these is the widest thing in the Properties panel. Measured in the
    running app with the ADMET section open, the panel at its 280 px
    minimum:

        viewport                    256 px
        scroll content              287 px   <- 31 px of overflow
        admet section minimum       287
          its form's minimum        184      <- the rows were never the problem
        "Open ADMET (hERG, CYP, Ames, ADME)..."  269

    A scroll area sizes its content to `max(viewport, minimum)`, so that
    one button pushed every row 31 px past the right edge and the text was
    clipped there -- `(93rd percentile amo` where a wrap was expected. It
    looks like a wrapping bug in the value and is nothing of the kind.

    Eliding rather than wrapping the button, because a two-line button in
    a list of one-line buttons reads as a different kind of control; the
    full name stays in the tooltip, and the section header already says
    which category it belongs to.
    """

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(_mnemonic_safe(text), parent)
        self._full_text = text
        #: The last text handed to `setText`, UNESCAPED. Compared against
        #: rather than `self.text()`, which comes back escaped and would
        #: never equal the elided string -- turning the guard below into a
        #: relayout every pass.
        self._shown_text = text
        self.setToolTip(text)
        # `Ignored` horizontally is what drops the minimum to zero, which
        # is the whole point: `Preferred` keeps the text's width as a
        # floor however the text is painted.
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.setMinimumWidth(_ELIDED_BUTTON_MIN_WIDTH)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt's own casing
        super().resizeEvent(event)
        metrics = QFontMetrics(self.font())
        available = max(0, self.width() - _ELIDED_BUTTON_PADDING)
        elided = metrics.elidedText(self._full_text, Qt.TextElideMode.ElideRight, available)
        # Guarded: `setText` re-lays-out the button, and assigning the same
        # string every pass is a loop with no exit condition. Compared
        # against `_shown_text`, not `self.text()` -- see there.
        if elided != self._shown_text:
            self._shown_text = elided
            super().setText(_mnemonic_safe(elided))


class _ElidingCaptionLabel(QLabel):
    """A row caption that may be narrower than its text.

    **THE SAME BUG AS `_ElidingPushButton`, ONE WIDGET ALONG.** That class
    fixed the case where the widest thing in the panel was a button; with
    buttons capped, the next-widest thing became a form row's CAPTION, and
    the panel went on overflowing by a smaller amount. Measured in the
    running app, ADMET expanded, panel at its 280 px minimum:

        scroll viewport                                256 px
        scroll content                                 272      <- 16 over
        admet section minimum                          272
          its form's minimum                           254
            widest caption, "Blood-Brain Barrier
            Permeant (heuristic)", wrap off            210

    A `QLabel` with word wrap OFF reports its full text width as its
    minimum, and `QFormLayout` sizes the label column to the widest of
    them -- so one long descriptor name set the column, the column set the
    form, and `setWidgetResizable` sized the content to
    `max(viewport, minimum)`. Every widget in the panel was then laid out
    with its right edge 14 px past the viewport and clipped there, which
    is why the symptom was "every visual line loses its last character"
    rather than one bad row.

    **ELIDING, NOT WRAPPING.** A wrapped caption is height-for-width, and
    one height-for-width widget anywhere in a section puts back the
    truncation that `ExplicitHeightLabel`, `DontWrapRows` and
    `_add_wide_row` exist to prevent -- `_add_wide_row`'s own docstring
    says so. This label never wraps, so it never offers one.

    **IT CAPS `minimumSizeHint`, AND `Ignored` IS THE WRONG TOOL HERE.**
    The obvious move is `_ElidingPushButton`'s -- `QSizePolicy.Ignored`
    horizontally, which drops the minimum to nothing. That works for a
    button sitting alone in a vertical layout and it CORRUPTS A FORM: an
    ignored label no longer sizes the label column, so `QFormLayout` laid
    the caption and its value on top of each other, and the panel read
    `Aqu36ous Solubility (...` -- "Aqueous Solubility" and "-3.68"
    painted in the same rectangle. Seen only by magnifying a screenshot;
    all 98 panel tests passed with the two overlapping.

    Capping `minimumSizeHint` instead keeps the ordinary `sizeHint`, so a
    wide panel still sizes the column to the full caption and elides
    nothing. Only the FLOOR moves, which is the single quantity that was
    wrong.

    `full_text` is the unelided string, and everything that EXPORTS a
    caption reads it -- see `_caption_text`. Copying the panel must not
    hand somebody "Blood-Brain Barrier Permeant (heur...".
    """

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.full_text = ""
        self.setWordWrap(False)
        self.setText(text)

    def _width_for_full_text(self) -> int:
        """How wide the UNELIDED caption would be, margins included.

        **BOTH HINTS DERIVE FROM `full_text`, AND THAT IS A LATCH FIX
        RATHER THAN TIDINESS.** Qt's own hints measure the text currently
        SET on the label, which is the elided string -- so once the label
        had been squeezed to `...` its hints reported the width of `...`,
        the layout duly gave it that, and it could never grow back. Seen
        in the running app: three ADMET captions rendered as a bare `...`
        beside their values, and no width the panel was given recovered
        them. `full_text` does not change when the painted string does,
        which is what breaks the loop.
        """
        margins = self.contentsMargins()
        return (
            QFontMetrics(self.font()).horizontalAdvance(self.full_text)
            + margins.left()
            + margins.right()
        )

    def _ceiling(self) -> int:
        """The widest this caption may ASK to be.

        **`QFormLayout` COLLAPSES A LABEL WHOSE `sizeHint` DOES NOT FIT,
        rather than clamping it at `minimumSizeHint`.** Measured on a bare
        form 290 px wide holding one row, label sizeHint 660,
        minimumSizeHint 120:

            label geometry   QRect(16, 2, 0, 14)      <- zero width
            field                          262 px

        So the caption vanished entirely, and because a zero-width label
        elides against no space at all it fell back to its full string and
        the hint stayed 660 -- a state it could never leave. Neither of the
        two obvious repairs works: `QSizePolicy.Ignored` and an explicit
        `setMinimumWidth` both stop the label sizing the column at all, and
        the field is then laid out UNDERNEATH it (measured, label at x=11
        w=120 against a field at x=17).

        Capping the hint at a constant fixes the collapse and costs the
        opposite defect -- a caption frozen at 120 px on a 900 px panel with
        nothing but empty space beside it. Deriving the cap from the room
        actually available keeps both ends right; measured on the same
        bare form, no overlap at any width and the caption growing with it:

            host 250   label 130     host 400   label 280
            host 290   label 170     host 900   label 660 (full text)

        `- _ELIDED_CAPTION_MIN_WIDTH` is the field's share: whatever the
        caption leaves, the value still needs somewhere to be.
        """
        parent = self.parentWidget()
        room = parent.width() if parent is not None else 0
        return max(_ELIDED_CAPTION_MIN_WIDTH, room - _ELIDED_CAPTION_MIN_WIDTH)

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt's own casing
        return QSize(
            min(self._width_for_full_text(), self._ceiling()), super().sizeHint().height()
        )

    def minimumSizeHint(self) -> QSize:  # noqa: N802 - Qt's own casing
        """The full caption's width, capped.

        The `min` matters: a short caption like "LogP" must not claim the
        cap as a floor, or every narrow row in the panel would reserve
        space it has no use for.
        """
        return QSize(
            min(self._width_for_full_text(), _ELIDED_CAPTION_MIN_WIDTH),
            super().minimumSizeHint().height(),
        )

    def setText(self, text: str) -> None:  # noqa: N802 - Qt's own casing
        """Record the full string, then show as much of it as fits.

        The caption is REWRITTEN after creation -- a descriptor row is
        built from a placeholder carrying only the internal id and
        recaptioned when the real name arrives -- so storing the full text
        at construction alone would keep the id forever.
        """
        self.full_text = text
        self.setToolTip(text)
        self._show_as_much_as_fits()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt's own casing
        super().resizeEvent(event)
        self._show_as_much_as_fits()

    def _show_as_much_as_fits(self) -> None:
        available = self.contentsRect().width()
        if available <= 0:
            # Before the first layout pass there is no width to elide
            # against. Show the full string; the resize that follows
            # narrows it if it has to.
            elided = self.full_text
        else:
            elided = QFontMetrics(self.font()).elidedText(
                self.full_text, Qt.TextElideMode.ElideRight, available
            )
        # Guarded: `setText` re-lays-out the label, so assigning the same
        # string on every resize is a loop with no exit condition. This is
        # the guard `_ElidingPushButton` documents, for the same reason.
        if elided != super().text():
            super().setText(elided)


def _caption_text(widget: QWidget | None) -> str:
    """A caption's FULL text, for anything that exports or searches it.

    An elided caption's `text()` is what is painted, which is the right
    answer for the screen and the wrong one for the clipboard. "Copy all"
    handing somebody `Blood-Brain Barrier Permeant (heur...` would be the
    presentation layer corrupting the data on its way out -- the same
    class of mistake as the glyphs, which `_without_glyphs` already
    strips at every exit for the same reason.
    """
    if widget is None:
        return ""
    full = getattr(widget, "full_text", None)
    if isinstance(full, str) and full:
        return full
    getter = getattr(widget, "text", None)
    return str(getter() or "") if callable(getter) else ""


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
    # ELIDING, and still with wrapping off. The docstring above is right
    # that a wrapped caption would be height-for-width and would put the
    # truncation back; what it did not cover is that a NON-wrapping label
    # reports its full text width as its minimum, so a long caption made
    # the content wider than the viewport and every row was clipped at the
    # right edge instead. `_ElidingCaptionLabel` is neither -- no wrap, and
    # no width demand. See its docstring for the measurement.
    caption = _ElidingCaptionLabel(name, holder)
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
        #: The caption currently ON each row. Held as plain data rather than
        #: read back off the widget, for the reason the comment above gives
        #: about QWidget keys -- and because a row's caption legitimately
        #: changes when the RUNNING placeholder's raw id is replaced by the
        #: real display name, which is a comparison this needs to make on
        #: every event without touching Qt.
        self._row_labels: dict[tuple[str, str], str] = {}

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
        #: calculator_id -> the "Running..." label on that calculator's own
        #: row. Built with the row and hidden, rather than inserted and
        #: removed around each run: this panel's layout is delicate enough
        #: that adding and deleting form rows mid-life is a worse risk than
        #: one permanently-parked label, and a hidden widget costs no space.
        self._calculator_status: dict[str, QLabel] = {}
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
        event_bus.subscribe(TrajectoryComputed, self._on_trajectory_computed)
        event_bus.subscribe(CalculationFinished, self._on_calculation_finished)

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
        # The indicators go with them. The rows themselves SURVIVE a
        # molecule change (they are the calculator buttons, not results),
        # so a "Running..." left visible here would sit beside a different
        # molecule's name claiming work that is no longer happening.
        for status in self._calculator_status.values():
            status.setVisible(False)
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
        title = _category_label(category)
        section = _CollapsibleSection(title, expanded, self._sections_container)
        self._sections[category] = section
        for definition in self._calculator_registry.by_category(category):
            if not isinstance(definition.execution, RegistryExecution):
                # ServiceExecution-backed (Docking, QuantumChemistry) --
                # registered for discovery only, run from their own panel.
                continue
            # NO "Open " PREFIX. The label used to be `Open {name}...`,
            # which spent about 32 px of a 192 px button on the same five
            # characters forty-nine times over -- measured in the running
            # app, and enough on its own to elide SEVEN names where one
            # elides now. "Open" says nothing a button under a section
            # heading does not already say, and the tooltip still spells
            # the action out in full.
            #
            # THE TRAILING ELLIPSIS STAYS ON ALL OF THEM, and that is a
            # measurement rather than an oversight. It promises a further
            # dialog, `_open_calculator` shows one `if
            # definition.parameters`, and the obvious next thought is that
            # the parameterless ones are lying. They are not: all 49
            # registry calculators declare parameters, most of them a
            # decimal-places setting, so every one of these buttons really
            # does open a dialog. Making it conditional would have added a
            # branch that never runs.
            button = _ElidingPushButton(f"{definition.display_name}...", section.content)
            apply_help_tooltip(button, calculator_help(definition))
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
            # ONE CONTRACT ACROSS ALL OF THEM, and this is the case that
            # rule exists for: "include this calculator in a batch run" is a
            # single concept rendered once per registered calculator, not 51
            # concepts. `instance_path` tells the renderings apart, and
            # `help_id` names the meaning -- which is why it must NOT become
            # `properties.batch_selection_1`, `_2`, ...
            apply_help_tooltip(tick, _BATCH_SELECTION_HELP)
            tick.setProperty(_CALCULATOR_ID_PROPERTY, definition.calculator_id)
            tick.toggled.connect(self._on_selection_toggled)
            self._calculator_ticks[definition.calculator_id] = tick
            row_layout.addWidget(tick)
            row_layout.addWidget(button, 1)

            # THE WAITING INDICATOR, on the row the user just clicked.
            #
            # Clicking a calculator used to produce NOTHING for as long as
            # it ran -- measured at 6.5 s for ADMET, sampling the panel
            # every 250 ms: no row, no status, no change of any kind, and
            # then the result and its dialog together. From the outside
            # that is indistinguishable from a slow dialog, which is
            # exactly how it was reported ("Details itself has a loading
            # time").
            #
            # `_present_alert` has rendered a "Running..." state since
            # Phase 18 AND IT COULD NEVER APPEAR, because a result row is
            # created when the first RESULT arrives -- there was nothing
            # on screen to put it in. Same wording here, deliberately, so
            # the two paths say one thing.
            #
            # ASCII dots, matching `_present_alert`: result text reaches
            # Windows console streams, where a non-ASCII ellipsis raises
            # (see regulatory/calculator.py, three times in one session).
            status = QLabel("Running...", row)
            status.setStyleSheet(_INFORMATION_STYLE)
            status.setVisible(False)
            self._calculator_status[definition.calculator_id] = status
            row_layout.addWidget(status)
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
            # A CAPTION WIDGET, not the string. `addRow(str, widget)` has
            # Qt build a plain `QLabel`, whose minimum width is its whole
            # text -- and the widest of those sized the form's label
            # column, the column sized the content, and the content
            # overflowed the viewport. See `_ElidingCaptionLabel`.
            section.content_layout().addRow(_ElidingCaptionLabel(label, section.content), value_label)
            self._value_labels[row_key] = value_label
            self._row_labels[row_key] = label
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
            section.content_layout().addRow(_ElidingCaptionLabel(label, section.content), value_label)
            self._row_labels[row_key] = label
        self._row_sections[row_key] = section

        # THE CAPTION IS REFRESHED, NOT WRITTEN ONCE, and that one word is
        # the whole bug. Every descriptor arrives twice: `DescriptorService`
        # publishes a RUNNING placeholder for each id BEFORE `compute()` runs
        # and therefore before anything knows the real names, so it fills in
        # `name=descriptor_id, units=""` (see `_publish`). The row was created
        # from that placeholder and its caption never touched again -- so the
        # display names and units in `_DESCRIPTOR_SPECS` were computed on
        # every run and thrown away, and EVERY row was captioned with its
        # internal id: measured, 26 of 26 from that table, plus the shape
        # descriptors. `mol_logp` for "LogP", `mol_wt` for "Molecular Weight
        # (g/mol)", `tpsa` for "TPSA (A^2)".
        #
        # It cannot be fixed at the producer: the placeholder is published
        # before the names exist, and this is the only place that sees both.
        if self._row_labels.get(row_key) != label:
            form = section.content_layout()
            row, _role = form.getWidgetPosition(value_label)
            item = form.itemAt(row, QFormLayout.ItemRole.LabelRole) if row >= 0 else None
            if item is not None and item.widget() is not None:
                item.widget().setText(label)
                self._row_labels[row_key] = label

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

    def _set_running(self, calculator_id: str, running: bool) -> None:
        """Say, on the calculator's own row, whether it is working.

        One place, so the button path and "Run selected" cannot drift --
        the batch path used to own `_running_calculator_ids` alone, which
        is why a single click showed nothing at all.
        """
        if running:
            self._running_calculator_ids.add(calculator_id)
        else:
            self._running_calculator_ids.discard(calculator_id)
        status = self._calculator_status.get(calculator_id)
        if status is not None:
            status.setVisible(running)

    def _on_calculation_finished(self, event) -> None:
        """A dispatched run is over, whatever it produced.

        **This is the authoritative signal and the result events are
        not.** A result is named after itself, and the two are not always
        the same -- `nmr_database` publishes `nmr_13c`, and
        `gasteiger_charge_at_ph` publishes `gasteiger_charge` -- so
        clearing on the result's id leaves those two showing "Running..."
        for the rest of the session. `_finish_batch_run` documents itself
        as best-effort for exactly this reason; it stays, because results
        also arrive from the descriptor providers at selection time
        without any dispatch behind them, and that path has no
        `CalculationFinished` to fire.

        `CalculationFinished` is published in a `finally`, so a calculator
        that failed or raised clears too. Those are the runs whose
        indicator would otherwise be stuck permanently, which is worse
        than never having shown one.
        """
        self._set_running(event.calculator_id, False)
        if not self._running_calculator_ids and self._batch_status.text().startswith("Running"):
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
            # EVERY fact, never a slice. This read `report.facts[:6]` from
            # the ReportResult migration (f8a3cdc) until it was measured:
            # 7 calculators over the cap, 50 of 126 facts never rendered,
            # `topology_analysis` showing 6 of 27. The only signal was a
            # tooltip nobody hovers, so a calculator that had computed 27
            # values looked like one that computed 6.
            #
            # The path this replaced -- `_present_alert`, still live for
            # the four catalogs -- has always joined its lines uncapped,
            # so this restores parity rather than inventing a policy. A
            # long report is a tall row in a section that collapses, in a
            # panel that already scrolls; that is a layout question, and
            # discarding the values is not an answer to it.
            label.setText("\n".join(f"{f.label}: {f.display_value}" for f in report.facts))
            label.setStyleSheet(_INFORMATION_STYLE)
            label.setToolTip(
                f"{len(report.facts)} facts. "
                "Details... for evidence, limitations and export."
            )
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
            #
            # `self` is the CONTEXT OBJECT for the same reason the two
            # reveal shots pass one (see `_reveal_pending_result`), and
            # this is the WIDEST window of the four: `_dump_panel_metrics`
            # opens on `panel.width()`, a C++ call that raises once the
            # panel is gone, and it waits 1500 ms rather than a turn.
            # Being behind an env var makes it rarely reached, not safe --
            # the one run where somebody is debugging a layout is exactly
            # the run that closes panels while shots are in flight.
            QTimer.singleShot(_INSTRUMENT_DELAY_MS, self, self._dump_metrics)
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
        # A producer that declared spatial annotations gets its result on
        # a 3D model -- the Marvin-style popup. THE ANNOTATION DECIDES,
        # never the presence of plausible numbers in provenance, and a
        # conformer must exist to draw on: a FAILED dipole has no
        # annotation, a conformer-less molecule has no canvas, and both
        # fall through to the plain facts dialog rather than to a blank
        # viewer.
        if getattr(report, "spatial", ()) and self._project is not None:
            molecule = self._project.find_molecule(report.molecule_uuid)
            best = canonical_conformer(molecule) if molecule is not None else None
            if best is not None and best.molblock:
                spatial_dialog = SpatialResultDialog(report, best.molblock, self)
                spatial_dialog.exec()
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

    def _on_trajectory_computed(self, event: TrajectoryComputed) -> None:
        """A trajectory is a result, and it used to arrive NOWHERE.

        `DescriptorService` has published `TrajectoryComputed` since Phase
        30 and nothing anywhere subscribed to it, so `molecular_dynamics`
        ran for nine seconds, produced 101 frames, and the panel showed no
        row at all -- indistinguishable from the calculator never having
        started. Found by running every registered calculator and asking
        which ones reach the screen.

        It used to get a row and deliberately NO inspector, because
        `_RESULT_VIEW_FACTORIES` had no view for a `TrajectoryResult` and
        the fallback would have depicted the input molecule rather than
        any of the frames. **That view exists now**
        (`TrajectoryPlayerWidget`), so an explicitly-run trajectory opens
        it like every other result.
        """
        trajectory = event.trajectory
        self._finish_batch_run(trajectory.trajectory_id)
        if trajectory.molecule_uuid == self._selected_molecule_uuid:
            self._show_result(
                trajectory.trajectory_id,
                getattr(trajectory, "name", trajectory.trajectory_id),
                self._category_of(trajectory.trajectory_id),
                trajectory,
            )
        if (
            self._pending_calculator_id == trajectory.trajectory_id
            and trajectory.molecule_uuid == self._selected_molecule_uuid
        ):
            self._pending_calculator_id = None
            self._open_inspector(trajectory)

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
            self._set_running(calculator_id, True)
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

        **Captions come through `_caption_text`, never `.text()`.** A
        caption on screen is elided to whatever the panel's width allows,
        so `.text()` would put `Blood-Brain Barrier Permeant (heur...`
        on the clipboard -- a width decision leaking into exported data.
        Same rule as `_without_glyphs` on the value side.
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
                rows.append(f"  {_caption_text(name_widget)}: {value}")
            if rows:
                lines.append(_category_label(category))
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
        # Shown BEFORE dispatch, not after: `run_calculator` hands the job
        # to a thread pool and returns immediately, but the settings dialog
        # above can have held the GUI thread for a while, and a user who
        # has just dismissed it should see the state change on the same
        # click rather than a frame later.
        self._set_running(definition.calculator_id, True)
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
        # `self` is the CONTEXT OBJECT, and it is what ties the pending
        # shot to this panel's lifetime -- see `_reveal_pending_result`.
        QTimer.singleShot(0, self, self._reveal_pending_result)

    def reveal_descriptor(self, descriptor_id: str) -> bool:
        """Scroll a computed property's row into view, and say so if it
        is not there.

        **A DESCRIPTOR CANNOT BE "RUN", which is why the command palette
        had none of them.** The 36 of them are computed as a batch the
        moment a molecule is selected, so there is no per-descriptor
        action to offer -- and the palette, which only knew how to offer
        actions, therefore knew nothing about Aqueous Solubility, QED,
        Lipinski, Veber, Ghose, Egan, Pfizer 3/75 or GSK 4/400. Searching
        "solubility" returned nothing at all.

        Revealing is the action that does exist, and it is the one the
        palette is for: "type what you want instead of remembering where
        it lives". The row is already on screen somewhere -- possibly a
        thousand pixels down, inside a collapsed section, which is the
        same invisibility `_reveal` was written for.

        Returns whether the row was found, so the caller can say
        something honest when it was not. Nothing is computed here: a
        palette entry that silently launched a calculation would be the
        surprise this panel already refuses elsewhere.
        """
        matches = [key for key in self._value_labels if key[1] == descriptor_id]
        if not matches:
            self._batch_status.setText(
                "Select a molecule to see its properties."
                if self._selected_molecule_uuid is None
                else "That property has not been computed for this molecule."
            )
            return False

        row_key = matches[0]
        label = self._value_labels[row_key]
        section = self._row_sections.get(row_key)
        if section is not None:
            section.set_expanded(True)
        # Same one-turn deferral `_reveal` uses: the section was expanded a
        # moment ago and the row's geometry is not settled, so asking now
        # scrolls to where it used to be. `self` is the context object for
        # the same reason it is there -- see `_reveal_pending_result`.
        self._reveal_target = label
        QTimer.singleShot(0, self, self._reveal_pending_result)
        return True

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

        **BOTH CALLERS PASS `self` AS THE CONTEXT OBJECT, and the `row is
        None` guard below cannot substitute for it.** A bare
        `QTimer.singleShot(0, callable)` is tied to nothing, so a pending
        shot outlives the panel: the panel is disposed, this runs anyway,
        and `self._scroll_area` is a live Python wrapper around a freed
        QScrollArea. That raises `RuntimeError: libshiboken: Internal C++
        object ... already deleted` -- inside whichever unrelated test
        happens to be pumping events, which is what made it read as a
        failure somewhere else entirely. Measured on PySide6 6.11.1, with
        the panel disposed by the recipe the fixtures use:

            plain     / panel alive        fired cleanly
            context   / panel alive        fired cleanly
            plain     / panel destroyed    FIRED, and raised
            context   / panel destroyed    never fired

        Qt disconnects a context-bound single shot when the context object
        is destroyed, so the shot is CANCELLED rather than firing and then
        declining. A `shiboken6.isValid` check here would be the latter:
        it would silence this one line while leaving every future line
        added to this method to be written against a dead widget.
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
