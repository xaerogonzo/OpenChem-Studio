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


def _molecule_with_conformers(count: int, smiles: str = "CCCCO") -> MoleculeModel:
    """`count` genuinely different conformers.

    FLEXIBLE by default, unlike `_mol`'s methanol: the gallery tests have
    to tell one cell's payload from another's, and methanol's conformers
    superimpose onto each other almost exactly once display alignment has
    run -- so a test asserting "these cells got different geometry" would
    pass or fail on float noise rather than on the routing it names.
    """
    model = MoleculeModel()
    for seed in range(1, count + 1):
        mol = _mol(smiles=smiles, seed=seed)
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


def _axes_report(molecule_uuid: str) -> ReportResult:
    """A SECOND spatial result, from a different real calculator.

    The principal axes rather than another dipole, so "two spatial
    results are registered" is a state a user can actually reach --
    which is what makes the re-request it triggers worth guarding.
    """
    from openchem.chem.geometry_analysis import compute_geometry_analysis

    result = compute_geometry_analysis(_mol(smiles="CCCCO"), molecule_uuid)
    return ReportResult(
        report_id="geometry_analysis",
        name="Geometry Analysis",
        molecule_uuid=molecule_uuid,
        spatial=result.spatial,
        provenance=Provenance(
            created_by="core", method="test", parameters={PARAMETERS_KEY: {}}
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


def test_switching_molecules_mid_flight_does_not_wedge_the_next_one(viewer):
    """The SAME bug as the rejected-result one, through a different early
    return -- and the reason the first fix was incomplete.

    A job in flight for molecule A, the user switches to B, A's answer
    arrives and is correctly discarded. If that discard skipped the
    release, B's cell would stay "running" forever and B's overlay would
    never draw. Measured before the fix: jobs_started stuck at 1 with
    every later request only ever becoming pending.
    """
    widget, _backend, service, pool, _bus = viewer
    first = _molecule_with_two_conformers()
    widget.set_molecule(first)
    widget.note_spatial_report(_dipole_report(first.uuid))
    widget._overlay_check.setChecked(True)
    in_flight = pool.started[-1]

    second = _molecule_with_two_conformers()
    widget.set_molecule(second)
    widget.note_spatial_report(_dipole_report(second.uuid))
    widget._overlay_check.setChecked(True)
    before = len(pool.started)

    in_flight.run()  # molecule A's stale answer
    QCoreApplication.processEvents()
    # NOT "running is None": the release immediately starts whatever was
    # queued, so the cell is legitimately busy again with B's own request.
    # The symptom to assert is that B's work RUNS AT ALL -- measured
    # before the fix, jobs_started stuck at 1 and every later request
    # only ever became pending.
    assert len(pool.started) > before, (
        "molecule B's request never started: the cell was wedged by A's discarded result"
    )

    started_before_step = len(pool.started)
    widget._show_next_conformer()
    for job in list(pool.started[started_before_step - 1 :]):
        job.run()
    QCoreApplication.processEvents()
    assert len(pool.started) >= started_before_step, "the overlay stopped requesting entirely"
    assert service._cells[SINGLE_VIEW_CELL].pending is None, (
        "a request is still queued with nothing running to release it"
    )


# --- the gallery: one conformer per cell, one request per cell ---------------
#
# The machinery underneath these -- `apply_grid_shapes`, the per-cell
# clears, the page's `drawnGridShapes` mirror -- shipped and was
# mutation-verified while NOTHING IN PRODUCTION CALLED IT, because
# `_request_overlay` only ever passed `SINGLE_VIEW_CELL`. So these tests
# are deliberately about the WIRING rather than about the drawing: they
# run the real `SpatialOverlayService` against a fake pool, which makes
# `_refresh_gallery -> _request_overlay -> service.request` the production
# chain end to end. A fake service would have been free to agree with the
# widget about an interface neither of them was using.


class _GalleryBackend(_Backend):
    """The single-view fake plus the gallery, recorded PER CELL.

    Extends `_Backend` rather than `test_molecule_viewer3d_widget`'s
    `GridBackend` because several of these cross between the two modes,
    which share cell 0, and the single-view recording has to keep working
    across the switch.
    """

    def __init__(self) -> None:
        super().__init__()
        self.grids: list[dict] = []
        #: What is on screen per cell RIGHT NOW, honouring clears -- so a
        #: test can ask "what does the gallery show" rather than
        #: reconstructing it from a call log.
        self.cells: dict[int, tuple] = {}
        #: Every per-cell call ever made, for "was this cell ever drawn
        #: on at all", which `cells` cannot answer after a clear.
        self.cell_calls: list[tuple[int, tuple]] = []
        self.cleared_all = 0
        self.left_grid = 0

    def load_conformer_grid(self, entries, rows, cols, linked=False, selected=None):
        self.grids.append({"entries": list(entries), "rows": rows, "cols": cols})

    def apply_grid_shapes(self, cell_index, annotations):
        self.cells[cell_index] = tuple(annotations)
        self.cell_calls.append((cell_index, tuple(annotations)))

    def clear_all_grid_shapes(self):
        self.cleared_all += 1
        self.cells.clear()

    def leave_grid(self) -> None:
        self.left_grid += 1


@pytest.fixture
def gallery(qapp):
    from openchem.chem.engine import ChemistryEngine
    from openchem.services.conformer_service import ConformerService
    from openchem.services.measurement_service import MeasurementService

    bus = EventBus()
    pool = _Pool()
    service = SpatialOverlayService(bus, _registry(), pool=pool)
    backend = _GalleryBackend()
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


#: 2 x 3 is the default gallery, so a page holds six cells and eight
#: conformers give a second page with a DIFFERENT cell-to-conformer map.
_PAGE = 6


def _showing_the_gallery(fixture, count: int = 8):
    """A molecule in the gallery with the overlay on, as a user reaches it."""
    widget, _backend, _service, _pool, _bus = fixture
    molecule = _molecule_with_conformers(count)
    widget.set_molecule(molecule)
    widget.note_spatial_report(_dipole_report(molecule.uuid))
    widget._gallery_check.setChecked(True)
    widget._overlay_check.setChecked(True)
    return molecule


def _requests(pool) -> list[tuple[int, int]]:
    """`(cell_index, conformer_index)` for every job the service started."""
    return [(job._cell_index, job._conformer_index) for job in pool.started]


def _deliver(job) -> None:
    job.run()
    QCoreApplication.processEvents()


def test_every_populated_cell_asks_about_its_own_conformer(gallery):
    """THE MISSING WIRE, as a guard.

    Asserted on the SECOND PAGE on purpose. On page one cell 0 shows
    conformer 0 and cell 5 shows conformer 5, so a widget that confused
    the two indices -- or passed `SINGLE_VIEW_CELL` for everything and
    happened to loop -- could still look right. On page two cell 0 shows
    conformer 6, and only a real cell-to-conformer map produces that.
    """
    widget, _backend, _service, pool, _bus = gallery
    _showing_the_gallery(gallery)
    assert _requests(pool) == [(cell, cell) for cell in range(_PAGE)], (
        "the first page did not ask once per cell for that cell's conformer"
    )

    # Let page one answer first. Otherwise the service correctly holds
    # page two's requests as `pending` -- one running plus one pending
    # per cell is the whole collapse -- and nothing new starts, which
    # says nothing either way about the mapping.
    for job in list(pool.started):
        _deliver(job)

    before = len(pool.started)
    widget._show_next_conformer()  # a PAGE forward, in the gallery
    assert _requests(pool)[before:] == [(0, 6), (1, 7)], (
        "page two asked about the wrong conformers: the cell index was used as "
        "the conformer index, or the page offset was dropped"
    )


def test_each_cell_is_asked_about_its_own_geometry(gallery):
    """The molblock, not just the index -- a correct index paired with one
    shared structure would draw the same arrow six times."""
    _widget, _backend, _service, pool, _bus = gallery
    _showing_the_gallery(gallery)

    molblocks = [job._molblock for job in pool.started]
    assert len(molblocks) == _PAGE
    assert len(set(molblocks)) == _PAGE, (
        "two cells were asked about the same structure, so the gallery would "
        "draw one conformer's geometry on another"
    )


def test_a_cells_answer_is_drawn_on_that_cell_alone(gallery):
    """Per-cell ownership at the widget, mirroring the page-level guard.

    Kills the mutation that routes every arrival to `SINGLE_VIEW_CELL`,
    which is what the code did before this branch.
    """
    _widget, backend, _service, pool, _bus = gallery
    _showing_the_gallery(gallery)
    backend.cells.clear()

    _deliver(pool.started[1])  # cell 1 only
    assert set(backend.cells) == {1}, (
        f"cell 1's answer landed on {sorted(backend.cells)} instead of on cell 1"
    )
    assert backend.cells[1], "cell 1 was cleared rather than drawn on"

    _deliver(pool.started[3])
    assert set(backend.cells) == {1, 3}, "drawing cell 3 disturbed cell 1"


def test_an_answer_for_a_cell_that_has_been_paged_away_is_refused(gallery):
    """Page two has two cells, so cell 5 is no longer on screen.

    Its token is untouched -- paging re-requests only the cells the new
    page has -- so the token check cannot catch this one. The bound
    against the visible page is what does, and this is where it is
    reachable.
    """
    widget, backend, _service, pool, _bus = gallery
    _showing_the_gallery(gallery)
    stale = pool.started[5]  # cell 5, conformer 5

    widget._show_next_conformer()  # page two: cells 0 and 1 only
    backend.cells.clear()

    _deliver(stale)
    assert backend.cells == {}, (
        "an answer for a cell the current page does not have was drawn anyway"
    )


def test_a_rejected_answer_does_not_wedge_its_own_cell(gallery):
    """The per-cell restatement of the release-before-every-rejection rule.

    A stale answer for cell 1 must still free cell 1, or the request
    queued behind it never starts and that cell never draws again -- the
    live bug this project already paid for once in the single view, which
    per-cell routing gives six fresh chances to reintroduce.
    """
    widget, backend, service, pool, _bus = gallery
    _showing_the_gallery(gallery)
    first = pool.started[1]

    # Move the page, which re-requests cell 1 for a different conformer
    # while cell 1's first job is still "running".
    widget._show_next_conformer()
    backend.cells.clear()

    _deliver(first)  # stale, correctly refused
    assert backend.cells == {}, "the stale answer was drawn"

    queued = [job for job in pool.started if job._cell_index == 1][-1]
    _deliver(queued)
    assert set(backend.cells) == {1}, (
        "cell 1 never drew again: a rejected answer left it wedged, so its "
        "queued request could not start"
    )
    assert service._cells[1].pending is None, (
        "a request is still queued for cell 1 with nothing running to release it"
    )


def test_a_result_for_the_previous_page_is_never_drawn_on_this_one(gallery):
    """The state transition the whole page-side machinery exists for.

    Grid A's cells are replaced by grid B's, so an answer computed for A
    describes structures no longer on screen -- and it arrives addressed
    to a cell index grid B also has, which is what makes it dangerous
    rather than merely late.

    **THE WIDGET'S HALF ONLY.** Discarding the shapes already drawn is
    the page's job, through `loadGrid`'s own `gridShapes` reset, and is
    guarded against the real page in `tests/test_spatial_annotations.py`.
    Asserting it here as well only measured the fake.
    """
    widget, backend, _service, pool, _bus = gallery
    _showing_the_gallery(gallery)
    from_page_one = [pool.started[0], pool.started[1]]

    widget._show_next_conformer()
    backend.cells.clear()

    for job in from_page_one:
        _deliver(job)
    assert backend.cells == {}, (
        "conformer 0/1's geometry was drawn onto the cells now showing "
        "conformers 6/7"
    )


def test_leaving_the_gallery_clears_every_cell(gallery):
    widget, backend, _service, pool, _bus = gallery
    _showing_the_gallery(gallery)
    _deliver(pool.started[0])
    _deliver(pool.started[2])
    assert backend.cells, "nothing was drawn, so the clear proves nothing"

    widget._gallery_check.setChecked(False)
    assert backend.cells == {}, "the gallery kept its shapes after being left"
    assert backend.left_grid == 1


def test_switching_the_overlay_off_clears_every_cell(gallery):
    """The single view's version of this already exists. In the gallery
    the same gesture has up to twelve cells to clear, and clearing only
    the one the single view uses would leave five arrows on screen."""
    widget, backend, _service, pool, _bus = gallery
    _showing_the_gallery(gallery)
    _deliver(pool.started[0])
    _deliver(pool.started[4])
    assert len(backend.cells) == 2, "nothing was drawn, so the clear proves nothing"

    widget._overlay_check.setChecked(False)
    assert backend.cells == {}


def test_answers_still_in_flight_when_the_overlay_goes_off_draw_nothing(gallery):
    """The combination this branch newly creates: six jobs outstanding,
    and the user unticks before any of them lands. The producers cannot
    be interrupted, so every one of them still finishes and publishes."""
    widget, backend, _service, pool, _bus = gallery
    _showing_the_gallery(gallery)

    widget._overlay_check.setChecked(False)
    backend.cells.clear()
    for job in list(pool.started):
        _deliver(job)

    assert backend.cells == {}, (
        "an answer requested before the overlay was switched off was drawn after"
    )


def test_a_stale_answer_for_the_SAME_cell_and_conformer_is_refused(gallery):
    """The one case only the token can catch, and it is not hypothetical.

    A second spatial result arriving re-requests every cell. The job
    already in flight was computed from FEWER reports, so if it lands
    afterwards it would replace a complete overlay with an incomplete
    one -- same molecule, same cell, same conformer, so every other
    check passes it.

    Guards the BEHAVIOUR, not a particular line: `_overlay_tokens` and
    `service.accepts` are measured-equivalent (see the comment in
    `_on_spatial_annotations_ready`), so deleting either leaves this
    green. What must never happen is both going.
    """
    widget, backend, service, pool, _bus = gallery
    molecule = _showing_the_gallery(gallery)
    in_flight = pool.started[1]
    stale_token = widget._overlay_tokens[1]

    # A second geometry-carrying result -- a real one, from a real
    # registry calculator -- which re-asks every cell about the very same
    # conformers. This is the ordinary way a user reaches this state:
    # run the dipole, look at the gallery, then run the axes.
    widget.note_spatial_report(_axes_report(molecule.uuid))
    assert widget._overlay_tokens[1] != stale_token, (
        "the re-request did not issue a new token, so this proves nothing"
    )
    assert widget._overlay_conformers[1] == 1, (
        "the cell changed conformer, so the conformer check would catch this "
        "and the token would not be under test"
    )
    backend.cells.clear()

    _deliver(in_flight)
    assert backend.cells == {}, (
        "an answer superseded for the same cell and the same conformer was drawn"
    )
    assert not service.accepts(1, stale_token)


def test_switching_the_overlay_off_leaves_the_gallery_line_describing_the_PAGE(gallery):
    """`_refresh_status` writes the SINGLE VIEW's line.

    Unticking "Show shapes" called it while the gallery was up, so the
    label under six pictures changed to "Conformer 7/8 - +0.62 kcal/mol"
    -- describing one of them, in the wording of a mode that was not on
    screen. Found by driving the app: every unit test read the label and
    none asked what the label was describing.
    """
    widget, _backend, _service, pool, _bus = gallery
    _showing_the_gallery(gallery)
    _deliver(pool.started[0])
    before = widget._status_label.text()
    assert before == f"Conformers 1-{_PAGE} of 8", "the gallery line was wrong already"

    widget._overlay_check.setChecked(False)
    assert widget._status_label.text() == before, (
        "unticking the overlay rewrote the gallery's page line as a single "
        "conformer's"
    )


def test_the_gallery_status_line_carries_no_overlay_value(gallery):
    """DELIBERATE, not an omission. One status line cannot honestly carry
    six values, and the page already draws each cell's own caption beside
    its own arrow -- so the line stays about the page."""
    widget, backend, _service, pool, _bus = gallery
    _showing_the_gallery(gallery)
    _deliver(pool.started[0])

    drawn = backend.cells[0]
    assert drawn, "nothing was drawn, so the absence of its value proves nothing"
    label = drawn[0].label
    assert label, "the arrow carried no label, so this test cannot detect one"
    assert label not in widget._status_label.text()
    assert widget._status_label.text() == f"Conformers 1-{_PAGE} of 8"
