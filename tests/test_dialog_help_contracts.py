"""Every control a DIALOG builds owes the user an explanation too.

`tests/test_tooltip_coverage.py` walks the MainWindow and its 355
controls; nothing walked the 17 dialogs, so the contracts written into
them were unguarded -- deleting one changed no test. This is the second
consumer `ui/dialogs/inventory.py` was written for, and the reason that
module exists rather than each caller knowing how to build a dialog.

SCOPED TO THE BARE CONTEXT, DELIBERATELY. Six dialogs need a computed
result -- a batch table, a per-atom result, an NMR spectrum -- and five
more need services, settings or a molecule. Handing this guard a context
rich enough to build all 17 would make it a slow integration test that
fails for reasons having nothing to do with help contracts. What it
covers is what a bare context can construct, and
`test_a_dialog_that_cannot_be_built_says_so` is what stops that set
shrinking silently.
"""

from __future__ import annotations

import pytest

from openchem.ui.dialogs.inventory import (
    DialogContext,
    DialogUnavailable,
    iter_dialog_fixtures,
)
from openchem.ui.widgets.tooltip_inventory import iter_documentable_controls

import conftest

#: THERE IS NO EXCEPTION LIST, AND THERE WAS ONE FOR EXACTLY ONE COMMIT.
#: `_NOT_YET_MIGRATED` held `PeriodicTableDialog` and its 137 controls
#: while they were written, and its mirror --
#: `test_the_unmigrated_dialog_really_is_unmigrated` -- required an
#: excused dialog to still HAVE undocumented controls, so the day the
#: periodic table reached zero the guard failed and asked for the name to
#: be deleted. It is deleted, and so is the mirror: "no control anywhere
#: is undocumented" says the same thing and needs nothing to maintain.
#: Same arc as `tooltip_migration_debt.json` one layer up, three days
#: shorter.


def _walk(name_filter=None) -> dict[str, list[tuple[str, str, str, object]]]:
    """Every bare-context dialog, walked, with NO Qt handles kept.

    Handles are dropped for the reason `test_tooltip_coverage`'s fixture
    drops them: holding live widgets across a fixture releases them all at
    once into the teardown `gc.collect()`, which is the moment this suite
    has a documented history of dying in.
    """
    walked: dict[str, list[tuple[str, str, str, object]]] = {}
    for fixture in iter_dialog_fixtures():
        if name_filter is not None and fixture.name not in name_filter:
            continue
        try:
            dialog = fixture.build(DialogContext())
        except DialogUnavailable:
            continue
        walked[fixture.name] = [
            (c.status, c.instance_path, c.widget_class, c.help_tooltip)
            for c in iter_documentable_controls(dialog, path=fixture.name)
        ]
        conftest.dispose(dialog)
    return walked


@pytest.fixture(scope="module")
def dialogs(qapp):
    return _walk()


def test_the_walk_reaches_more_than_one_dialog(dialogs):
    """The setup, asserted, so nothing below can pass vacuously.

    A `DialogContext()` that stopped building anything -- a constructor
    gaining a required argument, say -- would leave every assertion in
    this file quantified over an empty set and reporting success.
    """
    assert len(dialogs) >= 5, (
        f"only {len(dialogs)} dialog(s) could be built from a bare context: "
        f"{sorted(dialogs)}"
    )
    assert sum(len(c) for c in dialogs.values()) > 100, (
        "the dialogs are yielding almost no controls -- the walk is not "
        "reaching into them"
    )


def test_every_dialog_control_carries_a_help_contract(dialogs):
    """The blanket assertion, with no exception list behind it.

    Same claim as `test_every_control_carries_a_help_contract` makes about
    the window, and it is safe here for the same reason: the walk is ours,
    the context builds no plugin-contributed dialog, and a control with
    approved alternate documentation (`whatsThis`) already counts.

    A NEW DIALOG CONTROL IS RED UNTIL IT IS DOCUMENTED, deliberately.
    """
    undocumented = [
        path
        for controls in dialogs.values()
        for status, path, _class, _tooltip in controls
        if status == "missing"
    ]
    assert not undocumented, (
        f"{len(undocumented)} dialog control(s) carry no help contract. Use "
        f"`apply_help_tooltip`: {sorted(undocumented)[:5]}"
    )


def test_one_concept_is_not_split_across_the_element_cells(dialogs):
    """118 cells, ONE `help_id`, and the split is the mutation to fear.

    Giving each element its own id -- `periodic_table.element_cell_h`,
    `_he`, `_li` -- passes every other guard here, because each id would
    then have exactly one contract and one meaning. It is the batch tick
    boxes shredded into 51, and it reads as thoroughness.

    `instance_path` is what tells the renderings apart; the id names the
    concept, and selecting an element means the same thing in all 118.
    """
    cells = [
        tooltip
        for controls in dialogs.values()
        for _status, path, widget_class, tooltip in controls
        # The 118 cells are the QToolButtons in the grid. Filtered by
        # CLASS rather than by path: the palette combo lives under the
        # same container and a path prefix swept it in.
        if tooltip is not None and widget_class == "QToolButton"
    ]
    assert len(cells) > 100, (
        f"only {len(cells)} element cell(s) were walked -- the grid is not "
        "being reached and this guard is testing nothing"
    )
    ids = {tooltip.help_id for tooltip in cells}
    assert ids == {"periodic_table.element_cell"}, (
        f"the element cells carry {len(ids)} help_ids where they mean one "
        f"thing: {sorted(ids)[:5]}"
    )


def test_a_dialog_that_cannot_be_built_says_so(qapp):
    """A dialog the context cannot build is REPORTED, never skipped.

    The inventory's own claim, asserted from a consumer. An inventory that
    quietly omitted what it could not construct would report full coverage
    of a smaller world, and the guard above would shrink with it -- so a
    builder must raise `DialogUnavailable` and nothing else, and must
    never answer with None.
    """
    for fixture in iter_dialog_fixtures():
        try:
            dialog = fixture.build(DialogContext())
        except DialogUnavailable as exc:
            assert str(exc), f"{fixture.name} refused without saying what it needs"
            assert fixture.needs, (
                f"{fixture.name} raises DialogUnavailable but declares no "
                "`needs`, so the report cannot say what to supply"
            )
            continue
        assert dialog is not None, f"{fixture.name} built None rather than refusing"
        conftest.dispose(dialog)
