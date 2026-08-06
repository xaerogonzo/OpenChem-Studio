"""The Structure Check surfaces: the service, the panel, the status light.

Every widget built here is destroyed deterministically at teardown --
`setParent(None)`, `deleteLater()`, and a flush of THAT widget's own
DeferredDelete. Not the global form: draining every pending deferred delete
in the process takes ones other test files queued on already-collected
objects with it, which is the double-free CLAUDE.md records.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, Qt
from rdkit import Chem
from rdkit.Chem import AllChem
from rdkit.Geometry import Point3D

from openchem.app.main_window import MainWindow
from openchem.app.session import SessionManager
from openchem.app.settings import Settings
from openchem.bootstrap import build_service_container
from openchem.chem.engine import ChemistryEngine
from openchem.domain.molecule import MoleculeModel
from openchem.domain.structure_issue import (
    Basis,
    Category,
    CheckerResult,
    Severity,
    SkippedChecker,
    StructureIssue,
)
from openchem.events.base import EventBus
from openchem.events.events import MoleculeChanged, StructureChecked
from openchem.services.structure_check_service import StructureCheckService
from openchem.ui.panels.structure_check_panel import StructureCheckPanel
from openchem.ui.widgets.checker_status_indicator import CheckerStatusIndicator


def molblock_for(smiles: str, mutate=None) -> str:
    mol = Chem.MolFromSmiles(smiles, sanitize=False)
    mol.UpdatePropertyCache(strict=False)
    AllChem.Compute2DCoords(mol)
    if mutate is not None:
        mutate(mol.GetConformer())
    return Chem.MolToMolBlock(mol, kekulize=False)


@pytest.fixture
def widgets():
    built = []
    yield built
    for widget in built:
        widget.close()
        widget.setParent(None)
        widget.deleteLater()
        QCoreApplication.sendPostedEvents(widget, QEvent.Type.DeferredDelete)


@pytest.fixture
def bus() -> EventBus:
    return EventBus()


@pytest.fixture
def service(bus) -> StructureCheckService:
    return StructureCheckService(bus)


@pytest.fixture
def panel(qapp, service, bus, widgets) -> StructureCheckPanel:
    built = StructureCheckPanel(service, ChemistryEngine(), bus)
    widgets.append(built)
    return built


# --- the service ------------------------------------------------------------


def test_checking_publishes_the_result(service, bus, qapp):
    seen = []
    bus.subscribe(StructureChecked, lambda event: seen.append(event.result))

    returned = service.check("uuid", molblock_for("CCO"))
    qapp.processEvents()

    assert len(seen) == 1
    assert seen[0] is returned  # the caller gets it without a round trip


def test_every_edit_bumps_the_molecules_version(service, bus, qapp):
    assert service.current_version("uuid") == 0

    bus.publish(MoleculeChanged(molecule_uuid="uuid"))
    qapp.processEvents()

    assert service.current_version("uuid") == 1


def test_a_result_from_before_the_last_edit_is_not_current(service, bus, qapp):
    """The anti-staleness contract in one test.

    Editing is faster than checking. A result that arrives after the next
    edit describes atoms that have since been renumbered, so its highlights
    would point somewhere arbitrary -- and the panel would be showing a
    finding about a structure that no longer exists.
    """
    stale = service.check("uuid", molblock_for("CCO"))
    assert service.is_current(stale)

    bus.publish(MoleculeChanged(molecule_uuid="uuid"))
    qapp.processEvents()

    assert not service.is_current(stale)


def test_a_version_bump_on_one_molecule_does_not_stale_another(service, bus, qapp):
    other = service.check("other", molblock_for("CCO"))

    bus.publish(MoleculeChanged(molecule_uuid="uuid"))
    qapp.processEvents()

    assert service.is_current(other)


def test_suppression_is_per_molecule_and_recorded(service):
    service.suppress("uuid", "valence")

    result = service.check("uuid", molblock_for("C[N](C)(C)(C)C"))

    assert result.suppressed == ("valence",)
    assert "valence" not in {issue.checker_id for issue in result.issues}
    assert service.check("other", molblock_for("C[N](C)(C)(C)C")).errors


def test_applying_an_unknown_fix_raises_rather_than_silently_doing_nothing(service):
    with pytest.raises(KeyError):
        service.apply_fix("no_such_fix", molblock_for("CCO"))


def test_the_service_does_not_edit_the_molecule_itself(service):
    """`apply_fix` returns a molblock and touches nothing.

    A service that edited the project directly would produce a structure
    change nobody can undo -- worse than the issue it repaired. The command
    stays with the caller that owns the undo stack.
    """
    before = molblock_for("CC(=O)[O-].[Na+]")

    after = service.apply_fix("keep_largest_fragment", before)

    assert after != before
    assert "Na" in before  # the input was not mutated


# --- the status light -------------------------------------------------------


def _result(*issues: StructureIssue, skipped=()) -> CheckerResult:
    return CheckerResult(molecule_uuid="uuid", issues=tuple(issues), skipped=tuple(skipped))


def _issue(severity: Severity, category: Category = Category.VALIDITY, **kwargs) -> StructureIssue:
    return StructureIssue(
        checker_id=kwargs.pop("checker_id", "test"),
        category=category,
        severity=severity,
        basis=kwargs.pop("basis", Basis.DETERMINISTIC),
        message=kwargs.pop("message", "something"),
        **kwargs,
    )


def test_the_light_starts_disabled(qapp, widgets):
    indicator = CheckerStatusIndicator()
    widgets.append(indicator)

    assert indicator.state() == "disabled"


@pytest.mark.parametrize(
    "issues, expected",
    [
        ((), "clean"),
        ((Severity.INFO,), "clean"),
        ((Severity.WARNING,), "warning"),
        ((Severity.ERROR,), "error"),
        ((Severity.INFO, Severity.WARNING, Severity.ERROR), "error"),
    ],
)
def test_the_light_shows_the_most_serious_finding(qapp, widgets, issues, expected):
    """Notes do NOT turn it amber.

    An isotope label or an explained hypervalent centre is information. A
    light that goes amber for those trains people to ignore amber, which
    costs more than it gains.
    """
    indicator = CheckerStatusIndicator()
    widgets.append(indicator)

    indicator.show_result(_result(*(_issue(severity) for severity in issues)))

    assert indicator.state() == expected


def test_the_light_counts_what_it_found(qapp, widgets):
    indicator = CheckerStatusIndicator()
    widgets.append(indicator)

    indicator.show_result(_result(_issue(Severity.ERROR), _issue(Severity.WARNING)))

    assert "1 error" in indicator.text()
    assert "1 warning" in indicator.text()


def test_notes_are_counted_rather_than_dismissed(qapp, widgets):
    """An INFO-only result is clean, but it is not "No issues".

    Added after mutation testing: dropping the notes branch entirely left
    the state `clean` either way, so nothing noticed that an explained
    hypervalent centre had stopped being mentioned at all.
    """
    indicator = CheckerStatusIndicator()
    widgets.append(indicator)

    indicator.show_result(_result(_issue(Severity.INFO)))

    assert indicator.state() == "clean"
    assert "1 note" in indicator.text()


def test_every_state_has_its_own_symbol(qapp, widgets):
    """Roughly one man in twelve cannot tell the red from the amber, so the
    symbol has to carry the distinction on its own.

    Asserted over the whole table rather than by comparing two rendered
    strings: those also differ in the words "error" and "warning", so they
    stayed different even when both states were given the same symbol.
    """
    from openchem.ui.widgets.checker_status_indicator import _STATES

    symbols = [symbol for symbol, _, _ in _STATES.values()]

    assert len(set(symbols)) == len(symbols)


# --- the panel --------------------------------------------------------------


def _rows(panel: StructureCheckPanel) -> list[str]:
    tree = panel._tree
    return [tree.topLevelItem(i).text(0) for i in range(tree.topLevelItemCount())]


def test_findings_are_grouped_by_category_with_counts(panel, service):
    panel.set_molblock(molblock_for("CC(=O)[O-].[Na+]"))

    panel.show_result(service.check("uuid", molblock_for("CC(=O)[O-].[Na+]")))

    assert any(row.startswith("How it is written (") for row in _rows(panel))


def test_chemistry_is_listed_above_drawing(panel, service):
    """VALIDITY first, LAYOUT last. Burying "this valence is impossible"
    among cosmetic complaints is how the serious one gets missed."""

    def stack(conformer):
        position = conformer.GetAtomPosition(0)
        conformer.SetAtomPosition(3, Point3D(position.x, position.y, position.z))

    molblock = molblock_for("C[N](C)(C)(C)C", stack)
    panel.set_molblock(molblock)

    panel.show_result(service.check("uuid", molblock))

    rows = _rows(panel)
    assert rows[0].startswith("Chemistry")


def test_checkers_that_did_not_run_are_listed_with_their_reason(panel, service):
    molblock = molblock_for("C[I](C)(C)(C)(C)C")
    panel.set_molblock(molblock)

    panel.show_result(service.check("uuid", molblock))

    tree = panel._tree
    skipped_row = next(
        tree.topLevelItem(i)
        for i in range(tree.topLevelItemCount())
        if tree.topLevelItem(i).text(0).startswith("Not checked")
    )
    assert "does not sanitize" in skipped_row.child(0).text(0)


def test_the_panel_discards_a_result_the_structure_has_moved_past(panel, service, bus, qapp):
    """The other half of the version contract, at the surface that shows it.

    Built by hand at an old version rather than by checking and then
    editing, because "discard" means "do not update" -- a result that was
    displayed while it was current stays on screen, so a test that showed
    one first would pass without the guard doing anything.
    """
    bus.publish(MoleculeChanged(molecule_uuid="uuid"))
    qapp.processEvents()
    stale = CheckerResult(
        molecule_uuid="uuid", structure_version=0, issues=(_issue(Severity.ERROR),)
    )

    bus.publish(StructureChecked(result=stale))
    qapp.processEvents()

    assert _rows(panel) == []


def test_the_panel_does_display_a_current_result(panel, service, bus, qapp):
    """The complement. Without it, a guard that rejected everything would
    pass the test above -- and the panel would silently never update."""
    bus.publish(MoleculeChanged(molecule_uuid="uuid"))
    qapp.processEvents()
    current = CheckerResult(
        molecule_uuid="uuid", structure_version=1, issues=(_issue(Severity.ERROR),)
    )

    bus.publish(StructureChecked(result=current))
    qapp.processEvents()

    assert _rows(panel) == ["Chemistry (1)"]


def _select_issue_with_fix(panel: StructureCheckPanel, fix_id: str) -> None:
    tree = panel._tree
    for i in range(tree.topLevelItemCount()):
        top = tree.topLevelItem(i)
        for j in range(top.childCount()):
            issue = top.child(j).data(0, Qt.ItemDataRole.UserRole)
            if isinstance(issue, StructureIssue) and issue.fix_id == fix_id:
                tree.setCurrentItem(top.child(j))
                return
    raise AssertionError(f"no issue offering {fix_id!r}")


def test_the_fix_button_says_what_the_fix_will_cost(panel, service):
    """"Lossy" is on the button, before it is pressed. Keeping the largest
    fragment of a salt removes the counter-ion."""
    molblock = molblock_for("CC(=O)[O-].[Na+]")
    panel.set_molblock(molblock)
    panel.show_result(service.check("uuid", molblock))

    _select_issue_with_fix(panel, "keep_largest_fragment")

    assert panel._fix_button.isEnabled()
    assert "lossy" in panel._fix_button.text()


def test_selecting_an_issue_explains_what_the_verdict_rests_on(panel, service):
    molblock = molblock_for("CC(=O)[O-].[Na+]")
    panel.set_molblock(molblock)
    panel.show_result(service.check("uuid", molblock))

    _select_issue_with_fix(panel, "keep_largest_fragment")

    assert "Definite" in panel._detail.text()


def test_a_heuristic_finding_says_a_threshold_is_involved(panel, service):
    def stretch(conformer):
        position = conformer.GetAtomPosition(5)
        conformer.SetAtomPosition(5, Point3D(position.x + 8.0, position.y, position.z))

    molblock = molblock_for("CCCCCC", stretch)
    panel.set_molblock(molblock)
    panel.show_result(service.check("uuid", molblock))

    _select_issue_with_fix(panel, "recompute_layout")

    assert "Judgement" in panel._detail.text()


def test_an_issue_with_no_registered_fix_leaves_the_button_disabled(panel, service):
    molblock = molblock_for("[CH2]")
    panel.set_molblock(molblock)
    panel.show_result(service.check("uuid", molblock))

    tree = panel._tree
    tree.setCurrentItem(tree.topLevelItem(0).child(0))

    assert not panel._fix_button.isEnabled()


def test_the_panel_survives_a_structure_that_cannot_be_depicted(panel, service):
    """Half the structures worth checking are ones RDKit refuses -- which
    is exactly when the checker has the most to say and when the depiction
    is most likely to fail. A blank drawing beside a readable message beats
    an exception that takes the panel down.
    """
    molblock = molblock_for("C[I](C)(C)(C)(C)C")
    panel.set_molblock(molblock)

    panel.show_result(service.check("uuid", molblock))
    tree = panel._tree
    tree.setCurrentItem(tree.topLevelItem(0).child(0))

    assert _rows(panel)  # it rendered the findings regardless


def test_the_summary_reports_valences_we_accept_that_the_editor_flags(panel, service):
    """The one honest thing we can say about the canvas's own warnings.

    Ketcher exposes no way to enumerate them, so a general "3 editor
    warnings ignored" counter is not implementable -- but we do know when
    our own correction rules fired, which is the more useful direction.
    """
    molblock = molblock_for("FI(F)(F)(F)(F)(F)F")
    panel.set_molblock(molblock)

    panel.show_result(service.check("uuid", molblock))

    assert "accepted here" in panel._summary.text()


# --- the window -------------------------------------------------------------


@pytest.fixture
def window(qapp, tmp_path, widgets) -> MainWindow:
    services = build_service_container()
    settings = Settings(services.event_bus)
    settings.set("plugins/project_directory", str(tmp_path / "no_plugins"))
    settings.set("plugins/user_directory", str(tmp_path / "no_user"))
    main_window = MainWindow(services, settings, SessionManager())
    widgets.append(main_window)
    return main_window


def _add(window: MainWindow, name: str, smiles: str) -> MoleculeModel:
    molecule = MoleculeModel(display_name=name)
    molecule.molblock = molblock_for(smiles)
    window.add_molecule(molecule)
    QCoreApplication.processEvents()
    return molecule


def test_selecting_a_molecule_checks_it_without_being_asked(window):
    """A button somebody has to remember to press is a checker that reports
    on the structure you had five edits ago."""
    _add(window, "Ethanol", "CCO")

    assert window._checker_indicator.state() == "clean"


def test_the_reported_iron_oxide_bug_is_clean_in_the_window(window):
    """"Iron also strangely shows valence issues with all the oxides."

    The canvas will still draw its red circle -- Indigo's model is inside
    compiled WASM and there is no API to change or read it -- but the app's
    own verdict, in the status bar, is that there is nothing wrong.
    """
    _add(window, "Iron(III) oxide", "O=[Fe]O[Fe]=O")

    assert window._checker_indicator.state() == "clean"


def test_a_bad_valence_lights_the_indicator_red(window):
    _add(window, "Five-valent nitrogen", "C[N](C)(C)(C)C")

    assert window._checker_indicator.state() == "error"


def test_a_quick_fix_lands_on_the_undo_stack(window):
    """Every fix goes through `EditStructureCommand`. A repair that cannot
    be undone is worse than the issue it fixed, and this is the one place
    the app rewrites a structure without the user drawing anything.
    """
    molecule = _add(window, "Sodium acetate", "CC(=O)[O-].[Na+]")
    before_depth = window._undo_stack.count()
    before = molecule.molblock

    window._apply_structure_fix("keep_largest_fragment", molecule.molblock)
    QCoreApplication.processEvents()

    assert window._undo_stack.count() == before_depth + 1
    assert molecule.molblock != before

    window._undo_stack.undo()
    QCoreApplication.processEvents()
    assert molecule.molblock == before


def test_a_fix_that_would_change_nothing_says_so_instead_of_pushing_a_command(window):
    """An undo entry that undoes nothing is worse than no entry: it makes
    Ctrl+Z appear to do nothing, twice."""
    molecule = _add(window, "Ethanol", "CCO")
    before_depth = window._undo_stack.count()

    window._apply_structure_fix("keep_largest_fragment", molecule.molblock)
    QCoreApplication.processEvents()

    assert window._undo_stack.count() == before_depth


def test_the_check_panel_has_a_help_topic(window):
    """`_add_dock` only gives a "?" to docks with a topic, and
    tests/test_help.py fails if the topic names no anchor."""
    from openchem.app.main_window import HELP_TOPIC_BY_DOCK

    assert HELP_TOPIC_BY_DOCK[window._structure_check_dock.objectName()] == "structure-check"
