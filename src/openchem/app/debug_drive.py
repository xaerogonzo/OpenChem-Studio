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
      {"do": "panel",      "id": "Properties"},
      {"do": "expand",     "section": "admet"},
      {"do": "calculator", "id": "admet_ml", "parameters": {"tier": "basic"},
                           "after_ms": 45000},
      {"do": "shot",       "path": "C:/tmp/admet.png"},
      {"do": "rotate",     "dx": 120, "dy": -40},
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

from PySide6.QtCore import QTimer
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


class _Driver:
    """Runs the steps one at a time, off a `QTimer`.

    Sequential rather than concurrent because the interesting steps are
    asynchronous -- a calculator dispatches to a thread pool -- and the
    thing being measured is what the window looks like AFTER one has
    landed.
    """

    def __init__(self, window: QWidget, steps: list[dict[str, Any]]) -> None:
        self._window = window
        self._steps = steps
        self._index = 0

    def start(self) -> None:
        logger.warning("OPENCHEM_DRIVE: %d step(s) from %s", len(self._steps), _DRIVE_SCRIPT)
        QTimer.singleShot(_DEFAULT_AFTER_MS, self._run_next)

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
        QTimer.singleShot(after, self._run_next)

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
        self._window.grab().save(str(path))
        logger.warning("OPENCHEM_DRIVE: wrote %s", path)

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
        )

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

    def _do_editor_action(self, step: dict[str, Any]) -> None:
        """Press one of Ketcher's own toolbar buttons by its `data-testid`.

        The same route `_add_editor_action`'s menu items take, so what is
        measured is what a user gets -- including whatever the button
        makes Ketcher emit afterwards, which is the interesting part.
        """
        self._window._editor.trigger_toolbar_action(str(step["id"]))

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
        property_panel._dump_width_budget(self._window._property_panel)

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
