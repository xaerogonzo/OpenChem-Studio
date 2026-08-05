"""The Batch panel and the analysis dialog.

The panel is mostly wiring, and the parts worth testing are the ones that
look right and are not: a numeric column that sorts as text, a header that
collides with another, an inert checkbox for a calculator that cannot be
run this way, and an analysis dialog that offers a column it cannot plot.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, Qt, QThreadPool
from PySide6.QtWidgets import QApplication

from openchem.bootstrap import build_service_container
from openchem.domain.molecule import MoleculeModel
from openchem.domain.project import ProjectModel
from openchem.ui.dialogs.batch_analysis_dialog import BatchAnalysisDialog
from openchem.ui.panels.batch_panel import BatchPanel

_DRUGS = [
    ("aspirin", "CC(=O)Oc1ccccc1C(=O)O"),
    ("caffeine", "Cn1cnc2c1c(=O)n(C)c(=O)n2C"),
    ("ibuprofen", "CC(C)Cc1ccc(cc1)C(C)C(=O)O"),
    ("paracetamol", "CC(=O)Nc1ccc(O)cc1"),
    ("naproxen", "COc1ccc2cc(ccc2c1)C(C)C(=O)O"),
]


@pytest.fixture
def services(qapp):
    return build_service_container()


@pytest.fixture
def project(services):
    project = ProjectModel(name="test")
    for name, smiles in _DRUGS:
        molecule = MoleculeModel(display_name=name)
        services.chemistry_engine.set_structure_from_smiles(molecule, smiles)
        project.molecules.append(molecule)
    return project


@pytest.fixture
def widgets():
    """Every widget a test builds, destroyed deterministically after it.

    THIS IS NOT TIDINESS. Left to Python's collector, an unparented widget
    from an earlier test is destroyed at an arbitrary later moment, and the
    `processEvents()` these tests need in order to receive the batch's
    queued events then drains a `DeferredDelete` posted against an object
    whose wrapper has already gone. Measured: a straight access violation
    inside `processEvents`, reproducing on 3 of 3 full runs of this file
    but on only some subsets, because whether it fires depends on when the
    collector happened to run.

    Flushed PER WIDGET, never as `sendPostedEvents(None, DeferredDelete)` --
    the global form drains every pending deferred delete in the process,
    including ones other test files left queued, which is the same
    double-free `tests/conftest.py` documents for web engine views.
    """
    built = []
    yield built
    for widget in built:
        widget.setParent(None)
        widget.deleteLater()
        QCoreApplication.sendPostedEvents(widget, QEvent.Type.DeferredDelete)


@pytest.fixture
def panel(services, project, widgets):
    panel = BatchPanel(
        services.batch_service,
        services.calculator_registry,
        services.table_export_service,
        services.event_bus,
        services.chemistry_engine,
    )
    panel.set_project(project)
    widgets.append(panel)
    return panel


def _run(panel, identifiers):
    """Run a batch and let its queued events reach the panel.

    `processEvents` is required rather than defensive: `EventBus.publish`
    is a queued Qt signal, so the progress events raised on the worker
    thread are still in the GUI thread's queue when `waitForDone` returns
    and the panel has not seen any of them yet.
    """
    for identifier in identifiers:
        panel.check(identifier)
    panel._run()
    QThreadPool.globalInstance().waitForDone(120000)
    QApplication.instance().processEvents()
    return panel.table()


def _dialog(widgets, table, services, project) -> BatchAnalysisDialog:
    dialog = BatchAnalysisDialog(table, services.chemistry_engine, project)
    widgets.append(dialog)
    return dialog


# --- the picker ---------------------------------------------------------


def test_the_picker_offers_descriptors_alerts_and_calculators(panel):
    headings = {
        panel._tree.topLevelItem(index).text(0) for index in range(panel._tree.topLevelItemCount())
    }
    assert headings == {"Descriptors", "Structural alerts", "Calculators"}


def test_discovery_only_calculators_are_not_offered(panel):
    """Docking and ORCA run through their own panels. A checkbox for them
    here would be an inert control, which this project has already decided
    is worse than a missing one."""
    offered = {identifier for _item, (_kind, identifier) in panel._leaves()}
    assert "docking.vina" not in offered
    assert not any(identifier.startswith("orca.") for identifier in offered)
    assert "topology_analysis" in offered


def test_selecting_separates_descriptors_from_calculators(panel):
    panel.check("mol_wt")
    panel.check("pains")
    panel.check("topology_analysis")
    descriptors, calculators = panel.selected_ids()
    assert set(descriptors) == {"mol_wt", "pains"}
    assert calculators == ["topology_analysis"]


def test_the_filter_hides_non_matching_properties(panel):
    panel._filter.setText("wiener")
    hidden = {
        item.text(0) for item, _payload in panel._leaves() if item.isHidden()
    }
    assert "Molecular Weight" not in [
        item.text(0) for item, _payload in panel._leaves() if not item.isHidden()
    ]
    assert hidden


def test_a_group_with_nothing_matching_is_hidden_too(panel):
    """A heading left above zero children reads as a category that produced
    no results, which is a different and wrong statement."""
    panel._filter.setText("zzzzznothing")
    assert all(
        panel._tree.topLevelItem(index).isHidden()
        for index in range(panel._tree.topLevelItemCount())
    )


def test_clearing_the_selection_unticks_everything(panel):
    panel.check("mol_wt")
    panel._clear_selection()
    assert panel.selected_ids() == ([], [])


# --- the run and the table ---------------------------------------------


def test_a_run_fills_the_grid(panel, project):
    _run(panel, ["mol_wt", "mol_logp", "tpsa"])
    assert panel._results.rowCount() == len(project.molecules)
    assert panel._results.columnCount() == 4  # molecule name + three


def test_export_and_analysis_stay_disabled_until_there_are_results(panel):
    assert not panel._csv_button.isEnabled()
    assert not panel._analyse_button.isEnabled()
    _run(panel, ["mol_wt"])
    assert panel._csv_button.isEnabled()
    assert panel._analyse_button.isEnabled()


def test_a_numeric_column_sorts_as_numbers_not_as_text(panel):
    """`QTableWidget` sorts by the displayed string by default, so 1240
    sorts before 565. This is why the cells are a QTableWidgetItem subclass
    with its own `__lt__`."""
    table = _run(panel, ["topology_analysis"])
    column_id = "calculator:topology_analysis:Hyper Wiener index"
    index = 1 + [column.column_id for column in table.columns].index(column_id)
    panel._results.sortItems(index, Qt.SortOrder.AscendingOrder)
    shown = [float(panel._results.item(row, index).text()) for row in range(panel._results.rowCount())]
    assert shown == sorted(shown)
    # And the text order really would have been different -- otherwise this
    # test would pass against the broken behaviour it exists to catch.
    assert [str(int(value)) for value in shown] != sorted(str(int(value)) for value in shown)


def test_a_cell_carries_its_provenance_as_a_tooltip(panel):
    """A column header cannot say "computed by this method with these
    parameters" for 200 different runs; a cell can."""
    _run(panel, ["mol_wt"])
    tooltip = panel._results.item(0, 1).toolTip()
    assert "Method: core / rdkit" in tooltip


def test_a_column_header_says_where_it_came_from(panel):
    _run(panel, ["topology_analysis"])
    assert "calculator" in panel._results.horizontalHeaderItem(1).toolTip()


def test_the_prediction_basis_survives_tabulation(panel):
    """The single-molecule view badges empirical results. Losing that in a
    table of 200 rows is exactly the failure mode this panel had to avoid."""
    table = _run(panel, ["polarizability"])
    columns = [column for column in table.columns if column.source_id == "polarizability"]
    assert columns and all(column.prediction_basis == "empirical" for column in columns)


# --- the analysis dialog -----------------------------------------------


def test_the_dialog_offers_only_numeric_columns(panel, services, project, widgets):
    table = _run(panel, ["mol_wt", "mol_logp", "formula"])
    dialog = _dialog(widgets, table, services, project)
    offered = {dialog._x_combo.itemText(i) for i in range(dialog._x_combo.count())}
    assert "Molecular Formula" not in offered
    assert "Molecular Weight (g/mol)" in offered


def test_the_dialog_states_the_coefficient_and_the_sample_size(panel, services, project, widgets):
    table = _run(panel, ["mol_wt", "heavy_atom_count"])
    dialog = _dialog(widgets, table, services, project)
    caption = dialog._scatter._caption
    assert "Pearson r" in caption and "n = 5" in caption


def test_correlating_against_everything_ranks_by_strength(panel, services, project, widgets):
    """The confound check. A predicted property whose top correlate is
    molecular weight is measuring size."""
    table = _run(panel, ["mol_wt", "heavy_atom_count", "labute_asa", "tpsa"])
    dialog = _dialog(widgets, table, services, project)
    dialog._y_combo.setCurrentIndex(
        [dialog._y_combo.itemText(i) for i in range(dialog._y_combo.count())].index(
            "Molecular Weight (g/mol)"
        )
    )
    dialog._rank_against_everything()
    strengths = [
        abs(float(dialog._ranking.item(row, 1).text())) for row in range(dialog._ranking.rowCount())
    ]
    assert strengths == sorted(strengths, reverse=True)
    # Size descriptors are what molecular weight tracks, and the tool has to
    # be able to say so.
    assert strengths[0] > 0.9


def test_the_projection_names_what_dominates_each_axis(panel, services, project, widgets):
    """PC1 is not "PC1", it is whatever combination it turned out to be."""
    table = _run(panel, ["mol_wt", "mol_logp", "tpsa", "num_hbd", "qed", "heavy_atom_count"])
    dialog = _dialog(widgets, table, services, project)
    assert "PC1 is dominated by:" in dialog._space_note.text()
    assert "%" in dialog._space_scatter._caption  # explained variance


def test_clustering_colours_the_projection(panel, services, project, widgets):
    table = _run(panel, ["mol_wt", "mol_logp", "tpsa", "num_hbd", "qed", "heavy_atom_count"])
    dialog = _dialog(widgets, table, services, project)
    assert all(point.group is None for point in dialog._space_scatter.points())
    dialog._run_clustering()
    assert dialog._cluster_table.rowCount() == len(project.molecules)
    assert any(point.group is not None for point in dialog._space_scatter.points())


def test_the_distribution_tab_reports_the_statistics(panel, services, project, widgets):
    table = _run(panel, ["mol_wt"])
    dialog = _dialog(widgets, table, services, project)
    note = dialog._stat_note.text()
    assert "n = 5" in note and "median" in note


def test_a_table_with_nothing_numeric_says_why_rather_than_opening_empty_tabs(
    panel, services, project, widgets
):
    table = _run(panel, ["formula"])
    from PySide6.QtWidgets import QLabel

    dialog = _dialog(widgets, table, services, project)
    assert not hasattr(dialog, "_tabs")
    assert any(
        "No numeric columns" in label.text() for label in dialog.findChildren(QLabel)
    )
