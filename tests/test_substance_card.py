"""The identity header, and the collapse it exists to avoid.

The card's whole justification is that a name and a classification come
from different places, so most of these are about what it still shows when
one of the two is missing.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QCoreApplication, QEvent
from rdkit import Chem

from openchem.chem.substance import compute_substance_analysis
from openchem.ui.widgets.substance_card import (
    NOT_NAMED,
    NOTHING_SELECTED,
    SubstanceCard,
    SubstanceCardData,
    card_data_from_report,
)

FERROCENE = "[Fe+2].[cH-]1cccc1.[cH-]1cccc1"
SODIUM_CHLORIDE = "[Na+].[Cl-]"
FOUR_IONS = "[Na+].[Cl-].[K+].[Br-]"
ASPIRIN = "CC(=O)Oc1ccccc1C(=O)O"


def _data(smiles: str, *, name: str = "") -> SubstanceCardData:
    report = compute_substance_analysis(Chem.MolFromSmiles(smiles), "uuid")
    return card_data_from_report(report, name=name)


@pytest.fixture
def card(qapp):
    """Destroyed deterministically. A test that builds an unparented widget
    and walks away leaves Python to destroy it inside whatever later test
    happens to be pumping events, which is an access violation."""
    widget = SubstanceCard()
    yield widget
    widget.setParent(None)
    widget.deleteLater()
    QCoreApplication.sendPostedEvents(widget, QEvent.Type.DeferredDelete)


# --- the shape changes with the substance -----------------------------------


def test_a_salt_leads_with_its_formula_unit():
    data = _data(SODIUM_CHLORIDE, name="Sodium chloride")

    assert data.classification == "Ionic salt"
    assert ("Formula unit", "Na+ · Cl-") in data.rows


def test_a_complex_leads_with_its_metal_and_ligands():
    labels = [label for label, _ in _data(FERROCENE, name="Ferrocene").rows]

    assert labels == ["Metal centre", "Ligands", "Ligand coordination", "Donor-atom count"]


def test_a_molecule_does_not_grow_salt_rows():
    """A molecule has no formula unit and a salt has no metal. Neither
    should leave a blank row behind."""
    labels = [label for label, _ in _data(ASPIRIN, name="Aspirin").rows]

    assert "Formula unit" not in labels
    assert "Metal centre" not in labels


def test_a_refusal_shows_its_reason_on_the_card():
    """The reason is the useful half of a refusal, so it belongs where the
    refusal is, not three clicks away."""
    data = _data(FOUR_IONS)

    assert data.classification == "Ambiguous ionic components"
    assert "does not encode which ions" in data.reason


# --- the collapse this exists to avoid --------------------------------------


def test_a_structure_with_no_name_still_shows_its_classification():
    """**The name never decides the classification.** A bizarre
    organometallic nothing can name still gets its header -- collapsing
    the whole card to "unknown" because one of two independent sources
    came up empty would throw away the half that worked."""
    data = _data(FERROCENE, name="")

    assert data.name == ""
    assert data.classification == "Organometallic"
    assert data.rows


def test_the_missing_name_is_stated_rather_than_left_blank(card):
    """A reader has to be able to tell "this has no accepted name" from
    "the card has not finished loading"."""
    card.set_data(_data(FERROCENE, name=""))

    assert NOT_NAMED in card.summary_text()


def test_an_empty_card_says_so(card):
    card.clear()

    assert card.summary_text() == NOTHING_SELECTED


# --- rendering --------------------------------------------------------------


def test_switching_substance_replaces_the_rows_rather_than_appending(card):
    """Ferrocene's four coordination rows must not survive into a salt."""
    card.set_data(_data(FERROCENE, name="Ferrocene"))
    card.set_data(_data(SODIUM_CHLORIDE, name="Sodium chloride"))

    assert "Metal centre" not in card.summary_text()
    assert "Formula unit" in card.summary_text()


def test_the_card_is_fixed_height_not_expanding(card):
    """This project has measured what an Expanding policy does to a
    top-level row in this panel: a one-line status claimed 461px of a
    950px panel and pushed the scroll area off the bottom."""
    from PySide6.QtWidgets import QSizePolicy

    assert card.sizePolicy().verticalPolicy() is QSizePolicy.Policy.Fixed


def test_the_summary_is_copyable_as_plain_text(card):
    card.set_data(_data(FERROCENE, name="Ferrocene"))
    text = card.summary_text()

    assert text.startswith("Ferrocene")
    assert "Organometallic" in text
    assert "Donor-atom count: 10" in text


def test_the_widget_imports_no_chemistry():
    """`tests/test_layering.py` forbids `ui/` importing RDKit. The card
    computes nothing -- it is handed rows and draws them -- which is what
    makes that possible."""
    import ast
    from pathlib import Path

    tree = ast.parse(
        Path("src/openchem/ui/widgets/substance_card.py").read_text(encoding="utf-8")
    )
    imported = {
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    } | {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }

    # Parsed, not grepped. The first version of this searched the source
    # text and failed on the COMMENT saying RDKit must not be imported --
    # a check that cannot tell an import from a sentence about one.
    assert not any(name.startswith(("rdkit", "openchem.chem")) for name in imported)
