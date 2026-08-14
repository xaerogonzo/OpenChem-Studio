"""The overlay in the viewer: what reaches the screen, and what never does.

The service's own guards cover the token machinery. These cover the
widget's half of the contract -- that a result is drawn only when it
still describes what is on screen, and that stepping a conformer leaves
NOTHING drawn rather than the previous conformer's geometry.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QCoreApplication, QEvent
from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.chem.calculation_input import INPUT_PREFIX
from openchem.chem.dipole import compute_dipole_moment
from openchem.domain.common import Provenance
from openchem.domain.conformer import ConformerModel
from openchem.domain.molecule import MoleculeModel
from openchem.domain.report import ReportResult
from openchem.events.base import EventBus
from openchem.events.events import SpatialAnnotationsReady
from openchem.services.calculator_registry import CalculatorRegistry
from openchem.services.spatial_overlay_service import SINGLE_VIEW_CELL, SpatialOverlayService
from openchem.ui.widgets.molecule_viewer3d_widget import MoleculeViewer3DWidget
from tests.test_molecule_viewer3d_widget import FakeViewerBackend

PARAMETERS_KEY = f"{INPUT_PREFIX}parameters"


class _Backend(FakeViewerBackend):
    """The existing fake, plus a record of what was drawn.

    Subclassed rather than written fresh: `FakeViewerBackend` is a real
    `ViewerBackend` with the signals the widget connects to, and a
    hand-rolled stand-in was missing them.
    """

    def __init__(self) -> None:
        super().__init__()
        self.shapes: list = []

    def load_conformer(self, molblock, structure_key=None):
        super().load_conformer(molblock, structure_key)
        # The real backend DROPS shapes on load, which is what stops the
        # previous conformer's geometry ever being seen on the new one.
        # The fake must too, or a test could pass against a viewer that
        # kept stale geometry.
        self.shapes.append(())

    def apply_shapes(self, annotations):
        self.shapes.append(tuple(annotations))


class _Pool:
    def __init__(self) -> None:
        self.started: list = []

    def start(self, runnable) -> None:
        self.started.append(runnable)


def _mol(smiles="CO", seed=2):
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    params = AllChem.ETKDGv3()
    params.randomSeed = seed
    AllChem.EmbedMolecule(mol, params)
    AllChem.MMFFOptimizeMolecule(mol)
    return mol


def _registry() -> CalculatorRegistry:
    from openchem.chem.descriptor_providers import CALCULATOR_DEFINITIONS

    registry = CalculatorRegistry()
    for definition in CALCULATOR_DEFINITIONS:
        registry.register(definition)
    return registry


def _molecule_with_two_conformers() -> MoleculeModel:
    model = MoleculeModel()
    for seed in (1, 7):
        mol = _mol(seed=seed)
        model.conformers.append(
            ConformerModel(
                molblock=Chem.MolToMolBlock(mol),
                energy=float(seed),
                provenance=Provenance(created_by="core", method="test"),
            )
        )
    return model


def _dipole_report(molecule_uuid: str) -> ReportResult:
    result = compute_dipole_moment(_mol(), molecule_uuid)
    return ReportResult(
        report_id="dipole_moment",
        name="Dipole Moment",
        molecule_uuid=molecule_uuid,
        spatial=result.spatial,
        provenance=Provenance(
            created_by="core", method="test", parameters={PARAMETERS_KEY: {"decimals": 4}}
        ),
    )


@pytest.fixture
def viewer(qapp):
    from openchem.services.conformer_service import ConformerService
    from openchem.services.measurement_service import MeasurementService
    from openchem.chem.engine import ChemistryEngine

    bus = EventBus()
    pool = _Pool()
    service = SpatialOverlayService(bus, _registry(), pool=pool)
    backend = _Backend()
    engine = ChemistryEngine()
    widget = MoleculeViewer3DWidget(
        ConformerService(bus, engine),
        MeasurementService(engine),
        bus,
        backend=backend,
        spatial_overlay_service=service,
    )
    yield widget, backend, service, pool, bus
    widget.setParent(None)
    widget.deleteLater()
    QCoreApplication.sendPostedEvents(widget, QEvent.Type.DeferredDelete)


def test_the_control_stays_off_until_something_has_answered_with_geometry(viewer):
    """A molecule nobody has run a spatial calculator on must cost
    nothing -- conformer stepping is not a tax on everybody."""
    widget, _backend, _service, pool, _bus = viewer
    widget.set_molecule(_molecule_with_two_conformers())
    assert not widget._overlay_check.isEnabled()
    assert pool.started == [], "work was started with no spatial result to recompute"


def test_a_spatial_result_enables_the_control(viewer):
    widget, _backend, _service, _pool, _bus = viewer
    molecule = _molecule_with_two_conformers()
    widget.set_molecule(molecule)
    widget.note_spatial_report(_dipole_report(molecule.uuid))
    assert widget._overlay_check.isEnabled()


def test_stepping_a_conformer_leaves_nothing_drawn_until_the_new_result_lands(viewer):
    """THE KEY SAFETY PROPERTY, and it is about the gap rather than the
    end state: between asking for conformer B and hearing back, the
    viewer must show NO shapes -- never A's, which would be a plausible
    picture of the wrong geometry.
    """
    widget, backend, _service, pool, bus = viewer
    molecule = _molecule_with_two_conformers()
    widget.set_molecule(molecule)
    widget.note_spatial_report(_dipole_report(molecule.uuid))
    widget._overlay_check.setChecked(True)

    # A's result arrives and is drawn.
    pool.started[-1].run()
    drawn = [shapes for shapes in backend.shapes if shapes]
    assert drawn, "conformer A never drew anything, so the next assertion proves nothing"

    # Step to B, and look BEFORE B's job runs.
    backend.shapes.clear()
    widget._show_next_conformer()
    assert backend.shapes and backend.shapes[-1] == (), (
        "after stepping, the viewer still had shapes drawn for the previous conformer"
    )

    # B's result lands and is drawn.
    pool.started[-1].run()
    QCoreApplication.processEvents()
    assert backend.shapes[-1], "conformer B's own annotation never arrived"


def test_a_result_for_a_conformer_no_longer_shown_is_discarded(viewer):
    """The producers cannot be interrupted, so a superseded job finishes
    and publishes anyway. Rejecting it here is the entire mechanism."""
    widget, backend, _service, pool, bus = viewer
    molecule = _molecule_with_two_conformers()
    widget.set_molecule(molecule)
    widget.note_spatial_report(_dipole_report(molecule.uuid))
    widget._overlay_check.setChecked(True)
    stale_token = widget._overlay_tokens[SINGLE_VIEW_CELL]

    widget._show_next_conformer()  # now showing conformer 2
    backend.shapes.clear()

    arrow = compute_dipole_moment(_mol(), molecule.uuid).spatial
    bus.publish(
        SpatialAnnotationsReady(
            molecule_uuid=molecule.uuid,
            structure_key="whatever",
            conformer_index=0,  # the conformer that is no longer shown
            cell_index=SINGLE_VIEW_CELL,
            token=stale_token,
            annotations=arrow,
        )
    )
    QCoreApplication.processEvents()
    assert not any(shapes for shapes in backend.shapes), (
        "a result for the previous conformer was drawn on the current one"
    )


def test_a_current_token_carrying_a_stale_conformer_is_still_refused(viewer):
    """The conformer check, asserted DIRECTLY rather than end to end.

    Every ordinary route bumps the token when the conformer changes, so
    the token check alone catches the stale case and an end-to-end test
    passes with this guard deleted -- measured, the mutation survived
    eight tests. That makes it defence in depth against a future path
    that moves the conformer without re-requesting, not dead code, so it
    is asserted where it can actually be reached: a payload carrying the
    CURRENT token and the wrong conformer index.
    """
    widget, backend, _service, pool, bus = viewer
    molecule = _molecule_with_two_conformers()
    widget.set_molecule(molecule)
    widget.note_spatial_report(_dipole_report(molecule.uuid))
    widget._overlay_check.setChecked(True)
    current_token = widget._overlay_tokens[SINGLE_VIEW_CELL]
    backend.shapes.clear()

    bus.publish(
        SpatialAnnotationsReady(
            molecule_uuid=molecule.uuid,
            structure_key="whatever",
            conformer_index=widget._conformer_index + 1,  # not what is shown
            cell_index=SINGLE_VIEW_CELL,
            token=current_token,  # but still the accepted token
            annotations=compute_dipole_moment(_mol(), molecule.uuid).spatial,
        )
    )
    QCoreApplication.processEvents()
    assert not any(shapes for shapes in backend.shapes), (
        "a payload describing another conformer was drawn because its token matched"
    )


def test_a_result_for_a_different_molecule_is_discarded(viewer):
    widget, backend, _service, _pool, bus = viewer
    molecule = _molecule_with_two_conformers()
    widget.set_molecule(molecule)
    widget.note_spatial_report(_dipole_report(molecule.uuid))
    widget._overlay_check.setChecked(True)
    token = widget._overlay_tokens[SINGLE_VIEW_CELL]
    backend.shapes.clear()

    bus.publish(
        SpatialAnnotationsReady(
            molecule_uuid="a-completely-different-molecule",
            structure_key="whatever",
            conformer_index=0,
            cell_index=SINGLE_VIEW_CELL,
            token=token,
            annotations=compute_dipole_moment(_mol(), "other").spatial,
        )
    )
    QCoreApplication.processEvents()
    assert not any(shapes for shapes in backend.shapes)


def test_switching_molecules_forgets_the_previous_ones_results(viewer):
    widget, _backend, _service, _pool, _bus = viewer
    first = _molecule_with_two_conformers()
    widget.set_molecule(first)
    widget.note_spatial_report(_dipole_report(first.uuid))
    assert widget._overlay_check.isEnabled()

    widget.set_molecule(_molecule_with_two_conformers())
    assert not widget._overlay_check.isEnabled(), (
        "the new molecule inherited the previous one's spatial results"
    )


def test_switching_the_overlay_off_clears_what_is_drawn(viewer):
    widget, backend, _service, pool, _bus = viewer
    molecule = _molecule_with_two_conformers()
    widget.set_molecule(molecule)
    widget.note_spatial_report(_dipole_report(molecule.uuid))
    widget._overlay_check.setChecked(True)
    pool.started[-1].run()
    QCoreApplication.processEvents()

    backend.shapes.clear()
    widget._overlay_check.setChecked(False)
    assert backend.shapes[-1] == ()


def test_the_status_line_reports_the_drawn_arrows_own_value(viewer):
    """From the annotation ACTUALLY DRAWN, never the stored result: the
    panel reports the canonical conformer and this reports the one on
    screen, and the label is what makes that difference legible."""
    widget, _backend, _service, pool, _bus = viewer
    molecule = _molecule_with_two_conformers()
    widget.set_molecule(molecule)
    widget.note_spatial_report(_dipole_report(molecule.uuid))
    widget._overlay_check.setChecked(True)
    pool.started[-1].run()
    QCoreApplication.processEvents()

    event_annotations = widget._backend.shapes[-1]
    assert event_annotations, "nothing was drawn, so the label proves nothing"
    assert event_annotations[0].label in widget._status_label.text()
    assert "Conformer 1/2" in widget._status_label.text()


def test_a_rejected_result_still_releases_the_cell_for_the_next_one(viewer):
    """THE LIVE BUG, as a guard.

    Stepping two conformers quickly means the first step's answer arrives
    when the view has already moved on. It is correctly rejected -- but
    the cell must still be RELEASED, or the second step's request stays
    queued forever and the overlay never draws again. Found by driving
    the app with all nine tests above green: conformer 3 showed no arrow
    and no value, permanently.
    """
    widget, backend, service, pool, _bus = viewer
    molecule = _molecule_with_two_conformers()
    widget.set_molecule(molecule)
    widget.note_spatial_report(_dipole_report(molecule.uuid))
    widget._overlay_check.setChecked(True)

    # The first request is in flight; step, which queues a second.
    first_job = pool.started[-1]
    widget._show_next_conformer()
    assert len(pool.started) == 1, "the second request should be queued, not started"

    # The first answer arrives stale and is rejected.
    backend.shapes.clear()
    first_job.run()
    QCoreApplication.processEvents()
    assert not any(shapes for shapes in backend.shapes), "the stale result was drawn"

    # ...and the queued request must now have started.
    assert len(pool.started) == 2, (
        "a rejected result left the cell wedged: the queued request never ran, so the "
        "overlay would never draw again"
    )
    pool.started[-1].run()
    QCoreApplication.processEvents()
    assert backend.shapes[-1], "the second conformer never got its annotation"
