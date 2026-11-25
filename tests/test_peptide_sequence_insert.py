"""Insert a built peptide through insert_template_molblock on the real Ketcher bundle."""

from __future__ import annotations

import time

from PySide6.QtCore import QCoreApplication
from PySide6.QtGui import QUndoStack
from rdkit import Chem

from openchem.chem.engine import ChemistryEngine
from openchem.chem.peptide_sequence import molblock_from_sequence
from openchem.chem.structure_templates import bounds_2d, molblock_for
from openchem.domain.molecule import MoleculeModel
from openchem.domain.structure_template import TemplateEntry
from openchem.events.base import EventBus
from openchem.ui.widgets.molecule_editor_widget import MoleculeEditorWidget
from tests.test_ketcher_editor_backend import _get_molblock_sync, _ready_backend, _wait_until
from tests.test_template_insert import _wait_callback

_AMIDE = Chem.MolFromSmarts("[CX3](=O)[NX3]")


def _benzene(engine: ChemistryEngine) -> str:
    return molblock_for(TemplateEntry(id="r", name="r", category_id="x", smiles="c1ccccc1"), engine)


def _wait_undo(qapp, stack, before: int, timeout_seconds: float = 8.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while stack.count() == before and time.monotonic() < deadline:
        QCoreApplication.processEvents()
        time.sleep(0.02)


def test_empty_canvas_insert_of_aeg_is_one_undoable_peptide(qapp):
    engine = ChemistryEngine()
    backend = _ready_backend(qapp)
    bus = EventBus()
    stack = QUndoStack()
    widget = MoleculeEditorWidget(engine, bus, stack, backend=backend)
    molecule = MoleculeModel(display_name="Empty")
    widget.set_molecule(molecule)
    _wait_until(qapp, lambda: False, timeout_seconds=0.8)
    before = stack.count()
    peptide = molblock_from_sequence("AEG").molblock
    error = _wait_callback(qapp, lambda cb: widget.insert_template_molblock(peptide, cb))
    assert error is None
    _wait_undo(qapp, stack, before)
    assert stack.count() == before + 1
    returned = _get_molblock_sync(qapp, backend, timeout_seconds=10) or ""
    mol = Chem.MolFromMolBlock(returned)
    assert mol is not None
    assert len(Chem.GetMolFrags(mol)) == 1
    assert mol.GetNumHeavyAtoms() == 19
    assert len(mol.GetSubstructMatches(_AMIDE)) == 2
    assert Chem.MolToInchiKey(mol) == "PAIHPOGPJVUFJY-WDSKDSINSA-N"
    original = molecule.canonical_smiles
    stack.undo()
    assert molecule.canonical_smiles != original or molecule.molblock in (None, "")
    stack.redo()
    assert molecule.canonical_smiles == original


def test_occupied_canvas_keeps_the_original_and_adds_a_separate_peptide(qapp):
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
    canvas = _benzene(engine)
    peptide = molblock_from_sequence("AEG").molblock
    error = _wait_callback(qapp, lambda cb: widget.insert_template_molblock(peptide, cb))
    assert error is None
    deadline = time.monotonic() + 8.0
    while (stack.count() == before or molecule.canonical_smiles == before_smiles) and time.monotonic() < deadline:
        QCoreApplication.processEvents()
        time.sleep(0.02)
    assert stack.count() == before + 1
    returned = _get_molblock_sync(qapp, backend, timeout_seconds=10) or ""
    mol = Chem.MolFromMolBlock(returned)
    assert mol is not None
    frags = Chem.GetMolFrags(mol, asMols=True)
    assert len(frags) == 2
    heavies = sorted(f.GetNumHeavyAtoms() for f in frags)
    assert heavies == [6, 19]
    amides = [len(f.GetSubstructMatches(_AMIDE)) for f in frags]
    assert 2 in amides
    box = bounds_2d(returned)
    canvas_box = bounds_2d(canvas)
    assert box is not None and canvas_box is not None
    assert box[1] - box[0] > canvas_box[1] - canvas_box[0]
    stack.undo()
    assert molecule.canonical_smiles == before_smiles
    stack.redo()
    assert molecule.canonical_smiles != before_smiles


def test_two_and_ten_residue_peptides_insert_as_one_component(qapp):
    engine = ChemistryEngine()
    backend = _ready_backend(qapp)
    bus = EventBus()
    stack = QUndoStack()
    widget = MoleculeEditorWidget(engine, bus, stack, backend=backend)
    for text, n, heavy in (("AG", 2, 10), ("ACDEFGHIKL", 10, 79)):
        molecule = MoleculeModel(display_name=text)
        widget.set_molecule(molecule)
        _wait_until(qapp, lambda: False, timeout_seconds=0.8)
        before = stack.count()
        error = _wait_callback(
            qapp, lambda cb, t=text: widget.insert_template_molblock(molblock_from_sequence(t).molblock, cb)
        )
        assert error is None
        _wait_undo(qapp, stack, before)
        returned = _get_molblock_sync(qapp, backend, timeout_seconds=10) or ""
        mol = Chem.MolFromMolBlock(returned)
        assert mol is not None, text
        assert len(Chem.GetMolFrags(mol)) == 1, text
        assert mol.GetNumHeavyAtoms() == heavy, text
        assert len(mol.GetSubstructMatches(_AMIDE)) == n - 1, text
        backend.load_molblock("")
        _wait_until(qapp, lambda: False, timeout_seconds=0.5)
