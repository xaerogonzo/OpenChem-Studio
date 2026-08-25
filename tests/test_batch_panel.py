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


# --- the per-atom comparison -------------------------------------------


def test_the_run_keeps_the_per_atom_values_the_cells_throw_away(panel):
    """A cell holds the aggregate. The comparison needs the vector, and
    re-running every calculator to get it back is the alternative."""
    table = _run(panel, ["crippen_logp_contrib"])

    aspirin = table.row_uuids[0]
    retained = table.per_atom_for(aspirin, "crippen_logp_contrib")
    assert retained is not None
    assert len(retained.values) > 1, "a per-atom result reduced to one number"

    cell = table.cell(aspirin, "calculator:crippen_logp_contrib")
    assert cell is not None and cell.value is not None
    assert cell.value == pytest.approx(
        sum(retained.values.values()) / len(retained.values)
    )


def test_the_per_atom_tab_appears_only_when_there_is_per_atom_data(
    panel, services, project, widgets
):
    """A tab advertising a comparison that cannot be made is worse than no
    tab -- the same judgement the 'no numeric columns' message makes."""
    table = _run(panel, ["mol_wt"])
    dialog = _dialog(widgets, table, services, project)
    titles = {dialog._tabs.tabText(i) for i in range(dialog._tabs.count())}
    assert "Per-atom" not in titles


def test_the_per_atom_tab_compares_corresponding_atoms(
    panel, services, project, widgets
):
    table = _run(panel, ["crippen_logp_contrib"])
    dialog = _dialog(widgets, table, services, project)
    titles = {dialog._tabs.tabText(i) for i in range(dialog._tabs.count())}
    assert "Per-atom" in titles

    # Aspirin against ibuprofen -- two real molecules sharing a benzene ring
    # and a carboxyl, differing everywhere else.
    aspirin = next(m.uuid for m in project.molecules if m.display_name == "aspirin")
    ibuprofen = next(m.uuid for m in project.molecules if m.display_name == "ibuprofen")
    dialog._atom_reference.setCurrentIndex(dialog._atom_reference.findData(aspirin))
    dialog._atom_other.setCurrentIndex(dialog._atom_other.findData(ibuprofen))

    assert dialog._atom_table.rowCount() > 0, "no corresponding atoms were found"
    # The difference column really is the difference of the two beside it.
    for row in range(dialog._atom_table.rowCount()):
        reference = float(dialog._atom_table.item(row, 2).text())
        other = float(dialog._atom_table.item(row, 3).text())
        difference = float(dialog._atom_table.item(row, 4).text())
        assert difference == pytest.approx(other - reference, abs=1e-3)


def test_the_comparison_says_how_many_atoms_went_unmatched(
    panel, services, project, widgets
):
    """The atoms with no counterpart are exactly where the two structures
    differ. A table that silently omits them reads as 'nearly identical'."""
    table = _run(panel, ["crippen_logp_contrib"])
    dialog = _dialog(widgets, table, services, project)

    aspirin = next(m.uuid for m in project.molecules if m.display_name == "aspirin")
    ibuprofen = next(m.uuid for m in project.molecules if m.display_name == "ibuprofen")
    dialog._atom_reference.setCurrentIndex(dialog._atom_reference.findData(aspirin))
    dialog._atom_other.setCurrentIndex(dialog._atom_other.findData(ibuprofen))

    note = dialog._atom_note.text()
    assert "atoms in the reference" in note
    assert "genuinely differ" in note


def test_comparing_a_molecule_against_itself_is_refused_not_all_zeroes(
    panel, services, project, widgets
):
    table = _run(panel, ["crippen_logp_contrib"])
    dialog = _dialog(widgets, table, services, project)

    aspirin = next(m.uuid for m in project.molecules if m.display_name == "aspirin")
    dialog._atom_reference.setCurrentIndex(dialog._atom_reference.findData(aspirin))
    dialog._atom_other.setCurrentIndex(dialog._atom_other.findData(aspirin))

    assert dialog._atom_table.rowCount() == 0
    assert "two different molecules" in dialog._atom_note.text()


def test_a_categorical_per_atom_property_is_not_subtracted(
    panel, services, project, widgets
):
    """Ring-system id 3 minus id 1 is 2, which is a number and means
    nothing."""
    table = _run(panel, ["ring_systems"])
    dialog = _dialog(widgets, table, services, project)
    if "Per-atom" not in {dialog._tabs.tabText(i) for i in range(dialog._tabs.count())}:
        pytest.skip("ring_systems produced no per-atom data for two molecules")

    aspirin = next(m.uuid for m in project.molecules if m.display_name == "aspirin")
    caffeine = next(m.uuid for m in project.molecules if m.display_name == "caffeine")
    dialog._atom_reference.setCurrentIndex(dialog._atom_reference.findData(aspirin))
    dialog._atom_other.setCurrentIndex(dialog._atom_other.findData(caffeine))

    assert dialog._atom_table.rowCount() == 0
    assert "not measurements" in dialog._atom_note.text()
    assert "means nothing" in dialog._atom_note.text()


def test_every_comparison_row_fits_inside_its_table(
    panel, services, project, widgets
):
    """The Interactions bug was correct data rendered as blank rows -- row 0
    was 481px in a 106px viewport -- and only opening the app found it."""
    table = _run(panel, ["crippen_logp_contrib"])
    dialog = _dialog(widgets, table, services, project)
    dialog.resize(880, 680)
    dialog.show()

    # Qt does not lay out a tab that has never been current, so a table
    # measured while another tab is showing reports a 0px viewport and the
    # assertion below passes or fails for the wrong reason.
    atoms_index = next(
        index for index in range(dialog._tabs.count())
        if dialog._tabs.tabText(index) == "Per-atom"
    )
    dialog._tabs.setCurrentIndex(atoms_index)
    QApplication.instance().processEvents()

    aspirin = next(m.uuid for m in project.molecules if m.display_name == "aspirin")
    ibuprofen = next(m.uuid for m in project.molecules if m.display_name == "ibuprofen")
    dialog._atom_reference.setCurrentIndex(dialog._atom_reference.findData(aspirin))
    dialog._atom_other.setCurrentIndex(dialog._atom_other.findData(ibuprofen))
    QApplication.instance().processEvents()

    viewport_height = dialog._atom_table.viewport().height()
    assert viewport_height > 0, "the table was measured before it was laid out"
    for row in range(dialog._atom_table.rowCount()):
        height = dialog._atom_table.rowHeight(row)
        assert 0 < height <= viewport_height, (
            f"row {row} is {height}px inside a {viewport_height}px viewport"
        )


def test_the_comparison_says_so_when_the_structures_are_unavailable(
    panel, services, widgets
):
    """A table with no rows and no explanation reads as "these molecules are
    identical". The dialog is built without a project here, which is what a
    molecule deleted after the run looks like."""
    table = _run(panel, ["crippen_logp_contrib"])
    dialog = BatchAnalysisDialog(table, services.chemistry_engine, None)
    widgets.append(dialog)

    assert dialog._atom_table.rowCount() == 0
    assert "cannot be matched up" in dialog._atom_note.text()


# --- width: the panel used to demand more than any dock could give ---------


def test_no_control_row_sets_a_width_no_dock_can_satisfy(panel):
    """A `QHBoxLayout`'s minimum is the SUM of its children.

    All three of this panel's control rows were horizontal, so the export
    row alone -- Export CSV, Export Report, Analyse, Virtual Screening --
    put a floor under the whole panel: 409 px of content in a dock the
    application opens at 420 and which a saved layout can leave at 280.
    Measured in the running app, "Virtual Screening..." sat off the right
    edge with a horizontal scrollbar underneath it.

    THE SETUP IS ASSERTED FIRST. If the four buttons ever stop summing to
    more than the panel's minimum, this test proves nothing and should
    fail rather than pass quietly -- the same reason the pool-id guard
    asserts its own pool really is sparse.
    """
    buttons = (
        panel._csv_button,
        panel._report_button,
        panel._analyse_button,
        panel._screen_button,
    )
    summed = sum(b.minimumSizeHint().width() for b in buttons)
    widest = max(b.minimumSizeHint().width() for b in buttons)

    assert summed > widest * 2, (
        f"the export row is no longer several buttons wide (sum {summed}, "
        f"widest {widest}), so this guard cannot see a row that fails to wrap"
    )

    minimum = panel.minimumSizeHint().width()
    assert minimum < summed, (
        f"the panel demands {minimum} px, at least the sum of its export "
        f"buttons ({summed}) -- a control row has stopped wrapping. Use "
        f"`flow_row` from ui/widgets/flow_layout.py, not QHBoxLayout."
    )


def test_the_property_column_gets_the_width_not_the_basis_column(panel):
    """Qt stretches the LAST section, which is backwards for this tree.

    Every readable string is in column 0, indented up to three levels;
    "Basis" holds one short word and is EMPTY on the category rows. Left
    to Qt's default the categories rendered as "Ad...", "Cha...", "Elec..."
    -- three characters -- while the empty Basis column took more than
    half the panel. That is the unreadable-label symptom the panel rail
    was built to remove, reappearing one widget along.

    THE PANEL IS SIZED FROM ITS OWN CONTENT, never pinned at 420. A fixed
    width here would be a claim about the FONT: `offscreen`'s default is
    more than twice as wide as a user's, and the widest category measures
    472 px there against a panel the application opens at 420 -- so a
    pinned assertion fails on a panel that is measurably clean in the app.
    Measuring the requirement in the tree's own metrics and then giving it
    that much room tests the column RULE at any font.
    """
    tree = panel._tree
    metrics = tree.fontMetrics()
    indent = tree.indentation()

    categories = [
        top.child(child)
        for top in map(tree.topLevelItem, range(tree.topLevelItemCount()))
        for child in range(top.childCount())
    ]
    assert categories, "the tree has no nested categories; this guard is vacuous"

    needed = max(2 * indent + metrics.horizontalAdvance(c.text(0)) for c in categories)

    panel.resize(needed + 160, 900)
    panel.grab()  # a widget that was never shown lays nothing out

    assert tree.columnWidth(0) >= needed, (
        f"the Property column is {tree.columnWidth(0)} px in a tree {tree.width()} "
        f"px wide, and its widest category needs {needed} px, so names elide to "
        f"a few characters. Basis is {tree.columnWidth(1)} px and holds one word."
    )


def test_the_basis_column_takes_only_what_its_own_text_needs(panel):
    """The other half, and the one that fails if the stretch comes back.

    Widening the panel alone would satisfy the guard above even with Qt's
    default stretch restored -- give a stretched last section enough room
    and column 0 eventually gets what it needs too. What distinguishes the
    two arrangements at ANY width is where the SLACK goes: with the fix,
    Basis is sized to its own text and every spare pixel is Property's.

    Font-independent by construction: both sides are measured in the
    tree's own metrics.
    """
    tree = panel._tree
    metrics = tree.fontMetrics()

    panel.resize(1400, 900)
    panel.grab()

    basis_text = max(
        (
            leaf.text(1)
            for top in map(tree.topLevelItem, range(tree.topLevelItemCount()))
            for child in range(top.childCount())
            for leaf in map(top.child(child).child, range(top.child(child).childCount()))
        ),
        key=len,
        default="",
    )
    room_for_basis = metrics.horizontalAdvance(basis_text) + 4 * tree.indentation()

    assert tree.columnWidth(1) <= room_for_basis, (
        f"Basis is {tree.columnWidth(1)} px on a 1400 px panel while its widest "
        f"value ({basis_text!r}) needs about {room_for_basis} -- the last-section "
        f"stretch is back, and every one of those pixels belongs to Property."
    )
    assert tree.columnWidth(0) > tree.columnWidth(1), (
        f"Property {tree.columnWidth(0)} px vs Basis {tree.columnWidth(1)} px"
    )


# --- selection: 91 properties, and no way to tick a group ------------------


def _group_named(panel, text):
    stack = [panel._tree.topLevelItem(i) for i in range(panel._tree.topLevelItemCount())]
    while stack:
        item = stack.pop()
        if item.text(0) == text:
            return item
        stack.extend(item.child(i) for i in range(item.childCount()))
    raise AssertionError(f"no group named {text!r}")


def _draws_a_check_box(item) -> bool:
    """Whether Qt renders a tickable box on this row.

    **NEITHER OF THE OBVIOUS TESTS DISCRIMINATES**, measured on a bare
    `QTreeWidgetItem`: `ItemIsUserCheckable` is in Qt's DEFAULT item flags
    and is therefore True on a row nobody ever made checkable, and
    `checkState(0)` answers `Unchecked` whether a state was set or not.
    Only the role data tells them apart -- None until `setCheckState` is
    called -- and it is exactly what decides whether a box is drawn.

    A mutation removing the whole `_make_groups_checkable` body survived
    both of the obvious versions of this.
    """
    return item.data(0, Qt.ItemDataRole.CheckStateRole) is not None


def _leaf_states(group):
    return [group.child(i).checkState(0) for i in range(group.childCount())]


def test_ticking_a_category_ticks_everything_in_it(panel):
    """THE WHOLE OF THE REPORTED COMPLAINT. `_add_leaf` set
    `ItemIsUserCheckable` on leaves only, so a category heading had no
    check state at all and 91 properties could only be ticked one by
    one."""
    calculators = _group_named(panel, "Calculators")
    category = calculators.child(0)
    assert category.childCount() >= 2, "need a category with something in it"

    category.setCheckState(0, Qt.CheckState.Checked)

    assert all(state == Qt.CheckState.Checked for state in _leaf_states(category))
    _descriptors, ticked = panel.selected_ids()
    assert len(ticked) == category.childCount()


def test_unticking_a_category_unticks_everything_in_it(panel):
    category = _group_named(panel, "Calculators").child(0)
    category.setCheckState(0, Qt.CheckState.Checked)
    category.setCheckState(0, Qt.CheckState.Unchecked)
    assert all(state == Qt.CheckState.Unchecked for state in _leaf_states(category))


def test_a_partly_ticked_category_says_so(panel):
    """A group's box is a statement about its children and goes stale the
    moment one of them moves.

    **DRIVEN THROUGH THE LEAF, NOT THROUGH `_refresh_group_states`.** The
    first version of this called the helper itself, which proves the
    helper works and says nothing about whether anything calls it -- a
    mutation deleting the automatic recompute SURVIVED against it.
    """
    calculators = _group_named(panel, "Calculators")
    category = calculators.child(0)
    assert category.childCount() >= 2, "a one-child category cannot be partial"

    category.child(0).setCheckState(0, Qt.CheckState.Checked)

    assert category.checkState(0) == Qt.CheckState.PartiallyChecked
    assert calculators.checkState(0) == Qt.CheckState.PartiallyChecked, (
        "the state has to climb past the immediate parent"
    )


def test_a_category_row_is_something_a_user_can_actually_tick(panel):
    """**THE FLAG IS THE FEATURE.** `setCheckState` works on any item
    whether or not `ItemIsUserCheckable` is set, so every propagation test
    above passes with no check box drawn at all -- which was precisely the
    reported state of this panel. A mutation removing the flag survived
    all of them.
    """
    calculators = _group_named(panel, "Calculators")
    assert _draws_a_check_box(calculators)
    for index in range(calculators.childCount()):
        assert _draws_a_check_box(calculators.child(index))


def test_select_all_respects_the_filter(panel):
    """**THE FILTER'S OWN HELP TEXT PROMISES IT FILTERS THE LIST AND NEVER
    THE RESULTS**, so a select-all reaching entries the user cannot see
    would contradict a documented contract.

    Asserts its own setup: the filter must really be hiding something, or
    "respects the filter" is a claim about nothing.
    """
    panel._filter.setText("logp")
    hidden = [item for item, _p in panel._leaves() if item.isHidden()]
    shown = [item for item, _p in panel._leaves() if not item.isHidden()]
    assert hidden and shown, "the filter matched everything or nothing"

    panel._select_all_visible()

    assert all(item.checkState(0) == Qt.CheckState.Checked for item in shown)
    assert all(item.checkState(0) == Qt.CheckState.Unchecked for item in hidden)


def test_ticking_a_category_leaves_its_hidden_children_alone(panel):
    """Same contract, reached through the group box rather than the button."""
    panel._filter.setText("logp")
    category = None
    for index in range(_group_named(panel, "Calculators").childCount()):
        candidate = _group_named(panel, "Calculators").child(index)
        visible = [candidate.child(i) for i in range(candidate.childCount())
                   if not candidate.child(i).isHidden()]
        hidden = [candidate.child(i) for i in range(candidate.childCount())
                  if candidate.child(i).isHidden()]
        if visible and hidden:
            category = candidate
            break
    if category is None:
        pytest.skip("no category is partly filtered by this needle")

    category.setCheckState(0, Qt.CheckState.Checked)

    for index in range(category.childCount()):
        child = category.child(index)
        expected = Qt.CheckState.Unchecked if child.isHidden() else Qt.CheckState.Checked
        assert child.checkState(0) == expected


def test_select_all_says_how_many_it_ticked(panel):
    """"Select all" over a filtered list is otherwise a claim the user
    cannot check."""
    panel._select_all_visible()
    assert "Ticked" in panel._status.text()


def test_clear_selection_clears_the_group_boxes_too(panel):
    """A group left ticked above unticked children is a lie about what
    will run."""
    category = _group_named(panel, "Calculators").child(0)
    category.setCheckState(0, Qt.CheckState.Checked)

    panel._clear_selection()

    assert category.checkState(0) == Qt.CheckState.Unchecked
    assert panel.selected_ids() == ([], [])


# --- what a cell IS, and what gets computed unasked -------------------------


def test_opening_the_panel_computes_nothing(services, project, widgets):
    """**THE LAZY INVARIANT, ROW ONE.** Opening Batch over a project must
    run zero calculators -- the panel is a picker until something is
    asked for, and a project of 200 molecules is only dangerous if
    building the panel starts work.

    Spies on the registry rather than on a panel attribute, because what
    matters is whether a CALCULATOR RAN, not whether the panel believes it
    started one.
    """
    calls: list[str] = []
    original = services.calculator_registry.compute

    def spy(calculator_id, *args, **kwargs):
        calls.append(calculator_id)
        return original(calculator_id, *args, **kwargs)

    services.calculator_registry.compute = spy
    try:
        panel = BatchPanel(
            services.batch_service,
            services.calculator_registry,
            services.table_export_service,
            services.event_bus,
            services.chemistry_engine,
        )
        widgets.append(panel)
        panel.set_project(project)
    finally:
        services.calculator_registry.compute = original

    assert calls == [], f"building the panel ran {len(calls)} calculator(s)"


def _cell_of(kind, **fields):
    from openchem.domain.batch import BatchCell, BatchColumn

    column = BatchColumn(column_id="c", label="C", numeric=False)
    return _cell_item_for(column, BatchCell(kind=kind, **fields))


def _cell_item_for(column, cell):
    from openchem.domain.batch import BatchTable
    from openchem.ui.panels.batch_panel import _cell_item

    table = BatchTable()
    table.add_row("m", "aspirin")
    table.add_column(column)
    table.set_cell("m", column.column_id, cell)
    return _cell_item(table, "m", column)


def test_the_three_cell_kinds_render_distinguishably():
    """**THE EM DASH MEANT BOTH.** A failed calculation and a real result
    with no scalar form rendered identically, and they are opposite
    statements: one says nothing was computed, the other says something
    was and a table is the wrong shape for it.
    """
    from openchem.domain.batch import FAILED, NON_SCALAR, SCALAR
    from openchem.domain.common import CacheState

    scalar = _cell_of(SCALAR, value=1.5, text="1.50")
    non_scalar = _cell_of(NON_SCALAR, text="12 peaks")
    failed = _cell_of(FAILED, text="", cache_state=CacheState.FAILED, error="no conformer")

    texts = {scalar.text(), non_scalar.text(), failed.text()}
    assert len(texts) == 3, f"two kinds render the same text: {texts}"

    # The failure is the only one that hides its value behind a dash.
    assert failed.text() == "—"
    assert non_scalar.text() == "12 peaks"

    colours = {
        scalar.foreground().color().name(),
        non_scalar.foreground().color().name(),
        failed.foreground().color().name(),
    }
    assert len(colours) == 3, f"two kinds share a colour: {colours}"


def test_a_non_scalar_cell_says_how_to_reach_the_real_thing():
    """Naming it is not enough -- a reader has to know it is openable."""
    from openchem.domain.batch import NON_SCALAR

    item = _cell_of(NON_SCALAR, text="12 peaks")
    assert "Double-click" in item.toolTip()


def test_a_failed_cell_still_says_why():
    """Unchanged, and asserted so the new branch cannot swallow it."""
    from openchem.domain.batch import FAILED
    from openchem.domain.common import CacheState

    item = _cell_of(FAILED, text="", cache_state=CacheState.FAILED, error="no conformer")
    assert "no conformer" in item.toolTip()
