"""Script the running application, for measurements that need the REAL window.

**WHY THIS IS IN THE APP RATHER THAN A HARNESS.** `CLAUDE.md` and
`docs/ARCHITECTURE.md` record four occasions where an out-of-app Qt
harness said the opposite of the running application -- no clipping while
the app clipped, no horizontal scrollbar while the app had one, a
full-width label while the app truncated. So a measurement has to happen
inside the real `MainWindow`, with its real docks, fonts and DPI. What
does NOT have to happen is driving it through the machine's mouse and
keyboard.

**WHAT IT REPLACES.** Every earlier investigation drove the app with
`SetCursorPos` + `mouse_event` + `SendKeys`, which use the real input
queue: the cursor jumps, the app must hold focus for every step, and the
machine is unusable for the length of a run. It is also fragile in a way
that reads as an app bug -- a console window stealing focus mid-sequence
sent a paste somewhere else and the run looked like "the app ignored the
import". Worst of all, the native file dialog had to be driven by hand
every single time.

Here the actions happen INSIDE the process: no cursor, no focus, no file
dialog. The window can sit behind whatever the user is working in.

    OPENCHEM_DRIVE=<script.json>  uv run python -m openchem.main

The script is a JSON list of steps, run in order:

    [
      {"do": "import",     "path": "C:/tmp/ethylmorphine.mol"},
      {"do": "select",     "molecule": -1},
      {"do": "receptor",   "pdb_id": "6WGT"},
      {"do": "dock_panel", "tag": "after-6wgt"},
      {"do": "panel",      "id": "Properties"},
      {"do": "expand",     "section": "admet"},
      {"do": "calculator", "id": "admet_ml", "parameters": {"tier": "basic"},
                           "after_ms": 45000},
      {"do": "shot",       "path": "C:/tmp/admet.png"},
      {"do": "overlay",    "on": true, "gallery": true, "step": 0},
      {"do": "rotate",     "dx": 120, "dy": -40},
      {"do": "lewis"},
      {"do": "shot",       "path": "C:/tmp/lewis.png", "widget": "lewis"},
      {"do": "resize",     "maximized": true},
      {"do": "resize",     "width": 1100},
      {"do": "rail",       "collapsed": true},
      {"do": "geometry",   "label": "maximized/Quantum"},
      {"do": "quit"}
    ]

`after_ms` is how long to wait BEFORE the next step, which is how an
asynchronous calculator is waited on. Every step defaults to 400 ms.

It reaches into private attributes of `MainWindow` on purpose: this is a
diagnostic that must drive the window a user actually gets, not a
parallel construction of one, and a public API invented for it would be
a second way to do everything.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Qt, QTimer
from PySide6.QtWidgets import QWidget

logger = logging.getLogger("openchem.ui")

#: Set to a JSON script path to drive the app. Off otherwise, at the cost
#: of one `os.environ` read at import.
_DRIVE_SCRIPT = os.environ.get("OPENCHEM_DRIVE")

#: Pause between steps when one does not say otherwise. Long enough for a
#: layout pass and a queued event to be delivered, short enough that a
#: twenty-step script is not a coffee break.
_DEFAULT_AFTER_MS = 400


def start_if_requested(window: QWidget) -> "_Driver | None":
    """Begin driving `window` when `OPENCHEM_DRIVE` names a script.

    Returns the driver so the caller can keep it alive -- a `QTimer` whose
    owner is garbage collected stops firing, which would strand the script
    half-way through and look like the app hanging.
    """
    if not _DRIVE_SCRIPT:
        return None
    try:
        steps = json.loads(Path(_DRIVE_SCRIPT).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("OPENCHEM_DRIVE: cannot read %s: %s", _DRIVE_SCRIPT, exc)
        return None
    if not isinstance(steps, list):
        logger.error("OPENCHEM_DRIVE: %s must contain a JSON list of steps", _DRIVE_SCRIPT)
        return None
    driver = _Driver(window, steps)
    driver.start()
    return driver


def _walk_actions(menu):
    """Every action under `menu`, submenus included.

    Recursive because the interesting ones are two levels down --
    View > 2D Structure Display > Electron Display -- and a driver that
    only saw the top level could not reach anything worth driving.
    """
    for action in menu.actions():
        yield action
        child = action.menu()
        if child is not None:
            yield from _walk_actions(child)


class _Driver(QObject):
    """Runs the steps one at a time, off a `QTimer`.

    Sequential rather than concurrent because the interesting steps are
    asynchronous -- a calculator dispatches to a thread pool -- and the
    thing being measured is what the window looks like AFTER one has
    landed.

    **A QObject so it can carry signals if this harness ever grows them,
    and DELIBERATELY WITHOUT A Qt PARENT.** Parenting it to the window
    would be the reflexive next step and buys nothing here: the window is
    already the context object for both shots, which is what ends the
    script, and an unparented driver stays inspectable after the window
    goes -- `main.py` hangs it off `window._debug_driver`, and a wrapper
    whose C++ object had been destroyed as a child would raise on the way
    past.

    **THE CONTEXT OBJECT MUST STAY THE WINDOW, NOT `self`.** Becoming a
    QObject makes `self` newly available and it is the obvious-looking
    choice; it is also the one that fails in exactly this shape, because
    a pending shot holds the bound method, which holds the driver, so the
    driver cannot be collected while a step is queued. Measured, dropping
    every Python reference and destroying the window:

        parented,   bound to self     cancelled
        parented,   bound to window   cancelled
        UNPARENTED, bound to self     FIRED against a dead window
        UNPARENTED, bound to window   cancelled

    So the two are equivalent only under a parent this class does not
    have. Binding to the window is correct either way, which is why it is
    the one written down.
    """

    def __init__(self, window: QWidget, steps: list[dict[str, Any]]) -> None:
        super().__init__()
        self._window = window
        self._steps = steps
        self._index = 0
        #: The Lewis dialog a `lewis` step opened, so a later `shot` can
        #: grab it. Held rather than looked up: it is parented to the
        #: window and finding it by type would be one more place that can
        #: pick the wrong one once a second dialog exists.
        self._lewis: QWidget | None = None

    def start(self) -> None:
        logger.warning("OPENCHEM_DRIVE: %d step(s) from %s", len(self._steps), _DRIVE_SCRIPT)
        # THE WINDOW IS THE CONTEXT OBJECT, NOT THE DRIVER, and it is the
        # right one for a reason beyond `_Driver` being a plain class Qt
        # would refuse: every step acts on that window, so a window that
        # is gone means a script with nothing left to drive. Qt cancels a
        # context-bound shot when the context dies, which ends the chain
        # instead of running the remaining steps against a freed window.
        # `self._window` is safe to reach for here -- `main.py` hangs the
        # driver off the window, so the driver never outlives it.
        QTimer.singleShot(_DEFAULT_AFTER_MS, self._window, self._run_next)

    def _run_next(self) -> None:
        if self._index >= len(self._steps):
            logger.warning("OPENCHEM_DRIVE: script complete")
            return
        step = self._steps[self._index]
        self._index += 1
        action = str(step.get("do", ""))
        try:
            handler = getattr(self, f"_do_{action}", None)
            if handler is None:
                logger.error("OPENCHEM_DRIVE: unknown step %r", action)
            else:
                logger.warning("OPENCHEM_DRIVE: step %d %s", self._index, action)
                handler(step)
        except Exception:  # noqa: BLE001 - a bad script must not kill the app
            logger.exception("OPENCHEM_DRIVE: step %d (%s) failed", self._index, action)
        after = int(step.get("after_ms", _DEFAULT_AFTER_MS))
        # A BOUND METHOD, never a lambda capturing self: PySide6 holds a
        # plain callable strongly (see tests/test_qt_object_disposal.py).
        # Context-bound to the window for the reason given in `start`.
        QTimer.singleShot(after, self._window, self._run_next)

    # -- steps ---------------------------------------------------------

    def _do_smiles(self, step: dict[str, Any]) -> None:
        """Add a molecule from SMILES, with no file on disk.

        `import` needs a path, and half of what is worth driving is a
        one-line structure -- writing water to a temp file to look at its
        lone pairs is friction with no purpose.
        """
        from openchem.commands.molecule_commands import AddMoleculeCommand
        from openchem.domain.molecule import MoleculeModel

        window = self._window
        project = window._session.project
        if project is None:
            logger.error("OPENCHEM_DRIVE: no project to add to")
            return
        molecule = MoleculeModel(display_name=str(step.get("name", step["smiles"])))
        window._services.chemistry_engine.set_structure_from_smiles(molecule, str(step["smiles"]))
        window._undo_stack.push(
            AddMoleculeCommand(project, molecule, window._services.event_bus)
        )
        window._project_explorer.refresh()
        window._refresh_molecule_combos()

    def _do_import(self, step: dict[str, Any]) -> None:
        """Import a structure WITHOUT the file dialog.

        `MainWindow._import_molecule` exists to ask the user for a path;
        driving its native dialog was the most fragile part of every
        earlier run, so this pushes the same command with a path already
        in hand. The undo stack is used rather than bypassed, so the
        import is the same operation a user performs.
        """
        from openchem.commands.import_export_commands import ImportMoleculeCommand

        window = self._window
        project = window._session.project
        if project is None:
            logger.error("OPENCHEM_DRIVE: no project to import into")
            return
        command = ImportMoleculeCommand(
            window._services.import_service, project, Path(str(step["path"])), window._services.event_bus
        )
        window._undo_stack.push(command)
        window._project_explorer.refresh()
        window._refresh_molecule_combos()

    def _do_receptor(self, step: dict[str, Any]) -> None:
        """Add a receptor from the library cache, WITHOUT the network.

        `{"do": "receptor", "pdb_id": "6WGT"}`

        Goes through `add_macromolecule` with the same
        `entry_metadata` a real catalogue import records, because
        `ligand_code` is what the Docking panel derives its search box
        from -- an import that skipped the metadata would exercise the
        imported-receptor path instead of the catalogue one, which is a
        different branch and the wrong one to be checking.

        Reads the on-disk cache only. Downloading here would make a
        diagnostic run depend on the network and on RCSB being up, and
        the cache is populated by any real use of File > Receptor Library.
        """
        from openchem.chem.receptor_library import RECEPTOR_LIBRARY
        from openchem.domain.macromolecule import MacromoleculeModel
        from openchem.services.receptor_library_service import cached_structure, entry_metadata

        window = self._window
        pdb_id = str(step["pdb_id"]).upper()
        cached = cached_structure(pdb_id)
        if cached is None:
            logger.error(
                "OPENCHEM_DRIVE: %s is not in the receptor cache -- open it once "
                "through File > Receptor Library first",
                pdb_id,
            )
            return
        structure_text, source_format = cached
        # `"plain": true` drops the catalogue metadata, which is what an
        # imported receptor looks like -- no `ligand_code`, so the panel
        # takes the "no annotated site" branch. The one way to drive the
        # stale-box case, where a derived box must NOT survive the move to
        # a receptor that has no site of its own.
        entry = (
            None
            if bool(step.get("plain", False))
            else next((e for e in RECEPTOR_LIBRARY if e.pdb_id.upper() == pdb_id), None)
        )
        window.add_macromolecule(
            MacromoleculeModel(
                display_name=f"{entry.target} ({entry.pdb_id})" if entry else pdb_id,
                structure_text=structure_text,
                source_format=source_format,
                metadata=entry_metadata(entry) if entry else {},
            )
        )

    def _do_dock_receptor(self, step: dict[str, Any]) -> None:
        """Point the Docking panel's receptor combo at one entry.

        `{"do": "dock_receptor", "index": 1}` -- negative indexes from the
        end, as `select` does for molecules.

        Adding a receptor does NOT select it: `molecule_combo.repopulate`
        restores the previous pick by uuid, deliberately. So driving the
        receptor-CHANGE path needs this as a separate step, and a script
        that only adds a second receptor is still looking at the first --
        which is what a run of this harness reported before this existed,
        and read at first as the box failing to reset.
        """
        panel = getattr(self._window, "_docking_panel", None)
        if panel is None:
            logger.error("OPENCHEM_DRIVE: no docking panel on this window")
            return
        combo = panel._receptor_combo
        index = int(step.get("index", 0))
        if index < 0:
            index += combo.count()
        if not 0 <= index < combo.count():
            logger.error("OPENCHEM_DRIVE: receptor index %s out of range", step.get("index"))
            return
        combo.setCurrentIndex(index)
        logger.warning("OPENCHEM_DRIVE: dock_receptor -> %r", combo.currentText())

    def _do_dock_panel(self, step: dict[str, Any]) -> None:
        """Report what the Docking panel's search box currently says.

        `{"do": "dock_panel", "tag": "after-6wgt"}`

        The box is six spinboxes and a status line, so a screenshot shows
        it but cannot be asserted on. This logs the numbers, where they
        came from, and what the panel is telling the user -- which is the
        difference between "the shot looks right" and "the box is on the
        site".
        """
        panel = getattr(self._window, "_docking_panel", None)
        if panel is None:
            logger.error("OPENCHEM_DRIVE: no docking panel on this window")
            return
        box = panel.displayed_box()
        logger.warning(
            "OPENCHEM_DRIVE: dock_panel[%s] centre=(%.3f, %.3f, %.3f) size=(%.1f, %.1f, %.1f) "
            "source=%s derive_enabled=%s",
            step.get("tag", ""),
            *box.center,
            *box.size,
            panel._box_source,
            panel._derive_button.isEnabled(),
        )
        logger.warning("OPENCHEM_DRIVE: dock_panel[%s] box_status=%r",
                       step.get("tag", ""), panel._box_status_label.text())

    def _do_select(self, step: dict[str, Any]) -> None:
        """Select a molecule by index (-1 is the most recent) or by name."""
        from openchem.events.events import MoleculeSelected

        window = self._window
        molecules = window._session.project.molecules
        if not molecules:
            logger.error("OPENCHEM_DRIVE: no molecules to select")
            return
        wanted = step.get("molecule", -1)
        if isinstance(wanted, str):
            model = next((m for m in molecules if m.display_name == wanted), None)
        else:
            model = molecules[int(wanted)]
        if model is None:
            logger.error("OPENCHEM_DRIVE: no molecule %r", wanted)
            return
        window._services.event_bus.publish(MoleculeSelected(molecule_uuid=model.uuid))

    def _do_panel(self, step: dict[str, Any]) -> None:
        self._window._on_panel_chosen(str(step["id"]))

    def _do_align(self, step: dict[str, Any]) -> None:
        """Run the 3D Alignment panel on the project's molecules.

        The panel had no drive coverage at all before the pop-out work,
        which is why this exists: its output is a PICTURE, and a picture
        is the one thing the test suite cannot judge.

        **NAME THE REFERENCE.** Without one this ticks everything and
        aligns onto whatever sits at index 0, which is the STARTER
        MOLECULE -- it has no molblock, so the run reports "Ensemble
        alignment failed" and reads as a bug in the panel. Same shape as
        the `smiles`/`conformers` trap this file already documents one
        step along: a step that does not select what it added.

        `probes` names which molecules to tick; without it every other
        molecule is ticked, starter included.
        """
        panel = self._window._alignment_panel
        reference = step.get("reference")
        if reference is not None:
            index = panel._reference_combo.findText(str(reference))
            if index < 0:
                logger.error("OPENCHEM_DRIVE: no molecule %r to align onto", reference)
                return
            panel._reference_combo.setCurrentIndex(index)
        wanted = step.get("probes")
        for row in range(panel._probe_list.count()):
            item = panel._probe_list.item(row)
            ticked = True if wanted is None else item.text() in wanted
            item.setCheckState(
                Qt.CheckState.Checked if ticked else Qt.CheckState.Unchecked
            )
        if "method" in step:
            panel._method_combo.setCurrentText(str(step["method"]))
        if "accuracy" in step:
            panel._accuracy_combo.setCurrentText(str(step["accuracy"]))
        logger.warning(
            "OPENCHEM_DRIVE: aligning %d probe(s) onto %r, method=%s accuracy=%s",
            len(panel._checked_uuids()),
            panel._reference_combo.currentText(),
            panel._method_combo.currentText(),
            panel._accuracy_combo.currentText(),
        )
        panel._on_align_clicked()

    def _do_pop_out(self, step: dict[str, Any]) -> None:
        """Move a panel's view into its own window, or bring it back.

        `{"do": "pop_out", "panel": "3D_Alignment"}` -- note the
        UNDERSCORE. `_dock_by_panel_id` matches `dock.objectName()`, and
        a wrong id used to be a silent no-op that logged a healthy-looking
        step while photographing the wrong panel. An unrecognised name is
        LOGGED here rather than ignored, for the same reason a `tab` name
        that matches nothing is.

        Called a second time on the same panel it returns the view, so a
        script can photograph all three states without a second step.
        """
        from openchem.ui.widgets.pop_out_host import PopOutHost

        panel_id = str(step["panel"])
        dock = self._window._dock_by_panel_id(panel_id)
        if dock is None:
            logger.error(
                "OPENCHEM_DRIVE: no panel %r -- object names use underscores, "
                "e.g. '3D_Alignment', 'Quantum_Chemistry'",
                panel_id,
            )
            return
        widget = dock.widget()
        hosts = widget.findChildren(PopOutHost) if widget is not None else []
        if not hosts:
            logger.error("OPENCHEM_DRIVE: panel %r has no pop-out view", panel_id)
            return
        host = hosts[int(step.get("index", 0))]
        if host.is_popped_out():
            host.return_home()
            self._popout = None
            logger.warning("OPENCHEM_DRIVE: returned %r to its panel", panel_id)
            return
        self._popout = host.pop_out()
        logger.warning(
            "OPENCHEM_DRIVE: %r detached, window %dx%d",
            panel_id,
            self._popout.width(),
            self._popout.height(),
        )

    def _do_expand(self, step: dict[str, Any]) -> None:
        """Expand one Properties section, by category id (e.g. "admet")."""
        section = self._window._property_panel._sections.get(str(step["section"]))
        if section is None:
            logger.error("OPENCHEM_DRIVE: no section %r", step["section"])
            return
        section.set_expanded(bool(step.get("expanded", True)))

    def _do_calculator(self, step: dict[str, Any]) -> None:
        """Run a calculator with no settings dialog.

        `_pending_calculator_id` is set exactly as `_open_calculator`
        sets it, so the result is REVEALED the way a button press reveals
        it. Skipping that would make the driver measure a path no user
        takes.

        **`_set_running` is set here for the same reason, and its absence
        was already a hole.** This step reproduces `_open_calculator`
        minus the settings dialog; when that function gained the waiting
        indicator, a scripted run showed no indicator at all and the
        feature looked broken when it was simply not being driven. Any
        state `_open_calculator` sets before dispatch belongs here too.
        """
        from openchem.domain.calculator import CalculationRequest

        window = self._window
        panel = window._property_panel
        calculator_id = str(step["id"])
        definition = window._services.calculator_registry.get(calculator_id)
        if definition is None:
            logger.error("OPENCHEM_DRIVE: no calculator %r", calculator_id)
            return
        molecule = window._session.project.find_molecule(panel._selected_molecule_uuid)
        if molecule is None:
            logger.error("OPENCHEM_DRIVE: no molecule selected for %r", calculator_id)
            return
        parameters: dict[str, Any] = {p.name: p.default for p in definition.parameters}
        parameters.update(step.get("parameters") or {})
        panel._pending_calculator_id = calculator_id
        panel._set_running(calculator_id, True)
        window._services.descriptor_service.run_calculator(
            molecule,
            CalculationRequest(
                calculator_id=calculator_id, molecule_uuid=molecule.uuid, parameters=parameters
            ),
        )

    def _do_shot(self, step: dict[str, Any]) -> None:
        """Save a picture of the window from inside Qt.

        Cheap and needs nothing outside the process. It DOES capture
        `QWebEngineView` content -- measured, with Ketcher's rendered
        structure present in the grab -- which was worth checking rather
        than assuming, since the usual expectation is that it comes out
        blank. If a view ever does grab blank, `spikes/gui_drive/drive.ps1`'s
        `Save-AppShot` goes through `PrintWindow` instead and captures
        whatever the compositor has.
        """
        path = Path(str(step["path"]))
        path.parent.mkdir(parents=True, exist_ok=True)
        target = self._window
        if step.get("widget") == "lewis":
            if self._lewis is None:
                logger.error("OPENCHEM_DRIVE: no Lewis dialog open; run {'do': 'lewis'}")
                return
            target = self._lewis
        elif step.get("widget") == "details":
            if getattr(self, "_details", None) is None:
                logger.error("OPENCHEM_DRIVE: no details dialog open; run {'do': 'details'}")
                return
            target = self._details
        elif step.get("widget") == "periodic":
            if getattr(self, "_periodic", None) is None:
                logger.error("OPENCHEM_DRIVE: no periodic table open; run {'do': 'periodic'}")
                return
            target = self._periodic
        elif step.get("widget") == "dialog":
            if getattr(self, "_dialog", None) is None:
                logger.error("OPENCHEM_DRIVE: no dialog open; run {'do': 'dialog', ...}")
                return
            target = self._dialog
        elif step.get("widget") == "spatial":
            if getattr(self, "_spatial", None) is None:
                logger.error("OPENCHEM_DRIVE: no spatial dialog open; run {'do': 'spatial'}")
                return
            target = self._spatial
        elif step.get("widget") == "popout":
            if getattr(self, "_popout", None) is None:
                logger.error("OPENCHEM_DRIVE: no detached view; run {'do': 'pop_out', ...}")
                return
            target = self._popout
        target.grab().save(str(path))
        logger.warning("OPENCHEM_DRIVE: wrote %s", path)

    def _do_periodic(self, step: dict[str, Any]) -> None:
        """Open the periodic table, and optionally choose an element and mode.

        `{"do": "periodic", "element": "Po", "colour": "state", "tab": 1}`

        **`show()`, not `exec()`**, for the reason `_do_lewis` gives -- and
        here it costs nothing, because the dialog is non-modal in the
        application too. This drives the SAME window a user gets from
        Tools or from the editor's own PT button, which is the point: the
        panel suite has stayed green through three visibly broken layouts
        in this project, and every finding that matters about this table
        came from a magnified screenshot rather than a test.
        """
        from openchem.chem import element_palettes as palettes

        window = self._window
        window._show_periodic_table()
        dialog = getattr(window, "_periodic_table_dialog", None)
        if dialog is None:  # pragma: no cover - defensive
            logger.error("OPENCHEM_DRIVE: the periodic table did not open")
            return
        self._periodic = dialog

        colour = step.get("colour")
        if colour is not None:
            if colour not in palettes.PALETTE_ORDER:
                logger.error(
                    "OPENCHEM_DRIVE: unknown colour mode %r; have %s",
                    colour,
                    ", ".join(palettes.PALETTE_ORDER),
                )
            else:
                dialog._palette_combo.setCurrentIndex(
                    palettes.PALETTE_ORDER.index(colour)
                )
        if step.get("element"):
            dialog.select(str(step["element"]))
        if step.get("tab") is not None:
            dialog._tabs.setCurrentIndex(int(step["tab"]))
        if step.get("width") or step.get("height"):
            dialog.resize(int(step.get("width", 1000)), int(step.get("height", 860)))

        logger.warning(
            "OPENCHEM_DRIVE: periodic %s -- colour %s, tab %s, legend %r",
            dialog.selected_symbol(),
            dialog._palette_key,
            dialog._tabs.tabText(dialog._tabs.currentIndex()),
            dialog._legend.text(),
        )

    def _do_lewis(self, step: dict[str, Any]) -> None:
        """Open the Full Lewis Structure window on the selected molecule.

        **`show()`, not the menu action's `exec()`**, and that is the only
        difference from what a click gives. A modal `exec()` spins its own
        event loop inside this handler, so the step chain would not be
        scheduled again until somebody closed the dialog -- an unattended
        run would stall on a window with nobody to answer it, which is the
        same trap `quit()` set for an earlier scripted run.

        Everything that could be wrong is still exercised: the real build
        from the real molblock, the real renderer, and a real QSvgWidget
        drawing it -- which is the piece no test of the SVG string can
        check, since Qt's SVG renderer ignores attributes a browser
        honours.
        """
        from openchem.ui.dialogs.lewis_diagram_dialog import LewisDiagramDialog

        window = self._window
        molecule = window._current_molecule()
        if molecule is None:
            logger.error("OPENCHEM_DRIVE: no molecule selected")
            return
        self._lewis = LewisDiagramDialog(
            molecule.molblock,
            display_name=molecule.display_name,
            structure_revision=window._services.structure_check_service.current_version(
                molecule.uuid
            ),
            parent=window,
        )
        if step.get("details"):
            self._lewis._details_button.setChecked(True)
        self._lewis.resize(int(step.get("width", 640)), int(step.get("height", 620)))
        self._lewis.show()
        logger.warning(
            "OPENCHEM_DRIVE: lewis %s -- %s",
            self._lewis.diagram.status.value,
            self._lewis.status_text(),
        )

    def _do_conformers(self, step: dict[str, Any]) -> None:
        """Generate conformers through the real service.

        Goes through `ConformerService`, so the whole chain a user gets
        runs: the service publishes `ConformersReady`, `MainWindow` pushes
        `SetConformersCommand`, that publishes `ConformersChanged`, and
        the descriptor request follows. That chain is the reason this step
        exists -- it is the only route to the `GEOMETRY` descriptor path,
        and nothing shorter exercises it.
        """
        window = self._window
        molecule = window._session.project.find_molecule(
            window._property_panel._selected_molecule_uuid
        )
        if molecule is None:
            logger.error("OPENCHEM_DRIVE: no molecule selected for conformers")
            return
        window._services.conformer_service.request_conformers(
            molecule,
            num_conformers=int(step.get("count", 3)),
            optimize=bool(step.get("optimize", True)),
            num_embeddings=step.get("embeddings"),
        )

    def _do_overlay(self, step: dict[str, Any]) -> None:
        """Turn the 3D viewer's shape overlay on, and optionally step.

        Drives the REAL chain: the panel's result, the service's
        recompute on the DISPLAYED conformer, and the page drawing it.
        `step` advances that many conformers afterwards, which is the
        case worth seeing -- the arrow must follow the molecule rather
        than staying where the first conformer put it.
        """
        viewer = self._window._viewer3d
        # THE 3D TAB, or the shot photographs the 2D editor and the
        # overlay looks broken when it is merely off-screen -- which is
        # exactly what the first run of this step did.
        tabs = viewer.parent()
        while tabs is not None and not hasattr(tabs, "setCurrentWidget"):
            tabs = tabs.parent()
        if tabs is not None:
            tabs.setCurrentWidget(viewer)
        viewer._overlay_check.setChecked(bool(step.get("on", True)))
        if "gallery" in step:
            # **AFTER the overlay, and that ordering is the whole point of
            # the key.** It puts the gallery through its FIRST render with
            # requests already in flight, so the grid is still building
            # when the answers arrive -- which is the ordinary case (a
            # ~5 ms recompute against a build that waits tens of ms) and
            # the one `loadGrid`'s replay exists for. A script that ticked
            # the gallery first and the overlay afterwards would draw via
            # the already-built path and never reach it.
            viewer._gallery_check.setChecked(bool(step["gallery"]))
        for _ in range(int(step.get("step", 0))):
            viewer._show_next_conformer()
        logger.warning(
            "OPENCHEM_DRIVE: overlay on=%s enabled=%s reports=%d gallery=%s status=%r",
            viewer._overlay_check.isChecked(),
            viewer._overlay_check.isEnabled(),
            len(viewer._spatial_reports),
            viewer._gallery_check.isChecked(),
            viewer._status_label.text(),
        )
        if viewer._gallery_check.isChecked():
            self._report_gallery_cells(viewer)

    def _report_gallery_cells(self, viewer: Any) -> None:
        """Ask the PAGE what it drew per cell, and how many grids it built.

        What Python believes it sent is exactly what was already green
        while the gallery drew nothing, so the useful number comes from
        `drawnGridShapes` -- the page's own mirror of what reached a cell.
        `gridBuilds` comes with it because a superseded build is invisible
        in a screenshot and costs a whole `createViewerGrid`.

        Asynchronous, so give the step an `after_ms` long enough for the
        answer to reach the log. A STRING, because `runJavaScript` on this
        Qt build marshals primitives only.
        """
        page = viewer._backend._page
        page.runJavaScript(
            "JSON.stringify(Object.keys(drawnGridShapes).map(function (k) {"
            " return k + ':' + (drawnGridShapes[k] || []).length; }))",
            lambda value: logger.warning("OPENCHEM_DRIVE: cells drawn %s", value),
        )
        page.runJavaScript(
            "String(gridBuilds)",
            lambda value: logger.warning("OPENCHEM_DRIVE: grid builds %s", value),
        )

    def _do_spatial(self, step: dict[str, Any]) -> None:
        """Open the spatial-result dialog for the selected molecule's dipole.

        **`show()`, not `exec()`** -- `_do_lewis` explains why a modal
        stalls an unattended run. The whole real chain runs: the actual
        calculator on the actual stored conformer, the annotation it
        declares, the real dialog, the real page drawing the arrow. This
        is the live half the renderer tests cannot cover: they drive the
        page directly, and only a run like this proves the panel's
        routing hands the dialog the same conformer the calculator saw.
        """
        from openchem.chem.dipole import compute_dipole_moment
        from openchem.chem.calculation_input import canonical_conformer
        from openchem.ui.dialogs.spatial_result_dialog import SpatialResultDialog

        window = self._window
        molecule = window._session.project.find_molecule(
            window._property_panel._selected_molecule_uuid
        )
        if molecule is None:
            logger.error("OPENCHEM_DRIVE: no molecule selected for spatial")
            return
        best = canonical_conformer(molecule)
        if best is None or not best.molblock:
            logger.error("OPENCHEM_DRIVE: no conformer to draw on; run {'do': 'conformers'} first")
            return
        mol = window._services.chemistry_engine.mol_from_molblock(best.molblock)
        report = compute_dipole_moment(mol, molecule.uuid)
        logger.warning(
            "OPENCHEM_DRIVE: dipole %s, %d spatial annotation(s)",
            report.provenance.parameters.get("debye"),
            len(report.spatial),
        )
        self._spatial = SpatialResultDialog(report, best.molblock, window)
        self._spatial.show()

    def _do_details(self, step: dict[str, Any]) -> None:
        """Open the conformer generation details dialog.

        **`show()`, not `exec()`**, for the reason `_do_lewis` gives: a
        modal spins its own event loop inside this handler and the step
        chain is never scheduled again, so an unattended run stalls on a
        window with nobody to close it.

        Built from the selected molecule's conformer exactly as the
        toolbar button builds it, so what is on screen is what a click
        gives. This is the piece no unit test reaches: the dialog's own
        tests construct it from hand-made provenance, and only a real run
        proves the keys they assume are the keys the service writes.
        """
        from openchem.ui.dialogs.conformer_details_dialog import ConformerDetailsDialog

        window = self._window
        molecule = window._session.project.find_molecule(
            window._property_panel._selected_molecule_uuid
        )
        if molecule is None or not molecule.conformers:
            logger.error("OPENCHEM_DRIVE: no conformers to describe")
            return
        conformer = molecule.conformers[0]
        parameters = (conformer.provenance.parameters if conformer.provenance else {}) or {}
        logger.warning(
            "OPENCHEM_DRIVE: funnel attempted=%s embedded=%s converged=%s distinct=%s returned=%s cap=%s (%d conformers on the model)",
            parameters.get("conformers_attempted"),
            parameters.get("conformers_embedded"),
            parameters.get("conformers_converged"),
            parameters.get("conformers_distinct"),
            parameters.get("conformers_returned"),
            parameters.get("num_conformers"),
            len(molecule.conformers),
        )
        self._details = ConformerDetailsDialog(conformer, window)
        self._details.show()

    def _do_electrons(self, step: dict[str, Any]) -> None:
        """Switch the Electron Display mode, through the real menu action.

        Through the QAction rather than past it, so what is measured is
        what a user gets -- including the status line, which is the only
        thing distinguishing "no lone pairs" from "analysis unavailable".
        """
        wanted = str(step.get("mode", "pairs"))
        for menu_action in self._window.menuBar().actions():
            menu = menu_action.menu()
            if menu is None:
                continue
            for action in _walk_actions(menu):
                if action.data() == wanted and action.isCheckable():
                    action.trigger()
                    logger.warning("OPENCHEM_DRIVE: electron display -> %s", wanted)
                    return
        logger.error("OPENCHEM_DRIVE: no electron mode %r", wanted)

    def _do_zoom(self, step: dict[str, Any]) -> None:
        """Zoom the 2D editor, through Ketcher's own working call.

        `ketcher.setZoom` looks like the API and does nothing on this
        build -- measured in tests/test_ketcher_viewport_transform.py.
        """
        self._window._editor._backend._page.runJavaScript(
            "if (window.ketcher) window.ketcher.editor.zoom(%s);" % float(step.get("to", 1.5))
        )

    def _do_cip(self, step: dict[str, Any]) -> None:
        """Show or hide the CIP stereo descriptors, through the real menu action.

        Through the QAction rather than past it, for the same reason
        `_do_electrons` does: what is measured is what a user gets. Found
        by TEXT, because this action carries no `data()` -- it is a display
        toggle rather than a proxy for a Ketcher toolbar button, which is
        the whole of the fix it exists to check.
        """
        wanted = bool(step.get("on", True))
        for menu_action in self._window.menuBar().actions():
            menu = menu_action.menu()
            if menu is None:
                continue
            for action in _walk_actions(menu):
                if action.isCheckable() and "CIP" in action.text():
                    if action.isChecked() != wanted:
                        action.trigger()
                    logger.warning("OPENCHEM_DRIVE: CIP descriptors -> %s", wanted)
                    return
        logger.error("OPENCHEM_DRIVE: no CIP display action found")

    def _do_erase(self, step: dict[str, Any]) -> None:
        """Erase every atom of one element, through Ketcher's own Delete key.

        A REAL canvas edit, which is the one route into a new structure
        that `set_molecule` never covers -- and therefore the only way to
        drive the staleness this feature fixes. Synthesised on the page
        rather than through the machine's input queue, exactly as
        `_do_rotate` is and for the same reason.
        """
        element = str(step.get("element", "N"))
        self._window._editor._backend._page.runJavaScript(
            """
            (function () {
              if (!window.ketcher) return;
              var e = window.ketcher.editor, s = e.struct(), atoms = [];
              s.atoms.forEach(function (a, id) { if (a.label === %s) atoms.push(id); });
              var bonds = Array.from(s.bonds.keys()).filter(function (b) {
                var bd = s.bonds.get(b);
                return atoms.indexOf(bd.begin) >= 0 || atoms.indexOf(bd.end) >= 0; });
              e.selection({atoms: atoms, bonds: bonds});
              var el = document.querySelector('.Ketcher-root') || document.body;
              ['keydown', 'keyup'].forEach(function (t) {
                el.dispatchEvent(new KeyboardEvent(t, {key: 'Delete', code: 'Delete',
                  bubbles: true, cancelable: true, keyCode: 46, which: 46})); });
            })();
            """
            % json.dumps(element)
        )

    def _do_editor_action(self, step: dict[str, Any]) -> None:
        """Press one of Ketcher's own toolbar buttons by its `data-testid`.

        The same route `_add_editor_action`'s menu items take, so what is
        measured is what a user gets -- including whatever the button
        makes Ketcher emit afterwards, which is the interesting part.
        """
        self._window._editor.trigger_toolbar_action(str(step["id"]))

    def _do_right_click(self, step: dict[str, Any]) -> None:
        """Right-click the canvas at a fraction of its size, for real.

        `{"do": "right_click", "fx": 0.5, "fy": 0.5}`

        **A REAL `MouseEvent`, AND THE LISTENER DOES THE HIT TEST**, which
        is the only honest way to drive this. A synthetic plain object
        will not do: Ketcher's `page2obj` answers {x: 0, y: 0} for one, so
        `findItem` reports whichever atom sits nearest the model origin --
        measured, it returned `atoms#0` at every corner and at the centre
        alike, which looks exactly like a working hit test and is not one.

        So the step dispatches an event the page treats as genuine and
        logs what PYTHON received, which is the whole contract: an atom's
        molfile position, or nothing at all when the click missed.
        """
        window = self._window
        # **THE CANVAS MUST BE VISIBLE, or `clientArea` measures 0x0** and
        # every dispatched position collapses to the top-left corner --
        # which reads as "the listener never fired" rather than as a
        # hidden widget. You cannot right-click what is not on screen.
        window._center_tabs.setCurrentWidget(window._editor)
        received: list[tuple[int, int, int]] = []
        connection = window._editor.atom_context_menu.connect(
            lambda index, x, y: received.append((index, x, y))
        )

        def report(value):
            logger.warning(
                "OPENCHEM_DRIVE: right_click %s -- python received %s", value, received
            )
            try:
                window._editor.atom_context_menu.disconnect(connection)
            except (RuntimeError, TypeError):  # pragma: no cover - already gone
                pass

        fx = float(step.get("fx", 0.5))
        fy = float(step.get("fy", 0.5))
        # **THE PAGE HAS NOT REFLOWED YET.** Revealing the tab resizes the
        # Qt widget synchronously -- it reports 1347x698 at once -- while
        # Chromium lays out on its own schedule, so `clientArea` measures
        # 0x0 if the event is dispatched in the same handler and every
        # position collapses to the corner. Same trap the conformer
        # gallery already records: wait for the size to SETTLE.
        select = int(step.get('select', -1))
        QTimer.singleShot(
            500,
            self._window,
            lambda: self._dispatch_right_click(fx, fy, report, select),
        )

    def _dispatch_right_click(self, fx: float, fy: float, report, select: int = -1) -> None:
        self._window._editor._backend._page.runJavaScript(
            """
            JSON.stringify((function () {
              var ed = window.ketcher.editor;
              var area = ed.render.clientArea, b = area.getBoundingClientRect();
              var x = b.left + %f * b.width, y = b.top + %f * b.height;
              // Optionally select a DIFFERENT atom first: the menu must
              // act on the one under the cursor, and a selection-based
              // implementation passes every other check.
              var pre = %d;
              if (pre >= 0) {
                var ids = Array.from(ed.struct().atoms.keys());
                if (ids[pre] !== undefined) { ed.selection({atoms: [ids[pre]]}); }
              }
              var before = document.querySelectorAll('.contexify').length;
              area.dispatchEvent(new MouseEvent('contextmenu', {
                bubbles: true, cancelable: true, button: 2, buttons: 2,
                clientX: x, clientY: y}));
              return {x: Math.round(x), y: Math.round(y),
                      installed: String(window.openchemContextMenuInstalled),
                      contexify_before: before,
                      contexify_after: document.querySelectorAll('.contexify').length};
            })())
            """
            % (fx, fy, select),
            report,
        )

    def _do_place(self, step: dict[str, Any]) -> None:
        """Click an element in the periodic table, then click the canvas.

        `{"do": "place", "element": "C", "isotope": 13}`
        `{"do": "place", "arm": false}`   click the canvas WITHOUT arming

        **`arm: false` is how "does the tool stay armed" is measured**,
        and it cannot be answered any other way: arming again before each
        click makes every click land whether Ketcher retained the tool or
        not, so a probe without it says yes regardless of the truth.

        **THE TWO-CLICK GESTURE, end to end and through the real widgets**
        -- the table's own cell button, then a synthesised canvas click,
        which is the only way to check that what the tool was armed with
        is what lands. Pair it with `report`, whose SMILES is where a
        missing mass number shows up as plain `C` rather than `[13C]`.
        """
        window = self._window
        if step.get("arm", True) is False:
            logger.warning("OPENCHEM_DRIVE: place -- canvas click, tool NOT re-armed")
            self._click_canvas(step)
            return
        window._show_periodic_table()
        dialog = getattr(window, "_periodic_table_dialog", None)
        if dialog is None:  # pragma: no cover - defensive
            logger.error("OPENCHEM_DRIVE: place -- no periodic table")
            return
        element = str(step.get("element", "C"))
        # **THE CELL FIRST, THEN THE ROW**, which is the user's order and
        # the only one that works: `select()` repopulates the isotope
        # table, so choosing a row and then clicking the cell wipes the
        # choice. Picking the row afterwards re-arms through
        # `_rearm_from_isotope`.
        dialog._buttons[element].click()
        mass = step.get("isotope")
        if mass is not None:
            for row in range(dialog._isotope_table.rowCount()):
                item = dialog._isotope_table.item(row, 0)
                if item is not None and item.text() == f"{element}-{mass}":
                    dialog._isotope_table.selectRow(row)
                    break
            else:
                logger.error("OPENCHEM_DRIVE: place -- no %s-%s row", element, mass)
        logger.warning(
            "OPENCHEM_DRIVE: place %s isotope=%s -- %s",
            element,
            dialog.isotope_for_placement(),
            window.statusBar().currentMessage(),
        )
        # **THE TOOL'S OWN HANDLERS, NOT A DOM EVENT.** Measured in the
        # running app: dispatching mouse OR pointer events at
        # `render.clientArea` leaves Ketcher's struct untouched, so a
        # DOM-level click reads as "the tool did nothing" while the tool
        # is armed perfectly well. `AtomTool2` exposes `mousedown` and
        # `mouseup` taking an event with `pageX`/`pageY` -- the same shape
        # `page2obj` consumes -- and calling those places the atom.
        #
        # That is Ketcher doing its own work with only the DOM plumbing
        # skipped, which is what every step in this file does with the
        # machine's input queue.
        self._click_canvas(step)

    def _click_canvas(self, step: dict[str, Any]) -> None:
        """One canvas click through whatever tool is currently armed.

        Shared by both halves of `place` so the armed and un-armed paths
        cannot drift: if they clicked differently, "the tool stayed
        armed" would be a claim about two different gestures.
        """
        fx = float(step.get("fx", 0.25))
        fy = float(step.get("fy", 0.25))

        def _report(value):
            logger.warning("OPENCHEM_DRIVE: place -- struct now %s", value)

        self._window._editor._backend._page.runJavaScript(
            """
            JSON.stringify((function () {
              var ed = window.ketcher.editor;
              var area = ed.render.clientArea, box = area.getBoundingClientRect();
              var x = box.left + box.width * %FX%, y = box.top + box.height * %FY%;
              var ev = {pageX: x, pageY: y, clientX: x, clientY: y,
                        button: 0, buttons: 1, target: area,
                        preventDefault: function () {},
                        stopPropagation: function () {}};
              var t = ed.tool();
              if (!t || !t.mousedown) { return {error: 'no armed tool'}; }
              t.mousedown(ev);
              if (t.mouseup) { t.mouseup(ev); }
              var s = ed.struct(), atoms = [];
              s.atoms.forEach(function (a, id) {
                atoms.push({id: id, label: a.label, isotope: a.isotope}); });
              return {count: s.atoms.size, tool: t.constructor.name,
                      atoms: atoms.slice(-4)};
            })())
            """.replace("%FX%", repr(fx)).replace("%FY%", repr(fy)),
            _report,
        )

    def _do_isotope(self, step: dict[str, Any]) -> None:
        """Label an atom, through the window's own handlers.

        `{"do": "isotope", "atom": 0, "mass": 13, "all": false}`

        **It goes through `_on_editor_atom_selected` and `_apply_isotope`,
        not through the dialog's internals**, because the wiring between
        the two is the thing worth driving: the picker cannot arm itself,
        so the window has to push the selection into it, and a step that
        called `set_isotope` directly would prove only that RDKit works.

        Pair it with `report`, whose `conformers=` is how "did a mass
        label throw the geometry away" is answered -- the exemption is the
        one part of this feature a screenshot cannot show.
        """
        window = self._window
        atom = int(step.get("atom", 0))
        window._on_editor_atom_selected(atom)
        symbol = window._selected_atom_element()
        if symbol is None:
            logger.error("OPENCHEM_DRIVE: isotope -- atom %d names nothing", atom)
            return
        window._apply_isotope(symbol, int(step.get("mass", 13)), bool(step.get("all", False)))
        logger.warning(
            "OPENCHEM_DRIVE: isotope %s-%s on atom %d (all=%s) -- %s",
            symbol,
            step.get("mass", 13),
            atom,
            bool(step.get("all", False)),
            window.statusBar().currentMessage(),
        )

    def _do_report(self, step: dict[str, Any]) -> None:
        """Log a few facts about the selected molecule, so a run can
        assert on state rather than on a screenshot."""
        window = self._window
        molecule = window._session.project.find_molecule(
            window._property_panel._selected_molecule_uuid
        )
        if molecule is None:
            logger.warning("OPENCHEM_DRIVE: report -- no molecule selected")
            return
        logger.warning(
            "OPENCHEM_DRIVE: report %s conformers=%d undo=%d smiles=%s",
            step.get("tag", ""),
            len(molecule.conformers),
            window._undo_stack.count(),
            molecule.canonical_smiles,
        )

    def _do_rotate(self, step: dict[str, Any]) -> None:
        """Turn the structure in the 2D editor, as a real drag.

        **SYNTHESISED ON THE PAGE, not through the machine's input
        queue** -- same reason as every other step here, and the same
        reason the rotation tests do it this way: the overlay's handlers
        are ordinary DOM listeners, so dispatching to them exercises the
        whole path (rulers, readout, the commit on mouseup) without the
        cursor moving or the window needing focus.

        `dx`/`dy` are pixels of drag, which the mode reads as half a
        degree each -- so `{"dx": 120}` is 60 degrees about the vertical
        axis. Deliberately NOT angles: a step that set the angles
        directly would skip the gesture, and the gesture is the thing
        being checked.
        """
        editor = self._window._editor
        editor._rotate_button.setChecked(True)
        dx, dy = int(step.get("dx", 120)), int(step.get("dy", 0))
        editor._backend._page.runJavaScript(
            """
            (function () {
              var o = document.querySelector('.openchem-rotate');
              if (!o) { return 'no overlay -- is the drawing flat?'; }
              function at(type, target, x, y) {
                target.dispatchEvent(new MouseEvent(
                  type, {clientX: x, clientY: y, bubbles: true}));
              }
              at('mousedown', o, 200, 200);
              at('mousemove', window, %d, %d);
              at('mouseup', window, %d, %d);
              return 'dragged';
            })();
            """
            % (200 + dx, 200 + dy, 200 + dx, 200 + dy),
            lambda result: logger.warning("OPENCHEM_DRIVE: rotate -> %s", result),
        )

    def _do_dump(self, step: dict[str, Any]) -> None:
        """Dump the Properties panel's row geometry to the log.

        The same measurement `OPENCHEM_INSTRUMENT_PANEL` produces, but at
        a moment the script chooses. That variable fires the dump from
        inside `_report_row`, which only ever catches a REPORT row -- an
        alert row could not be measured at all without either editing the
        panel or clicking through by hand.
        """
        from openchem.ui.panels import property_panel

        property_panel._dump_panel_metrics(self._window._property_panel)
        property_panel._dump_height_budget(self._window._property_panel)
        # The container walk belongs here and was missing: a starved
        # SECTION is handed its height by the container's layout, and
        # `item.minimumSize()` beside `item.hasHeightForWidth()` is the
        # only place the height-for-width substitution is visible rather
        # than inferred. Without it this step can show that a section is
        # starved but not what starved it.
        property_panel._dump_container_items(self._window._property_panel)
        property_panel._dump_width_budget(self._window._property_panel)
        # ...and the RENDERED geometry, which is a different question
        # from the one above it. `_dump_width_budget` reports
        # minimum-width PRESSURE; this reports what actually got laid
        # out past the viewport edge, which is what a reader loses
        # characters to. A widget can pass either and fail the other.
        property_panel._dump_rendered_overflow(self._window._property_panel)

    def _do_geometry(self, step: dict[str, Any]) -> None:
        """Dump the right-hand width budget, one line per quantity.

        **FOUR WIDTHS THAT MUST NOT BE CONFLATED**, which is why they are
        logged side by side rather than summarised: a panel's MINIMUM
        width, its ACTUAL width, the AVAILABLE width, and the central
        widget's minimum. A panel whose minimum is sane but whose actual
        width suddenly expands is a different bug from one whose minimum
        is intrinsically too large, and a single "too wide" number cannot
        tell them apart.

        It walks `dock -> scroll area -> content -> widest child` and
        names that child, because knowing WHICH dock is too wide without
        knowing WHAT is forcing it is not actionable.

        The window's `sizeHint`/`minimumSizeHint` are logged next to its
        actual `size`, since a widget can change what the window ASKS FOR
        without the window changing size yet -- a deferred request that
        only bites at the next maximize is exactly the shape of the
        reported "had to leave fullscreen to recover it" bug.
        """
        from PySide6.QtWidgets import QScrollArea

        window = self._window
        label = str(step.get("label", ""))
        screen = window.screen()
        available = screen.availableGeometry().width() if screen is not None else -1

        logger.warning(
            "GEOMETRY[%s] window size=%dx%d hint=%d min=%d minHint=%d "
            "maximized=%s available=%d",
            label,
            window.width(),
            window.height(),
            window.sizeHint().width(),
            window.minimumWidth(),
            window.minimumSizeHint().width(),
            window.isMaximized(),
            available,
        )

        central = window.centralWidget()
        if central is not None:
            # BOTH MINIMUMS, because they are different questions and the
            # obvious one is the wrong one. `minimumSizeHint()` is Qt's
            # RECOMMENDED minimum and is unmoved by `setMinimumWidth`, so a
            # centre with an enforced 400 px floor still reports 282 here --
            # measured, and it cost a guard that failed against correct code.
            # `minimumWidth()` is what the layout is actually held to.
            logger.warning(
                "GEOMETRY[%s]   central width=%d minHint=%d min=%d",
                label,
                central.width(),
                central.minimumSizeHint().width(),
                central.minimumWidth(),
            )
            # Follow the widest child DOWN, so the culprit is named rather
            # than merely localised to "the central widget".
            for line in self._widest_chain(central):
                logger.warning("GEOMETRY[%s]     central %s", label, line)
            # ...and every descendant over the threshold, because the
            # chain stops when no direct child explains its parent, which
            # is exactly the case where the demand comes from something
            # nested inside an intermediate container.
            floor = int(step.get("floor", 300))
            for child in central.findChildren(QWidget):
                width = child.minimumSizeHint().width()
                if width < floor:
                    continue
                text = getattr(child, "text", None)
                shown = f" text={text()[:40]!r}" if callable(text) else ""
                logger.warning(
                    "GEOMETRY[%s]     wide %s(%s) minHint=%d min=%d%s",
                    label,
                    type(child).__name__,
                    child.objectName() or "unnamed",
                    width,
                    child.minimumWidth(),
                    shown,
                )

        rail_bar = self._rail_toolbar()
        if rail_bar is not None:
            # In WINDOW coordinates, because "is the rail on screen" is a
            # question about where it sits, not about isVisible() -- which
            # is True for a rail sitting entirely past the right edge.
            top_left = rail_bar.mapTo(window, rail_bar.rect().topLeft())
            logger.warning(
                "GEOMETRY[%s]   rail width=%d minHint=%d x=%d..%d hidden=%s",
                label,
                rail_bar.width(),
                rail_bar.minimumSizeHint().width(),
                top_left.x(),
                top_left.x() + rail_bar.width(),
                rail_bar.isHidden(),
            )

        for dock in window._right_docks:
            content = dock.widget()
            logger.warning(
                "GEOMETRY[%s]   dock %-22s hidden=%-5s width=%4d minHint=%4d "
                "hint=%4d max=%d",
                label,
                dock.objectName(),
                dock.isHidden(),
                dock.width(),
                dock.minimumSizeHint().width(),
                dock.sizeHint().width(),
                dock.maximumWidth(),
            )
            if isinstance(content, QScrollArea):
                inner = content.widget()
                logger.warning(
                    "GEOMETRY[%s]     scroll minHint=%d viewport=%d "
                    "| content minHint=%s hint=%s",
                    label,
                    content.minimumSizeHint().width(),
                    content.viewport().width(),
                    inner.minimumSizeHint().width() if inner else "-",
                    inner.sizeHint().width() if inner else "-",
                )
                widest = self._widest_child(inner)
                if widest:
                    logger.warning("GEOMETRY[%s]     widest %s", label, widest)
            elif content is not None:
                logger.warning(
                    "GEOMETRY[%s]     content minHint=%d hint=%d",
                    label,
                    content.minimumSizeHint().width(),
                    content.sizeHint().width(),
                )
                widest = self._widest_child(content)
                if widest:
                    logger.warning("GEOMETRY[%s]     widest %s", label, widest)

    @classmethod
    def _widest_chain(cls, widget, depth: int = 0) -> list[str]:
        """Walk down the widest child at each level, naming the chain.

        A single "the central widget wants 1336" is not actionable -- the
        question is WHICH descendant is asking for it. Following the
        widest child answers that, and stops as soon as a level no longer
        explains its parent (within 20 px), because past that point the
        parent's own margins are the remainder rather than any child.
        """
        lines: list[str] = []
        current = widget
        while current is not None and depth < 8:
            children = [
                child
                for child in current.findChildren(QWidget)
                if child.parent() is current
            ]
            if not children:
                break
            width, widest = max(
                ((c.minimumSizeHint().width(), c) for c in children),
                key=lambda pair: pair[0],
            )
            lines.append(
                f"{'  ' * depth}-> {type(widest).__name__}"
                f"({widest.objectName() or 'unnamed'}) minHint={width} "
                f"min={widest.minimumWidth()}"
            )
            if width < current.minimumSizeHint().width() - 20:
                break
            current = widest
            depth += 1
        return lines

    @staticmethod
    def _widest_child(widget) -> str:
        """The child demanding the most width, named.

        Direct children only. Recursing would report a leaf whose parent
        already accommodates it, which names the wrong thing -- what is
        wanted is the row that sets the panel's own minimum.
        """
        if widget is None:
            return ""
        ranked = sorted(
            (
                (child.minimumSizeHint().width(), child)
                for child in widget.findChildren(QWidget)
                if child.parent() is widget
            ),
            key=lambda pair: pair[0],
            reverse=True,
        )
        return ", ".join(
            f"{type(child).__name__}({child.objectName() or 'unnamed'})={width}"
            for width, child in ranked[:3]
        )

    def _rail_toolbar(self):
        from PySide6.QtWidgets import QToolBar

        for bar in self._window.findChildren(QToolBar):
            if bar.objectName() == "Panel_Rail":
                return bar
        return None

    def _do_dialog(self, step: dict[str, Any]) -> None:
        """Open any dialog by name, for a screenshot.

        `{"do": "dialog", "name": "PeriodicTableDialog"}`, then
        `{"do": "shot", "path": "...", "widget": "dialog"}`.

        THE CONSTRUCTION IS NOT HERE. `ui/dialogs/inventory.py` knows how
        each dialog is built, and the help-contract guard walks the same
        fixtures -- so the harness and the guard cannot grow two ideas of
        what the dialogs are, which is the drift `tooltip_inventory`
        exists to prevent one layer up.

        **`show()`, never `exec()`**, for the reason `_do_lewis` gives: a
        modal spins its own event loop inside this handler and an
        unattended run stalls on a window with nobody to close it.

        A dialog the context cannot supply is LOGGED with what it needs
        rather than passed over, because "I could not build it" and "it
        has nothing to show" are different answers.
        """
        from openchem.ui.dialogs.inventory import (
            DialogContext,
            DialogUnavailable,
            iter_dialog_fixtures,
        )

        window = self._window
        wanted = str(step.get("name", ""))
        # CLEARED FIRST, and this is not tidiness. A `shot` step targets
        # `self._dialog`, so a step that fails while the previous dialog is
        # still held photographs THAT one and the run looks healthy -- the
        # same silent no-op the `panel` step's wrong-id trap produces, and
        # the reason this file says to read the shot rather than the log.
        self._dialog = None
        fixture = next((f for f in iter_dialog_fixtures() if f.name == wanted), None)
        if fixture is None:
            logger.error(
                "OPENCHEM_DRIVE: no dialog %r (have %s)",
                wanted,
                [f.name for f in iter_dialog_fixtures()],
            )
            return

        molecule = window._current_molecule()
        context = DialogContext(
            services=window._services,
            settings=window._settings,
            molecule=molecule,
            project=window._session.project,
            conformer_molblock=(
                molecule.conformers[0].molblock
                if molecule is not None and molecule.conformers
                else None
            ),
        )
        try:
            dialog = fixture.build(context)
        except DialogUnavailable as exc:
            logger.error(
                "OPENCHEM_DRIVE: %s needs %s -- %s", wanted, fixture.needs or "?", exc
            )
            return

        dialog.setParent(window)
        dialog.setWindowFlag(Qt.WindowType.Dialog, True)
        if "width" in step:
            dialog.resize(int(step["width"]), int(step.get("height", dialog.height())))
        dialog.show()
        self._dialog = dialog
        # `"tab": "Isotopes"` -- half these dialogs are tabbed, and a shot
        # of the default page cannot show what is on the other three. The
        # tab is named rather than indexed, and a name that matches
        # nothing is LOGGED: an unrecognised index would silently
        # photograph page 0, which is the wrong-panel-id trap again.
        wanted_tab = str(step.get("tab", ""))
        if wanted_tab:
            from PySide6.QtWidgets import QTabWidget

            tabs = dialog.findChild(QTabWidget)
            titles = [tabs.tabText(i) for i in range(tabs.count())] if tabs else []
            if wanted_tab in titles:
                tabs.setCurrentIndex(titles.index(wanted_tab))
            else:
                logger.error(
                    "OPENCHEM_DRIVE: %s has no tab %r (have %s)",
                    wanted, wanted_tab, titles,
                )
        logger.warning(
            "OPENCHEM_DRIVE: dialog %s open at %dx%d, tab %r",
            wanted,
            dialog.width(),
            dialog.height(),
            wanted_tab or "(default)",
        )

    def _do_rail(self, step: dict[str, Any]) -> None:
        """Fold or unfold the panel rail's name list.

        `{"do": "rail", "collapsed": true}`

        The rail costs 270 px expanded and 34 collapsed, so the two are
        different geometry regimes rather than a cosmetic preference --
        and `geometry` cannot report the collapsed one without a way to
        reach it. Driven through `PanelRail.set_list_visible`, which is
        the same call the second-click gesture makes, so a script
        measures the state a user can actually get to.
        """
        rail = self._window._panel_rail
        rail.set_list_visible(not bool(step.get("collapsed", True)))
        logger.warning(
            "OPENCHEM_DRIVE: rail list visible=%s", rail.is_list_visible()
        )

    def _do_resize(self, step: dict[str, Any]) -> None:
        """Resize or maximize the window, so a script can walk the path
        the bug was reported on rather than only its endpoints."""
        window = self._window
        if step.get("maximized") is True:
            window.showMaximized()
        elif step.get("maximized") is False:
            window.showNormal()
        if "width" in step:
            window.resize(int(step["width"]), int(step.get("height", window.height())))

    def _do_tab(self, step: dict[str, Any]) -> None:
        """Switch the CENTRE tab by its label ("3D Viewer", "2D Editor")."""
        tabs = self._window._center_tabs
        wanted = str(step["name"])
        for index in range(tabs.count()):
            if tabs.tabText(index) == wanted:
                tabs.setCurrentIndex(index)
                return
        logger.error(
            "OPENCHEM_DRIVE: no centre tab %r (have %s)",
            wanted,
            [tabs.tabText(i) for i in range(tabs.count())],
        )

    def _do_wait(self, step: dict[str, Any]) -> None:
        """Nothing; the pause is `after_ms`. Present so a script can say
        it is waiting rather than hiding it in the previous step."""

    def _do_quit(self, step: dict[str, Any]) -> None:
        """Leave without going through `closeEvent`.

        **A SCRIPTED RUN HANGS ON AN "Unsaved changes" MODAL, and dropping
        `window.close()` is NOT enough to avoid it.** `MainWindow.closeEvent`
        asks a visible window's user whether to discard, and any script
        that imported something is dirty. Measured twice, with the process
        left alive and that dialog up both times:

            close() then quit()   modal, blocked
            quit() alone          modal, blocked  <- quit() closes windows

        The second is the surprise: in Qt 6 `quit()` closes all windows
        itself, so removing the explicit `close()` changed nothing.
        `exit(0)` leaves the event loop without closing anything, and the
        session is marked clean as well so no other shutdown path can
        raise the same box.

        Bypassing `closeEvent` also means a diagnostic run does NOT
        overwrite the geometry and dock layout the user has saved -- worth
        having from something run twenty times in an afternoon, since
        `panel` steps change which dock is visible and that is part of
        `saveState`.

        The undo stack is emptied by hand because `closeEvent` is no
        longer doing it, and destroying a `MainWindow` whose stack still
        holds commands faults -- bisected, and recorded in CLAUDE.md.
        """
        from PySide6.QtWidgets import QApplication

        logger.warning("OPENCHEM_DRIVE: quitting")
        # Nothing is worth saving from a scripted run, and a dirty session
        # is what raises the modal.
        self._window._session.mark_clean()
        self._window._undo_stack.clear()
        QApplication.instance().exit(0)
