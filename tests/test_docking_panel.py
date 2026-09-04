from __future__ import annotations

import pytest
from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.app.settings import Settings
from openchem.chem.engine import ChemistryEngine
from openchem.domain.conformer import ConformerModel
from openchem.domain.macromolecule import MacromoleculeModel
from openchem.domain.molecule import MoleculeModel
from openchem.domain.project import ProjectModel
from openchem.events.base import EventBus
from openchem.events.events import MoleculeSelected
from openchem.services.docking_service import DockingService
from openchem.ui.panels.docking_panel import DockingPanel

import conftest


class _RecordingDockingService(DockingService):
    """Stands in for the real DockingService -- captures request_docking's
    kwargs instead of actually scheduling a QThreadPool job, so tests can
    inspect exactly what ligand Mol the panel built without needing a real
    Vina backend."""

    def __init__(self, event_bus: EventBus) -> None:
        super().__init__(event_bus, Settings(event_bus), providers={})
        self.requests: list[dict] = []

    def request_docking(self, **kwargs) -> None:  # noqa: D102 - test double
        self.requests.append(kwargs)


#: Every panel this file builds, destroyed at the end of its test.
#:
#: **THIS FILE LEAKED ALL 26 OF THEM**, and the census on the Linux job is what
#: said so: this branch's runs reported "1 late destruction" where master's
#: reported 0. A late destruction is a widget built in one test and destroyed
#: inside a LATER one, from Python's collector rather than at a boundary --
#: which is the shape this project's access-violation family has.
#:
#: Five of the guards added here `show()` their panel, and a shown widget runs
#: far more of its own code and holds far more state than an unshown one, so
#: what was a dormant leak became a live one.
#:
#: `conftest.dispose` is THE implementation -- the same one
#: `test_screening_service.py` and `test_batch_panel.py` take, per file and per
#: widget. It is emphatically NOT `dispose_app_widgets`, the autouse fixture
#: that DISCOVERED its own subjects and was reverted for crashing the suite 8
#: of 8 runs.
_BUILT: list = []


@pytest.fixture(autouse=True)
def _dispose_panels():
    """Destroyed deterministically rather than left to the collector.

    Autouse over the FIXTURE, not over the widgets: it serves only what
    `_make_panel` explicitly hands over, which is what keeps it on the safe
    side of the line `conftest.dispose` draws.
    """
    yield
    while _BUILT:
        conftest.dispose(_BUILT.pop())


def _make_panel():
    bus = EventBus()
    engine = ChemistryEngine()
    settings = Settings(bus)
    docking_service = _RecordingDockingService(bus)
    panel = DockingPanel(docking_service, engine, settings, bus)
    _BUILT.append(panel)
    return panel, engine, docking_service


def _project_with_receptor_and_ligand(ligand: MoleculeModel) -> ProjectModel:
    project = ProjectModel(name="Test project")
    receptor = MacromoleculeModel(
        display_name="Receptor", structure_text="HEADER\nATOM\nEND\n", source_format="pdb"
    )
    project.macromolecules.append(receptor)
    project.molecules.append(ligand)
    return project


def _has_nonzero_z_coordinate(mol) -> bool:
    conf = mol.GetConformer()
    return any(abs(conf.GetAtomPosition(i).z) > 1e-6 for i in range(mol.GetNumAtoms()))


def test_dock_click_prefers_3d_conformer_over_flat_2d_molblock(qapp):
    """Regression test: docking used to build the ligand Mol straight from
    the molecule's own (possibly 2D, all-zero-z) molblock via
    mol_from_model -- QuantumChemistryPanel already preferred a stored 3D
    conformer, and DockingPanel needed the identical fix (docking a flat
    structure against a 3D receptor is scientifically meaningless).

    `Chem.MolFromMolBlock` removes explicit Hs by default, so atom count
    alone can't distinguish the two sources once both are re-parsed -- the
    real, reliable signal is that the 2D editor's molblock has z=0 for
    every atom, while an embedded 3D conformer (essentially) never does.
    """
    panel, engine, docking_service = _make_panel()

    ligand = MoleculeModel(display_name="Ethanol")
    engine.set_structure_from_smiles(ligand, "CCO")  # flat molblock, no conformer
    assert not _has_nonzero_z_coordinate(engine.mol_from_molblock(ligand.molblock))

    mol_3d = Chem.AddHs(engine.mol_from_smiles("CCO"))
    AllChem.EmbedMolecule(mol_3d, randomSeed=1)
    assert _has_nonzero_z_coordinate(mol_3d)
    ligand.conformers.append(ConformerModel(molblock=Chem.MolToMolBlock(mol_3d)))

    panel.set_project(_project_with_receptor_and_ligand(ligand))
    panel._receptor_combo.setCurrentIndex(0)
    panel._ligand_combo.setCurrentIndex(0)

    panel._on_dock_clicked()

    assert len(docking_service.requests) == 1
    used_mol = docking_service.requests[0]["ligand_mol"]
    assert _has_nonzero_z_coordinate(used_mol)


def test_dock_click_refuses_a_ligand_with_no_structure_at_all(qapp):
    panel, _, docking_service = _make_panel()
    ligand = MoleculeModel(display_name="Blank")  # no molblock, no conformers

    panel.set_project(_project_with_receptor_and_ligand(ligand))
    panel._receptor_combo.setCurrentIndex(0)
    panel._ligand_combo.setCurrentIndex(0)

    panel._on_dock_clicked()

    assert docking_service.requests == []
    assert "no structure" in panel._status_label.text().lower()


def test_the_panel_strips_the_ligand_that_defined_the_box():
    """A catalogue receptor records `ligand_code` in its metadata precisely
    so this can happen without the user knowing which residue defined the
    site. See `pose_analysis.is_stripped_residue` for the measurement."""
    from openchem.domain.macromolecule import MacromoleculeModel
    from openchem.ui.panels.docking_panel import _box_defining_ligand_codes

    catalogue = MacromoleculeModel(metadata={"ligand_code": "MK1"})
    assert _box_defining_ligand_codes(catalogue) == ["MK1"]


def test_a_user_imported_receptor_has_nothing_stripped():
    """No catalogue entry means nothing knows which residue defined the
    box, and guessing would delete part of somebody's receptor."""
    from openchem.domain.macromolecule import MacromoleculeModel
    from openchem.ui.panels.docking_panel import _box_defining_ligand_codes

    assert _box_defining_ligand_codes(MacromoleculeModel()) == []
    assert _box_defining_ligand_codes(MacromoleculeModel(metadata={"ligand_code": " "})) == []


def _dock_and_capture(panel, engine, docking_service) -> dict:
    """Drive a real dock click and return the prep options it sent."""
    ligand = MoleculeModel(display_name="Ethanol")
    engine.set_structure_from_smiles(ligand, "CCO")
    panel.set_project(_project_with_receptor_and_ligand(ligand))
    panel._receptor_combo.setCurrentIndex(0)
    panel._ligand_combo.setCurrentIndex(0)
    panel._on_dock_clicked()
    assert len(docking_service.requests) == 1
    return docking_service.requests[0]["receptor_prep_options"]


def test_the_assembly_choice_reaches_the_service(qapp):
    """The HOP NOBODY WAS TESTING.

    The Contents dialog's checkbox has its own tests and
    `DockingJob._build_requested_assembly` has its own; between them sits
    `DockingPanel._build_assembly`, and a search of the suite for
    `build_assembly` found it in the dialog's tests and the service's and
    nowhere in this file. Every hop being covered is not the same as the
    chain being covered, and this is the one that carries the user's
    answer to the thing that actually builds.
    """
    panel, engine, docking_service = _make_panel()
    panel._build_assembly = True

    assert _dock_and_capture(panel, engine, docking_service)["build_assembly"] is True


def test_the_default_is_not_to_build(qapp):
    """Off unless asked. Building silently would change what a saved
    docking box means without anybody having asked for it, and it is the
    default path that protects the 49-receptor catalogue."""
    panel, engine, docking_service = _make_panel()

    assert _dock_and_capture(panel, engine, docking_service)["build_assembly"] is False


def test_choosing_a_different_receptor_forgets_the_assembly_choice(qapp):
    """The tick belongs to the structure it was made about.

    Carrying it to the next receptor would silently build an assembly for
    a file the user never opened the dialog for -- and for a receptor that
    holds its whole biological unit already, the request cannot even be
    seen in the dialog, because the checkbox is hidden there.
    """
    panel, engine, docking_service = _make_panel()
    panel._build_assembly = True

    panel._on_receptor_changed(0)

    assert panel._build_assembly is False


def test_cancelling_the_contents_dialog_changes_nothing(qapp, monkeypatch):
    """The last hop: dialog -> panel.

    `_on_contents_clicked` is the only place `_build_assembly` is ever set
    to True, and it needs a modal dialog, which is exactly why it was the
    hop with no test. The dialog class is substituted here rather than
    shown, so both branches of `exec()` are reachable.

    **Patched on the DIALOG's module, not the panel's.** The panel imports
    it inside the method, so the name is resolved from
    `structure_contents_dialog` at call time and never becomes an
    attribute of `docking_panel` at all -- patching there raises
    `AttributeError` rather than silently doing nothing, which is the one
    mercy in it.

    Cancel must leave the previous answer alone -- a dialog somebody
    opened to LOOK at a receptor and then dismissed has not asked for
    anything to change.
    """
    from openchem.ui.dialogs import structure_contents_dialog as module

    panel, engine, docking_service = _make_panel()
    ligand = MoleculeModel(display_name="Ethanol")
    engine.set_structure_from_smiles(ligand, "CCO")
    panel.set_project(_project_with_receptor_and_ligand(ligand))
    panel._receptor_combo.setCurrentIndex(0)

    class _Cancelled:
        def __init__(self, *args, **kwargs) -> None: ...
        def exec(self) -> int:
            return 0  # QDialog.DialogCode.Rejected
        def keep_chains(self) -> list[str]:
            raise AssertionError("a cancelled dialog must not be read")
        def build_assembly(self) -> bool:
            raise AssertionError("a cancelled dialog must not be read")

    monkeypatch.setattr(module, "StructureContentsDialog", _Cancelled)
    panel._build_assembly = True

    panel._on_contents_clicked()

    assert panel._build_assembly is True


def test_accepting_the_contents_dialog_takes_its_answer(qapp, monkeypatch):
    """The same hop, accepted. Asserted against a dialog that says True
    while the panel starts False, so a handler that simply left the field
    alone would fail rather than coincide."""
    from openchem.ui.dialogs import structure_contents_dialog as module

    panel, engine, docking_service = _make_panel()
    ligand = MoleculeModel(display_name="Ethanol")
    engine.set_structure_from_smiles(ligand, "CCO")
    panel.set_project(_project_with_receptor_and_ligand(ligand))
    panel._receptor_combo.setCurrentIndex(0)

    class _Accepted:
        def __init__(self, *args, **kwargs) -> None: ...
        def exec(self) -> int:
            return 1  # QDialog.DialogCode.Accepted
        def keep_chains(self) -> list[str]:
            return []
        def build_assembly(self) -> bool:
            return True

    monkeypatch.setattr(module, "StructureContentsDialog", _Accepted)
    assert panel._build_assembly is False

    panel._on_contents_clicked()

    assert panel._build_assembly is True


# --- the search box ---------------------------------------------------------
#
# Reported by a user who docked four tryptamines against 5-HT2A (6WGT)
# from the receptor library and asked whether the numbers meant anything.
# They did not: the panel never placed the box, so all four ran against
# its constructor default of (0, 0, 0), which is 55.1 A from where LSD
# actually binds. `metadata["ligand_code"]` had carried the answer since
# the catalogue was written -- the panel used it only to STRIP the ligand
# out of the pocket, never to find the pocket.


def _hetatm(serial, name, code, chain, resnum, x, y, z, element):
    """Column-exact, per `tests/test_binding_site.py` -- a mis-aligned
    fixture parses as a different residue and the test silently changes
    meaning."""
    return (
        f"HETATM{serial:>5d} {name:<4} {code:>3} {chain}{resnum:>4d}    "
        f"{x:>8.3f}{y:>8.3f}{z:>8.3f}  1.00 20.00          {element:>2}\n"
    )


#: A ligand "LIG" whose bounding box is centred on (20, 0, 0), symmetric
#: on every axis so the expected centre is exact, plus protein around it.
_STRUCTURE_WITH_LIG = (
    "HEADER    TEST\n"
    + _hetatm(1, "C1", "LIG", "A", 500, 18.0, 0.0, 0.0, "C")
    + _hetatm(2, "C2", "LIG", "A", 500, 22.0, 0.0, 0.0, "C")
    + _hetatm(3, "N1", "LIG", "A", 500, 20.0, 2.0, 0.0, "N")
    + _hetatm(4, "O1", "LIG", "A", 500, 20.0, -2.0, 0.0, "O")
    + _hetatm(5, "CA", "ALA", "A", 1, 20.0, 0.0, 4.0, "C")
    + _hetatm(6, "CA", "GLY", "A", 2, 20.0, 0.0, -4.0, "C")
    + "END\n"
)

#: The site those coordinates imply: 4 x 4 x 0 A plus 4 A padding each
#: side, floored to `MINIMUM_SIZE`, centred on the ligand's midpoint.
_LIG_CENTRE = (20.0, 0.0, 0.0)


def _receptor(structure_text=_STRUCTURE_WITH_LIG, ligand_code="LIG"):
    metadata = {"ligand_code": ligand_code} if ligand_code is not None else {}
    return MacromoleculeModel(
        display_name="Receptor with a site",
        structure_text=structure_text,
        source_format="pdb",
        metadata=metadata,
    )


def _project_with(receptors, ligand):
    project = ProjectModel(name="Test project")
    project.macromolecules.extend(receptors)
    project.molecules.append(ligand)
    return project


def _dockable_ligand(engine):
    ligand = MoleculeModel(display_name="Ethanol")
    engine.set_structure_from_smiles(ligand, "CCO")
    return ligand


def test_choosing_a_catalogue_receptor_boxes_its_annotated_site(qapp):
    """The fix, at its simplest: the box lands on the ligand rather than
    on the origin. Asserts the SOURCE too, because a box that happens to
    be right while marked `manual` cannot be re-derived later."""
    panel, engine, _ = _make_panel()
    panel.set_project(_project_with([_receptor()], _dockable_ligand(engine)))

    panel._receptor_combo.setCurrentIndex(0)

    assert panel.displayed_box().center == pytest.approx(_LIG_CENTRE)
    assert panel._box_source == "derived"
    assert "LIG" in panel._box_status_label.text()


def test_the_derived_box_is_what_the_docking_request_receives(qapp):
    """Payload level, and comparing the whole `DockingBox`.

    Six independent numeric assertions cannot see a constructor
    argument-order or unit bug; comparing the object can. The UI showing
    the right numbers is not the claim -- what was SENT is.
    """
    panel, engine, docking_service = _make_panel()
    panel.set_project(_project_with([_receptor()], _dockable_ligand(engine)))
    panel._receptor_combo.setCurrentIndex(0)
    panel._ligand_combo.setCurrentIndex(0)

    panel._on_dock_clicked()

    assert docking_service.requests[0]["box"] == panel.displayed_box()
    assert docking_service.requests[0]["box"].center == pytest.approx(_LIG_CENTRE)


def test_a_hand_typed_box_is_docked_and_not_silently_re_derived(qapp):
    """`_box_source` is provenance; the spinboxes are the truth.

    Derive first, then type over it -- exactly the sequence a user follows
    to dock somewhere other than the annotated site. This is what stops a
    future "just derive immediately before docking" refactor from
    defeating the controls while every other test still passes.
    """
    panel, engine, docking_service = _make_panel()
    panel.set_project(_project_with([_receptor()], _dockable_ligand(engine)))
    panel._receptor_combo.setCurrentIndex(0)
    panel._ligand_combo.setCurrentIndex(0)
    assert panel._box_source == "derived", "setup: the box really was derived first"

    for spin, value in zip(
        (panel._center_x, panel._center_y, panel._center_z), (0.0, 0.0, 0.0), strict=True
    ):
        spin.setValue(value)

    panel._on_dock_clicked()

    assert panel._box_source == "manual"
    assert docking_service.requests[0]["box"].center == pytest.approx((0.0, 0.0, 0.0))


def test_a_manual_box_survives_everything_except_a_receptor_change(qapp):
    """The guard against a future `_refresh_*` deriving opportunistically.

    A user who positioned the box by hand must not have it overwritten
    because something unrelated happened in the project.
    """
    panel, engine, _ = _make_panel()
    receptor = _receptor()
    ligand = _dockable_ligand(engine)
    project = _project_with([receptor], ligand)
    panel.set_project(project)
    panel._receptor_combo.setCurrentIndex(0)
    panel._center_x.setValue(3.0)
    panel._center_y.setValue(4.0)
    assert panel._box_source == "manual"

    panel.set_project(project)
    panel.sync_with_project(project)
    panel._on_molecule_selected(MoleculeSelected(molecule_uuid=ligand.uuid))

    assert panel.displayed_box().center[:2] == pytest.approx((3.0, 4.0))
    assert panel._box_source == "manual"


def test_switching_receptors_never_leaves_the_previous_ones_box(qapp):
    """The bug the fix could have introduced, and the reason the reset is
    unconditional.

    Receptor A derives a real site. Receptor B has no annotation at all.
    Leaving A's coordinates on screen would present one structure's
    binding site as though it belonged to another -- the same
    silently-plausible-wrong-box failure, moved one step along. The panel
    already resets `_keep_chains` and `_build_assembly` here for exactly
    this reason.
    """
    panel, engine, _ = _make_panel()
    with_site = _receptor()
    without_site = _receptor(structure_text="HEADER    BARE\nEND\n", ligand_code=None)
    panel.set_project(_project_with([with_site, without_site], _dockable_ligand(engine)))

    panel._receptor_combo.setCurrentIndex(0)
    assert panel.displayed_box().center == pytest.approx(_LIG_CENTRE), "setup"
    panel._receptor_combo.setCurrentIndex(1)

    assert panel.displayed_box().center != pytest.approx(_LIG_CENTRE)
    assert panel._box_source == "none"


def test_a_receptor_whose_declared_ligand_cannot_be_found_says_so(qapp):
    """Metadata claims a site that is not in the file.

    Different from having no annotation, and must read differently: the
    deposit revision may have moved, or the ligand may be part of the
    polymer. Silence would say "nothing to box here" when the truth is
    that something is wrong and the user can act on it.
    """
    panel, engine, _ = _make_panel()
    # The code is real in the catalogue sense and absent from the file --
    # assert the setup, or a fixture that happened to contain ZZZ would
    # make this pass for the wrong reason.
    receptor = _receptor(ligand_code="ZZZ")
    assert "ZZZ" not in receptor.structure_text
    panel.set_project(_project_with([receptor], _dockable_ligand(engine)))

    panel._receptor_combo.setCurrentIndex(0)

    assert panel._box_source == "none"
    assert "ZZZ" in panel._box_status_label.text()
    assert panel._derive_button.isEnabled(), (
        "a failed automatic derivation must not make the manual route look "
        "permanently unavailable -- LIG is still in this file"
    )


def test_deriving_twice_gives_the_same_box(qapp):
    """Idempotence. Cheap to assert, and it protects against a derivation
    that accumulates -- a transform applied to already-transformed
    coordinates, or state carried between calls."""
    panel, engine, _ = _make_panel()
    panel.set_project(_project_with([_receptor()], _dockable_ligand(engine)))
    panel._receptor_combo.setCurrentIndex(0)
    first, first_status = panel.displayed_box(), panel._box_status_label.text()

    panel._on_derive_clicked()

    assert panel.displayed_box() == first
    assert panel._box_status_label.text() == first_status
    assert panel._box_source == "derived"


def test_writing_the_box_is_never_announced_as_the_users_own_edit(qapp):
    """`setValue` emits `valueChanged` exactly as a keystroke does.

    The final `_box_source` comes out right either way -- `_write_box`
    assigns it after the loop -- so a test on the end state cannot see
    this, and the mutation that removes the guard survives every other
    test in this file. What it changes is what the USER is told: six
    spinboxes written means six "Search box: manually positioned"
    announcements for a box they never touched, and the panel briefly
    contradicting itself about where its own numbers came from.
    """
    panel, engine, _ = _make_panel()
    panel.set_project(_project_with([_receptor()], _dockable_ligand(engine)))
    panel._receptor_combo.setCurrentIndex(0)
    # Move the box FIRST, so re-deriving genuinely changes the values.
    # Qt emits no `valueChanged` for a no-op `setValue`, so deriving twice
    # over identical numbers fires nothing and would make this vacuous --
    # the same degenerate-fixture trap that let a caption-overflow guard
    # pass with its fix reverted.
    panel._center_x.setValue(0.0)
    assert panel.displayed_box().center[0] != pytest.approx(_LIG_CENTRE[0]), "setup"

    announcements = []
    original = panel._box_status_label.setText
    panel._box_status_label.setText = lambda text: (  # type: ignore[method-assign]
        announcements.append(text), original(text)
    )[1]
    panel._on_derive_clicked()

    assert panel.displayed_box().center == pytest.approx(_LIG_CENTRE), (
        "setup: the derive really did move the spinboxes back"
    )

    assert not [text for text in announcements if "manually" in text.lower()], (
        f"a programmatic write was reported as a user edit: {announcements}"
    )


def test_a_far_box_warns_without_blocking_the_run(qapp):
    """Warn, never block.

    Blind docking and allosteric sites are real uses and a distant box is
    the intended experiment for both, so the warning must not become a
    refusal. Asserts BOTH halves -- a test that only checked the message
    would pass against a panel that had stopped docking entirely.
    """
    panel, engine, docking_service = _make_panel()
    panel.set_project(_project_with([_receptor()], _dockable_ligand(engine)))
    panel._receptor_combo.setCurrentIndex(0)
    panel._ligand_combo.setCurrentIndex(0)
    panel._center_x.setValue(0.0)  # 20 A off site

    panel._on_dock_clicked()

    assert len(docking_service.requests) == 1, "the run must still go out"
    assert "LIG" in panel._box_status_label.text()
    assert "20.0" in panel._box_status_label.text()


def test_every_pose_column_explains_itself(qapp):
    """The question that prompted all of this was "what are RMSD l.b. and
    u.b.?", and nothing in the app answered it.

    Walks the header ITEMS the table actually built rather than the
    tooltip dict -- these are `QTableWidgetItem`s, not widgets, so a
    tooltip audit that walks `QWidget`s alone cannot see them and would
    report this table fully documented.
    """
    panel, _, _ = _make_panel()

    for column in range(panel._table.columnCount()):
        item = panel._table.horizontalHeaderItem(column)
        assert item is not None
        tip = item.toolTip()
        assert tip.strip(), f"column {item.text()!r} has no tooltip"
        assert tip.strip().lower() not in {"options", "value", "details"}

    rmsd = panel._table.horizontalHeaderItem(2).toolTip()
    assert "pose 1" in rmsd.lower(), "must say what the RMSD is measured against"
    assert "not" in rmsd.lower() and "experimental" in rmsd.lower(), (
        "the misreading this exists to prevent: RMSD here is not accuracy"
    )


def test_the_scoring_error_is_never_quoted_without_its_source(qapp):
    """A number in a tooltip carries the authority of the application.

    2.85 kcal/mol was written into this tooltip FROM MEMORY, removed
    because nothing in the repository supported it, and restored only
    after the paper was read -- `[source:trott_olson2010]`, "Vina achieves
    a comparatively low standard error of 2.85 kcal/mol". The remembered
    figure was right, which is luck rather than method: it was
    unverifiable when written.

    So the guard is on the PAIRING, not on the number. Quoting the figure
    is fine; quoting it bare is not, because an unattributed error bar
    reads as this application's own measurement of the user's run rather
    than as the authors' result for their 190-complex set. Tidying the
    attribution away while keeping the number fails here.
    """
    panel, _, _ = _make_panel()

    affinity = panel._table.horizontalHeaderItem(1).toolTip()

    if "2.85" in affinity:
        assert "Trott" in affinity and "Olson" in affinity, (
            "the scoring error is quoted with no attribution"
        )
        assert "their own" in affinity or "test set" in affinity, (
            "must say whose set the figure is for, or it reads as a "
            "universal error bar for any run"
        )
def test_the_derive_buttons_live_tooltip_still_carries_its_contract(qapp):
    """The rendered tooltip is state-dependent; the MEANING must survive it.

    "Derive from ligand" is the one control here whose useful text depends
    on the receptor -- naming the ligand codes actually present is what
    answers "will this button do anything for me". So the contract is
    attached once and the rendering is recomputed, which is exactly what
    "a tooltip is one RENDERING of a declared meaning" is for.

    The failure this guards is silent: substituting the live text for the
    contract's leaves the contract attached as a Qt property, so the
    coverage guard still reports the control documented while the user is
    shown only a list of three-letter codes with nothing saying what
    pressing it does.
    """
    from openchem.ui.widgets.help_tooltip import help_tooltip_for

    panel, _engine, _service = _make_panel()
    contract = help_tooltip_for(panel._derive_button)
    assert contract is not None, "the derive button lost its contract entirely"

    for codes in ((), ("7LD", "NAG")):
        panel._describe_derivable_ligands(codes)
        rendered = panel._derive_button.toolTip()
        assert contract.text in rendered, (
            "the live tooltip replaced the contract instead of composing with "
            f"it: {rendered[:80]!r}"
        )
    # ... and the live half really is there, or the composition is vacuous.
    panel._describe_derivable_ligands(("7LD", "NAG"))
    assert "7LD" in panel._derive_button.toolTip()


# --- the replicate control and the spread label -----------------------------


def _replicate_set(*affinities, protocol_seed=4712, representative=0, seeds=None):
    from openchem.domain.docking import DockingReplicate, DockingReplicateSet

    seeds = seeds if seeds is not None else [1000 + i for i in range(len(affinities))]
    return DockingReplicateSet(
        protocol_seed=protocol_seed,
        representative_index=representative,
        replicates=[
            DockingReplicate(seed=seed, best_affinity_kcal_mol=value)
            for seed, value in zip(seeds, affinities, strict=True)
        ],
    )


def _result_with(replicates, affinities=(-8.79,)):
    from openchem.domain.common import Provenance
    from openchem.domain.docking import DockingBox, DockingPoseModel, DockingResultModel

    return DockingResultModel(
        ligand_molecule_uuid="lig-1",
        receptor_macromolecule_uuid="rec-1",
        box=DockingBox(center=(0.0, 0.0, 0.0), size=(10.0, 10.0, 10.0)),
        poses=[
            DockingPoseModel(
                pose_molblock="pose",
                binding_affinity_kcal_mol=value,
                rmsd_lb=0.0,
                rmsd_ub=0.0,
            )
            for value in affinities
        ],
        provenance=Provenance(created_by="core", method="vina", parameters={}),
        engine="vina",
        engine_version="1.2.7",
        scoring_function="vina",
        exhaustiveness=25,
        seed=1000,
        replicates=replicates,
    )


# --- the control ------------------------------------------------------------


def test_the_replicate_count_defaults_to_one(qapp):
    """The default is what almost every user will run, and it is the reason
    every pre-existing docking test passes unedited.

    Anything above 1 would multiply every existing user's docking wall clock
    with no announcement, and multiply every virtual-screening budget.
    """
    from openchem.services.docking_service import DEFAULT_REPLICATES

    panel, _engine, _service = _make_panel()

    assert panel._replicates_spin.value() == 1
    assert panel._replicates_spin.value() == DEFAULT_REPLICATES
    assert panel._replicates_spin.minimum() == 1
    assert panel._replicates_spin.maximum() == 25


def test_the_panel_sends_the_replicate_count_it_displays(qapp):
    """One accessor, so the panel cannot display one count and dock another."""
    panel, engine, service = _make_panel()
    panel.set_project(_project_with([_receptor()], _dockable_ligand(engine)))
    panel._receptor_combo.setCurrentIndex(0)
    panel._ligand_combo.setCurrentIndex(0)
    panel._replicates_spin.setValue(5)

    panel._on_dock_clicked()

    assert panel.displayed_replicates() == 5
    assert service.requests[-1]["replicates"] == 5


def test_the_replicate_count_is_not_a_search_option(qapp):
    """A SIBLING OF `num_poses`, and the mutation is putting it in the dict.

    `search_options` goes straight to the provider, which never sees more than
    one run at a time -- a replicate count there would name something it cannot
    act on. It is also asserted as an exact dict by
    `tests/test_ligand_extent_warning.py`, which this placement leaves valid
    unedited; that guard would go red the moment the key moved.
    """
    panel, engine, service = _make_panel()
    panel.set_project(_project_with([_receptor()], _dockable_ligand(engine)))
    panel._receptor_combo.setCurrentIndex(0)
    panel._ligand_combo.setCurrentIndex(0)
    panel._replicates_spin.setValue(3)

    panel._on_dock_clicked()

    assert "replicates" not in service.requests[-1]["search_options"]


def test_replicates_is_offered_above_seed_because_it_changes_what_seed_means(qapp):
    """Order, asserted on the FORM rather than on the construction order.

    A pinned seed is the root of a derived set of per-run seeds rather than the
    number Vina receives, so a reader who meets Seed first forms the older
    meaning and has no reason to revisit it. Only the laid-out row order says
    which they meet first.
    """
    from PySide6.QtWidgets import QFormLayout

    panel, _engine, _service = _make_panel()
    form = panel._replicates_spin.parent().layout()
    assert isinstance(form, QFormLayout), "setup: the Search group is a QFormLayout"

    rows = {}
    for row in range(form.rowCount()):
        field = form.itemAt(row, QFormLayout.ItemRole.FieldRole)
        if field is not None:
            rows[field.widget()] = row

    assert rows[panel._replicates_spin] < rows[panel._seed_spin]


# --- the three states -------------------------------------------------------


def test_a_result_that_predates_replicates_says_so(qapp):
    """State one of three. `None` is not a synonym for one run.

    Rendering it as "1 run" would make every pre-existing project file assert a
    replicate structure nobody chose -- the reason `from_dict` synthesises
    nothing.
    """
    from openchem.ui.panels.docking_panel import describe_replicate_spread

    text = describe_replicate_spread(None)

    assert "not recorded" in text
    assert "1 run" not in text


def test_a_single_run_says_no_spread_was_measured(qapp):
    """State two, and the whole behavioural fix at the default count.

    The panel stops printing a bare -8.79 as though it were a measurement. It
    reports one run and says outright that nothing about the spread is known.
    """
    from openchem.ui.panels.docking_panel import describe_replicate_spread

    text = describe_replicate_spread(_replicate_set(-8.79, seeds=[358255849]))

    assert "1 run" in text
    assert "no spread measured" in text
    assert "358255849" in text
    assert "4712" in text, "the pinned root, which is NOT the seed the run used"


def test_a_replicate_set_reports_its_range_median_and_count(qapp):
    """State three. All of range, median and COUNT, because the range grows
    with n in expectation -- so a width with no count beside it invites two
    widths measured at different counts being compared.
    """
    from openchem.ui.panels.docking_panel import describe_replicate_spread

    text = describe_replicate_spread(
        _replicate_set(-8.85, -8.79, -8.73, representative=1)
    )

    assert "3 runs" in text
    assert "-8.85" in text and "-8.73" in text
    assert "median -8.79" in text


def test_a_zero_width_range_is_a_measurement_and_not_an_absence(qapp):
    """Five runs that genuinely agree measured a width of zero. One run
    measured nothing at all. They must not read the same.

    This is `n/a is not 0` in reverse, and it is why `AffinityRange.width` is
    None at n = 1 rather than 0.0.
    """
    from openchem.ui.panels.docking_panel import describe_replicate_spread

    agreeing = describe_replicate_spread(_replicate_set(*([-8.79] * 5)))
    single = describe_replicate_spread(_replicate_set(-8.79))

    assert "5 runs" in agreeing
    assert "no spread measured" not in agreeing
    assert "no spread measured" in single


# --- what the text may and may not say --------------------------------------


def test_the_label_names_the_median_run_and_never_the_best(qapp):
    """A UI-string guard, DISTINCT from the numerical one in the service.

    The label and the selection rule can drift apart silently -- the plan for
    this feature did exactly that, specifying a median representative in one
    paragraph and a "best-scoring" label in another. A reader told the poses
    are the best of five would read the headline affinity as a best-of-N, which
    is the statistic this whole feature exists to stop reporting.
    """
    from openchem.ui.panels.docking_panel import describe_replicate_spread

    text = describe_replicate_spread(_replicate_set(-8.85, -8.79, -8.73, representative=1))

    assert "median run" in text
    assert "best" not in text.lower()


def test_the_label_never_renders_an_error_bar_or_calls_itself_an_interval(qapp):
    """The one-directional reading, guarded as a clean word ban.

    "+/-" is the unambiguous error-bar glyph and "confidence interval" /
    "prediction interval" are the two readings this feature exists to prevent.

    THE TEXT AVOIDS THOSE WORDS ENTIRELY RATHER THAN DENYING THEM, which is a
    deliberate departure from the plan's own draft wording ("It is not a
    confidence interval, a prediction interval, or a binding-affinity
    uncertainty"). A denial teaches the reader the exact frame it is trying to
    prevent, and it makes any guard on the rendered string unable to tell a
    denial from a claim -- so the ban below could not have been written at all.
    """
    from openchem.ui.panels.docking_panel import describe_replicate_spread

    for replicates in (None, _replicate_set(-8.79), _replicate_set(-8.85, -8.79, -8.73)):
        text = describe_replicate_spread(replicates).lower()
        assert "±" not in text
        assert "+/-" not in text
        assert "interval" not in text
        assert "confidence" not in text


def test_the_label_carries_its_interpretation_limit_on_screen(qapp):
    """ON SCREEN, not only in the tooltip.

    This project has twice recorded a meaning that lived only in a hover and
    was therefore absent from every screenshot -- the isotope table's
    spin/parity marks, and `Fact.limitations`, which reaches a row tooltip and
    nothing else. A range printed beside two affinities reads as an error bar
    unless something on the same surface says it is not one.
    """
    from openchem.ui.panels.docking_panel import _SPREAD_LIMIT_NOTE, describe_replicate_spread

    text = describe_replicate_spread(_replicate_set(-8.85, -8.79, -8.73))

    assert _SPREAD_LIMIT_NOTE in text


def test_no_control_contract_still_claims_the_seed_cannot_be_pinned(qapp):
    """Two contracts on one screen used to contradict each other about one
    fact: `run` said "this application does not pin its seed" while
    `random_seed`, a row above it, said "Pin one to compare two settings".

    A CHANGE DETECTOR for a recorded contradiction, and it generalises a
    little: any future contract making the same claim fails it too.
    """
    from openchem.ui.panels.docking_panel import _CONTROL_HELP

    offenders = [
        name for name, contract in _CONTROL_HELP.items()
        if "does not pin" in contract.text
    ]

    assert offenders == []


# --- rendering, and the two ways it used to be lost -------------------------


def test_the_spread_label_is_hidden_until_there_is_a_result(qapp):
    """Hidden rather than blank: an empty word-wrapped QLabel still claims a
    line of font height, and this panel is height-constrained enough that its
    3D sibling was once 63 px tall.

    `isHidden`, not `isVisible` -- every child of an unshown widget reports
    `isVisible() == False`, so that assertion would pass against a label that
    is permanently shown.
    """
    panel, _engine, _service = _make_panel()

    assert panel._spread_label.isHidden()
    assert panel._spread_label.text() == ""


def test_showing_a_result_shows_the_spread(qapp):
    panel, _engine, _service = _make_panel()

    panel._show_result(_result_with(_replicate_set(-8.85, -8.79, -8.73)))

    assert not panel._spread_label.isHidden()
    assert "3 runs" in panel._spread_label.text()


def test_a_job_state_arriving_after_the_result_does_not_wipe_the_spread(qapp):
    """The defect `_box_status_label` already exists to prevent, one label on.

    `_status_label` carries job state and is rewritten on every
    `DockingJobStateChanged` -- and COMPLETED arrives after
    `DockingResultReady`, so a spread written there would be wiped microseconds
    after appearing. Asserted through the real event, not by calling the
    handler.
    """
    from openchem.domain.common import CacheState
    from openchem.events.events import DockingJobStateChanged

    panel, _engine, _service = _make_panel()
    panel._pending_ligand_uuid = "lig-1"
    panel._pending_receptor_uuid = "rec-1"
    panel._show_result(_result_with(_replicate_set(-8.85, -8.79, -8.73)))
    assert "3 runs" in panel._spread_label.text(), "setup: the spread was shown"

    panel._on_job_state_changed(
        DockingJobStateChanged(
            ligand_molecule_uuid="lig-1",
            receptor_macromolecule_uuid="rec-1",
            state=CacheState.COMPLETED,
        )
    )

    assert "3 runs" in panel._spread_label.text()
    assert "completed" in panel._status_label.text()


def test_undoing_a_dock_takes_the_spread_label_with_the_poses(qapp):
    """Symmetric with the table, and for the same reason.

    Undoing a dock removed the result and left the poses on screen -- binding
    affinities, to two decimal places, for a run the project no longer
    contains. A spread label left behind is the same defect with a count and a
    seed attached.
    """
    panel, engine, _service = _make_panel()
    receptor = _receptor()
    ligand = _dockable_ligand(engine)
    project = _project_with([receptor], ligand)
    panel.set_project(project)
    panel._receptor_combo.setCurrentIndex(0)
    panel._ligand_combo.setCurrentIndex(0)

    result = _result_with(_replicate_set(-8.85, -8.79, -8.73))
    result.ligand_molecule_uuid = ligand.uuid
    result.receptor_macromolecule_uuid = receptor.uuid
    project.docking_results.append(result)
    panel.sync_with_project(project)
    assert not panel._spread_label.isHidden(), "setup: the spread really was shown"

    project.docking_results.clear()
    panel.sync_with_project(project)

    assert panel._spread_label.isHidden()
    assert panel._spread_label.text() == ""
    assert panel._table.rowCount() == 0



# --- the pose table's own headers -------------------------------------------


def _header_shortfalls(panel):
    """Every pose column whose section is narrower than its own header text.

    BOTH SIDES COME FROM THE HEADER'S OWN `QFontMetrics`, so this is not a
    claim about a font: it asks whether the section fits the string Qt is about
    to paint into it, in whatever font this platform supplies. `offscreen`'s
    default is more than twice as wide as the one a user sees, and a pinned
    pixel width here would be a statement about the test platform.

    The margin is asked of the STYLE rather than typed, for the same reason.
    """
    from PySide6.QtGui import QFontMetrics
    from PySide6.QtWidgets import QStyle

    header = panel._table.horizontalHeader()
    metrics = QFontMetrics(header.font())
    margin = 2 * header.style().pixelMetric(QStyle.PixelMetric.PM_HeaderMargin)
    from openchem.ui.panels.docking_panel import _POSE_COLUMNS

    # A HIDDEN column is skipped, and the exclusion keys on Qt's own live
    # `isColumnHidden` rather than on a column NAME. A hidden section has
    # width 0 and paints nothing, so it cannot clip -- but naming the
    # rescore column here would exempt it forever, including once it is
    # shown. `test_a_shown_rescore_header_is_still_checked` asserts this
    # narrowing did not create a blind spot.
    return [
        (name, header.sectionSize(column), metrics.horizontalAdvance(name) + margin)
        for column, name in enumerate(_POSE_COLUMNS)
        if not panel._table.isColumnHidden(column)
        and header.sectionSize(column) < metrics.horizontalAdvance(name) + margin
    ]


def test_no_pose_table_header_is_clipped(qapp):
    """Every column header fits the section it is painted into.

    Stretch on all four divided the table's 440 px into four equal 110 px
    sections while "Binding Affinity (kcal/mol)" needs 141, so it rendered
    clipped at BOTH ends as "ling Affinity (kcal/r" -- the identical defect
    `virtual_screening_dialog.py:109-119` records fixing in its own table.

    Found by grabbing the panel with real fonts and magnifying 3x. Nothing in
    the suite could see it: no test asserted a section width, and there is no
    ellipsis to detect because a header overflows rather than eliding.
    """
    panel, _engine, _service = _make_panel()
    panel.show()
    panel.resize(panel.minimumSizeHint().width(), 900)
    qapp.processEvents()

    assert _header_shortfalls(panel) == []


def test_three_pose_columns_can_never_clip_whatever_the_font(qapp):
    """The narrow half, and it is the load-bearing one.

    "Nothing clips at this width" is satisfied by four hand-tuned pixel widths
    that happen to fit THIS font, and would clip on a machine with a wider one.
    `ResizeToContents` sizes a section to the wider of its header and its
    cells, so those three cannot clip at any font or DPI -- which is a stronger
    statement than any measurement, and the reason only the affinity column
    takes the remainder.
    """
    from PySide6.QtWidgets import QHeaderView

    from openchem.ui.panels.docking_panel import _AFFINITY_COLUMN, _POSE_COLUMNS

    panel, _engine, _service = _make_panel()
    header = panel._table.horizontalHeader()

    modes = {
        name: header.sectionResizeMode(column)
        for column, name in enumerate(_POSE_COLUMNS)
    }
    assert modes.pop(_AFFINITY_COLUMN) == QHeaderView.ResizeMode.Stretch
    assert set(modes.values()) == {QHeaderView.ResizeMode.ResizeToContents}


def test_the_stretched_column_is_chosen_by_name_and_not_by_index(qapp):
    """Reordering `_POSE_COLUMNS` must not silently stretch a different one.

    An index would still be a valid column, so nothing would look wrong until
    somebody magnified the header again.
    """
    from openchem.ui.panels.docking_panel import _AFFINITY_COLUMN, _POSE_COLUMNS

    assert _AFFINITY_COLUMN in _POSE_COLUMNS


# --- the panel fits the dock it opens in ------------------------------------


def _widest_value_fits(spin) -> tuple[int, int]:
    """(line-edit width, width the widest permitted value needs).

    Asked of the LINE EDIT, which is where the text is painted -- not of the
    spin box, whose width includes buttons and frame. A first check allowed
    30 px for those and concluded a 90 px spin was fine; the real chrome is
    52 px on this platform, so it would have clipped "-1000.00".
    """
    from PySide6.QtGui import QFontMetrics
    from PySide6.QtWidgets import QLineEdit

    edit = spin.findChild(QLineEdit)
    metrics = QFontMetrics(edit.font())
    return edit.width(), metrics.horizontalAdvance(spin.text())


def test_a_coordinate_spin_always_fits_the_widest_value_its_range_permits(qapp):
    """The narrow half, and the one that rules out a pixel constant.

    A fixed cap measures beautifully on one machine and clips the NUMBER under
    a larger UI font -- strictly worse than clipping a label, because a
    half-shown coordinate is a wrong coordinate. Both sides of this assertion
    come from the widget's own font, so it holds wherever it runs: under
    `offscreen`, whose font is more than twice as wide, the derived width grows
    with it.
    """
    panel, _engine, _service = _make_panel()
    panel.show()

    for spin in (panel._center_x, panel._center_y, panel._center_z):
        spin.setValue(spin.minimum())
    for spin in (panel._size_x, panel._size_y, panel._size_z):
        spin.setValue(spin.maximum())
    panel.resize(panel.minimumSizeHint().width(), 900)
    qapp.processEvents()

    too_narrow = [
        (spin.text(), *_widest_value_fits(spin))
        for spin in (
            panel._center_x, panel._center_y, panel._center_z,
            panel._size_x, panel._size_y, panel._size_z,
        )
        if _widest_value_fits(spin)[0] < _widest_value_fits(spin)[1]
    ]

    assert not too_narrow, f"a coordinate would be shown clipped: {too_narrow}"


def test_the_spin_width_is_derived_from_the_range_and_not_a_constant(qapp):
    """A constant answers the same for every range; this must not.

    The box centre spans -1000..1000 and the box size 1..200, so "-1000.00" is
    wider than "200.00" and the two controls are entitled to different widths.
    A flat cap -- which is what this shipped as for one commit -- returns one
    number for both and is caught here.
    """
    from openchem.ui.panels.docking_panel import coordinate_spin_width

    panel, _engine, _service = _make_panel()

    assert coordinate_spin_width(panel._center_x) > coordinate_spin_width(panel._size_x)


def test_narrowing_the_coordinate_spins_really_shrinks_the_panel(qapp):
    """The behavioural half, phrased so it does not depend on the font.

    "The panel's minimum is at most 420" is a claim about the platform's font:
    measured at REAL fonts it is 406 against a dock that opens at 420, and
    under `offscreen` -- whose font is far wider -- no arrangement of this
    panel fits 420 and none should be asked to.

    ASSERTED ON THE BOX GROUP, NOT THE PANEL, and the first version of this
    test asserted the panel and failed under `offscreen`: there the panel's
    minimum is 706 with the cap and without it, because a different group is
    binding at that font. The group the cap acts on shrinks on BOTH -- 405 to
    384 at real fonts, 522 to 510 under `offscreen` -- which is the honest
    scope of the claim.
    """
    from PySide6.QtWidgets import QGroupBox

    panel, _engine, _service = _make_panel()
    panel.show()
    panel.resize(420, 900)
    qapp.processEvents()
    group = next(
        g for g in panel.findChildren(QGroupBox) if g.title().startswith("Search box")
    )
    fitted = group.minimumSizeHint().width()

    for spin in (
        panel._center_x, panel._center_y, panel._center_z,
        panel._size_x, panel._size_y, panel._size_z,
    ):
        spin.setMaximumWidth(16777215)
    panel.resize(420, 900)
    qapp.processEvents()

    assert fitted < group.minimumSizeHint().width()


def test_the_short_form_labels_are_the_other_half_of_the_fit(qapp):
    """Narrowing the spins alone does not reach the dock's width.

    Measured at real fonts: the spins take the panel from 466 to 427 and the
    labels take it the rest of the way to 406, against a dock that opens at
    420. So "Center:" rather than "Center (x, y, z):" is load-bearing, not
    tidying -- and a mutation restoring the long form survived every other
    guard in this file on BOTH font platforms until this one existed.

    Asserted on the box GROUP for the reason the spin guard is: the panel's own
    minimum is bound by a different group under `offscreen`.
    """
    from PySide6.QtWidgets import QFormLayout, QGroupBox, QLabel

    panel, _engine, _service = _make_panel()
    panel.show()
    panel.resize(420, 900)
    qapp.processEvents()
    group = next(
        g for g in panel.findChildren(QGroupBox) if g.title().startswith("Search box")
    )
    fitted = group.minimumSizeHint().width()

    form = group.layout()
    assert isinstance(form, QFormLayout), "setup: the box group is a QFormLayout"
    for row, text in ((0, "Center (x, y, z):"), (1, "Size (x, y, z):")):
        item = form.itemAt(row, QFormLayout.ItemRole.LabelRole)
        assert item is not None and isinstance(item.widget(), QLabel), "setup: a real label"
        item.widget().setText(text)
    panel.resize(420, 900)
    qapp.processEvents()

    assert fitted < group.minimumSizeHint().width()


def test_the_fix_costs_the_panel_no_height(qapp):
    """`flow_row` was the other candidate and this is why it was refused.

    Wrapping the coordinate rows would split an x, y, z triple across lines and
    add ~42 px to a panel whose 3D sibling was once 63 px tall. Narrowing the
    spins reaches the same width with the rows intact, so the height must not
    move -- measured 610 px before and after at real fonts.
    """
    panel, _engine, _service = _make_panel()
    panel.show()
    panel.resize(420, 900)
    qapp.processEvents()
    fitted = panel.minimumSizeHint().height()

    for spin in (
        panel._center_x, panel._center_y, panel._center_z,
        panel._size_x, panel._size_y, panel._size_z,
    ):
        spin.setMaximumWidth(16777215)
    panel.resize(420, 900)
    qapp.processEvents()

    assert fitted == panel.minimumSizeHint().height()


# --- the rescore column -----------------------------------------------------


def _rescored(result, *, function="vinardo", values=(-5.47,), failed=False):
    """Attach a PoseScore to each pose of `result`, as the provider does."""
    from openchem.domain.docking import AS_DOCKED, POSE_SCORE_KEY, PoseScore

    for pose, value in zip(result.poses, values, strict=False):
        score = PoseScore(
            function=function,
            protocol=AS_DOCKED,
            value=None if failed else value,
            engine="vina-executable",
            engine_version="1.2.7",
            error="The ligand is outside the grid box." if failed else None,
            error_summary="Rescore failed" if failed else None,
        )
        pose.metadata[POSE_SCORE_KEY] = score.to_dict()
    return result


def _rescore_column(panel):
    from openchem.ui.panels.docking_panel import _POSE_COLUMNS, _RESCORE_COLUMN

    return _POSE_COLUMNS.index(_RESCORE_COLUMN)


def test_the_rescore_column_is_hidden_until_one_is_requested(qapp):
    """NOT REQUESTED is a real state and its rendering is "no column".

    An empty fifth column is not a neutral default either: `ResizeToContents`
    gives it its header's width, which is what took the affinity header past
    clipping when this was first added.
    """
    panel, _engine, _service = _make_panel()
    assert panel._table.isColumnHidden(_rescore_column(panel))

    panel._show_result(_result_with(_replicate_set(-8.79)))
    assert panel._table.isColumnHidden(_rescore_column(panel))


def test_a_requested_rescore_shows_a_column_naming_its_function(qapp):
    panel, _engine, _service = _make_panel()
    panel._show_result(_rescored(_result_with(_replicate_set(-8.79))))

    column = _rescore_column(panel)
    assert not panel._table.isColumnHidden(column)
    assert panel._table.item(0, column).text() == "-5.47"


def test_the_header_says_the_scale_is_separate_rather_than_only_the_tooltip(qapp):
    """**ON SCREEN, NOT IN HOVER.** A reader who sees -8.79 beside -5.47 will
    conclude the second says it binds worse; they are 3.3 kcal/mol apart for
    the same atoms in the same place because the functions weight their terms
    differently. This project has twice recorded a meaning that lived only in
    a tooltip being absent from every screenshot.
    """
    panel, _engine, _service = _make_panel()
    panel._show_result(_rescored(_result_with(_replicate_set(-8.79))))

    header = panel._table.horizontalHeaderItem(_rescore_column(panel)).text()
    # THE FUNCTION NAME ALONE, and the brevity is measured rather than a
    # preference. With " (kcal/mol)" on it the header was 110 px at the real
    # font and the five columns totalled 426 against a 367 px viewport, so
    # the table overflowed by 59 px and grew a horizontal scrollbar -- which
    # the magnified shot showed as a header reading "Vinard". At 51 px the
    # total is 367 against 379 and nothing scrolls. The units are in the note
    # below the table and in the column's own tooltip.
    assert header == "Vinardo"
    # The SENTENCE is under the table, where there is room for one.
    # `isHidden`, NOT `isVisible`: a child of a window nobody showed reports
    # isVisible() False whatever its own flag says, which this project has
    # recorded twice.
    assert not panel._rescore_label.isHidden()
    note = panel._rescore_label.text().lower()
    assert "separate scale" in note
    assert "must not be compared" in note


def test_a_failed_rescore_still_shows_its_column_and_says_why(qapp):
    """"Not requested" and "requested and broken" must stay distinguishable.
    A missing column collapses them, which is this codebase's *n/a is not 0*
    rule."""
    panel, _engine, _service = _make_panel()
    panel._show_result(_rescored(_result_with(_replicate_set(-8.79)), failed=True))

    column = _rescore_column(panel)
    assert not panel._table.isColumnHidden(column)
    item = panel._table.item(0, column)
    assert item.text() == "Rescore failed"
    assert "outside the grid box" in item.toolTip()


def test_the_rescore_never_reorders_the_poses(qapp):
    """The table is ordered by the DOCKING affinity, and a rescore that
    disagreed with it must not move anything. Here the rescore's order is
    deliberately the reverse."""
    panel, _engine, _service = _make_panel()
    result = _result_with(_replicate_set(-8.79), affinities=(-8.79, -8.50, -8.10))
    _rescored(result, values=(-4.10, -5.00, -6.30))
    panel._show_result(result)

    affinities = [panel._table.item(row, 1).text() for row in range(3)]
    assert affinities == ["-8.79", "-8.50", "-8.10"]
    rescores = [panel._table.item(row, _rescore_column(panel)).text() for row in range(3)]
    assert rescores == ["-4.10", "-5.00", "-6.30"]


def test_off_sends_no_rescore_key_at_all(qapp):
    """The dict a run with no rescore sends is byte-identical to the one it
    sent before this control existed, so an opt-in feature does not
    re-baseline every other user's request."""
    panel, _engine, _service = _make_panel()
    assert "rescore_with" not in panel.displayed_search_options()


def test_choosing_a_function_puts_it_in_the_search_options(qapp):
    panel, _engine, _service = _make_panel()
    panel._rescore_combo.setCurrentIndex(panel._rescore_combo.findData("vinardo"))
    assert panel.displayed_search_options()["rescore_with"] == "vinardo"


def test_a_shown_rescore_header_is_still_checked(qapp):
    """The narrow half of the clipping guard's hidden-column exclusion.

    That exclusion keys on Qt's live `isColumnHidden`, not on a column name --
    so once the column IS shown it is held to the same standard as the other
    four. Without this, skipping hidden columns would have exempted it
    permanently and nobody would notice.
    """
    from openchem.ui.panels.docking_panel import _POSE_COLUMNS, _RESCORE_COLUMN

    panel, _engine, _service = _make_panel()
    panel.show()
    panel._show_result(_rescored(_result_with(_replicate_set(-8.79))))
    panel.resize(panel.minimumSizeHint().width(), 900)
    qapp.processEvents()

    checked = {name for name, _, _ in _header_shortfalls(panel)}
    assert not panel._table.isColumnHidden(_POSE_COLUMNS.index(_RESCORE_COLUMN))
    # It is in the population now: nothing is clipped, but the column is
    # being measured rather than skipped.
    assert _header_shortfalls(panel) == []
    assert checked == set()
