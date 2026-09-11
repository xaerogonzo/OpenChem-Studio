"""A stale result's picture must not be drawn against the current structure.

**THE FAILURE THIS PREVENTS IS A PLAUSIBLE-LOOKING LIE.** A depiction, a
per-atom dataset and a spatial annotation carry atom INDICES describing the
structure they were computed on. The obvious resolver --
`project.find_molecule(uuid).molblock` -- returns the CURRENT structure, so
after an edit the old result stays visible, correctly marked stale, and its
`atom 7` becomes atom 7 of a different molecule. Nothing looks wrong.

`MoleculeModel` stores exactly one molblock and no history, so there is no
snapshot to resolve against and refusal is the only honest answer. That is a
measurement rather than a preference, and it is why these guards assert a
REFUSAL rather than a correct historical drawing.

The guards come in pairs throughout. Refusing everything satisfies every
"must refuse" test while making the feature useless, so each has a companion
asserting what must still draw.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from rdkit import Chem

from openchem.chem.lewis import compute_lewis_sites
from openchem.domain.common import Provenance
from openchem.domain.molecule import ConformerModel, MoleculeModel
from openchem.domain.project import ProjectModel
from openchem.domain.report import ReportResult
from openchem.domain.structure_resolution import (
    DRAWING_SOURCE,
    INPUT_CONFORMER_KEY,
    INPUT_SOURCE_KEY,
    is_stale,
    resolve_structure_for_report,
    structure_request,
)
from openchem.ui.widgets.results_view import ResultsView
from openchem.ui.widgets.depiction_widget import DepictionWidget
from tests.conftest import dispose

SRC = Path(__file__).resolve().parent.parent / "src" / "openchem"


def _project(molblock: str = "DRAWING", conformers=()) -> ProjectModel:
    return ProjectModel(
        molecules=[MoleculeModel(uuid="u", molblock=molblock, conformers=list(conformers))]
    )


def _report(version: int = 1, parameters: dict | None = None) -> ReportResult:
    return ReportResult(
        report_id="r",
        name="R",
        molecule_uuid="u",
        structure_version=version,
        provenance=(
            None
            if parameters is None
            else Provenance(created_by="c", method="m", parameters=parameters)
        ),
    )


# --- the decision --------------------------------------------------------


def test_a_current_result_resolves_the_molecule():
    assert resolve_structure_for_report(_report(2), _project(), 2).molblock == "DRAWING"


def test_a_stale_result_is_refused_rather_than_drawn_on_the_current_structure():
    """The whole point. It must not merely return "" -- an empty molblock is
    indistinguishable from "no structure here", and the reader would show a
    generic message instead of saying the result is out of date."""
    resolved = resolve_structure_for_report(_report(1), _project(), 2)
    assert not resolved.molblock
    assert resolved.refusal
    assert not resolved.drawable
    # The version numbers travel, so a reader can see WHICH is out of date.
    assert "1" in resolved.refusal and "2" in resolved.refusal


def test_an_unversioned_result_is_stale_against_a_versioned_molecule():
    """A report stamped 0 against a current version above 0 counts as stale --
    the honest answer for "this one does not say when it was computed", and
    the same rule `MergedResults.is_stale` applies to the badge."""
    assert is_stale(0, 3)
    assert resolve_structure_for_report(_report(0), _project(), 3).refusal


def test_a_missing_molecule_fails_closed_with_a_reason():
    """Not a blank frame. "I could not find it" and "there is nothing to
    draw" are different statements."""
    resolved = resolve_structure_for_report(_report(1), ProjectModel(), 1)
    assert resolved.refusal and not resolved.drawable


def test_no_project_at_all_fails_closed():
    assert resolve_structure_for_report(_report(1), None, 1).refusal


def test_a_report_naming_no_molecule_is_not_a_refusal():
    """The narrow half of failing closed. There is nothing to refuse -- a
    report with no molecule has no structure-bound picture to get wrong -- and
    reporting one would put an alarming sentence under every such result."""
    resolved = resolve_structure_for_report(
        ReportResult(report_id="r", name="R", molecule_uuid=""), _project(), 0
    )
    assert not resolved.refusal and not resolved.molblock


# --- the second identity: which conformer --------------------------------


def test_a_conformer_bound_result_draws_on_its_own_conformer():
    """NOT on whichever conformer is displayed. A result can be current for
    the molecule and computed on a geometry that is not the one on screen, so
    structure version alone does not make a picture safe."""
    project = _project(conformers=[
        ConformerModel(conformer_id="c1", molblock="CONF1"),
        ConformerModel(conformer_id="c2", molblock="CONF2"),
    ])
    report = _report(1, {INPUT_SOURCE_KEY: "automatic_lowest_energy", INPUT_CONFORMER_KEY: "c2"})
    assert resolve_structure_for_report(report, project, 1).molblock == "CONF2"


def test_a_vanished_conformer_is_refused_rather_than_substituted():
    """Substituting another conformer would be the same class of wrong as
    drawing a stale result: a different geometry, silently."""
    project = _project(conformers=[ConformerModel(conformer_id="c1", molblock="CONF1")])
    report = _report(1, {INPUT_SOURCE_KEY: "automatic_lowest_energy", INPUT_CONFORMER_KEY: "gone"})
    resolved = resolve_structure_for_report(report, project, 1)
    assert resolved.refusal and "conformer" in resolved.refusal.lower()
    assert resolved.molblock != "CONF1", "it must not fall back to another geometry"


def test_a_drawing_based_result_is_not_refused_for_a_conformer_change():
    """The narrow half. A calculator that ran on the 2D drawing is not
    conformer-bound, and refusing it when conformers change would make the
    rule fire on results it cannot apply to."""
    project = _project(conformers=[ConformerModel(conformer_id="c1", molblock="CONF1")])
    report = _report(1, {INPUT_SOURCE_KEY: DRAWING_SOURCE})
    assert resolve_structure_for_report(report, project, 1).molblock == "DRAWING"


def test_a_result_with_no_geometry_provenance_draws_on_the_drawing():
    """Most reports carry no `input_source` at all. They must not all be
    refused for failing to declare a conformer."""
    assert resolve_structure_for_report(_report(1), _project(), 1).molblock == "DRAWING"


def test_the_input_keys_match_geometry_provenance():
    """These keys are PERSISTED, and `domain/` may not import `chem/` to get
    them -- so they are named twice and this is what stops the two drifting.
    Promised in the module docstring; asserted here."""
    from openchem.chem.calculation_input import INPUT_PREFIX

    assert INPUT_SOURCE_KEY == f"{INPUT_PREFIX}source"
    assert INPUT_CONFORMER_KEY == f"{INPUT_PREFIX}conformer_id"


# --- what the reader does with it ----------------------------------------


def _lewis_report(version: int):
    mol = Chem.MolFromSmiles("CCO")
    molblock = Chem.MolToMolBlock(Chem.AddHs(mol, addCoords=True))
    base = compute_lewis_sites(mol, "u")
    assert base.charts, "fixture is degenerate: Lewis Sites declared no depiction"
    return type(base)(**{**base.__dict__, "structure_version": version}), molblock


def _depiction(dialog) -> DepictionWidget:
    widgets = [w for w in dialog._view.chart_widgets() if isinstance(w, DepictionWidget)]
    assert len(widgets) == 1, f"expected one depiction, got {len(widgets)}"
    return widgets[0]


def test_the_lewis_depiction_actually_draws(qapp):
    """**IT NEVER HAD, IN PRODUCTION.** `lewis_site_depiction` builds a
    complete `DepictionAnnotation` and `compute_lewis_sites` attaches it, but
    `set_structure_resolver` had zero production callers -- only the drive
    harness -- so the diagram was fully built, tested, and invisible.

    `isHidden`, not `isVisible`: every child of an unshown window reports
    False for the latter, which this repository has paid for twice.
    """
    report, molblock = _lewis_report(4)
    project = _project(molblock)
    dialog = ResultsView("u")
    dialog.set_structure_resolver(lambda r: resolve_structure_for_report(r, project, 4))
    dialog.set_reports([report], structure_version=4)
    dialog.set_focus("lewis_sites")
    widget = _depiction(dialog)
    assert widget._view.renderer().isValid(), "the depiction rendered nothing"
    assert not widget._view.isHidden()
    assert widget._message.isHidden()
    dispose(dialog)


def test_a_stale_lewis_depiction_refuses_on_screen(qapp):
    """And the reason is where the picture would have been -- not in a log,
    not in a tooltip. A reader who cannot see it has been shown a blank."""
    report, molblock = _lewis_report(4)
    project = _project(molblock)
    dialog = ResultsView("u")
    dialog.set_structure_resolver(lambda r: resolve_structure_for_report(r, project, 5))
    dialog.set_reports([report], structure_version=5)
    dialog.set_focus("lewis_sites")
    widget = _depiction(dialog)
    assert widget._view.isHidden(), "a stale depiction must not render"
    assert not widget._message.isHidden()
    assert "earlier version" in widget._message.text()
    dispose(dialog)


def test_a_view_with_no_resolver_still_renders_a_chart_that_needs_no_structure(qapp):
    """The narrow half of the whole feature. A plot on axes carries its own
    coordinates, so a host with no project must not lose it -- only the
    depiction depends on a structure."""
    from openchem.domain.report import LineChartAnnotation, LineSeries
    from openchem.ui.widgets.line_chart_widget import LineChartWidget

    chart = LineChartAnnotation(
        series=(LineSeries(points=((0.0, 1.0), (1.0, 2.0)), name="s"),),
        x_label="pH",
        y_label="logD",
        x_descending=False,
        title="Curve",
    )
    dialog = ResultsView("u")
    dialog.set_reports([ReportResult(report_id="c", name="C", molecule_uuid="u", charts=(chart,))])
    dialog.set_focus("c")
    assert any(isinstance(w, LineChartWidget) for w in dialog._view.chart_widgets())
    dispose(dialog)


def test_a_resolver_that_raises_refuses_rather_than_escaping_the_paint_path(qapp):
    report, _molblock = _lewis_report(1)

    def boom(_report):
        raise RuntimeError("project exploded")

    dialog = ResultsView("u")
    dialog.set_structure_resolver(boom)
    dialog.set_reports([report], structure_version=1)
    dialog.set_focus("lewis_sites")
    widget = _depiction(dialog)
    assert not widget._message.isHidden()
    assert "unavailable" in widget._message.text().lower()
    dispose(dialog)


# --- the wiring ----------------------------------------------------------


def _is_a_pure_forward(tree: ast.Module, call: ast.Call) -> bool:
    """Whether this `set_structure_resolver` call merely passes its own
    parameter along.

    **THE GUARD BELOW FLAGGED ONE ON ITS FIRST RUN, AND THAT WAS A FALSE
    POSITIVE ON CORRECT CODE.** `MergedResultsDialog.set_structure_resolver`
    hands the host's resolver down to its `FactView` -- it does not decide
    anything, so demanding it call the domain decision would be demanding a
    pass-through re-derive what it was given. A guard whose first finding is a
    false positive is a guard that gets deleted.

    The rule is structural: the argument is a bare name, and that name is a
    parameter of the enclosing function.
    """
    arg = call.args[0]
    if not isinstance(arg, ast.Name):
        return False
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if call not in set(ast.walk(node)):
            continue
        params = {a.arg for a in node.args.args} | {a.arg for a in node.args.kwonlyargs}
        if arg.id in params:
            return True
    return False


def test_a_production_host_supplies_a_resolver():
    """The wide half, asserted on the SOURCE.

    A depiction that silently cannot draw is what the last several months
    looked like, and nothing failed. `PropertyPanel` is the host with both the
    project and the structure version, so it is the one that must wire it.
    """
    source = (SRC / "ui" / "panels" / "property_panel.py").read_text(encoding="utf-8")
    assert "set_structure_resolver" in source, (
        "no production host supplies a render context -- every declared "
        "depiction is invisible again"
    )


def test_no_host_resolves_a_structure_without_going_through_the_decision():
    """The narrow half, and the one that matters.

    `project.find_molecule(uuid).molblock` is the obvious resolver and the
    unsafe one -- it answers with the CURRENT structure for a result that may
    describe an older one. This walks every `ui/` module for a resolver that
    does not route through the domain decision, so the safe path cannot be
    bypassed by writing the tempting one-liner beside it.
    """
    wanted = "resolve_structure_for_report"
    offenders: list[str] = []
    for path in (SRC / "ui").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
                continue
            if node.func.attr != "set_structure_resolver" or not node.args:
                continue
            if _is_a_pure_forward(tree, node):
                continue
            names = {
                n.id for n in ast.walk(node.args[0]) if isinstance(n, ast.Name)
            } | {
                n.attr for n in ast.walk(node.args[0]) if isinstance(n, ast.Attribute)
            }
            if not any(wanted in name for name in names):
                offenders.append(f"{path.relative_to(SRC)}:{node.lineno}")
    assert not offenders, (
        "a host resolves a structure without the staleness decision: "
        + ", ".join(offenders)
        + f" -- route it through {wanted}"
    )


@pytest.mark.parametrize(
    "version, current, expected",
    [(1, 1, False), (1, 2, True), (0, 0, False), (0, 1, True), (2, 1, True)],
)
def test_staleness_has_one_rule(version, current, expected):
    """`is_stale` and the refusal decision cannot disagree, because the second
    calls the first. Asserted together so a future shortcut in either is
    caught."""
    assert is_stale(version, current) is expected
    assert bool(structure_request(_report(version), current).refusal) is expected
