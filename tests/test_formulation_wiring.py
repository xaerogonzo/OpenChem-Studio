"""A user can state a formulation and see what it would do.

**THIS FILE EXISTS BECAUSE THE ARITHMETIC SHIPPED WITH NO WAY IN.**
`build_formulation_report` landed correct, sourced, and covered by 24
tests in `test_formulations.py` -- and reached by nothing a user could
press. `tests/test_calculator_reachability.py` was GREEN throughout,
because its three directions are all about the MODULE and
`chem/energetics.py` was reachable on account of a different function
in it. That blind spot has its own guard there now; this file is the
other half, the route itself.

The split is deliberate. The guard says *something calls it*; these say
*the thing that calls it does the right thing with the answer*.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QDialog

from openchem.commands.formulation_commands import (
    DeleteFormulationCommand,
    SaveFormulationCommand,
)
from openchem.domain.formulation import FormulationComponent, FormulationModel
from openchem.domain.project import ProjectModel
from openchem.events.base import EventBus
from openchem.events.events import FormulationChanged, FormulationSelected
from openchem.ui.dialogs.formulation_dialog import FormulationDialog

import conftest


#: ANFO, the case the whole feature exists for: both components are
#: refused individually by Kamlet-Jacobs' arbitrary and the mixture lands
#: inside it. Enthalpies are the ones `test_formulations.py` already
#: uses, so the two files cannot disagree about the fixture.
_AN = FormulationComponent(
    smiles="[NH4+].[N+](=O)([O-])[O-]",
    mass_fraction=0.945,
    enthalpy_kcal_per_mol=-87.3,
    display_name="Ammonium nitrate",
)
_FUEL = FormulationComponent(
    smiles="CCCCCCCCCCCC",
    mass_fraction=0.055,
    enthalpy_kcal_per_mol=-83.9,
    display_name="Fuel oil",
)


def _dispose(widget) -> None:
    """The per-widget disposal recipe, never the global drain.

    `sendPostedEvents(None, DeferredDelete)` drains every pending delete
    in the process, including ones other files left queued -- see
    CLAUDE.md.
    """
    conftest.dispose(widget)


@pytest.fixture
def anfo() -> FormulationModel:
    return FormulationModel(
        display_name="ANFO",
        components=(_AN, _FUEL),
        loading_density=0.85,
    )


# --- the dialog collects what cannot be derived -----------------------------


def test_the_dialog_builds_with_no_arguments_at_all(qapp):
    """Which is what puts it in the bare-context half of the inventory.

    A dialog needing a molecule or a computed result can only be walked
    by a context carrying one; this one needs nothing, so the help-contract
    guard covers it for free.
    """
    dialog = FormulationDialog()
    try:
        assert dialog.formulation().components == ()
    finally:
        _dispose(dialog)


def test_a_recipe_typed_in_comes_back_as_the_model(qapp, anfo):
    dialog = FormulationDialog(anfo)
    try:
        restated = dialog.formulation()
        assert restated.display_name == "ANFO"
        assert [c.smiles for c in restated.components] == [_AN.smiles, _FUEL.smiles]
        assert [c.mass_fraction for c in restated.components] == [0.945, 0.055]
        assert [c.enthalpy_kcal_per_mol for c in restated.components] == [-87.3, -83.9]
        assert restated.loading_density == pytest.approx(0.85)
    finally:
        _dispose(dialog)


def test_editing_keeps_the_uuid_so_it_updates_rather_than_forking(qapp, anfo):
    """Otherwise "edit" silently produces a second formulation.

    The save command is add-or-replace keyed on the uuid, so a dialog
    that regenerated one would append a near-duplicate under the same
    name and leave the original in the project.
    """
    dialog = FormulationDialog(anfo)
    try:
        assert dialog.formulation().uuid == anfo.uuid
    finally:
        _dispose(dialog)


def test_a_fresh_dialog_does_NOT_reuse_a_uuid(qapp):
    """The narrow half of the test above.

    "Always keep the uuid" satisfies it and would make every new
    formulation collide with the last one saved.
    """
    first = FormulationDialog()
    second = FormulationDialog()
    try:
        assert first.formulation().uuid != second.formulation().uuid
    finally:
        _dispose(first)
        _dispose(second)


def test_an_unstated_loading_density_is_None_and_not_zero(qapp):
    """`float | None` against a spin box that has no null.

    Zero is the sentinel, and the distinction is load-bearing: the report
    REFUSES without a density, and a zero would instead be carried into
    an equation where pressure goes as its square.
    """
    dialog = FormulationDialog()
    try:
        assert dialog.loading_density() is None
    finally:
        _dispose(dialog)


def test_the_running_total_reports_the_SUM_and_not_only_a_verdict(qapp):
    """"0.995" says which component is short; "inconsistent" does not."""
    short = FormulationModel(
        display_name="short",
        components=(_AN, FormulationComponent(smiles="C", mass_fraction=0.05,
                                              enthalpy_kcal_per_mol=-20.0)),
    )
    dialog = FormulationDialog(short)
    try:
        assert "0.995" in dialog.status_text()
    finally:
        _dispose(dialog)


def test_the_dialog_never_rescales_what_was_typed(qapp):
    """94.5 + 5.0 must come back as 0.945 + 0.05, summing to 0.995.

    Renormalising produces a perfectly ordinary recipe that is not the
    one anybody mixed, and the missing half a percent is exactly the typo
    a rescale hides forever.
    """
    short = FormulationModel(
        display_name="short",
        components=(_AN, FormulationComponent(smiles="C", mass_fraction=0.05,
                                              enthalpy_kcal_per_mol=-20.0)),
    )
    dialog = FormulationDialog(short)
    try:
        fractions = [c.mass_fraction for c in dialog.formulation().components]
        assert fractions == [0.945, 0.05]
        assert sum(fractions) == pytest.approx(0.995)
    finally:
        _dispose(dialog)


# --- the commands -----------------------------------------------------------


def test_saving_a_new_formulation_appends_it(anfo):
    project = ProjectModel(name="p")
    bus = EventBus()
    SaveFormulationCommand(project, anfo, bus).redo()
    assert [f.uuid for f in project.formulations] == [anfo.uuid]


def test_saving_an_edit_REPLACES_rather_than_appending(anfo):
    """The model is frozen, so an edit is a replacement.

    Appending instead would leave the project holding two formulations
    with one uuid, and `find_formulation` would answer with whichever
    came first.
    """
    project = ProjectModel(name="p")
    bus = EventBus()
    SaveFormulationCommand(project, anfo, bus).redo()
    edited = FormulationModel(
        uuid=anfo.uuid,
        display_name="ANFO, 94/6",
        components=anfo.components,
        loading_density=0.9,
    )
    SaveFormulationCommand(project, edited, bus).redo()
    assert len(project.formulations) == 1
    assert project.formulations[0].display_name == "ANFO, 94/6"


def test_undoing_an_edit_restores_the_previous_version_in_place(anfo):
    project = ProjectModel(name="p")
    bus = EventBus()
    SaveFormulationCommand(project, anfo, bus).redo()
    other = FormulationModel(display_name="other")
    SaveFormulationCommand(project, other, bus).redo()
    edited = FormulationModel(
        uuid=anfo.uuid, display_name="edited", components=anfo.components
    )
    command = SaveFormulationCommand(project, edited, bus)
    command.redo()
    command.undo()
    assert [f.display_name for f in project.formulations] == ["ANFO", "other"]


def test_deleting_puts_it_back_where_it_was(anfo):
    """Undo has to be a true inverse, position included."""
    project = ProjectModel(name="p")
    bus = EventBus()
    first = FormulationModel(display_name="first")
    last = FormulationModel(display_name="last")
    project.formulations.extend([first, anfo, last])
    command = DeleteFormulationCommand(project, anfo, bus)
    command.redo()
    assert [f.display_name for f in project.formulations] == ["first", "last"]
    command.undo()
    assert [f.display_name for f in project.formulations] == ["first", "ANFO", "last"]


def test_two_identical_recipes_are_told_apart_by_uuid_and_not_by_value():
    """A FROZEN dataclass compares EQUAL field-wise, so `list.index` lies.

    `DeleteCrystalCommand` locates its subject with `list.index(...)`,
    which is safe for a MUTABLE model whose instances are distinct
    objects. Here two formulations stating the same recipe are equal, so
    an index-by-value lookup deletes the first of them -- the wrong row.
    """
    recipe = dict(display_name="same", components=(_AN, _FUEL), loading_density=0.85)
    first = FormulationModel(**recipe)
    second = FormulationModel(**recipe)
    # The setup assertion: without this the test passes vacuously the day
    # FormulationModel stops comparing field-wise.
    assert first.uuid != second.uuid
    assert [first.components, first.display_name] == [
        second.components,
        second.display_name,
    ]
    project = ProjectModel(name="p")
    project.formulations.extend([first, second])
    DeleteFormulationCommand(project, second, EventBus()).redo()
    assert [f.uuid for f in project.formulations] == [first.uuid]


# --- the events -------------------------------------------------------------


def test_a_formulation_gets_its_OWN_selection_event():
    """Never `MoleculeSelected` carrying a formulation uuid.

    Every panel subscribing to `MoleculeSelected` looks the uuid up in
    `project.molecules`, finds nothing, and goes on showing the previous
    molecule's results beside a mixture's name -- the index-space
    confusion `CrystalSelected` was split out to prevent.
    """
    assert FormulationSelected(formulation_uuid="x").formulation_uuid == "x"
    assert FormulationChanged(formulation_uuid="x").formulation_uuid == "x"


# --- the answer must be VISIBLE, not merely present -------------------------


def _sections(view):
    """`{title: expanded}` for every section a FactView is showing."""
    from PySide6.QtWidgets import QToolButton

    from openchem.ui.widgets.collapsible_section import CollapsibleSection

    out = {}
    for section in view.findChildren(CollapsibleSection):
        button = section.findChild(QToolButton)
        if button is not None:
            out[button.text()] = button.isChecked()
    return out


def _anfo_report(anfo):
    from openchem.chem.energetics import build_formulation_report

    return build_formulation_report(anfo)


def test_the_report_opens_with_every_answer_visible(qapp, anfo):
    """**THE WHOLE ANSWER WAS BEHIND A FOLD, AND EVERY TEST WAS GREEN.**

    `DEFAULT_EXPANDED` holds IDENTITY and ELECTRONIC. The composite
    formula, the detonation pressure, the velocity and the heat of
    detonation are all `STRUCTURE`, so the window opened on a name and a
    component list under a collapsed "Structure (4)" -- the identical
    heading, and the identical count, that `FactView._compact`'s own
    docstring already records for the solubility stats block.

    Found by driving the app and looking at the shot. Nothing in the
    suite asserted a section's INITIAL state, which is why it shipped
    that way and why this guard reads `isChecked()` rather than counting
    rows: the facts were always present, and present is not visible.
    """
    from openchem.ui.widgets.fact_view import FactView

    view = FactView()
    try:
        report = _anfo_report(anfo)
        view.set_report(
            report,
            title=report.name,
            expanded={fact.category for fact in report.facts},
        )
        sections = _sections(view)
        assert sections, "the view rendered no sections at all"
        folded = sorted(title for title, shown in sections.items() if not shown)
        assert not folded, f"the answer is behind a fold: {folded}"
    finally:
        _dispose(view)


def test_without_the_override_the_default_fold_still_applies(qapp, anfo):
    """The narrow half, and it is the load-bearing one.

    "Expand everything, always" satisfies the guard above and quietly
    deletes progressive disclosure from the atom report, where
    `DEFAULT_EXPANDED` exists because a hundred-odd facts rendered flat
    is a wall. This asserts the DEFAULT is unchanged -- so the override
    has to be an override rather than a new global.
    """
    from openchem.ui.widgets.fact_view import FactView

    view = FactView()
    try:
        report = _anfo_report(anfo)
        view.set_report(report, title=report.name)
        sections = _sections(view)
        assert sections.get("Structure (4)") is False, (
            "STRUCTURE is not in DEFAULT_EXPANDED, so without an override it "
            f"must still start folded -- got {sections}"
        )
        assert sections.get("Identity (2)") is True
    finally:
        _dispose(view)


# --- the WIRING, not the helper ---------------------------------------------


def test_the_windows_own_report_dialog_opens_with_the_answer_visible(qapp, tmp_path, anfo):
    """Through `MainWindow`, because the two guards above test a HELPER.

    "Testing a helper is not testing the wiring" is a lesson this project
    has paid for twice. `FactView` accepting an `expanded` override says
    nothing about `_formulation_report_dialog` passing one, and that call
    site is the whole fix -- reverting it restores the defect while every
    FactView test stays green.

    It also exercises the production route to `build_formulation_report`
    end to end, which is what
    `test_every_report_builder_is_called_by_the_application` can only
    assert statically.
    """
    from openchem.app.main_window import MainWindow
    from openchem.app.session import SessionManager
    from openchem.app.settings import Settings
    from openchem.bootstrap import build_service_container
    from openchem.ui.widgets.fact_view import FactView

    services = build_service_container()
    settings = Settings(services.event_bus)
    settings.set("plugins/project_directory", str(tmp_path / "no_plugins_here"))
    settings.set("plugins/user_directory", str(tmp_path / "no_user_plugins_here"))
    window = MainWindow(services, settings, SessionManager())
    try:
        # Built and NOT shown -- `exec()` here spins its own event loop and
        # the run stalls on an invisible modal with nobody to close it.
        dialog = window._formulation_report_dialog(anfo)
        view = dialog.findChild(FactView)
        assert view is not None, "the dialog holds no FactView"
        sections = _sections(view)
        assert sections, "the dialog's view rendered no sections"
        folded = sorted(title for title, shown in sections.items() if not shown)
        assert not folded, f"the answer is behind a fold: {folded}"
        # The setup assertion: without it this passes vacuously the day the
        # report stops carrying its results under STRUCTURE.
        assert any(title.startswith("Structure") for title in sections), sections
    finally:
        window.close()
