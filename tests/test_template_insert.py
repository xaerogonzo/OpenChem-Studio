"""Insert a template through EditorBackend.add_fragment on the real Ketcher bundle."""

from __future__ import annotations

import time

from PySide6.QtCore import QCoreApplication
from PySide6.QtGui import QUndoStack

from openchem.chem.engine import ChemistryEngine
from openchem.chem.structure_templates import bounds_2d, molblock_for, place_to_the_right
from openchem.domain.molecule import MoleculeModel
from openchem.domain.structure_template import TemplateEntry
from openchem.events.base import EventBus
from openchem.ui.widgets.ketcher_editor_backend import KetcherEditorBackend
from openchem.ui.widgets.molecule_editor_widget import MoleculeEditorWidget
from tests.test_ketcher_editor_backend import (
    _get_molblock_sync,
    _ready_backend,
    _run_js,
    _wait_until,
)


def _benzene(engine: ChemistryEngine) -> str:
    return molblock_for(TemplateEntry(id="r", name="r", category_id="x", smiles="c1ccccc1"), engine)


def _pyridine(engine: ChemistryEngine) -> str:
    return molblock_for(TemplateEntry(id="p", name="p", category_id="x", smiles="c1ccncc1"), engine)


def _wait_callback(qapp, action, timeout_seconds: float = 10):
    result: dict[str, object] = {}
    action(lambda error: result.__setitem__("error", error))
    _wait_until(qapp, lambda: "error" in result, timeout_seconds=timeout_seconds)
    return result.get("error")


def test_add_fragment_refuses_when_the_editor_is_not_ready(qapp):
    backend = KetcherEditorBackend()
    assert not backend._ketcher_ready
    errors = []
    backend.add_fragment("anything", errors.append)
    assert errors == ["The 2D editor is still loading."]


def test_add_fragment_exists_on_the_vendored_ketcher(qapp):
    backend = _ready_backend(qapp)
    assert _run_js(qapp, backend, "typeof window.ketcher.addFragment") == "function"


def test_add_fragment_on_an_occupied_canvas_keeps_the_original_and_does_not_overlap(qapp):
    engine = ChemistryEngine()
    backend = _ready_backend(qapp)
    canvas = _benzene(engine)
    fragment = place_to_the_right(canvas, _pyridine(engine))
    backend.load_molblock(canvas)
    _wait_until(qapp, lambda: False, timeout_seconds=1.0)
    fired = []
    backend.edited.connect(lambda: fired.append(True))
    error = _wait_callback(qapp, lambda cb: backend.add_fragment(fragment, cb))
    assert error is None
    deadline = time.monotonic() + 5.0
    while not fired and time.monotonic() < deadline:
        QCoreApplication.processEvents()
        time.sleep(0.02)
    assert len(fired) == 1
    combined = _get_molblock_sync(qapp, backend, timeout_seconds=10) or ""
    mol = engine.mol_from_molblock(combined)
    assert mol.GetNumAtoms() >= 11
    box = bounds_2d(combined)
    canvas_box = bounds_2d(canvas)
    assert box is not None and canvas_box is not None
    assert box[1] - box[0] > canvas_box[1] - canvas_box[0]


def test_add_fragment_on_an_empty_canvas_is_one_undoable_edit(qapp):
    engine = ChemistryEngine()
    backend = _ready_backend(qapp)
    bus = EventBus()
    stack = QUndoStack()
    widget = MoleculeEditorWidget(engine, bus, stack, backend=backend)
    molecule = MoleculeModel(display_name="Empty")
    widget.set_molecule(molecule)
    _wait_until(qapp, lambda: False, timeout_seconds=0.8)
    before = stack.count()
    error = _wait_callback(
        qapp, lambda cb: widget.insert_template_molblock(_benzene(engine), cb)
    )
    assert error is None
    deadline = time.monotonic() + 8.0
    while stack.count() == before and time.monotonic() < deadline:
        QCoreApplication.processEvents()
        time.sleep(0.02)
    assert stack.count() == before + 1
    original = molecule.canonical_smiles
    stack.undo()
    assert molecule.canonical_smiles != original or molecule.molblock in (None, "")
    stack.redo()
    assert molecule.canonical_smiles == original


def test_inserting_onto_a_drawing_undoes_in_one_step(qapp):
    engine = ChemistryEngine()
    backend = _ready_backend(qapp)
    bus = EventBus()
    stack = QUndoStack()
    widget = MoleculeEditorWidget(engine, bus, stack, backend=backend)
    molecule = MoleculeModel(display_name="Benzene")
    engine.set_structure_from_smiles(molecule, "c1ccccc1")
    widget.set_molecule(molecule)
    _wait_until(qapp, lambda: False, timeout_seconds=1.0)
    before_smiles = molecule.canonical_smiles
    before = stack.count()
    error = _wait_callback(
        qapp, lambda cb: widget.insert_template_molblock(_pyridine(engine), cb)
    )
    assert error is None
    deadline = time.monotonic() + 8.0
    while (stack.count() == before or molecule.canonical_smiles == before_smiles) and time.monotonic() < deadline:
        QCoreApplication.processEvents()
        time.sleep(0.02)
    assert stack.count() == before + 1
    assert molecule.canonical_smiles != before_smiles
    inserted = molecule.molblock
    stack.undo()
    assert molecule.canonical_smiles == before_smiles
    assert stack.canRedo()
    # Live MainWindow drive: Ketcher's getMolfile still returned the insert
    # ~1 s after Undo, and applying it pushed a new command that discarded
    # Redo. That molfile must not become a command, immediately or after
    # the delay the drive saw.
    widget.apply_edited_molblock(inserted)
    assert molecule.canonical_smiles == before_smiles
    assert stack.canRedo()
    # The live window applied the insert ~3 s after Undo, after the 2 s
    # suppress window. Redo still being available must drop it too.
    settle = time.monotonic() + 3.0
    while time.monotonic() < settle:
        QCoreApplication.processEvents()
        time.sleep(0.02)
    widget.apply_edited_molblock(inserted)
    assert molecule.canonical_smiles == before_smiles
    assert stack.canRedo()
    stack.redo()
    assert molecule.canonical_smiles != before_smiles


def test_two_successive_inserts_each_add_one_undo_step(qapp):
    engine = ChemistryEngine()
    backend = _ready_backend(qapp)
    bus = EventBus()
    stack = QUndoStack()
    widget = MoleculeEditorWidget(engine, bus, stack, backend=backend)
    molecule = MoleculeModel(display_name="Empty")
    widget.set_molecule(molecule)
    _wait_until(qapp, lambda: False, timeout_seconds=0.8)
    before = stack.count()
    assert _wait_callback(qapp, lambda cb: widget.insert_template_molblock(_benzene(engine), cb)) is None
    deadline = time.monotonic() + 8.0
    while stack.count() == before and time.monotonic() < deadline:
        QCoreApplication.processEvents()
        time.sleep(0.02)
    after_first = stack.count()
    assert after_first == before + 1
    assert _wait_callback(qapp, lambda cb: widget.insert_template_molblock(_pyridine(engine), cb)) is None
    deadline = time.monotonic() + 8.0
    while stack.count() == after_first and time.monotonic() < deadline:
        QCoreApplication.processEvents()
        time.sleep(0.02)
    assert stack.count() == after_first + 1
