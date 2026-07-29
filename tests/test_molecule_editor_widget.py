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

    def load_molblock(self, molblock: str) -> None:
        self.load_calls.append(molblock)

    def get_molblock(self, callback):
        callback(self.load_calls[-1] if self.load_calls else None)

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
