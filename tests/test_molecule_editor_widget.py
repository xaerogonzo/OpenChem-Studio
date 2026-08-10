from __future__ import annotations

from PySide6.QtGui import QUndoStack
from PySide6.QtWidgets import QWidget

from openchem.chem.engine import ChemistryEngine
from openchem.domain.molecule import MoleculeModel
from openchem.events.base import EventBus
from openchem.ui.editor_backend import EditorBackend
from openchem.ui.widgets.molecule_editor_widget import MoleculeEditorWidget


class _RecordingEditorBackend(EditorBackend):
    """Minimal in-memory stand-in for KetcherEditorBackend -- no
    QWebEngineView involved, just records what MoleculeEditorWidget asks it
    to do. Exercises the real (inherited) `EditorBackend.clear()` default,
    not an override, so these tests cover the actual production code path.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._widget = QWidget(parent)
        self.load_calls: list[str] = []
        self.render_option_calls: list[tuple[str, object]] = []
        self.toolbar_action_calls: list[str] = []
        self.atom_tool_calls: list[str] = []

    def load_molblock(self, molblock: str) -> None:
        self.load_calls.append(molblock)

    def get_molblock(self, callback):
        callback(self.load_calls[-1] if self.load_calls else None)

    def set_render_option(self, name, value):
        self.render_option_calls.append((name, value))

    def trigger_toolbar_action(self, action_id):
        self.toolbar_action_calls.append(action_id)

    def set_atom_tool(self, symbol):
        self.atom_tool_calls.append(symbol)

    def widget(self):
        return self._widget


def _make_widget():
    engine = ChemistryEngine()
    bus = EventBus()
    undo_stack = QUndoStack()
    backend = _RecordingEditorBackend()
    widget = MoleculeEditorWidget(engine, bus, undo_stack, backend=backend)
    return engine, widget, backend


def test_editor_backend_default_clear_delegates_to_load_molblock_empty(qapp):
    backend = _RecordingEditorBackend()
    backend.clear()
    assert backend.load_calls == [""]


def test_set_molecule_with_structure_loads_its_molblock(qapp):
    engine, widget, backend = _make_widget()
    molecule = MoleculeModel()
    engine.set_structure_from_smiles(molecule, "CCO")

    widget.set_molecule(molecule)

    assert backend.load_calls == [molecule.molblock]


def test_set_molecule_none_clears_the_canvas(qapp):
    _, widget, backend = _make_widget()
    backend.load_molblock("some previously-drawn structure")

    widget.set_molecule(None)

    assert backend.load_calls[-1] == ""


def test_set_molecule_with_no_structure_clears_instead_of_leaving_stale_content(qapp):
    """Regression test for the 'phantom structure' bug: switching to a
    freshly-created molecule with no molblock yet used to silently no-op,
    leaving whatever was drawn before this molecule was selected still
    visible on the canvas."""
    _, widget, backend = _make_widget()
    backend.load_molblock("leftover drawing from before a molecule existed")

    molecule = MoleculeModel(display_name="New molecule")  # no molblock
    widget.set_molecule(molecule)

    assert backend.load_calls[-1] == ""


def test_editing_is_no_longer_silently_discarded_once_a_molecule_is_selected(qapp):
    """Root cause of 'nothing works until File > New Molecule': edits are
    only ever silently dropped when self._molecule is None. Once a molecule
    is selected (even one auto-created with no structure), editing must
    actually apply."""
    engine, widget, backend = _make_widget()
    molecule = MoleculeModel(display_name="New molecule")
    widget.set_molecule(molecule)

    backend.load_molblock(engine.mol_to_molblock(engine.mol_from_smiles("CCO")))
    widget._on_editor_edited()

    assert molecule.molblock is not None


def test_set_render_option_delegates_to_the_backend(qapp):
    _, widget, backend = _make_widget()

    widget.set_render_option("showHydrogenLabels", "All")

    assert backend.render_option_calls == [("showHydrogenLabels", "All")]


def test_trigger_toolbar_action_delegates_to_the_backend(qapp):
    _, widget, backend = _make_widget()

    widget.trigger_toolbar_action("Add/Remove explicit hydrogens button")

    assert backend.toolbar_action_calls == ["Add/Remove explicit hydrogens button"]


# --- the canvas must follow changes it did not make -------------------------


def _widget_with_molecule():
    engine, widget, backend = _make_widget()
    molecule = MoleculeModel(display_name="Test")
    widget.set_molecule(molecule)
    return engine, widget, backend, molecule


def _external_edit(widget, engine, molecule, smiles):
    """Change the model the way Paste Structure does: through a command,
    not through the editor."""
    from rdkit import Chem

    from openchem.commands.molecule_commands import EditStructureCommand

    molblock = Chem.MolToMolBlock(Chem.MolFromSmiles(smiles))
    widget._undo_stack.push(
        EditStructureCommand(engine, molecule, molblock, widget._event_bus)
    )


def test_undo_reloads_the_canvas(qapp):
    """The bug this exists for.

    `EditStructureCommand` reverts the model and publishes MoleculeChanged;
    nothing was listening, so pasting a structure and pressing Ctrl+Z
    emptied the molecule while the editor went on drawing it. Confirmed
    live: Properties read mol_wt 0 with a blank formula and aspirin was
    still on screen.
    """
    engine, widget, backend, molecule = _widget_with_molecule()
    _external_edit(widget, engine, molecule, "CC(=O)Oc1ccccc1C(=O)O")
    after_paste = len(backend.load_calls)

    widget._undo_stack.undo()

    assert not molecule.canonical_smiles
    assert len(backend.load_calls) > after_paste, "the model reverted and the canvas was not told"
    assert backend.load_calls[-1] == "", "an emptied molecule must clear the canvas"


def test_redo_reloads_the_canvas(qapp):
    engine, widget, backend, molecule = _widget_with_molecule()
    _external_edit(widget, engine, molecule, "C1CN1")
    widget._undo_stack.undo()
    before = len(backend.load_calls)

    widget._undo_stack.redo()

    assert molecule.canonical_smiles == "C1CN1"
    assert len(backend.load_calls) > before


def test_the_users_own_edit_does_not_reload_the_canvas(qapp):
    """THIS MATTERS MORE THAN THE FIX ITSELF.

    Reloading on every MoleculeChanged would pull the drawing out from
    under someone mid-structure. The comparison is on constitution, so the
    model holding what the user just drew is a no-op here.
    """
    from rdkit import Chem

    engine, widget, backend, molecule = _widget_with_molecule()
    backend.load_calls.append(Chem.MolToMolBlock(Chem.MolFromSmiles("CCO")))
    before = len(backend.load_calls)

    widget._on_editor_edited()

    assert molecule.canonical_smiles == "CCO"
    assert len(backend.load_calls) == before, "reloaded the canvas during the user own edit"


def test_a_change_to_another_molecule_is_ignored(qapp):
    from openchem.events.events import MoleculeChanged

    engine, widget, backend, molecule = _widget_with_molecule()
    before = len(backend.load_calls)

    widget._event_bus.publish(MoleculeChanged(molecule_uuid="a-different-molecule"))
    qapp.processEvents()

    assert len(backend.load_calls) == before


def test_the_widget_forwards_the_editors_intercepted_controls(qapp):
    """Ketcher's own toolbar controls are answered by the APPLICATION, so
    each request has to survive the trip backend -> widget -> window.
    Forwarded straight through, which makes a break here silent: the
    button simply stops doing anything at all.

    The ACTION NAME is asserted, not merely that something arrived --
    every one of these travels on the same signal, so a forwarder that
    dropped or rewrote the payload would route every control to whichever
    handler happened to be first.
    """
    _engine, widget, backend = _make_widget()
    seen: list[str] = []
    widget.editor_action_requested.connect(seen.append)

    for action in ("periodic_table", "import", "export", "about", "help", "viewer_3d",
                   "undo", "redo"):
        backend.editor_action_requested.emit(action)

    assert seen == ["periodic_table", "import", "export", "about", "help", "viewer_3d",
                    "undo", "redo"]


def test_the_widget_arms_the_canvas_with_a_chosen_element(qapp):
    """"Insert into drawing" reaches the backend as an atom tool."""
    _engine, widget, backend = _make_widget()

    widget.set_atom_tool("Fe")

    assert backend.atom_tool_calls == ["Fe"]
