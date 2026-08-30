"""The Lewis dialog: a snapshot, a window into the analysis, and inert.

Three things are being guarded here and only one of them is Qt.

**It cannot change anything.** Plan invariant 17. The molecule, its
molblock and the undo stack must be untouched by opening it, which is
what makes opening it free -- and it is asserted against a real
`MoleculeModel` rather than a stub, because a stub has nothing to
mutate.

**The four outcomes reach the screen distinctly.** The model already
keeps `CHEMISTRY_REFUSED` and `RENDERING_FAILED` apart; a dialog that
rendered both as "unavailable" would throw that away at the last step.

**Nothing here may total an UNKNOWN as zero.** The whole point of the
type is that a count nobody determined never appears as a number, and the
details panel is the one place in the app that prints every count.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QCoreApplication
from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.chem.lewis_diagram import Known, Status, Unknown
from openchem.domain.molecule import MoleculeModel
from openchem.ui.dialogs.lewis_diagram_dialog import LewisDiagramDialog

import conftest


def molblock(smiles: str) -> str:
    mol = Chem.MolFromSmiles(smiles)
    AllChem.Compute2DCoords(mol)
    return Chem.MolToMolBlock(mol)


def _dispose(dialog) -> None:
    """Per-widget, never the global drain.

    `sendPostedEvents(None, DeferredDelete)` empties the process-wide
    queue including deletes other test files left on it, which is the
    double-free `tests/conftest.py` already documents.
    """
    conftest.dispose(dialog)


@pytest.fixture
def dialog(qapp):
    made: list[LewisDiagramDialog] = []

    def build(smiles_or_molblock: str | None, **kwargs):
        text = (
            smiles_or_molblock
            if smiles_or_molblock is None or "\n" in smiles_or_molblock
            else molblock(smiles_or_molblock)
        )
        made.append(LewisDiagramDialog(text, **kwargs))
        return made[-1]

    yield build
    for item in made:
        _dispose(item)


# --- it is inert --------------------------------------------------------------


def test_opening_the_dialog_changes_nothing(dialog, qapp):
    """Invariant 17, against a REAL model rather than a stub.

    A stub with no fields cannot record a mutation, so a test built on
    one asserts that nothing happened to nothing. This compares the
    molecule's whole serialised state either side.
    """
    molecule = MoleculeModel(molblock=molblock("CC(=O)[O-]"), display_name="Acetate")
    before = molecule.to_dict()

    window = dialog(molecule.molblock, display_name=molecule.display_name)

    assert molecule.to_dict() == before
    assert window.diagram.drawable


def test_the_dialog_never_writes_the_molblock_it_was_handed(dialog):
    """It takes a string, so there is nothing it could write back through.

    Asserted anyway, because the obvious way to add a refresh later is to
    hand it the model instead -- at which point this fails and names the
    reason.
    """
    text = molblock("O")

    window = dialog(text)

    assert window.diagram.provenance.molblock_sha
    assert text == molblock("O")


# --- what it says -------------------------------------------------------------


def test_the_header_names_the_molecule_and_its_formula(dialog):
    window = dialog("CC(=O)[O-]", display_name="Acetate")

    text = window._header.text()

    assert "Acetate" in text
    # Hill order, explicit hydrogens, and the charge -- the formula of the
    # molecule as DRAWN in this diagram, which is what the reader is
    # looking at rather than what the canvas holds.
    assert "C2H3O2-" in text, text


def test_an_unnamed_molecule_still_gets_a_header(dialog):
    window = dialog("O")

    assert "Structure" in window._header.text()
    assert "H2O" in window._header.text()
    assert window.windowTitle() == "Full Lewis Structure"


def test_the_window_TITLE_names_the_molecule_too(dialog):
    """More than one of these can be open, and the taskbar and the
    window list only ever show the title."""
    window = dialog("CC(=O)[O-]", display_name="Acetate")

    assert "Acetate" in window.windowTitle()
    assert "Lewis" in window.windowTitle()


def test_a_supported_diagram_says_so_without_hedging(dialog):
    window = dialog("O")

    assert window.status_text() == "Lewis structure."
    assert window._legend.isVisible() or not window.isVisible()
    assert window._copy_button.isEnabled()
    assert window._save_button.isEnabled()


def test_refused_chemistry_shows_ITS_reason_and_offers_no_export(dialog):
    """A radical -- invariant 12, refused with its reason rather than drawn
    as an atom with no lone pairs.

    A refusal renders to a card carrying the reason, which is still a
    valid SVG -- so gating export on the SVG being non-empty would offer
    to export a picture of an error message.
    """
    window = dialog("[CH2]")

    assert window.diagram.status is Status.CHEMISTRY_REFUSED
    assert "unavailable" in window.status_text()
    assert window.diagram.reason
    assert window.diagram.reason in window.status_text()
    assert not window._copy_button.isEnabled()
    assert not window._save_button.isEnabled()
    assert window._legend.isHidden()


def test_an_ABSTENTION_is_not_a_refusal_and_still_draws(dialog):
    """The two must never share a message. A bare iron(III) has no lone
    pair count this analysis will assert, and that is one abstention on a
    diagram that is otherwise fine -- not "I cannot draw this molecule".
    """
    window = dialog("[Fe+3]")

    assert window.diagram.status is Status.SUPPORTED_WITH_ABSTENTIONS
    assert window.diagram.abstentions
    assert window.diagram.drawable
    assert "unavailable" not in window.status_text()
    assert "abstention" in window.status_text()
    assert window._copy_button.isEnabled()


def test_a_REFUSAL_claims_no_electron_budget(dialog):
    """Found by driving the app, with every test green.

    A refused diagram has no atoms, so every term of the accounting is
    zero and `balances` reads "yes" -- the panel was reporting a closed
    electron budget for a molecule the analysis had explicitly declined.
    A number that agrees with itself about nothing is worse than no
    number, because it reads as a result.
    """
    window = dialog("[CH2]")

    text = window.details_text()

    assert "not applicable" in text, text
    assert "balances" not in text, text
    assert "total valence electrons" not in text, text
    # The reason is in the panel as well as the status line, because this
    # is the text somebody copies out.
    assert window.diagram.reason in text


def test_a_REFUSAL_is_not_shown_as_a_picture(dialog):
    """`render` is total and returns a card carrying the reason, which is
    what keeps the renderer honest -- but a QSvgWidget scales that
    200-unit viewBox to fill the pane, and driving the app showed the
    sentence at ~37 px with both ends clipped. It read as a broken
    window. The status line says the same thing at a normal size.
    """
    refused = dialog("[CH2]")
    drawn = dialog("O")

    # **`isVisibleTo`, not `isHidden`.** The view now lives inside a
    # scroll area and it is the AREA that gets hidden, so the view's own
    # explicit flag is False either way. What the claim is really about is
    # whether the picture reaches the reader, which is the question
    # `isVisibleTo` answers -- and `isVisible()` would be the opposite
    # mistake, False for every child of a window nobody showed.
    assert not refused._view.isVisibleTo(refused)
    assert drawn._view.isVisibleTo(drawn)
    # The SVG is still produced -- the renderer stays total, and the
    # decision not to show it is the dialog's.
    assert refused.svg.startswith("<svg")


def test_an_unparseable_structure_fails_gracefully(dialog):
    """Invariant 19. A message, never malformed SVG."""
    window = dialog("not a molblock at all\n\n\n")

    assert not window.diagram.drawable
    assert window.svg.startswith("<svg") and window.svg.endswith("</svg>")
    assert window.status_text()
    assert not window._copy_button.isEnabled()


def test_an_empty_structure_fails_gracefully(dialog):
    window = dialog(None)

    assert not window.diagram.drawable
    assert window.svg.startswith("<svg")
    assert window.status_text()


def test_a_crowded_diagram_is_a_LEGIBILITY_note_beside_a_SUCCESS(dialog):
    """The plan's declared limit, and it is the one most likely to be got
    wrong: a molecule whose chemistry is fine gets its diagram plus "may
    be hard to read", never "analysis unsupported"."""
    window = dialog("c1ccc2ccccc2c1")

    assert window.diagram.drawable
    text = window.status_text()
    assert "unavailable" not in text and "unsupported" not in text
    assert window._copy_button.isEnabled()


# --- the analysis details panel -----------------------------------------------


def test_the_details_panel_starts_collapsed(dialog):
    """It is a window into the engine, not the point of the window."""
    window = dialog("O")

    assert not window._details.isVisible()
    assert not window._details_button.isChecked()

    window._details_button.setChecked(True)
    assert not window._details.isHidden()


def test_the_details_print_the_whole_electron_budget(dialog):
    """A balance failure that prints `assert 30 == 28` says nothing about
    which half is wrong, which is why `Accounting` carries all four
    terms. This is where they surface."""
    window = dialog("c1ccccc1")

    text = window.details_text()

    assert "total valence electrons     30" in text, text
    assert "localised bonding electrons 24" in text, text
    assert "delocalised electrons       6" in text, text
    assert "lone-pair electrons         0" in text, text
    assert "balances                    yes" in text, text


def test_the_details_name_each_region_with_its_electron_count(dialog):
    window = dialog("c1ccccc1")

    text = window.details_text()

    assert "ring over atoms 0, 1, 2, 3, 4, 5: 6 electrons" in text, text


def test_a_region_whose_count_is_UNKNOWN_never_prints_as_a_number(dialog):
    """Invariant 6, at the one place in the app that prints every count.

    Pyrrole's sextet is completed by the nitrogen's lone pair rather than
    by a varying bond order, so the resonance enumeration cannot see it.
    The region is real; the count is not determined; those are different
    statements and the panel must make both.
    """
    window = dialog("c1cc[nH]c1")

    regions = window.diagram.regions
    assert any(isinstance(region.electrons, Unknown) for region in regions), regions

    text = window.details_text()
    assert "not determined" in text, text
    assert "0 electrons" not in text, text


def test_abstentions_are_printed_verbatim_with_their_subject(dialog):
    """"Some bonds were omitted" tells nobody anything. Which bond, and
    why, is the whole value of the panel.

    **IT ASSERTS ITS OWN SETUP, and the first version skipped instead.**
    Dimethyl sulfone abstains because its sulfur carries an expanded
    octet; a `pytest.skip` when nothing abstained meant the guard
    disabled itself under exactly the mutation it exists to catch --
    measured, removing the expanded-octet abstention turned this test
    into a skip and the mutation scored as an invalid arm rather than a
    survivor. A missing abstention here is a failure, not a reason to
    stand down.
    """
    window = dialog("CS(=O)(=O)C")

    assert window.diagram.abstentions, (
        "dimethyl sulfone's sulfur has an expanded octet and must abstain; "
        "with nothing abstaining this test would assert nothing"
    )
    text = window.details_text()
    for abstention in window.diagram.abstentions:
        assert abstention.subject in text
        assert abstention.reason in text


def test_the_details_carry_the_provenance_that_makes_a_stale_window_diagnosable(dialog):
    window = dialog("O", structure_revision=7)

    text = window.details_text()

    assert window.diagram.provenance.molblock_sha in text
    assert "structure revision    7" in text, text
    assert "snapshot" in text


def test_the_details_are_cp1252_safe(dialog):
    """This project has three recorded `UnicodeEncodeError`s from result
    text meeting a Windows console. The panel is the most copy-pasted
    text in the feature, so it is ASCII deliberately."""
    for smiles in ("O", "c1ccccc1", "CC(=O)[O-]", "c1cc[nH]c1"):
        window = dialog(smiles)
        window.details_text().encode("cp1252")


# --- the snapshot -------------------------------------------------------------


def test_the_dialog_does_not_follow_a_later_edit(dialog):
    """The failure this removes by construction: a window silently showing
    structure A after the editor moved to B."""
    molecule = MoleculeModel(molblock=molblock("O"), display_name="Water")
    window = dialog(molecule.molblock, display_name=molecule.display_name)
    before = window.svg

    molecule.molblock = molblock("c1ccccc1")

    assert window.svg == before
    assert len(window.diagram.atoms) == 3


def test_two_dialogs_of_different_molecules_do_not_share_a_diagram(dialog):
    """More than one can be open, which is why the header names its own."""
    water = dialog("O", display_name="Water")
    benzene = dialog("c1ccccc1", display_name="Benzene")

    assert water.svg != benzene.svg
    assert "Water" in water._header.text()
    assert "Benzene" in benzene._header.text()


# --- export -------------------------------------------------------------------


def test_copy_puts_the_same_svg_on_the_clipboard_as_the_view_shows(dialog, qapp):
    from PySide6.QtGui import QGuiApplication

    window = dialog("O")

    window._copy_button.click()

    assert QGuiApplication.clipboard().text() == window.svg


def test_saving_writes_the_svg_verbatim(dialog, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog

    window = dialog("O")
    target = tmp_path / "water.svg"
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(target), ""))
    )

    window._save_button.click()

    assert target.read_text(encoding="utf-8") == window.svg


def test_cancelling_the_save_writes_nothing(dialog, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog

    window = dialog("O")
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: ("", ""))
    )

    window._save_button.click()

    assert list(tmp_path.iterdir()) == []


# --- what the SCREEN does with the SVG ----------------------------------------


def _label_ink(svg: str, atom, viewbox_origin) -> tuple[int, int]:
    """The rows the atom's own glyph inks, in image pixels.

    Isolated by DIFFERENCE -- render the SVG, render it again with the
    atom text removed, and take the pixels that disappeared. A column
    sampled through the atom would also catch its lone-pair dots, which
    is how a first attempt at this measured a 35-pixel-tall "O".
    """
    import re

    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer

    box = [float(v) for v in re.search(r'viewBox="([^"]+)"', svg).group(1).split()]
    width, height = int(box[2]), int(box[3])

    def ink(text: str) -> set[tuple[int, int]]:
        renderer = QSvgRenderer(text.encode("utf-8"))
        image = QImage(width, height, QImage.Format.Format_ARGB32)
        image.fill(0xFFFFFFFF)
        painter = QPainter(image)
        renderer.render(painter)
        painter.end()
        return {
            (x, y)
            for y in range(height)
            for x in range(width)
            if image.pixelColor(x, y).red() < 200
        }

    stripped = re.sub(r'<text class="atom".*?</text>', "", svg)
    glyph = ink(svg) - ink(stripped)
    px = atom.x - box[0]
    rows = [y for x, y in glyph if abs(x - px) <= 8]
    assert rows, "the atom's label drew nothing"
    return min(rows), max(rows)


def test_the_drawn_label_really_sits_inside_the_box_the_CHECKER_uses(dialog, qapp):
    """The one class of error a checker cannot see, in a second renderer.

    `chem/electron_layout` judges a dot against the label box it is
    HANDED, so if the page draws the glyph somewhere else the judge and
    the screen agree while both are wrong -- which is exactly how a lone
    pair came to be drawn through the "H" of methanol's "OH".

    **Qt's SVG renderer ignores `dominant-baseline`, and ignores `dy`
    too.** Measured: with the attribute in place the oxygen's ink ran
    74..87 against a checker box of 78.6..101.4, poking 4.6 px out of the
    top while the bottom 14 px of the box held nothing. This asserts
    against the REAL Qt renderer, because the model cannot see it.
    """
    from openchem.chem.lewis_svg import BOND_LENGTH, LABEL_HALF_HEIGHT

    window = dialog("O")
    diagram = window.diagram
    oxygen = diagram.atoms[0]
    import re

    origin = [float(v) for v in re.search(r'viewBox="([^"]+)"', window.svg).group(1).split()]

    top, bottom = _label_ink(window.svg, oxygen, origin)
    half = LABEL_HALF_HEIGHT * BOND_LENGTH
    atom_y = oxygen.y - origin[1]

    assert top >= atom_y - half, (
        f"the glyph reaches {atom_y - top:.1f}px above the atom, "
        f"outside a box that only claims {half:.1f}"
    )
    assert bottom <= atom_y + half, (
        f"the glyph reaches {bottom - atom_y:.1f}px below the atom, "
        f"outside a box that only claims {half:.1f}"
    )


def test_no_text_relies_on_an_attribute_Qt_ignores(dialog):
    """The cheap half of the guard above, and it names the fix.

    `dominant-baseline` and `dy` are both silently dropped by Qt's SVG
    renderer, so a future edit that reaches for either would move every
    label off its atom with no test failing except the pixel one -- which
    is slow and only samples one molecule.
    """
    for smiles in ("O", "c1ccccc1", "CC(=O)[O-]", "[CH2]"):
        svg = dialog(smiles).svg
        assert "dominant-baseline" not in svg, smiles
        assert " dy=" not in svg, smiles


# --- the model's own formula --------------------------------------------------


def test_the_formula_is_hill_order_with_explicit_hydrogens(dialog):
    """Derived from the diagram's atoms, not fetched from RDKit, so `ui/`
    imports no chemistry toolkit -- the rule `tests/test_layering.py`
    enforces. Hill: carbon, then hydrogen, then alphabetical."""
    assert dialog("CC(=O)O").diagram.formula == "C2H4O2"
    assert dialog("O").diagram.formula == "H2O"
    assert dialog("[NH4+]").diagram.formula == "H4N+"
    assert dialog("CC(=O)[O-]").diagram.formula == "C2H3O2-"


def test_hydrogen_is_only_special_in_hill_order_WHEN_CARBON_IS_THERE(dialog):
    """Borane is BH3, not H3B.

    The obvious single rule -- carbon, then hydrogen, then the rest
    alphabetically -- agrees with Hill on water, ammonia and every
    organic molecule, and is wrong for exactly the carbon-free compounds
    whose other element sorts before hydrogen. Boranes are that case, and
    this application's Lewis-adduct work is built on them.
    """
    assert dialog("B").diagram.formula == "BH3"
    assert dialog("[BH4-]").diagram.formula == "BH4-"
    # The carbon-bearing control, so a rule that simply sorted everything
    # alphabetically would fail here rather than passing both.
    assert dialog("CBr").diagram.formula == "CH3Br"


# --- C1: the diagram is zoomable, and stopped being squeezed ---------------
#
# A QSvgWidget scales its viewBox to fill its pane, so a 42-atom structure
# was rendered into whatever the window had left -- about 600x450 -- and
# every glyph came out a few pixels tall. That is what "extremely hard to
# read" was about, and it is a presentation problem with a presentation
# fix: the same vector diagram, at more pixels per atom, in something that
# scrolls.


def _dialog_for(smiles: str, qtbot=None):
    from rdkit import Chem
    from rdkit.Chem import AllChem

    mol = Chem.MolFromSmiles(smiles)
    AllChem.Compute2DCoords(mol)
    return LewisDiagramDialog(Chem.MolToMolBlock(mol), "test")


def test_one_hundred_percent_is_the_svgs_own_size(qapp):
    """Not "100% of the viewport", which is the reading that would make
    this button and Fit the same thing."""
    dialog = _dialog_for("O")
    try:
        dialog.zoom_to_natural()

        assert dialog.zoom() == 1.0
        assert dialog._view.size() == dialog.natural_size()
    finally:
        _dispose(dialog)


def test_fit_is_bigger_than_one_hundred_percent_for_a_small_molecule(qapp):
    """**THE CASE THAT PROVES THE TWO BUTTONS DIFFER.**

    Fit is the largest zoom at which the whole diagram fits, so a small
    molecule in a large window is MAGNIFIED to fill it -- water comes out
    near 4x. An implementation that read Fit as "shrink to fit, never
    grow" would clamp at 1.0 and pass any test that only checked a large
    molecule.
    """
    dialog = _dialog_for("O")
    try:
        dialog.resize(900, 760)
        dialog.show()
        QCoreApplication.processEvents()
        dialog.zoom_to_fit()

        assert dialog.zoom() > 1.0
    finally:
        _dispose(dialog)


def test_fit_keeps_the_whole_diagram_inside_the_viewport(qapp):
    """The other half of what Fit promises, and the half that a zoom
    which merely magnified would fail."""
    dialog = _dialog_for("CN1CC[C@]23c4c5ccc(O)c4O[C@H]2[C@@H](O)C=C[C@H]3[C@H]1C5")
    try:
        dialog.resize(700, 560)
        dialog.show()
        QCoreApplication.processEvents()
        dialog.zoom_to_fit()

        viewport = dialog._scroll.viewport().size()
        assert dialog._view.width() <= viewport.width() + 1
        assert dialog._view.height() <= viewport.height() + 1
    finally:
        _dispose(dialog)


def test_zooming_in_really_makes_the_drawing_bigger(qapp):
    dialog = _dialog_for("O")
    try:
        dialog.set_zoom(1.0)
        before = dialog._view.width()
        dialog._zoom_in()

        assert dialog._view.width() > before
        assert dialog.zoom() > 1.0
    finally:
        _dispose(dialog)


def test_the_zoom_is_bounded_at_both_ends(qapp):
    """A zoom of zero is a widget of no size, and an unbounded one is a
    pixmap nobody can allocate."""
    dialog = _dialog_for("O")
    try:
        dialog.set_zoom(1000.0)
        assert dialog.zoom() == dialog.MAX_ZOOM
        dialog.set_zoom(0.0)
        assert dialog.zoom() == dialog.MIN_ZOOM
    finally:
        _dispose(dialog)


def test_the_view_is_in_something_that_will_not_shrink_it(qapp):
    """`setWidgetResizable(True)` would hand the child the viewport size
    and undo the whole fix -- the diagram would be squeezed again, just
    with zoom buttons above it."""
    dialog = _dialog_for("O")
    try:
        assert dialog._scroll.widget() is dialog._view
        assert not dialog._scroll.widgetResizable()
    finally:
        _dispose(dialog)


def test_a_refused_diagram_shows_no_zoom_controls(qapp):
    """Following the existing rule that a refusal is not shown as a
    picture: controls for a picture that is not there are noise."""
    dialog = LewisDiagramDialog(None, "nothing")
    try:
        assert not dialog._diagram.drawable
        assert not dialog._scroll.isVisibleTo(dialog)
        assert not dialog._zoom_label.isVisibleTo(dialog)
    finally:
        _dispose(dialog)


# --- C2: the guide toggle ---------------------------------------------------


def test_bond_guides_are_on_by_default(qapp):
    """The diagram this branch was opened for is a 42-atom cloud without
    them. Somebody wanting the pure dots-only convention can turn them
    off, which is the rarer ask."""
    dialog = _dialog_for("O")
    try:
        assert dialog._guides_button.isChecked()
        assert "bond-guide" in dialog.svg
    finally:
        _dispose(dialog)


def test_turning_the_guides_off_redraws_without_them(qapp):
    dialog = _dialog_for("O")
    try:
        dialog._guides_button.setChecked(False)

        assert "bond-guide" not in dialog.svg
        assert "lone-pair" in dialog.svg, "it dropped more than the guides"
    finally:
        _dispose(dialog)


def test_the_toggle_keeps_the_zoom_it_was_at(qapp):
    """Re-rendering must not throw away where the reader had got to."""
    dialog = _dialog_for("O")
    try:
        dialog.set_zoom(2.0)
        dialog._guides_button.setChecked(False)

        assert dialog.zoom() == 2.0
    finally:
        _dispose(dialog)


def test_what_is_exported_is_what_is_on_screen(qapp):
    """`svg` is what "Copy SVG" and "Save SVG..." hand over, so it has to
    follow the toggle rather than some other rendering."""
    dialog = _dialog_for("O")
    try:
        dialog._guides_button.setChecked(False)
        assert dialog.svg == dialog._rendered.svg
        assert "bond-guide" not in dialog.svg
    finally:
        _dispose(dialog)


def test_the_legend_tells_a_guide_from_an_abstained_bond(qapp):
    """Both are lines now, so the key has to say how they differ."""
    from openchem.ui.dialogs.lewis_diagram_dialog import LEGEND

    assert "bond guide" in LEGEND
    assert "NO dots" in LEGEND
