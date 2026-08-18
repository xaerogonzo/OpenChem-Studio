"""Writing an isotope: what it touches, what it refuses, what it keeps."""

from __future__ import annotations

import pytest
from PySide6.QtGui import QUndoStack
from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.chem.engine import ChemistryEngine
from openchem.chem.isotopes import (
    IsotopeError,
    element_at,
    isotope_free_smiles,
    set_isotope,
)
from openchem.commands.molecule_commands import EditStructureCommand
from openchem.domain.conformer import ConformerModel
from openchem.domain.molecule import MoleculeModel
from openchem.events.base import EventBus
from openchem.events.events import ConformersInvalidated


def _drawn(smiles: str, *, explicit_hydrogens: bool = False) -> str:
    mol = Chem.MolFromSmiles(smiles)
    if explicit_hydrogens:
        mol = Chem.AddHs(mol)
    AllChem.Compute2DCoords(mol)
    return Chem.MolToMolBlock(mol)


def _labels(molblock: str) -> list[tuple[str, int]]:
    mol = Chem.MolFromMolBlock(molblock, removeHs=False)
    return [(a.GetSymbol(), a.GetIsotope()) for a in mol.GetAtoms()]


def _positions(molblock: str) -> list[tuple[float, float, float]]:
    mol = Chem.MolFromMolBlock(molblock, removeHs=False)
    conformer = mol.GetConformer()
    return [
        tuple(round(v, 4) for v in conformer.GetAtomPosition(i))
        for i in range(mol.GetNumAtoms())
    ]


# --- the write --------------------------------------------------------------


def test_one_atom_is_the_default():
    """Labelling a single position is the ordinary case -- a tracer, one
    deuterium -- and "every carbon" is a different enough request to have
    to be made."""
    ethanol = _drawn("CCO")

    labelled = set_isotope(ethanol, 0, 13)

    assert _labels(labelled) == [("C", 13), ("C", 0), ("O", 0)]


def test_all_of_element_covers_that_element_and_nothing_else():
    ethanol = _drawn("CCO")

    labelled = set_isotope(ethanol, 0, 13, all_of_element=True)

    assert _labels(labelled) == [("C", 13), ("C", 13), ("O", 0)]


def test_the_scope_follows_the_ATOM_and_not_a_symbol_the_caller_supplies():
    """**THE MISTAKE THE SIGNATURE MAKES UNEXPRESSIBLE.** The periodic
    table is a browsing tool, so somebody can be reading carbon's isotopes
    with an oxygen selected. There is no argument through which "apply
    C-13 to every oxygen" can be asked for: the element comes off the atom
    `index` names, so an all-atoms write can only ever cover that atom's
    own element.
    """
    ethanol = _drawn("CCO")

    # index 2 is the oxygen, so "all of element" is all the OXYGENS,
    # whatever the caller may have been looking at.
    labelled = set_isotope(ethanol, 2, 18, all_of_element=True)

    assert _labels(labelled) == [("C", 0), ("C", 0), ("O", 18)]


def test_the_drawing_does_not_move():
    """A mass label is not a geometry change, and if it moved atoms the
    conformer exemption below would be wrong to keep them."""
    ethanol = _drawn("CCO")

    labelled = set_isotope(ethanol, 0, 13, all_of_element=True)

    assert _positions(labelled) == _positions(ethanol)


def test_the_atom_order_does_not_move():
    """The caller keeps using the indices it already has, and so does
    every panel holding a selection."""
    aspirin = _drawn("CC(=O)Oc1ccccc1C(=O)O")

    labelled = set_isotope(aspirin, 3, 18)

    assert [s for s, _ in _labels(labelled)] == [s for s, _ in _labels(aspirin)]


def test_an_explicit_hydrogen_keeps_its_index():
    """**`removeHs=False` IS LOAD-BEARING.** The default strips explicit
    hydrogens, which renumbers every atom after the first one removed --
    so the index would silently come to mean a different atom. A drawing
    carrying explicit hydrogens is exactly where somebody wants a
    deuterium.
    """
    methanol = _drawn("CO", explicit_hydrogens=True)
    before = _labels(methanol)
    assert before[3][0] == "H", "the fixture must have explicit hydrogens"

    labelled = set_isotope(methanol, 3, 2)

    assert _labels(labelled)[3] == ("H", 2)
    assert [s for s, _ in _labels(labelled)] == [s for s, _ in before]


# --- what it refuses --------------------------------------------------------


def test_an_index_past_the_end_is_refused():
    with pytest.raises(IsotopeError, match="not in this structure"):
        set_isotope(_drawn("CCO"), 99, 13)


@pytest.mark.parametrize("mass_number", [0, -1])
def test_a_non_positive_mass_number_is_refused(mass_number):
    with pytest.raises(IsotopeError, match="not a mass number"):
        set_isotope(_drawn("CCO"), 0, mass_number)


def test_a_mass_number_that_is_not_a_nuclide_of_THAT_element_is_refused():
    """**THE PLAN'S OWN FIXTURE FOR THIS WAS DEGENERATE**, which measuring
    it caught: it proposed asking for O-18 on a carbon, and mass number 18
    is a real nuclide of BOTH elements -- C-18 exists, at 92 ms. So that
    call is correctly ACCEPTED and produces C-18, because the element
    always comes from the atom.

    Mass number 2 is the sharp case: H-2 is deuterium and C-2 does not
    exist, so a mass number that is perfectly real elsewhere is refused
    here. Carbon's table runs 8..23.
    """
    with pytest.raises(IsotopeError, match="C-2 is not in the nuclide table"):
        set_isotope(_drawn("CCO"), 0, 2)

    # The control, and the disproof of the plan's fixture: 18 IS a carbon.
    assert _labels(set_isotope(_drawn("CCO"), 0, 18))[0] == ("C", 18)


def test_a_structure_that_cannot_be_read_is_refused_rather_than_guessed():
    with pytest.raises(IsotopeError, match="could not be read"):
        set_isotope("not a molblock", 0, 13)


def test_the_refusal_names_the_nuclide_so_a_user_can_act_on_it():
    with pytest.raises(IsotopeError) as raised:
        set_isotope(_drawn("CCO"), 2, 99)

    assert "O-99" in str(raised.value)


# --- reading an element off an index ---------------------------------------


def test_element_at_reads_the_atom():
    ethanol = _drawn("CCO")

    assert [element_at(ethanol, i) for i in range(3)] == ["C", "C", "O"]


@pytest.mark.parametrize("index", [-1, 3, 99])
def test_element_at_answers_None_rather_than_raising_out_of_range(index):
    """**RDKit RAISES INSIDE A QT SIGNAL HANDLER.** An index from the
    editor can outrun the structure the model holds -- an erase between
    the click and the read -- and `GetAtomWithIdx` answers that with a
    `RuntimeError`, which is the crash `_atom_is_in_report` already
    exists to prevent one panel along.
    """
    assert element_at(_drawn("CCO"), index) is None


def test_element_at_answers_None_for_nothing_at_all():
    assert element_at(None, 0) is None
    assert element_at("", 0) is None
    assert element_at("not a molblock", 0) is None


# --- the conformer exemption, as the whole matrix --------------------------


def _molecule_with_a_conformer(engine: ChemistryEngine, smiles: str):
    molecule = MoleculeModel(display_name="Test")
    engine.set_structure_from_smiles(molecule, smiles)
    molecule.conformers = [ConformerModel(molblock="geometry", energy=1.0, method="rdkit")]
    return molecule


def test_an_isotope_edit_KEEPS_the_conformers(qapp):
    """**THE ROW THIS BRANCH ADDS.** Labelling an atom C-13 moves no atom,
    breaks no bond and changes no configuration, so every conformer
    remains a valid geometry of the labelled structure -- but canonical
    SMILES carries the mass, so `[13CH3]CO` and `CCO` differ and the
    naive comparison throws the geometry away.
    """
    bus, engine = EventBus(), ChemistryEngine()
    molecule = _molecule_with_a_conformer(engine, "CCO")
    conformer = molecule.conformers[0]
    labelled = set_isotope(molecule.molblock, 0, 13)
    invalidated = []
    bus.subscribe(ConformersInvalidated, lambda e: invalidated.append(e.molecule_uuid))

    QUndoStack().push(EditStructureCommand(engine, molecule, labelled, bus))

    assert "13" in (molecule.canonical_smiles or ""), "the isotope must have landed"
    assert molecule.conformers == [conformer]
    assert invalidated == []


def test_a_CONSTITUTION_change_still_invalidates(qapp):
    """The row that stops the exemption widening into "never invalidate"."""
    bus, engine = EventBus(), ChemistryEngine()
    molecule = _molecule_with_a_conformer(engine, "CCO")
    scratch = MoleculeModel()
    engine.set_structure_from_smiles(scratch, "CCCO")
    invalidated = []
    bus.subscribe(ConformersInvalidated, lambda e: invalidated.append(e.molecule_uuid))

    QUndoStack().push(EditStructureCommand(engine, molecule, scratch.molblock, bus))

    assert molecule.conformers == []
    assert invalidated == [molecule.uuid]


def test_a_STEREO_change_still_invalidates_even_at_an_isotopic_centre(qapp):
    """**THE CASE THAT HAD TO BE MEASURED RATHER THAN ASSUMED.** An
    isotope can CREATE a stereocentre -- H, D, F and Cl on one carbon --
    so stripping the mass labels could in principle make a wedge flip
    invisible and preserve conformers through a genuine mirror image.

    It does not: RDKit keeps the explicit hydrogen and the chiral tag, so
    the two forms still differ after stripping.
    """
    bus, engine = EventBus(), ChemistryEngine()
    molecule = _molecule_with_a_conformer(engine, "[2H][C@](F)(Cl)Br")
    scratch = MoleculeModel()
    engine.set_structure_from_smiles(scratch, "[2H][C@@](F)(Cl)Br")
    assert scratch.canonical_smiles != molecule.canonical_smiles

    QUndoStack().push(EditStructureCommand(engine, molecule, scratch.molblock, bus))

    assert molecule.conformers == []


def test_the_exemption_is_derived_and_so_covers_ketchers_own_dialog(qapp):
    """**A FLAG WOULD HAVE COVERED THE PICKER AND MISSED THE DIALOG BESIDE
    IT.** Ketcher's Atom Properties sets isotopes too -- it stays exactly
    as it is, by decision -- and that route arrives as an ordinary editor
    change with nothing anywhere to mark it as isotope-only.

    So the fixture deliberately does NOT go through `set_isotope`: it is
    a molblock somebody else labelled, which is what the editor sends.
    """
    bus, engine = EventBus(), ChemistryEngine()
    molecule = _molecule_with_a_conformer(engine, "CCO")
    conformer = molecule.conformers[0]

    foreign = Chem.MolFromMolBlock(molecule.molblock, removeHs=False)
    foreign.GetAtomWithIdx(0).SetIsotope(13)

    QUndoStack().push(
        EditStructureCommand(engine, molecule, Chem.MolToMolBlock(foreign), bus)
    )

    assert molecule.conformers == [conformer]


def test_applying_to_every_atom_is_ONE_undo_entry(qapp):
    """Eighteen atoms changing is still one isotope edit, and one Ctrl+Z."""
    bus, engine = EventBus(), ChemistryEngine()
    molecule = MoleculeModel(display_name="Test")
    engine.set_structure_from_smiles(molecule, "c1ccccc1")
    before = molecule.canonical_smiles
    stack = QUndoStack()

    stack.push(
        EditStructureCommand(
            engine, molecule, set_isotope(molecule.molblock, 0, 13, all_of_element=True), bus
        )
    )

    assert stack.count() == 1
    assert (molecule.canonical_smiles or "").count("13") == 6
    stack.undo()
    assert molecule.canonical_smiles == before


# --- the stripping itself ---------------------------------------------------


def test_isotope_free_smiles_removes_every_label():
    assert isotope_free_smiles("[13CH3][13CH2]O") == isotope_free_smiles("CCO")


def test_isotope_free_smiles_keeps_stereochemistry():
    assert isotope_free_smiles("C[C@H](N)O") != isotope_free_smiles("C[C@@H](N)O")


def test_isotope_free_smiles_fails_closed():
    """None on either side means the conformers clear. Keeping geometry
    through an edit nobody could read is the expensive mistake; dropping
    it is the cheap one."""
    assert isotope_free_smiles(None) is None
    assert isotope_free_smiles("this is not a smiles") is None


# --- and the same rule at the window, where the two selections meet --------


@pytest.fixture
def window(qapp, tmp_path):
    """A real MainWindow, because the disagreement being guarded against
    is between two pieces of state only this layer holds at once: the
    element the periodic table is SHOWING and the atom the canvas has
    SELECTED."""
    from openchem.app.main_window import MainWindow
    from openchem.app.session import SessionManager
    from openchem.app.settings import Settings
    from openchem.bootstrap import build_service_container

    services = build_service_container()
    settings = Settings(services.event_bus)
    settings.set("plugins/project_directory", str(tmp_path / "none"))
    settings.set("plugins/user_directory", str(tmp_path / "none"))
    built = MainWindow(services, settings, SessionManager())
    yield built
    built.close()


def _ethanol_in(window):
    molecule = window._current_molecule()
    window._services.chemistry_engine.set_structure_from_smiles(molecule, "CCO")
    return molecule


def test_the_window_writes_the_isotope_through_the_undo_stack(window):
    molecule = _ethanol_in(window)
    window._selected_atom_index = 0
    depth = window._undo_stack.count()

    window._apply_isotope("C", 13, False)

    assert window._undo_stack.count() == depth + 1
    assert "13" in (molecule.canonical_smiles or "")
    window._undo_stack.undo()
    assert "13" not in (molecule.canonical_smiles or "")


def test_the_windows_scope_flag_reaches_the_write(window):
    """**"A 13C LANDED" IS NOT THE CLAIM**, and asserting it let a
    mutation through: hardcoding `all_of_element=True` still puts a 13C on
    the molecule, so the test passed while the default scope had silently
    become every atom. Ethanol has TWO carbons, and counting them is what
    tells the two scopes apart.
    """
    molecule = _ethanol_in(window)
    window._selected_atom_index = 0

    window._apply_isotope("C", 13, False)
    assert (molecule.canonical_smiles or "").count("13") == 1

    window._undo_stack.undo()
    window._apply_isotope("C", 13, True)
    assert (molecule.canonical_smiles or "").count("13") == 2


def test_a_table_showing_one_element_cannot_write_to_another(window):
    """**THE MISTAKE THE SCOPE RULE EXISTS FOR, end to end.** The periodic
    table is showing carbon; the canvas has an oxygen selected. The dialog
    already refuses that pairing, and this is the second of the two -- the
    one a drive script or a plugin would meet.
    """
    molecule = _ethanol_in(window)
    before = molecule.canonical_smiles
    depth = window._undo_stack.count()
    window._selected_atom_index = 2  # the oxygen

    window._apply_isotope("C", 13, True)

    assert molecule.canonical_smiles == before
    assert window._undo_stack.count() == depth, "nothing may reach the undo stack"


def test_with_no_atom_selected_it_says_so_rather_than_guessing(window):
    molecule = _ethanol_in(window)
    before = molecule.canonical_smiles
    depth = window._undo_stack.count()
    window._selected_atom_index = None

    window._apply_isotope("C", 13, False)

    assert molecule.canonical_smiles == before
    assert window._undo_stack.count() == depth
    assert "Select an atom" in window.statusBar().currentMessage()


def test_a_refused_nuclide_reaches_the_status_bar_rather_than_raising(window):
    """`set_isotope` raises; a Qt signal handler that lets it out kills
    the window. C-2 is the case: real as H-2, absent for carbon."""
    _ethanol_in(window)
    depth = window._undo_stack.count()
    window._selected_atom_index = 0

    window._apply_isotope("C", 2, False)

    assert window._undo_stack.count() == depth
    assert "refused" in window.statusBar().currentMessage()
    assert "C-2" in window.statusBar().currentMessage()


def test_the_window_keeps_the_conformers_through_an_isotope_write(window):
    """The end-to-end form of the exemption: generate, label, and the
    geometry is still there."""
    from openchem.domain.conformer import ConformerModel

    molecule = _ethanol_in(window)
    molecule.conformers = [ConformerModel(molblock="geometry", energy=1.0, method="rdkit")]
    window._selected_atom_index = 0

    window._apply_isotope("C", 13, False)

    assert len(molecule.conformers) == 1


def test_selecting_an_atom_reaches_the_open_periodic_table(window):
    """The picker cannot arm itself -- the dialog is non-modal and
    reachable with no molecule open at all, so the window pushes."""
    _ethanol_in(window)
    window._show_periodic_table()
    dialog = window._periodic_table_dialog

    window._on_editor_atom_selected(2)

    assert dialog._selected_atom == ("O", 2)


def test_a_selection_made_while_the_table_was_CLOSED_still_arrives(window):
    """It is pushed on every open, not only on the first: a long-lived
    non-modal window that only ever learned the selection once would sit
    there saying "select an atom first" with one selected."""
    _ethanol_in(window)
    window._on_editor_atom_selected(1)

    window._show_periodic_table()

    assert window._periodic_table_dialog._selected_atom == ("C", 1)


def test_a_decay_product_arms_the_canvas_and_says_what_is_left(window):
    """**THE CANVAS HAS NO ATOM YET**, so the mass number cannot be
    written at this instant -- `insert_requested` arms the atom TOOL and
    the user still places it. Remembering an isotope across a gesture the
    app does not own would land it on whatever gets drawn several actions
    later, which is worse than being asked for it.
    """
    window._show_periodic_table()
    dialog = window._periodic_table_dialog
    dialog.select("U")
    dialog._focus_decay_node(82, 206)

    dialog._insert_decay_nuclide()

    message = window.statusBar().currentMessage()
    assert "Pb-206" in message
    assert "Isotopes tab" in message


# --- the invariant the Ketcher spike was held to ---------------------------


def test_the_isotope_table_is_reachable_without_any_ketcher_change(window):
    """**THE ISOTOPE FEATURE NEVER DEPENDS ON THE EDITOR BUNDLE.**

    The plan for this branch proposed appending `Isotopes...` to Ketcher's
    atom context menu, as an ADDITION on top of an application-owned path
    -- and made that ordering an invariant precisely so the spike could
    come back negative without costing the feature. It did; see the
    commit. These are the doors that need nothing from `main.jsx`.

    Asserted through the real menu bar and the real panel, so a future
    refactor that quietly makes the nuclide table reachable only from the
    canvas fails here.
    """
    # **HOLD THE LIST.** `menuBar().actions()` is a temporary, and
    # releasing it invalidates every wrapper obtained from it -- reading
    # the submenu on the next line raises "Internal C++ object already
    # deleted", which this project has already paid for twice.
    bar_actions = window.menuBar().actions()
    menu = next(
        action.menu()
        for action in bar_actions
        if action.text().replace("&", "") == "Structure"
    )
    labels = [a.text() for a in menu.actions()]

    assert "Isotopes..." in labels
    assert window._atom_inspector_panel._isotopes_button is not None


def test_both_doors_open_the_same_tab_on_the_selected_atoms_element(window):
    """One method behind every door, so they cannot come to mean slightly
    different things."""
    molecule = _ethanol_in(window)
    assert molecule is not None
    window._selected_atom_index = 2  # the oxygen

    window._show_isotopes_for_selection()

    dialog = window._periodic_table_dialog
    assert dialog.selected_symbol() == "O"
    assert dialog._tabs.tabText(dialog._tabs.currentIndex()) == "Isotopes"

    # The inspector's button is the same call, not a parallel one.
    window._show_periodic_table()
    dialog.select("C")
    window._atom_inspector_panel.isotopes_requested.emit()

    assert dialog.selected_symbol() == "O"


def test_it_still_opens_with_no_atom_selected(window):
    """A browsing window that refuses to open because nothing is selected
    is the more annoying of the two behaviours."""
    _ethanol_in(window)
    window._selected_atom_index = None

    window._show_isotopes_for_selection()

    dialog = window._periodic_table_dialog
    assert dialog.isVisible() or dialog._tabs.count() > 0
    assert dialog._tabs.tabText(dialog._tabs.currentIndex()) == "Isotopes"


def test_pressing_insert_really_arms_the_editor(window):
    """**THE PATH ALEX REPORTED AS BROKEN, END TO END.**

    It was not broken -- the button had been pushed 105 px below the
    bottom of the screen by a tab's oversized minimum, so it could not be
    pressed. But nothing in the suite asserted that pressing it reaches
    the canvas at all: the dialog's own tests stop at the signal, and the
    window's wiring of that signal had no guard.

    So this is the half that was missing, not the half that failed.
    """
    armed = []
    window._editor.set_atom_tool = lambda symbol, mass=None: armed.append(symbol)
    window._show_periodic_table()
    dialog = window._periodic_table_dialog
    dialog.select("Na")

    # **LOOK AWAY FROM THE EDITOR FIRST.** Without this the centre tab is
    # already the editor, so "it reveals the editor" holds whether or not
    # anything reveals it -- a mutation deleting the reveal survived.
    window._center_tabs.setCurrentIndex(1)
    assert window._center_tabs.currentWidget() is not window._editor

    dialog._insert_symbol()

    assert armed == ["Na"]
    assert window._center_tabs.currentWidget() is window._editor


def test_the_dialog_stays_open_after_inserting(window):
    """Placing three heteroatoms should not mean reopening the table
    between each -- and a dialog that closed itself would look exactly
    like the button not working."""
    window._editor.set_atom_tool = lambda symbol, mass=None: None
    window._show_periodic_table()
    dialog = window._periodic_table_dialog
    dialog.select("Na")

    dialog._insert_symbol()

    assert dialog.isVisible()


# --- P1 at the window ------------------------------------------------------


def test_arming_reaches_the_editor_with_the_mass_number(window):
    armed = []
    window._editor.set_atom_tool = lambda symbol, mass=None: armed.append((symbol, mass))

    window._arm_element("C", 13)

    assert armed == [("C", 13)]


def test_zero_means_no_isotope_rather_than_isotope_zero(window):
    """A Qt signal cannot carry None, so 0 is the absence -- and it must
    not reach the editor as a mass number of zero."""
    armed = []
    window._editor.set_atom_tool = lambda symbol, mass=None: armed.append((symbol, mass))

    window._arm_element("Na", 0)

    assert armed == [("Na", None)]


def test_the_status_line_says_what_will_be_placed(window):
    """**ARMING IS INVISIBLE**, which is the cost of a click that both
    browses and arms. The wording separates the canvas being primed from
    the table merely showing an element."""
    window._editor.set_atom_tool = lambda symbol, mass=None: None

    window._arm_element("C", 13)

    message = window.statusBar().currentMessage()
    assert "Ready to place" in message
    assert "13C" in message


def test_a_browse_click_does_NOT_yank_the_centre_tab(window):
    """The table is read WHILE working, so arming must not steal the view
    -- that would be worse than the button press it replaces. The
    deliberate button still reveals; this is the browse click.
    """
    window._editor.set_atom_tool = lambda symbol, mass=None: None
    window._show_periodic_table()
    window._center_tabs.setCurrentIndex(1)
    assert window._center_tabs.currentWidget() is not window._editor

    window._periodic_table_dialog._buttons["Na"].click()

    assert window._center_tabs.currentWidget() is not window._editor


def test_the_button_still_reveals_the_editor(window):
    """The control for the test above: the two doors differ in exactly
    one way, and it is this one."""
    window._editor.set_atom_tool = lambda symbol, mass=None: None
    window._show_periodic_table()
    window._center_tabs.setCurrentIndex(1)

    window._insert_element_into_drawing("Na", 0)

    assert window._center_tabs.currentWidget() is window._editor


# --- P3: the right-click menu ----------------------------------------------


def _menu(window, atom_index=0):
    """**BUILT, NEVER SHOWN.** `QMenu.exec` is modal and blocks the whole
    suite -- the first version of these tests ran for 42 minutes on an
    invisible menu, and monkeypatching `exec` did not help because it is a
    C++ slot. `build_atom_context_menu` exists so this can read the menu
    without one ever opening.
    """
    return window.build_atom_context_menu(atom_index)


def test_the_menu_offers_the_three_things_it_promised(window):
    """Isotopes and the Atom Inspector are what Alex asked for; the
    editor's own `Edit...` is what he asked to KEEP, and replacing the
    menu would otherwise have taken it away."""
    _ethanol_in(window)

    labels = [a.text() for a in _menu(window, 0).actions() if a.text()]

    assert any("Isotopes" in text for text in labels)
    assert any("Atom Inspector" in text for text in labels)
    assert any("Edit" in text for text in labels)


def test_the_menu_names_the_element_under_the_cursor(window):
    """It acts on the atom the right-click landed on, so it says which."""
    _ethanol_in(window)

    oxygen = [a.text() for a in _menu(window, 2).actions() if "Isotopes" in a.text()]
    carbon = [a.text() for a in _menu(window, 0).actions() if "Isotopes" in a.text()]

    assert oxygen and "O" in oxygen[0]
    assert carbon and "C" in carbon[0]


def test_the_right_clicked_atom_becomes_the_selection(window):
    """So Isotopes and the Inspector both act on it without being told
    twice -- one selection, three consumers."""
    _ethanol_in(window)

    _menu(window, 2)

    assert window._selected_atom_index == 2
    assert window._selected_atom_element() == "O"


def test_the_editor_edit_item_asks_the_editor_for_that_atom(window):
    """The passthrough that keeps Ketcher's own dialog reachable."""
    opened = []
    window._editor.open_atom_editor = lambda index: opened.append(index)
    _ethanol_in(window)

    menu = _menu(window, 1)
    next(a for a in menu.actions() if "Edit" in a.text()).trigger()

    assert opened == [1]
