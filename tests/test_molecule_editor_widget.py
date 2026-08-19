from __future__ import annotations

from PySide6.QtGui import QUndoStack
from PySide6.QtWidgets import QWidget

from openchem.chem.engine import ChemistryEngine
from openchem.domain.molecule import MoleculeModel
from openchem.events.base import EventBus
from openchem.ui.editor_backend import EditorBackend
from openchem.ui.widgets.molecule_editor_widget import MoleculeEditorWidget


class _RecordingEditorBackend(EditorBackend):
    """Minimal in-memory stand-in for KetcherEditorBackend -- no
    QWebEngineView involved, just records what MoleculeEditorWidget asks it
    to do. Exercises the real (inherited) `EditorBackend.clear()` default,
    not an override, so these tests cover the actual production code path.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._widget = QWidget(parent)
        self.load_calls: list[str] = []
        self.render_option_calls: list[tuple[str, object]] = []
        self.toolbar_action_calls: list[str] = []
        self.atom_tool_calls: list[str] = []
        self.cip_calls: list[bool] = []
        #: What the canvas will hand back on the next `edited`. None means
        #: "whatever was last loaded", i.e. an edit that changed nothing --
        #: set it to stage a real one.
        self.next_molblock: str | None = None

    def load_molblock(self, molblock: str) -> None:
        self.load_calls.append(molblock)

    def get_molblock(self, callback):
        if self.next_molblock is not None:
            callback(self.next_molblock)
            return
        callback(self.load_calls[-1] if self.load_calls else None)

    def set_cip_labels(self, on):
        self.cip_calls.append(on)

    #: What `set_atom_tool` answers. True is the ordinary case; a test
    #: that wants the drop sets it False.
    atom_tool_armed = True

    def set_render_option(self, name, value):
        self.render_option_calls.append((name, value))

    def trigger_toolbar_action(self, action_id):
        self.toolbar_action_calls.append(action_id)

    def set_atom_tool(self, symbol, mass_number=None):
        self.atom_tool_calls.append(symbol)
        # **A REAL BACKEND ANSWERS WHETHER IT ARMED**, and a fake that
        # returned None was silently modelling a DROPPED arming -- which
        # is what the window shows "the 2D editor is still loading" for.
        return self.atom_tool_armed

    def widget(self):
        return self._widget


def _make_widget():
    engine = ChemistryEngine()
    bus = EventBus()
    undo_stack = QUndoStack()
    backend = _RecordingEditorBackend()
    widget = MoleculeEditorWidget(engine, bus, undo_stack, backend=backend)
    return engine, widget, backend


def test_editor_backend_default_clear_delegates_to_load_molblock_empty(qapp):
    backend = _RecordingEditorBackend()
    backend.clear()
    assert backend.load_calls == [""]


def test_set_molecule_with_structure_loads_its_molblock(qapp):
    engine, widget, backend = _make_widget()
    molecule = MoleculeModel()
    engine.set_structure_from_smiles(molecule, "CCO")

    widget.set_molecule(molecule)

    assert backend.load_calls == [molecule.molblock]


def test_set_molecule_none_clears_the_canvas(qapp):
    _, widget, backend = _make_widget()
    backend.load_molblock("some previously-drawn structure")

    widget.set_molecule(None)

    assert backend.load_calls[-1] == ""


def test_set_molecule_with_no_structure_clears_instead_of_leaving_stale_content(qapp):
    """Regression test for the 'phantom structure' bug: switching to a
    freshly-created molecule with no molblock yet used to silently no-op,
    leaving whatever was drawn before this molecule was selected still
    visible on the canvas."""
    _, widget, backend = _make_widget()
    backend.load_molblock("leftover drawing from before a molecule existed")

    molecule = MoleculeModel(display_name="New molecule")  # no molblock
    widget.set_molecule(molecule)

    assert backend.load_calls[-1] == ""


def test_editing_is_no_longer_silently_discarded_once_a_molecule_is_selected(qapp):
    """Root cause of 'nothing works until File > New Molecule': edits are
    only ever silently dropped when self._molecule is None. Once a molecule
    is selected (even one auto-created with no structure), editing must
    actually apply."""
    engine, widget, backend = _make_widget()
    molecule = MoleculeModel(display_name="New molecule")
    widget.set_molecule(molecule)

    backend.load_molblock(engine.mol_to_molblock(engine.mol_from_smiles("CCO")))
    widget._on_editor_edited()

    assert molecule.molblock is not None


def test_set_render_option_delegates_to_the_backend(qapp):
    _, widget, backend = _make_widget()

    widget.set_render_option("showHydrogenLabels", "All")

    assert backend.render_option_calls == [("showHydrogenLabels", "All")]


def test_trigger_toolbar_action_delegates_to_the_backend(qapp):
    _, widget, backend = _make_widget()

    widget.trigger_toolbar_action("Add/Remove explicit hydrogens button")

    assert backend.toolbar_action_calls == ["Add/Remove explicit hydrogens button"]


# --- the canvas must follow changes it did not make -------------------------


def _widget_with_molecule():
    engine, widget, backend = _make_widget()
    molecule = MoleculeModel(display_name="Test")
    widget.set_molecule(molecule)
    return engine, widget, backend, molecule


def _external_edit(widget, engine, molecule, smiles):
    """Change the model the way Paste Structure does: through a command,
    not through the editor."""
    from rdkit import Chem

    from openchem.commands.molecule_commands import EditStructureCommand

    molblock = Chem.MolToMolBlock(Chem.MolFromSmiles(smiles))
    widget._undo_stack.push(
        EditStructureCommand(engine, molecule, molblock, widget._event_bus)
    )


def test_undo_reloads_the_canvas(qapp):
    """The bug this exists for.

    `EditStructureCommand` reverts the model and publishes MoleculeChanged;
    nothing was listening, so pasting a structure and pressing Ctrl+Z
    emptied the molecule while the editor went on drawing it. Confirmed
    live: Properties read mol_wt 0 with a blank formula and aspirin was
    still on screen.
    """
    engine, widget, backend, molecule = _widget_with_molecule()
    _external_edit(widget, engine, molecule, "CC(=O)Oc1ccccc1C(=O)O")
    after_paste = len(backend.load_calls)

    widget._undo_stack.undo()

    assert not molecule.canonical_smiles
    assert len(backend.load_calls) > after_paste, "the model reverted and the canvas was not told"
    assert backend.load_calls[-1] == "", "an emptied molecule must clear the canvas"


def test_redo_reloads_the_canvas(qapp):
    engine, widget, backend, molecule = _widget_with_molecule()
    _external_edit(widget, engine, molecule, "C1CN1")
    widget._undo_stack.undo()
    before = len(backend.load_calls)

    widget._undo_stack.redo()

    assert molecule.canonical_smiles == "C1CN1"
    assert len(backend.load_calls) > before


def test_the_users_own_edit_does_not_reload_the_canvas(qapp):
    """THIS MATTERS MORE THAN THE FIX ITSELF.

    Reloading on every MoleculeChanged would pull the drawing out from
    under someone mid-structure. The comparison is on constitution, so the
    model holding what the user just drew is a no-op here.
    """
    from rdkit import Chem

    engine, widget, backend, molecule = _widget_with_molecule()
    backend.load_calls.append(Chem.MolToMolBlock(Chem.MolFromSmiles("CCO")))
    before = len(backend.load_calls)

    widget._on_editor_edited()

    assert molecule.canonical_smiles == "CCO"
    assert len(backend.load_calls) == before, "reloaded the canvas during the user own edit"


def test_a_change_to_another_molecule_is_ignored(qapp):
    from openchem.events.events import MoleculeChanged

    engine, widget, backend, molecule = _widget_with_molecule()
    before = len(backend.load_calls)

    widget._event_bus.publish(MoleculeChanged(molecule_uuid="a-different-molecule"))
    qapp.processEvents()

    assert len(backend.load_calls) == before


def test_the_widget_forwards_the_editors_intercepted_controls(qapp):
    """Ketcher's own toolbar controls are answered by the APPLICATION, so
    each request has to survive the trip backend -> widget -> window.
    Forwarded straight through, which makes a break here silent: the
    button simply stops doing anything at all.

    The ACTION NAME is asserted, not merely that something arrived --
    every one of these travels on the same signal, so a forwarder that
    dropped or rewrote the payload would route every control to whichever
    handler happened to be first.
    """
    _engine, widget, backend = _make_widget()
    seen: list[str] = []
    widget.editor_action_requested.connect(seen.append)

    for action in ("periodic_table", "import", "export", "about", "help", "viewer_3d",
                   "undo", "redo"):
        backend.editor_action_requested.emit(action)

    assert seen == ["periodic_table", "import", "export", "about", "help", "viewer_3d",
                    "undo", "redo"]


def test_the_widget_arms_the_canvas_with_a_chosen_element(qapp):
    """"Insert into drawing" reaches the backend as an atom tool."""
    _engine, widget, backend = _make_widget()

    widget.set_atom_tool("Fe")

    assert backend.atom_tool_calls == ["Fe"]


def test_the_widget_passes_the_arming_ANSWER_back_up(qapp):
    """**THE MIDDLE LAYER IS WHERE A DROPPED ARMING GETS LOST.** The
    backend refuses before Ketcher is ready and the window shows "the 2D
    editor is still loading" -- but only if the answer survives the trip
    through here. A `set_atom_tool` that calls down and returns None
    passes every test at either end while restoring the defect.

    Both arms, because returning a constant satisfies one of them.
    """
    _engine, widget, backend = _make_widget()

    backend.atom_tool_armed = True
    assert widget.set_atom_tool("Fe") is True

    backend.atom_tool_armed = False
    assert widget.set_atom_tool("Fe", 56) is False
    assert backend.atom_tool_calls == ["Fe", "Fe"], "it still tried"


def _electron_backend():
    """A recording backend that also captures electron payloads."""
    backend = _RecordingEditorBackend()
    backend.electron_payloads = []
    backend.set_electron_overlay = backend.electron_payloads.append
    return backend


def _widget_with_electrons(qapp, smiles="CO"):
    engine = ChemistryEngine()
    bus = EventBus()
    backend = _electron_backend()
    widget = MoleculeEditorWidget(engine, bus, QUndoStack(), backend=backend)
    molecule = MoleculeModel(display_name="Test")
    engine.set_structure_from_smiles(molecule, smiles)
    widget.set_molecule(molecule)
    return widget, backend, molecule


def test_the_electron_overlay_is_off_until_asked_for(qapp):
    """An annotation nobody asked for is one more thing on a crowded
    canvas -- and the payload is None rather than an empty one, so the
    page takes the layer down instead of drawing zero dots."""
    widget, backend, _ = _widget_with_electrons(qapp)

    assert widget.electron_mode() == "off"
    assert backend.electron_payloads == [None]


def test_turning_the_mode_on_sends_the_counts(qapp):
    widget, backend, _ = _widget_with_electrons(qapp, "CO")

    widget.set_electron_mode("pairs")

    payload = backend.electron_payloads[-1]
    assert payload["mode"] == "pairs"
    # Methanol: the oxygen carries two pairs, the carbon none -- and the
    # carbon's ZERO is present, because absent means "no definite answer".
    assert payload["counts"] == {"0": 0, "1": 2}
    assert payload["refused"] is False


def test_a_NEW_STRUCTURE_republishes_without_anyone_asking(qapp):
    """**The chemistry tier, owned in one place.** Selection, undo, adopt
    and rotate all arrive through `set_molecule`, so putting the refresh
    at each call site is how one of them gets forgotten and the dots
    describe the previous molecule."""
    widget, backend, molecule = _widget_with_electrons(qapp, "CO")
    widget.set_electron_mode("pairs")
    before = len(backend.electron_payloads)

    other = MoleculeModel(display_name="Other")
    ChemistryEngine().set_structure_from_smiles(other, "CC=O")
    widget.set_molecule(other)

    assert len(backend.electron_payloads) > before
    assert backend.electron_payloads[-1]["counts"] == {"0": 0, "1": 0, "2": 2}


def test_turning_the_mode_off_takes_the_layer_down(qapp):
    widget, backend, _ = _widget_with_electrons(qapp)
    widget.set_electron_mode("pairs")

    widget.set_electron_mode("off")

    assert backend.electron_payloads[-1] is None


def test_a_refusal_is_announced_rather_than_drawn_as_nothing(qapp):
    """Ferrocene and a carbene draw no dots, and so does an ammonium
    nitrogen. The status line is the only thing that tells them apart."""
    widget, backend, _ = _widget_with_electrons(qapp, "[CH2]")
    said: list[str] = []
    widget.electron_status.connect(said.append)

    widget.set_electron_mode("pairs")

    assert backend.electron_payloads[-1]["refused"] is True
    assert said and "unavailable" in said[-1].lower(), said


# --- an edit the USER makes on the canvas --------------------------------
#
# The route `set_molecule` never covers, and the one both stale-annotation
# bugs came down the.


def _molblock_for(smiles: str) -> str:
    molecule = MoleculeModel(display_name="staged")
    ChemistryEngine().set_structure_from_smiles(molecule, smiles)
    return molecule.molblock


def _nudged(molblock: str) -> str:
    """The same structure, drawn somewhere slightly different.

    What Layout, Clean Up and dragging an atom produce: new coordinates,
    identical chemistry. Built by editing the first atom's x in the V2000
    atom block rather than by re-embedding, so nothing but the coordinate
    can differ.
    """
    lines = molblock.splitlines()
    first_atom = 4
    x = float(lines[first_atom][0:10]) + 1.5
    lines[first_atom] = f"{x:10.4f}" + lines[first_atom][10:]
    return "\n".join(lines) + "\n"


def _edit_the_canvas(widget, backend, molblock: str) -> None:
    """Drive the path a user's own drawing takes, exactly as Ketcher does:
    the canvas reports a new molblock through `edited`."""
    backend.next_molblock = molblock
    backend.edited.emit()


def test_an_edit_on_the_canvas_republishes_the_counts(qapp):
    """THE REPORTED BUG'S SIBLING, and the half nothing covered.

    `test_a_NEW_STRUCTURE_republishes_without_anyone_asking` above proves
    the `set_molecule` routes -- selection, undo, adopt, rotate. A user
    drawing on the canvas reaches none of them: `_on_editor_edited` pushes
    the command and updates `_synced_smiles`, so `_on_molecule_changed`
    returns early every single time. The counts therefore described
    whatever structure was last SELECTED, however much had been drawn since.
    """
    widget, backend, _ = _widget_with_electrons(qapp, "CO")
    widget.set_electron_mode("pairs")
    assert backend.electron_payloads[-1]["counts"] == {"0": 0, "1": 2}

    _edit_the_canvas(widget, backend, _molblock_for("CCO"))

    assert backend.electron_payloads[-1]["counts"] == {"0": 0, "1": 0, "2": 2}


def test_after_a_deletion_the_counts_describe_the_SURVIVING_atoms(qapp):
    """A stale count is not merely old here -- it is attached to the wrong atom.

    The payload is keyed on MOLFILE POSITION, and deleting an atom shifts
    every position after it. So the failure is not "the oxygen's dots are
    out of date", it is "the oxygen's dots are now drawn on a carbon", plus
    an entry for a position the structure no longer has.

    Asserted on where the pairs LAND rather than on the whole dict, so the
    test says what it is about and does not also pin the amine's own count.
    """
    widget, backend, _ = _widget_with_electrons(qapp, "NCCO")
    widget.set_electron_mode("pairs")
    before = backend.electron_payloads[-1]["counts"]
    # Assert the setup: without the oxygen at position 3 there is no shift
    # to detect and this test would pass against anything.
    assert before["3"] == 2 and len(before) == 4, before

    _edit_the_canvas(widget, backend, _molblock_for("CCO"))

    after = backend.electron_payloads[-1]["counts"]
    assert len(after) == 3, after
    assert after["2"] == 2, "the oxygen's pairs are not on the oxygen"
    assert "3" not in after, "an atom that was deleted still carries dots"


def test_an_edit_refreshes_the_descriptors_only_when_they_are_shown(qapp):
    """The reported bug itself, at the widget.

    "If a molecule is changed while the label is turned on, it won't
    update." Both halves matter: refreshing when they are OFF would draw
    labels nobody asked for, and is also how a "recompute everything on
    every change" hook starts.
    """
    widget, backend, _ = _widget_with_electrons(qapp, "CO")

    _edit_the_canvas(widget, backend, _molblock_for("CCO"))
    assert backend.cip_calls == [], "descriptors were never turned on"

    widget.set_cip_labels(True)
    assert backend.cip_calls == [True]

    _edit_the_canvas(widget, backend, _molblock_for("CCCO"))
    assert backend.cip_calls == [True, True], "the edit did not recompute them"

    widget.set_cip_labels(False)
    _edit_the_canvas(widget, backend, _molblock_for("CCCCO"))
    assert backend.cip_calls == [True, True, False], "an edit refreshed a display that is off"


def test_a_change_that_moves_no_chemistry_recomputes_nothing(qapp):
    """THE TIER BOUNDARY, and it is what stops this becoming "recalculate
    everything on every change".

    Ketcher fires `change` for a great deal that is not a structure edit --
    Layout, Clean Up and dragging an atom all move coordinates and leave
    the chemistry alone. The page repositions the dots itself from the
    struct it already has, and a descriptor does not depend on where an
    atom was drawn. Recomputing here would run a `LewisAnalysis` per drag
    frame for no change in the answer.

    Both annotations are checked in one test on purpose: they share the
    gate, so a mutation that opens it would otherwise be caught twice and
    fixed once.
    """
    widget, backend, molecule = _widget_with_electrons(qapp, "NCCO")
    widget.set_electron_mode("pairs")
    widget.set_cip_labels(True)
    overlays = len(backend.electron_payloads)
    cips = len(backend.cip_calls)

    _edit_the_canvas(widget, backend, _nudged(molecule.molblock))

    assert len(backend.electron_payloads) == overlays, "a move recomputed the chemistry"
    assert len(backend.cip_calls) == cips, "a move recomputed the descriptors"


def test_a_refresh_cannot_trigger_a_refresh(qapp):
    """The recursion guard, asserted rather than reasoned about.

    Whatever the descriptor refresh does must not itself count as a
    structural change, or every refresh schedules another one. It
    terminates on the same discriminator `_on_molecule_changed` and
    `EditStructureCommand._invalidate_stale_conformers` already use --
    canonical SMILES -- rather than on a flag, which is why an editor
    change reporting the very same structure has to be a no-op here.
    """
    widget, backend, molecule = _widget_with_electrons(qapp, "CO")
    widget.set_cip_labels(True)
    cips = len(backend.cip_calls)

    for _ in range(3):
        _edit_the_canvas(widget, backend, molecule.molblock)

    assert len(backend.cip_calls) == cips


def test_no_lone_pairs_is_announced_too_because_it_LOOKS_the_same(qapp):
    widget, backend, _ = _widget_with_electrons(qapp, "C[NH3+]")
    said: list[str] = []
    widget.electron_status.connect(said.append)

    widget.set_electron_mode("pairs")

    assert backend.electron_payloads[-1]["refused"] is False
    assert said[-1] == "No lone pairs."
