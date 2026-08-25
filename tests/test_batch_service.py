"""Running properties across a whole project.

These go through the real registry and the real RDKit provider rather than
mocks: the thing worth testing is that 50 registered calculators survive
being invoked in one pass, which is precisely what a mock cannot tell you.
It is also how the `functional_groups` shadowing defect was found.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import QApplication

from openchem.bootstrap import build_service_container
from openchem.domain.batch import BatchCell, BatchColumn, BatchRequest, BatchTable
from openchem.domain.common import CacheState
from openchem.domain.molecule import MoleculeModel
from openchem.services.batch_service import BatchProgress

_DRUGS = [
    ("aspirin", "CC(=O)Oc1ccccc1C(=O)O"),
    ("caffeine", "Cn1cnc2c1c(=O)n(C)c(=O)n2C"),
    ("ibuprofen", "CC(C)Cc1ccc(cc1)C(C)C(=O)O"),
]


@pytest.fixture
def services(qapp):
    return build_service_container()


def _molecules(services, entries=_DRUGS):
    molecules = []
    for name, smiles in entries:
        molecule = MoleculeModel(display_name=name)
        services.chemistry_engine.set_structure_from_smiles(molecule, smiles)
        molecules.append(molecule)
    return molecules


def _run(services, request, molecules, timeout_ms=120000):
    """Start a run and return every progress event it published.

    `processEvents` is required, not defensive: `EventBus.publish` is a
    queued Qt signal, so the events raised on the worker thread are still
    sitting in the GUI thread's queue when `waitForDone` returns.
    """
    events = []
    services.event_bus.subscribe(BatchProgress, events.append)
    services.batch_service.request_batch(request, molecules)
    QThreadPool.globalInstance().waitForDone(timeout_ms)
    application = QApplication.instance()
    if application is not None:
        application.processEvents()
    return events


# --- the run ------------------------------------------------------------


def test_a_run_fills_a_cell_for_every_molecule_and_property(services):
    molecules = _molecules(services)
    events = _run(
        services,
        BatchRequest(
            molecule_uuids=[m.uuid for m in molecules],
            descriptor_ids=["mol_wt", "mol_logp", "tpsa"],
            calculator_ids=["elemental_analysis"],
        ),
        molecules,
    )
    table = events[-1].table
    assert events[-1].state is CacheState.COMPLETED
    assert len(table.row_uuids) == 3
    for molecule in molecules:
        assert table.cell(molecule.uuid, "descriptor:mol_wt").value > 100.0


def test_a_report_calculator_becomes_many_numeric_columns(services):
    """The expansion that makes 46 calculators worth tabulating. Topology
    alone contributed 27 columns when this was measured."""
    molecules = _molecules(services)
    events = _run(
        services,
        BatchRequest(
            molecule_uuids=[m.uuid for m in molecules], calculator_ids=["topology_analysis"]
        ),
        molecules,
    )
    table = events[-1].table
    assert len(table.columns) >= 20
    assert table.column("calculator:topology_analysis:Wiener index") is not None


def test_a_column_only_some_molecules_have_leaves_real_gaps(services):
    """Nitrogen percentage exists for caffeine and not for aspirin. The
    column is real; the gaps are the answer, not a failure."""
    molecules = _molecules(services)
    events = _run(
        services,
        BatchRequest(
            molecule_uuids=[m.uuid for m in molecules], calculator_ids=["elemental_analysis"]
        ),
        molecules,
    )
    table = events[-1].table
    nitrogen = table.column("calculator:elemental_analysis:N")
    assert nitrogen is not None
    assert len(table.values(nitrogen.column_id)) == 1  # caffeine only


def test_progress_is_published_per_molecule_with_a_partial_table(services):
    """A table that appears only at the end is indistinguishable from a
    broken one over a run of minutes."""
    molecules = _molecules(services)
    events = _run(
        services,
        BatchRequest(molecule_uuids=[m.uuid for m in molecules], descriptor_ids=["mol_wt"]),
        molecules,
    )
    running = [event for event in events if event.state is CacheState.RUNNING]
    assert [event.completed for event in running] == [1, 2, 3]
    assert all(event.table is not None for event in running)


def test_a_molecule_with_no_structure_gets_an_explained_row_not_a_missing_one(services):
    """Skipping it would silently shorten the table and leave the user
    counting rows to find out which one went."""
    molecules = _molecules(services)
    empty = MoleculeModel(display_name="not drawn yet")
    molecules.append(empty)
    events = _run(
        services,
        BatchRequest(
            molecule_uuids=[m.uuid for m in molecules], descriptor_ids=["mol_wt", "tpsa"]
        ),
        molecules,
    )
    table = events[-1].table
    assert empty.uuid in table.row_uuids
    cell = table.cell(empty.uuid, "descriptor:mol_wt")
    assert cell.failed and "structure" in cell.error


def test_one_failing_calculator_does_not_end_the_run(services):
    """steric_analysis legitimately refuses a molecule with no donor atom.
    The rest of the row must still be computed."""
    molecules = _molecules(services)
    events = _run(
        services,
        BatchRequest(
            molecule_uuids=[m.uuid for m in molecules],
            descriptor_ids=["mol_wt"],
            calculator_ids=["steric_analysis"],
        ),
        molecules,
    )
    table = events[-1].table
    assert events[-1].state is CacheState.COMPLETED
    assert table.cell(molecules[0].uuid, "descriptor:mol_wt").value is not None


def test_alert_catalogs_are_selectable_alongside_descriptors(services):
    molecules = _molecules(services)
    events = _run(
        services,
        BatchRequest(molecule_uuids=[m.uuid for m in molecules], descriptor_ids=["pains", "brenk"]),
        molecules,
    )
    table = events[-1].table
    assert table.column("alert:pains:count") is not None
    assert table.cell(molecules[0].uuid, "alert:brenk:count").value is not None


def test_alerts_are_not_computed_when_none_were_asked_for(services):
    """585 SMARTS patterns per molecule is not something to run by
    accident."""
    molecules = _molecules(services)
    events = _run(
        services,
        BatchRequest(molecule_uuids=[m.uuid for m in molecules], descriptor_ids=["mol_wt"]),
        molecules,
    )
    assert all(not column.column_id.startswith("alert:") for column in events[-1].table.columns)


def test_the_per_atom_aggregate_reaches_the_computation(services):
    """The option is only worth having if it changes the answer."""
    molecules = _molecules(services)
    request = dict(
        molecule_uuids=[m.uuid for m in molecules], calculator_ids=["crippen_logp_contrib"]
    )
    means = _run(services, BatchRequest(**request, per_atom_aggregate="mean"), molecules)[-1].table
    sums = _run(services, BatchRequest(**request, per_atom_aggregate="sum"), molecules)[-1].table
    mean_value = means.cell(molecules[0].uuid, "calculator:crippen_logp_contrib").value
    sum_value = sums.cell(molecules[0].uuid, "calculator:crippen_logp_contrib").value
    assert mean_value != sum_value
    assert "sum" in sums.column("calculator:crippen_logp_contrib").label


def test_every_cell_carries_the_provenance_of_what_made_it(services):
    """The reason a table is allowed to exist at all in this codebase."""
    molecules = _molecules(services)
    events = _run(
        services,
        BatchRequest(molecule_uuids=[m.uuid for m in molecules], descriptor_ids=["mol_wt"]),
        molecules,
    )
    cell = events[-1].table.cell(molecules[0].uuid, "descriptor:mol_wt")
    assert cell.provenance is not None
    assert cell.provenance.method == "rdkit"


# --- refusals and single flight ----------------------------------------


def test_an_empty_selection_is_refused_with_a_reason(services):
    molecules = _molecules(services)
    events = _run(services, BatchRequest(molecule_uuids=[m.uuid for m in molecules]), molecules)
    assert events[-1].state is CacheState.FAILED
    assert "choose at least one" in events[-1].error


def test_running_with_no_molecules_is_refused_with_a_reason(services):
    events = _run(services, BatchRequest(descriptor_ids=["mol_wt"]), [])
    assert "No molecules" in events[-1].error


def test_a_second_run_is_refused_while_one_is_active(services):
    """Two concurrent runs would compete for the same sidecar interpreters
    and produce a second table nothing knows what to do with."""
    from openchem.services.batch_service import BATCH_JOB_KEY, BATCH_JOB_KIND

    molecules = _molecules(services)
    services.job_manager.try_start(BATCH_JOB_KIND, BATCH_JOB_KEY)
    try:
        events = _run(
            services,
            BatchRequest(molecule_uuids=[m.uuid for m in molecules], descriptor_ids=["mol_wt"]),
            molecules,
        )
        assert "already in progress" in events[-1].error
    finally:
        services.job_manager.finish(BATCH_JOB_KIND, BATCH_JOB_KEY)


def test_a_run_registers_and_releases_its_job(services):
    molecules = _molecules(services)
    assert not services.batch_service.is_running()
    _run(
        services,
        BatchRequest(molecule_uuids=[m.uuid for m in molecules], descriptor_ids=["mol_wt"]),
        molecules,
    )
    assert not services.batch_service.is_running()


def test_cancelling_stops_the_run_and_says_where_it_stopped(services):
    """Cancelled before the pool starts, so the first check catches it --
    which is the case a Jobs panel actually produces."""
    molecules = _molecules(services, _DRUGS * 8)
    events = []
    services.event_bus.subscribe(BatchProgress, events.append)
    services.batch_service.request_batch(
        BatchRequest(
            molecule_uuids=[m.uuid for m in molecules],
            descriptor_ids=["mol_wt"],
            calculator_ids=["topology_analysis"],
        ),
        molecules,
    )
    services.batch_service.cancel()
    QThreadPool.globalInstance().waitForDone(120000)
    QApplication.instance().processEvents()
    assert events[-1].state is CacheState.FAILED
    assert "Cancelled" in events[-1].message
    assert not services.batch_service.is_running()


# --- the table itself ---------------------------------------------------


def _table():
    table = BatchTable()
    table.add_row("a", "A")
    table.add_row("b", "B")
    table.add_row("c", "C")
    for column_id in ("x", "y"):
        table.add_column(BatchColumn(column_id=column_id, label=column_id))
    table.set_cell("a", "x", BatchCell(value=1.0))
    table.set_cell("a", "y", BatchCell(value=10.0))
    table.set_cell("b", "x", BatchCell(value=2.0))
    table.set_cell("c", "y", BatchCell(value=30.0))
    return table


def test_paired_values_are_pairwise_complete():
    """A correlation between two columns has no reason to lose rows because
    a third, unrelated column failed."""
    xs, ys, uuids = _table().paired_values("x", "y")
    assert (xs, ys, uuids) == ([1.0], [10.0], ["a"])


def test_the_matrix_drops_incomplete_rows_and_says_which_survived():
    """Listwise here, unlike paired_values: a row with a gap cannot be
    projected."""
    rows, uuids = _table().matrix(["x", "y"])
    assert rows == [[1.0, 10.0]]
    assert uuids == ["a"]


def test_a_numeric_column_with_under_two_values_is_not_offered():
    """Selectable but empty reads as a broken tool rather than as missing
    data. `x` and `y` have two values each and are offered; `lonely` has
    one and is not."""
    table = _table()
    table.add_column(BatchColumn(column_id="lonely", label="lonely"))
    table.set_cell("a", "lonely", BatchCell(value=1.0))
    table.add_column(BatchColumn(column_id="words", label="words", numeric=False))
    table.set_cell("a", "words", BatchCell(text="hello"))
    table.set_cell("b", "words", BatchCell(text="there"))
    assert [column.column_id for column in table.numeric_columns()] == ["x", "y"]


def test_redefining_a_column_mid_run_does_not_reorder_the_table():
    table = _table()
    table.add_column(BatchColumn(column_id="x", label="different label"))
    assert [column.label for column in table.columns] == ["x", "y"]


def test_the_request_decides_which_molecules_run(services):
    """**THE SCOPE FIELD WAS WRITTEN BY EVERY CALLER AND READ BY
    NOTHING.** The task iterated whatever list it was handed, so a request
    naming two molecules while the caller passed twenty ran twenty --
    found by mutation, which changed the request's scope to the whole
    project and changed no behaviour at all.

    That is the shape of a latent bug rather than a live one: no caller
    disagreed with itself today. It is the lazy path that makes them
    disagree easily, since it asks for one molecule out of a project.
    """
    molecules = _molecules(services)
    only = molecules[0]
    events = _run(
        services,
        BatchRequest(molecule_uuids=[only.uuid], descriptor_ids=["mol_wt"]),
        molecules,
    )
    assert len(molecules) > 1, "a one-molecule fixture cannot show this"
    assert events[-1].table.row_uuids == [only.uuid]


def test_naming_no_molecules_still_means_everything_given(services):
    """A request that names nothing is not a request to compute nothing --
    which is what every fixture and the older callers rely on."""
    molecules = _molecules(services)
    events = _run(services, BatchRequest(descriptor_ids=["mol_wt"]), molecules)
    assert len(events[-1].table.row_uuids) == len(molecules)
