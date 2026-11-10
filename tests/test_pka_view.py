"""pKa viewer: partial states, UUID from the request, series hover, table copy."""

from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QMouseEvent
from rdkit import Chem

from openchem.chem.engine import ChemistryEngine
from openchem.chem.ionisable_sites import ACID
from openchem.chem.pka_sites import PkaSiteRecord, with_site_records
from openchem.domain.common import CacheState, Provenance
from openchem.domain.molecule import MoleculeModel
from openchem.domain.report import LineChartAnnotation, LineSeries
from openchem.domain.report import ReportResult
from openchem.domain.scientific_result import AlertResult, PhCurveResult
from openchem.ui.result_adapters import PKA_VIEW, PKA_VIEW_LABEL, summarise
from openchem.ui.widgets.line_chart_widget import LineChartWidget
from openchem.ui.widgets.results_view import ResultsView, _VIEWER_ACTIONS
from openchem.ui.result_summary import ResultSummaryView
from tests.conftest import dispose


def _acetic():
    engine = ChemistryEngine()
    mol = Chem.MolFromSmiles("CC(=O)O")
    return engine, MoleculeModel(display_name="Acetic acid", molblock=Chem.MolToMolBlock(mol), uuid="acid-1")


def _acid_record(index: int) -> PkaSiteRecord:
    return PkaSiteRecord(index, 4.76, 0.1, ACID, (1, 0), (0, -1))


def _curve(records, uuid="acid-1"):
    from openchem.chem.ph_curves import microspecies_fractions, ph_grid

    grid = ph_grid()
    pkas = [record.pka for record in records]
    rows = [microspecies_fractions(ph, pkas) for ph in grid]
    series = {
        f"Species {index}": [100.0 * row[index] for row in rows]
        for index in range(len(pkas) + 1)
    }
    return PhCurveResult(
        curve_id="pka_microspecies",
        name="Microspecies distribution (%)",
        method="pkasolver",
        molecule_uuid=uuid,
        ph_values=grid,
        series=series,
        y_label="% of total",
        y_min=0.0,
        y_max=100.0,
        provenance=Provenance(
            created_by="core",
            method="pkasolver",
            parameters=with_site_records({"pka_values": pkas}, tuple(records)),
        ),
    )


def test_pka_and_distribution_open_the_pka_view_not_the_inspector():
    records = (_acid_record(3),)
    pka = ReportResult(
        molecule_uuid="acid-1",
        report_id="pka",
        name="pKa",
        category="pka",
        facts=(),
        provenance=Provenance(created_by="core", method="pkasolver", parameters=with_site_records({}, records)),
    )
    view = summarise(pka, result_id="pka", name="pKa", category="pka")
    assert view.rich_view == PKA_VIEW
    curve = summarise(_curve(records), result_id="pka_microspecies", name="Distribution", category="pka")
    assert curve.rich_view == PKA_VIEW and curve.rich_view_label == PKA_VIEW_LABEL
    other = summarise(
        PhCurveResult(curve_id="isoelectric_point", name="pI", method="pkasolver", molecule_uuid="u", ph_values=[0.0], series={"q": [0.0]}),
        result_id="isoelectric_point",
        name="pI",
        category="pka",
    )
    assert other.rich_view == "calculator_inspector"


def test_the_open_request_carries_the_reader_molecule_uuid(qapp):
    window = ResultsView(molecule_uuid="from-compare")
    captured = []
    window.link_activated.connect(captured.append)
    window.set_reports([
        ResultSummaryView(report_id="pka", name="pKa", rich_view="pka_view", molecule_uuid="wrong-one"),
    ])
    window.set_focus("pka")
    window._on_open_clicked()
    assert captured[0].target == "pka_view"
    assert captured[0].params["molecule_uuid"] == "from-compare"
    assert captured[0].params["report_id"] == "pka"
    dispose(window)


def test_pka_only_distribution_only_and_a_refused_ladder(qapp):
    from openchem.ui.dialogs.pka_view_dialog import PkaViewDialog

    engine, molecule = _acetic()
    oxygen = next(
        atom.GetIdx()
        for atom in Chem.MolFromMolBlock(molecule.molblock).GetAtoms()
        if atom.GetSymbol() == "O" and atom.GetTotalNumHs() == 1
    )
    records = (_acid_record(oxygen),)
    pka = ReportResult(
        molecule_uuid=molecule.uuid,
        report_id="pka",
        name="pKa",
        category="pka",
        facts=(),
        provenance=Provenance(created_by="core", method="pkasolver", parameters=with_site_records({}, records)),
    )
    dialog = PkaViewDialog(engine, molecule)
    dialog.set_payload(molecule, pka, None)
    assert "no distribution" in dialog._status.text()
    assert "Pictures need" in dialog.picture_message() or "No distribution" in dialog.picture_message()
    dialog.set_payload(molecule, None, _curve(records, molecule.uuid))
    assert dialog.records()
    assert "Species 0" in dialog.table_text()
    unmapped = (_acid_record(None),)
    dialog.set_payload(molecule, None, _curve(unmapped, molecule.uuid))
    assert "mapped" in dialog.picture_message().lower() or "could not be mapped" in dialog.picture_message().lower()
    failed = AlertResult(
        alert_id="pka", name="pKa", molecule_uuid=molecule.uuid, matched=[],
        cache_state=CacheState.FAILED, error="pkasolver is not configured",
    )
    dialog.set_payload(molecule, failed, None)
    assert "pkasolver" in dialog._status.text()
    dispose(dialog)


def test_series_hover_is_not_inferred_from_ph_alone(qapp):
    grid = [0.0, 7.0, 14.0]
    annotation = LineChartAnnotation(
        series=(
            LineSeries(points=tuple((x, 100.0 if x == 0.0 else 0.0) for x in grid), name="Species 0"),
            LineSeries(points=tuple((x, 100.0 if x == 14.0 else 0.0) for x in grid), name="Species 1"),
        ),
        x_label="pH",
        y_label="%",
        x_descending=False,
        y_min=0.0,
        y_max=100.0,
    )
    widget = LineChartWidget(annotation)
    widget.resize(400, 300)
    widget.show()
    seen = []
    widget.series_hovered.connect(seen.append)
    rect = widget._plot_rect()
    # Middle of the plot, vertically away from both curves (one is at the top, one at the bottom).
    position = QPointF(rect.center().x(), rect.center().y())
    move = QMouseEvent(
        QMouseEvent.Type.MouseMove, position, position,
        Qt.MouseButton.NoButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
    )
    widget.mouseMoveEvent(move)
    assert widget._hover_x is not None
    assert widget.hovered_series() is None
    widget.highlight_series("Species 1")
    assert widget._highlight_series == "Species 1"
    dispose(widget)


def test_pka_view_is_a_literal_viewer_action():
    assert _VIEWER_ACTIONS["pka_view"].target == "pka_view"


def test_a_stored_pka_report_opens_even_without_a_summary_wrapper(qapp):
    window = ResultsView(molecule_uuid="acid-1")
    captured = []
    window.link_activated.connect(captured.append)
    report = ReportResult(
        molecule_uuid="acid-1",
        report_id="pka",
        name="pKa",
        category="pka",
        facts=(),
        provenance=Provenance(created_by="core", method="pkasolver"),
    )
    window.set_reports([report])
    window.set_focus("pka")
    window.show()
    assert window._viewer_for(report) == "pka_view"
    assert window._open_button.isVisible()
    assert window._open_button.text() == "Open pKa view"
    window._on_open_clicked()
    assert captured[0].target == "pka_view"
    assert captured[0].params["molecule_uuid"] == "acid-1"
    dispose(window)
