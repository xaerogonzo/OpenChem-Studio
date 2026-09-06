"""The virtual screening dialog.

Its table shipped with one column configured and three left at Qt's
default width, which clipped the longest header at both ends. Found by
driving the dialog and magnifying the shot, with every test in the suite
green -- the dialogs had no coverage at all until this file.
"""

from __future__ import annotations

import pytest

from openchem.bootstrap import build_service_container
from openchem.domain.molecule import MoleculeModel
from openchem.domain.project import ProjectModel
from openchem.ui.dialogs.inventory import DialogContext, iter_dialog_fixtures

import conftest


@pytest.fixture
def dialog(qapp):
    """Built through `ui/dialogs/inventory.py`, not by hand.

    That module is the one place that knows how each dialog is
    constructed, shared with the `OPENCHEM_DRIVE` harness. Reaching past
    it here would be the second implementation it exists to prevent --
    and this fixture is also the proof that a guard CAN use it, which is
    what the drive step alone would not establish.
    """
    services = build_service_container()
    molecule = MoleculeModel(display_name="Aspirin")
    services.chemistry_engine.set_structure_from_smiles(molecule, "CC(=O)Oc1ccccc1C(=O)O")
    context = DialogContext(
        services=services,
        molecule=molecule,
        project=ProjectModel(name="screening", molecules=[molecule]),
    )
    fixture = next(f for f in iter_dialog_fixtures() if f.name == "VirtualScreeningDialog")
    built = fixture.build(context)
    yield built
    conftest.dispose(built)


def test_no_results_header_is_narrower_than_its_own_text(dialog):
    """Every column header fits the words in it.

    ASSERTED IN THE HEADER'S OWN FONT, so this is a claim about the
    layout and not about the platform: `offscreen`'s default font is far
    wider than a user's, and a pinned pixel width here would fail against
    a dialog that is measurably clean in the app.

    The defect this catches rendered "Best score (kcal/mol)" as
    "est score (kcal/mo" -- clipped at BOTH ends, which is the tell that
    a section is narrower than its content rather than merely elided.
    """
    dialog.resize(900, 600)
    dialog.grab()  # a widget that was never shown lays nothing out

    header = dialog._results.horizontalHeader()
    metrics = header.fontMetrics()

    too_narrow = []
    for column in range(dialog._results.columnCount()):
        item = dialog._results.horizontalHeaderItem(column)
        text = item.text() if item is not None else ""
        needed = metrics.horizontalAdvance(text)
        if header.sectionSize(column) < needed:
            too_narrow.append((text, header.sectionSize(column), needed))

    assert not too_narrow, (
        "column header(s) narrower than their own text, so the words are "
        f"clipped: {too_narrow}"
    )


def test_the_ligand_column_is_the_one_that_absorbs_the_slack(dialog):
    """The other half, and the one that fails if every column is fixed.

    Sizing all four to their contents would satisfy the guard above while
    leaving a ragged table with dead space on the right. Ligand holds the
    variable-length value and is the column that should grow, which is
    what makes the arrangement a decision rather than an accident.
    """
    dialog.resize(1200, 600)
    dialog.grab()

    header = dialog._results.horizontalHeader()
    sizes = [header.sectionSize(c) for c in range(dialog._results.columnCount())]

    assert sizes[1] == max(sizes), (
        f"Ligand is not the widest column ({sizes}); the slack has gone "
        "somewhere it cannot be read"
    )
    assert sizes[1] > sum(sizes[c] for c in (0, 2, 3)) / 3, (
        f"Ligand did not absorb the extra width on a 1200 px dialog: {sizes}"
    )


# -- the pocket the screen used to dock into with the crystal ligand in it --


def _hetatm(serial, name, code, chain, resnum, x, y, z, element):
    """One column-exact HETATM record. The columns are load-bearing -- a
    mis-aligned fixture parses as a different residue entirely, which is
    the trap `tests/test_binding_site.py` records."""
    return (
        f"HETATM{serial:>5d} {name:<4} {code:>3} {chain}{resnum:>4d}    "
        f"{x:>8.3f}{y:>8.3f}{z:>8.3f}  1.00 20.00          {element:>2}\n"
    )


#: A receptor with a boxable ligand in it, so `_start` reaches
#: `request_screen` through the REAL `box_from_ligand` rather than past a
#: monkeypatched one. Without a parseable structure the dialog reports a
#: failure and returns, and a guard written that way asserts nothing.
_RECEPTOR_PDB = "HEADER    TEST\n" + "".join([
    _hetatm(1, "C1", "MK1", "A", 500, 0.0, 0.0, 0.0, "C"),
    _hetatm(2, "C2", "MK1", "A", 500, 4.0, 4.0, 4.0, "C"),
    _hetatm(3, "N1", "MK1", "A", 500, 2.0, 2.0, 2.0, "N"),
    _hetatm(4, "CA", "ALA", "A", 1, 30.0, 30.0, 30.0, "C"),
]) + "END\n"


class _CapturingScreeningService:
    """Records the one call, and never runs anything."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def request_screen(self, ligands, receptor, box, **kwargs) -> None:
        self.calls.append({"ligands": ligands, "receptor": receptor, "box": box, **kwargs})

    def cancel(self) -> None:  # the Cancel button connects to it at build time
        pass


def _screen_and_capture(qapp, metadata):
    """Drive the real Run button and return the one request it made."""
    from openchem.domain.macromolecule import MacromoleculeModel
    from openchem.events.base import EventBus
    from openchem.ui.dialogs.virtual_screening_dialog import VirtualScreeningDialog

    receptor = MacromoleculeModel(
        display_name="Receptor",
        structure_text=_RECEPTOR_PDB,
        source_format="pdb",
        metadata=metadata,
    )
    ligand = MoleculeModel(display_name="Ethanol")
    build_service_container().chemistry_engine.set_structure_from_smiles(ligand, "CCO")
    project = ProjectModel(name="p", molecules=[ligand], macromolecules=[receptor])

    service = _CapturingScreeningService()
    dialog = VirtualScreeningDialog(service, EventBus(), project)
    try:
        dialog._start()
    finally:
        conftest.dispose(dialog)
    return service.calls


def test_a_screen_strips_the_ligand_that_defined_its_own_box(qapp):
    """THE DEFECT THIS FILE WAS WRITTEN FOR.

    `_start` passed no `receptor_prep_options` at all, so
    `strip_ligand_codes` defaulted to empty and every screen against a
    catalogued receptor searched a pocket the co-crystallised ligand was
    still occupying. `pose_analysis.is_stripped_residue` measured that on
    real Vina against real 1HSG -- indinavir into its own structure, -5.34
    against -9.78 kcal/mol, and the occupied run was SLOWER -- and named
    this surface as the one that suffers most, because the penalty is
    size-dependent and so the RANKING can invert.

    Asserted on what reaches the service, not on the helper: the helper
    was correct the whole time and the dialog simply never called it.
    """
    calls = _screen_and_capture(qapp, {"ligand_code": "MK1"})

    assert len(calls) == 1, "the run did not reach the service at all"
    prep = calls[0].get("receptor_prep_options") or {}
    assert prep.get("strip_ligand_codes") == ["MK1"]


def test_a_receptor_with_no_ligand_code_never_reaches_the_service_at_all(qapp):
    """WHY THE NARROW HALF IS NOT ASSERTED HERE, written down rather than
    left as a gap.

    The obvious companion to the guard above is "an imported receptor
    strips nothing". Through this dialog that case is UNREACHABLE: `_start`
    needs `metadata["ligand_code"]` to derive the box in the first place,
    so a receptor without one is refused several lines before
    `strip_ligand_codes` could matter. A test written that way would assert
    on an empty call list and pass whatever the prep dict said.

    So the reachable property is this one -- the dialog refuses rather than
    screening an unboxed receptor -- and the narrow half lives on the
    predicate, in `tests/test_binding_site.py::
    test_an_imported_receptor_has_nothing_stripped`. This project's own
    rule: an unreachable branch is a question about WHERE to assert.
    """
    calls = _screen_and_capture(qapp, {})

    assert calls == [], (
        "a receptor with no ligand_code was screened anyway; if the dialog "
        "ever learns to box one, the imported-receptor strip case becomes "
        "reachable here and needs its own guard"
    )


def test_the_screen_and_the_panel_ask_THE_SAME_FUNCTION(qapp):
    """One implementation, so the two surfaces cannot drift apart again.

    This project has paid for that drift four times -- `is_stripped_residue`,
    `filter_altlocs`, `is_symmetry_generated`, `normalise_element_symbols` --
    and the defect above is what it looks like when one copy is simply
    missing. A source check rather than a behavioural one, because two
    correct copies agree on every input and only their EXISTENCE differs.
    """
    import ast
    import inspect

    from openchem.ui.dialogs import virtual_screening_dialog
    from openchem.ui.panels import docking_panel

    def imported_names(module) -> set[str]:
        tree = ast.parse(inspect.getsource(module))
        return {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module == "openchem.chem.binding_site"
            for alias in node.names
        }

    assert "box_defining_ligand_codes" in imported_names(docking_panel)
    assert "box_defining_ligand_codes" in imported_names(virtual_screening_dialog)
