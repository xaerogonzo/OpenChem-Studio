"""The spatial-result dialog: routing contract and frame caveat."""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, QEvent

from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.chem.dipole import compute_dipole_moment
from openchem.ui.dialogs.spatial_result_dialog import SpatialResultDialog


def _conformer_mol():
    mol = Chem.AddHs(Chem.MolFromSmiles("CO"))
    params = AllChem.ETKDGv3()
    params.randomSeed = 3
    AllChem.EmbedMolecule(mol, params)
    AllChem.MMFFOptimizeMolecule(mol)
    return mol


def _dispose(dialog) -> None:
    dialog.setParent(None)
    dialog.deleteLater()
    QCoreApplication.sendPostedEvents(dialog, QEvent.Type.DeferredDelete)


def test_the_dialog_hands_the_annotations_to_the_renderer(qapp):
    """The full chain short of pixels: real calculator, real annotation,
    real backend -- the shapes must reach the backend's queue (the page is
    not ready inside a synchronous test, which is exactly the deferral the
    backend exists to handle)."""
    mol = _conformer_mol()
    report = compute_dipole_moment(mol, "u")
    assert report.spatial, "fixture must produce an arrow or this proves nothing"
    dialog = SpatialResultDialog(report, Chem.MolToMolBlock(mol))
    try:
        pending = dialog._backend._pending_shapes
        assert pending is not None and len(pending) == 1
        assert pending[0]["kind"] == "arrow"
        assert pending[0]["vector"] == list(report.spatial[0].vector)
    finally:
        _dispose(dialog)


def test_the_dialog_states_the_stored_conformer_assumption(qapp):
    """The picture must not claim more authority than the result it draws:
    nothing proves the stored conformer is the one the calculator saw, and
    the caveat says so on screen rather than in a docstring."""
    from PySide6.QtWidgets import QLabel

    mol = _conformer_mol()
    report = compute_dipole_moment(mol, "u")
    dialog = SpatialResultDialog(report, Chem.MolToMolBlock(mol))
    try:
        texts = " ".join(label.text() for label in dialog.findChildren(QLabel))
        assert "stored conformer" in texts
        assert "rerun the calculator" in texts
    finally:
        _dispose(dialog)
