"""The header that changes shape with what the thing on screen IS.

The reason this is not another descriptor row: what the app should call a
structure depends on what kind of thing it is. A molecule wants a name and
a molecular weight; a salt wants a formula UNIT and its ions; a complex
wants its metal, its ligands and two separate counts. Rendering all three
as "Property: value" would bury the one line that answers "what am I
looking at".

    Sodium chloride                  Ferrocene
    NaCl        Ionic salt           C10H10Fe     Organometallic
    Formula unit  Na+ - Cl-          Metal        Fe(II)
    Charge        0                  Ligands      2 x eta5-Cp
    Components    2                  Donor atoms  10

**Classification and name come from independent sources, and the name
never decides the classification.** A bizarre organometallic the namer
cannot name still gets its header -- "Organometallic compound / (not
named) / C10H10Fe" is worth far more to a reader than collapsing the whole
card into "unknown" because one of the two sources came up empty.

The widget computes nothing. It is handed rows and draws them, which is
what keeps `tests/test_layering.py` satisfied -- `ui/` must not import
RDKit, and every chemical judgement here was made in the chem layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from PySide6.QtCore import Qt
from openchem.ui.widgets.collapsible_section import WrappedLabel
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

#: Shown where the namer produced nothing. Not blank: a reader has to be
#: able to tell "this has no accepted name" from "the card is still
#: loading".
NOT_NAMED = "(not named)"

#: Before anything has been perceived. The card is persistent, so it is on
#: screen in this state more often than any other.
NOTHING_SELECTED = "No structure selected"

#: Facts the card promotes into its own rows, per classification, in this
#: order. Anything absent is skipped -- a molecule has no formula unit and
#: a salt has no metal, and neither should leave a blank row behind.
_ROWS_BY_KIND: dict[str, tuple[str, ...]] = {
    "ionic salt": ("Formula unit", "Total charge", "Components"),
    "ion": ("Formula unit", "Total charge"),
    "coordination compound": ("Metal centre", "Ligands", "Ligand coordination", "Donor-atom count"),
    "organometallic": ("Metal centre", "Ligands", "Ligand coordination", "Donor-atom count"),
    "mixture": ("Components",),
    "ambiguous ionic components": ("Components", "Total charge"),
}

#: For a plain molecule the identity question is answered by the name and
#: the formula in the title rows, so the card stays short rather than
#: repeating what the panel below already lists.
_DEFAULT_ROWS: tuple[str, ...] = ("Total charge",)


@dataclass(frozen=True)
class SubstanceCardData:
    """Everything the card draws, already decided elsewhere.

    A plain value object rather than a report, so the card can be built
    and asserted on without a chemistry stack behind it -- and so the
    "namer returned nothing" case is expressible rather than requiring a
    broken namer to reproduce.
    """

    name: str = ""
    formula: str = ""
    classification: str = ""
    rows: tuple[tuple[str, str], ...] = ()
    #: Why the classification is a refusal, if it is. Shown under the
    #: rows, because a refusal's reason is the useful half of it.
    reason: str = ""
    limitations: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_empty(self) -> bool:
        return not (self.classification or self.formula or self.name)


def card_data_from_report(report, *, name: str = "", formula: str = "") -> SubstanceCardData:
    """Read a `substance_analysis` report into the card's shape.

    Takes the report loosely rather than by type: this module must not
    import the chem layer, and everything needed is `label` and
    `display_value` off each fact.

    `name` and `formula` are passed IN rather than read out, because they
    come from somewhere else entirely -- the namer and the descriptor
    service. That separation is the point: a card whose namer returned
    nothing still shows its classification.
    """
    facts = {fact.label: fact for fact in getattr(report, "facts", ())}
    classification_fact = facts.get("Substance classification")
    classification = classification_fact.display_value if classification_fact else ""
    reason = ""
    if classification_fact is not None and classification_fact.limitations:
        reason = classification_fact.limitations[0]

    wanted = _ROWS_BY_KIND.get(classification.lower(), _DEFAULT_ROWS)
    rows = tuple(
        (label, facts[label].display_value) for label in wanted if label in facts
    )
    # The plain formula, NOT the formula unit. They are different facts and
    # the subtitle showing the same string as the row under it was a live
    # check's finding: "Na+ - Cl-  Ionic salt / Formula unit  Na+ - Cl-"
    # spends two lines saying one thing.
    if not formula and "Formula" in facts:
        formula = facts["Formula"].display_value

    return SubstanceCardData(
        name=name,
        formula=formula,
        classification=classification,
        rows=rows,
        reason=reason,
    )


class SubstanceCard(QFrame):
    """A persistent identity header for the selected structure."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("substanceCard")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        # Fixed vertically, deliberately. This project has already measured
        # what an Expanding policy does to a top-level row in this panel:
        # a one-line status claimed 461px of a 950px panel and pushed the
        # scroll area off the bottom. A header is not content.
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(2)

        self._name = QLabel(NOTHING_SELECTED, self)
        self._name.setStyleSheet("font-size: 13px; font-weight: bold;")
        self._name.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self._name)

        self._subtitle = QLabel("", self)
        self._subtitle.setStyleSheet("color: #555;")
        self._subtitle.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self._subtitle)

        self._rows_container = QWidget(self)
        self._rows = QGridLayout(self._rows_container)
        self._rows.setContentsMargins(0, 4, 0, 0)
        self._rows.setHorizontalSpacing(10)
        self._rows.setVerticalSpacing(1)
        layout.addWidget(self._rows_container)

        # **`WrappedLabel`, not a plain wrapped `QLabel`.** A plain one does
        # not report its wrapped height, so the card -- which is Fixed
        # vertically -- sized itself from the unwrapped hint and CLIPPED the
        # last line. Caught by screenshotting the running app: the four-ion
        # refusal ended "...belong to the same" with "formula unit." cut
        # off, which turns a careful explanation into a confusing fragment.
        #
        # This is the one place in this widget that needs it. Its
        # MinimumExpanding policy is safe here because the card itself is
        # Fixed, so the policy only corrects the height hint rather than
        # claiming the panel's stretch -- the failure mode recorded against
        # the batch status line.
        self._reason = WrappedLabel("", self)
        self._reason.setStyleSheet("color: #8a6d00;")
        self._reason.hide()
        layout.addWidget(self._reason)

        self._data = SubstanceCardData()

    # --- state --------------------------------------------------------------

    def data(self) -> SubstanceCardData:
        return self._data

    def clear(self) -> None:
        self.set_data(SubstanceCardData())

    def set_data(self, data: SubstanceCardData) -> None:
        self._data = data
        self._clear_rows()

        if data.is_empty:
            self._name.setText(NOTHING_SELECTED)
            self._subtitle.setText("")
            self._reason.hide()
            return

        # A name is not required, and its absence is stated rather than
        # left blank -- the classification below it stands on its own.
        self._name.setText(data.name or NOT_NAMED)
        parts = [part for part in (data.formula, data.classification) if part]
        self._subtitle.setText("   ".join(parts))

        for index, (label, value) in enumerate(data.rows):
            caption = QLabel(label, self._rows_container)
            caption.setStyleSheet("color: #555;")
            content = QLabel(value, self._rows_container)
            content.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self._rows.addWidget(caption, index, 0, Qt.AlignmentFlag.AlignTop)
            self._rows.addWidget(content, index, 1, Qt.AlignmentFlag.AlignTop)
        self._rows.setColumnStretch(1, 1)

        self._reason.setText(data.reason)
        self._reason.setVisible(bool(data.reason))

    def summary_text(self) -> str:
        """What "copy" should produce. ASCII by construction, since every
        string here came from the chem layer's ASCII labels."""
        if self._data.is_empty:
            return NOTHING_SELECTED
        lines = [self._data.name or NOT_NAMED]
        subtitle = "   ".join(p for p in (self._data.formula, self._data.classification) if p)
        if subtitle:
            lines.append(subtitle)
        lines.extend(f"{label}: {value}" for label, value in self._data.rows)
        if self._data.reason:
            lines.append(self._data.reason)
        return "\n".join(lines)

    # --- internals ----------------------------------------------------------

    def _clear_rows(self) -> None:
        while self._rows.count():
            item = self._rows.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
