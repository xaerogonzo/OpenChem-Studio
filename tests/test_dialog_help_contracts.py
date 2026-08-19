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
from PySide6.QtCore import QCoreApplication, QEvent

from openchem.ui.dialogs.inventory import (
    DialogContext,
    DialogUnavailable,
    iter_dialog_fixtures,
)
from openchem.ui.widgets.tooltip_inventory import iter_documentable_controls

#: The one dialog a bare context can build that is not migrated yet.
#:
#: 137 controls, of which 118 are element cells -- one concept rendered
#: 118 times, in the shape `properties.batch_selection` already has. It is
#: the next commit's work.
#:
#: A NAME IN A SET, NOT A FIXTURE FILE. The migration this repeats used
#: `tooltip_migration_debt.json` and its mirror, and both were deleted the
#: day the count reached zero. One name with a reason beside it is the
#: whole of what is needed here, and
#: `test_the_unmigrated_dialog_really_is_unmigrated` is what deletes it:
#: the day the periodic table is documented, that test fails and says so.
_NOT_YET_MIGRATED = frozenset({"PeriodicTableDialog"})


def _walk(name_filter=None) -> dict[str, list[tuple[str, str, object]]]:
    """Every bare-context dialog, walked, with NO Qt handles kept.

    Handles are dropped for the reason `test_tooltip_coverage`'s fixture
    drops them: holding live widgets across a fixture releases them all at
    once into the teardown `gc.collect()`, which is the moment this suite
    has a documented history of dying in.
    """
    walked: dict[str, list[tuple[str, str, object]]] = {}
    for fixture in iter_dialog_fixtures():
        if name_filter is not None and fixture.name not in name_filter:
            continue
        try:
            dialog = fixture.build(DialogContext())
        except DialogUnavailable:
            continue
        walked[fixture.name] = [
            (c.status, c.instance_path, c.help_tooltip)
            for c in iter_documentable_controls(dialog, path=fixture.name)
        ]
        dialog.setParent(None)
        dialog.deleteLater()
        QCoreApplication.sendPostedEvents(dialog, QEvent.Type.DeferredDelete)
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


def test_every_migrated_dialog_control_carries_a_help_contract(dialogs):
    """The blanket assertion, for every dialog that has been migrated.

    Same claim as `test_every_control_carries_a_help_contract` makes about
    the window, and it is safe here for the same reason: the walk is ours,
    the context builds no plugin-contributed dialog, and a control with
    approved alternate documentation (`whatsThis`) already counts.
    """
    undocumented = [
        path
        for name, controls in dialogs.items()
        if name not in _NOT_YET_MIGRATED
        for status, path, _ in controls
        if status == "missing"
    ]
    assert not undocumented, (
        f"{len(undocumented)} dialog control(s) carry no help contract. Use "
        f"`apply_help_tooltip`: {sorted(undocumented)[:5]}"
    )


def test_the_unmigrated_dialog_really_is_unmigrated(dialogs):
    """The mirror, and the half that makes the exception self-deleting.

    An exception list that outlives the work it excuses is how a finished
    surface falls back into the backlog unseen -- the failure the deleted
    `tooltip_completed_surfaces.json` existed to catch. So the claim runs
    both ways: a name in `_NOT_YET_MIGRATED` must still HAVE undocumented
    controls, and the day it does not, this test fails and asks for the
    name to be deleted.
    """
    for name in _NOT_YET_MIGRATED:
        assert name in dialogs, (
            f"{name} is excused from the contract guard and can no longer be "
            "built from a bare context -- the exception is now unfalsifiable"
        )
        missing = [path for status, path, _ in dialogs[name] if status == "missing"]
        assert missing, (
            f"{name} carries a contract on every control. Delete it from "
            "_NOT_YET_MIGRATED -- the guard covers it now."
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
        dialog.setParent(None)
        dialog.deleteLater()
        QCoreApplication.sendPostedEvents(dialog, QEvent.Type.DeferredDelete)
