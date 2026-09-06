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
      {"do": "scroll",     "to": "bottom"},
      {"do": "geometry",   "label": "maximized/Quantum"},
      {"do": "open_project",     "path": "C:/tmp/MPMI.ocsproj"},
      {"do": "batch_select",     "category": "Identity"},
      {"do": "batch_select_all", "filter": "logp"},
      {"do": "batch_fill"},
      {"do": "batch_details",    "molecule": "MPMI"},
      {"do": "batch_report",     "tag": "after"},
      {"do": "align",            "reference": "MPMI", "probes": ["4-HO-MPMI"],
                                 "method": "Common scaffold (MCS)",
                                 "flexibility": "Flexible"},
      {"do": "align_report",     "tag": "after"},
      {"do": "ensemble_visible", "row": 1, "on": false},
      {"do": "overlay_colour",   "mode": "element"},
      {"do": "visual_check",     "surface": "properties", "tag": "at-minimum"},
      {"do": "screen_run",       "receptor": 0}   the REAL Run button
      {"do": "screen_run",       "receptor": 0, "exhaustiveness": 32,
                                 "scoring_function": "vinardo", "seed": 4712},
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

    def _do_dock_run(self, step: dict[str, Any]) -> None:
        """Press the Docking panel's Dock button, for real.

        `{"do": "dock_run", "after_ms": 300000, "replicates": 3}`

        `replicates` SETS THE SPIN BOX and then presses Dock, rather than
        passing a count to the handler. The panel reads the control through
        `displayed_replicates()`, so driving the control is what checks that
        wiring -- handing the number to `request_docking` directly would prove
        the service loops and say nothing about whether the box reaches it.
        Omit it and the panel's own default (1) runs, which is what almost
        every user gets.

        THE BUTTON, NOT `_on_dock_clicked` -- the same reason `jobs_cancel`
        presses a real row's button. The handler reads the panel's current
        selection and enabled state, so calling it directly proves the
        handler works and says nothing about whether the control is wired,
        which is the half a screenshot is being taken to check.

        Docking is ASYNCHRONOUS and runs a real Vina. Give the step an
        `after_ms` long enough for the result to come back, or the next step
        photographs a viewer that has not been handed a pose yet -- which
        looks exactly like the pose failing to draw.

        A DISABLED BUTTON IS LOGGED RATHER THAN CLICKED. Qt silently ignores
        a click on a disabled control, so without this the run would report
        a healthy `dock_run` step and simply never dock -- the wrong-panel-id
        trap in another costume.
        """
        panel = getattr(self._window, "_docking_panel", None)
        if panel is None:
            logger.error("OPENCHEM_DRIVE: no docking panel on this window")
            return
        replicates = step.get("replicates")
        if replicates is not None:
            panel._replicates_spin.setValue(int(replicates))
            logger.warning(
                "OPENCHEM_DRIVE: dock_run -- replicates set to %d (panel reads %d)",
                int(replicates),
                panel.displayed_replicates(),
            )
        # SETS THE COMBO, for the same reason `replicates` sets the spin box:
        # the panel reads it through `displayed_search_options()`, so driving
        # the control is what checks that wiring. Handing "vinardo" to the
        # provider directly would prove the rescorer runs and say nothing
        # about whether the combo reaches it.
        rescore = step.get("rescore")
        if rescore is not None:
            index = panel._rescore_combo.findData(rescore)
            if index < 0:
                logger.error(
                    "OPENCHEM_DRIVE: dock_run -- no rescore option %r; the run "
                    "will use whatever the combo already shows",
                    rescore,
                )
            else:
                panel._rescore_combo.setCurrentIndex(index)
            logger.warning(
                "OPENCHEM_DRIVE: dock_run -- rescore set to %r (panel sends %r)",
                rescore,
                panel.displayed_search_options().get("rescore_with"),
            )

        button = panel._dock_button
        if not button.isEnabled():
            logger.error(
                "OPENCHEM_DRIVE: dock_run -- the Dock button is DISABLED "
                "(receptor=%r, no docking started)",
                panel._receptor_combo.currentText(),
            )
            return
        logger.warning(
            "OPENCHEM_DRIVE: dock_run -> pressing Dock (receptor=%r)",
            panel._receptor_combo.currentText(),
        )
        button.click()

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
        # THE SPREAD LABEL CARRIES A FLAG NO SCREENSHOT CAN, which is why it
        # is logged beside a `shot` rather than instead of one: `hidden` is
        # what tells "no result yet" from "a result with nothing to say", and
        # an empty label and a hidden one photograph identically.
        logger.warning(
            "OPENCHEM_DRIVE: dock_panel[%s] replicates=%d spread_hidden=%s spread=%r",
            step.get("tag", ""),
            panel.displayed_replicates(),
            panel._spread_label.isHidden(),
            panel._spread_label.text(),
        )
        # THE RESCORE COLUMN, FOR THE SAME REASON AS THE SPREAD LABEL. Four
        # states have to stay distinguishable and a screenshot separates only
        # two of them: "not requested" and "requested, and every pose failed"
        # both photograph as a table with no numbers in that column, while
        # "hidden" and "shown but empty" are indistinguishable outright. The
        # stored PoseScore is what tells them apart.
        from openchem.domain.docking import pose_score_of
        from openchem.ui.panels.docking_panel import _POSE_COLUMNS, _RESCORE_COLUMN

        column = _POSE_COLUMNS.index(_RESCORE_COLUMN)
        header = panel._table.horizontalHeaderItem(column)
        logger.warning(
            "OPENCHEM_DRIVE: dock_panel[%s] rescore_hidden=%s header=%r note_hidden=%s "
            "cells=%r",
            step.get("tag", ""),
            panel._table.isColumnHidden(column),
            header.text() if header is not None else None,
            panel._rescore_label.isHidden(),
            [
                panel._table.item(row, column).text()
                if panel._table.item(row, column) is not None
                else None
                for row in range(panel._table.rowCount())
            ],
        )
        result = getattr(panel, "_displayed_result", None)
        if result is not None:
            for index, pose in enumerate(result.poses):
                score = pose_score_of(pose)
                logger.warning(
                    "OPENCHEM_DRIVE: dock_panel[%s] pose %d affinity=%s rescore=%s",
                    step.get("tag", ""), index, pose.binding_affinity_kcal_mol,
                    None if score is None else
                    f"{score.function}/{score.protocol}={score.value}"
                    f" inapplicable={score.inapplicable} err={score.error_summary!r}",
                )

        # The search settings CARRY WHAT NO SCREENSHOT CAN: a seed of 0 reads
        # "Random" on screen and must leave the panel as None, and the
        # exhaustiveness shown is only interesting if it is also what is sent.
        # Same argument as `jobs_report` logging QTimer.isActive().
        logger.warning(
            "OPENCHEM_DRIVE: dock_panel[%s] ph=%.2f search=%r seed_shows=%r",
            step.get("tag", ""),
            panel._ph_spin.value(),
            panel.displayed_search_options(),
            panel._seed_spin.text(),
        )

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
        if "flexibility" in step:
            panel._flexibility_combo.setCurrentText(str(step["flexibility"]))
        logger.warning(
            "OPENCHEM_DRIVE: aligning %d probe(s) onto %r, method=%s accuracy=%s flexibility=%s",
            len(panel._checked_uuids()),
            panel._reference_combo.currentText(),
            panel._method_combo.currentText(),
            panel._accuracy_combo.currentText(),
            panel._flexibility_combo.currentText(),
        )
        panel._on_align_clicked()

    def _do_align_report(self, step: dict[str, Any]) -> None:
        """Dump what the alignment table SHOWS, cell by cell.

        `{"do": "align_report", "tag": "flexible"}`

        The panel's own numbers rather than the code's: this exists because
        the reported defect was a table that looked healthy -- score 109.75,
        RMSD 0.116 -- beside a picture that was wrong. Reading Core and Tail
        off the rendered cells is the cheap half of checking that the two
        now agree; the shot is the other half.
        """
        panel = self._window._alignment_panel
        table = panel._result_table
        tag = step.get("tag", "")
        headers = [
            table.horizontalHeaderItem(c).text() for c in range(table.columnCount())
        ]
        view = panel._viewer.widget()
        # EVERY DIRECT CHILD, not a summary: this panel's whole problem is
        # that fixed-height siblings leave the overlay a strip, and "the
        # viewer is 63 px" does not say which sibling to argue with.
        parts = []
        layout = panel.layout()
        for i in range(layout.count()):
            w = layout.itemAt(i).widget()
            if w is not None:
                parts.append(f"{type(w).__name__}={w.height()}")
        logger.warning(
            "OPENCHEM_DRIVE: align_report %s | panel %d | viewer %dx%d | %s",
            tag, panel.height(), view.width(), view.height(), " ".join(parts),
        )
        logger.warning("OPENCHEM_DRIVE: align_report %s | %s", tag, " | ".join(headers))
        for row in range(table.rowCount()):
            cells = []
            for column in range(table.columnCount()):
                item = table.item(row, column)
                if item is None:
                    cells.append("")
                elif column == 0:
                    cells.append(
                        "on" if item.checkState() == Qt.CheckState.Checked else "off"
                    )
                else:
                    cells.append(item.text())
            logger.warning("OPENCHEM_DRIVE: align_report %s | %s", tag, " | ".join(cells))

    def _do_ensemble_visible(self, step: dict[str, Any]) -> None:
        """Tick or untick one row's visibility box.

        `{"do": "ensemble_visible", "row": 1, "on": false}` -- driven
        through the box rather than through `_show_ensemble`, because the
        thing worth checking is the WIRING and a helper called directly
        proves only that the helper works.
        """
        panel = self._window._alignment_panel
        row = int(step.get("row", 0))
        item = panel._result_table.item(row, 0)
        if item is None:
            logger.error("OPENCHEM_DRIVE: no visibility box on row %d", row)
            return
        item.setCheckState(
            Qt.CheckState.Checked if step.get("on", True) else Qt.CheckState.Unchecked
        )
        logger.warning(
            "OPENCHEM_DRIVE: row %d visible=%s", row, bool(step.get("on", True))
        )

    def _do_overlay_colour(self, step: dict[str, Any]) -> None:
        """`{"do": "overlay_colour", "mode": "element"}` -- by molecule or
        by element. Driven through the combo, for the reason above."""
        panel = self._window._alignment_panel
        mode = str(step.get("mode", "molecule"))
        index = panel._color_mode_combo.findData(mode)
        if index < 0:
            logger.error("OPENCHEM_DRIVE: no overlay colour mode %r", mode)
            return
        panel._color_mode_combo.setCurrentIndex(index)
        logger.warning("OPENCHEM_DRIVE: overlay colour mode %s", mode)

    def _do_batch_select(self, step: dict[str, Any]) -> None:
        """Tick a property, or a whole category, in the Batch picker.

        `{"do": "batch_select", "property": "topology_analysis"}`
        `{"do": "batch_select", "category": "Identity"}`

        The category form goes through the GROUP'S OWN CHECK BOX rather
        than ticking each leaf, because the thing worth exercising is the
        propagation -- setting the leaves directly would drive a path the
        user never takes.
        """
        panel = self._window._batch_panel
        if "property" in step:
            panel.check(str(step["property"]))
            logger.warning("OPENCHEM_DRIVE: ticked %s", step["property"])
            return
        from openchem.ui.panels.batch_panel import _GROUP_NAME_ROLE

        wanted = str(step.get("category", ""))
        stack = [panel._tree.topLevelItem(i) for i in range(panel._tree.topLevelItemCount())]
        while stack:
            item = stack.pop()
            # The NAME, not the rendering -- a group row reads
            # "Identity  0 / 2" once it carries its count.
            if item.data(0, _GROUP_NAME_ROLE) == wanted or item.text(0) == wanted:
                item.setCheckState(0, Qt.CheckState.Checked)
                descriptors, calculators = panel.selected_ids()
                logger.warning(
                    "OPENCHEM_DRIVE: ticked category %r -> %d descriptor(s), %d calculator(s)",
                    wanted, len(descriptors), len(calculators),
                )
                return
            stack.extend(item.child(i) for i in range(item.childCount()))
        logger.error("OPENCHEM_DRIVE: no category %r in the picker", wanted)

    def _do_batch_select_all(self, step: dict[str, Any]) -> None:
        """`{"do": "batch_select_all", "filter": "logp"}` -- the filter is
        applied FIRST, so this also exercises "select all respects it"."""
        panel = self._window._batch_panel
        if "filter" in step:
            panel._filter.setText(str(step["filter"]))
        panel._select_all_visible()
        logger.warning("OPENCHEM_DRIVE: %s", panel._status.text())

    def _do_batch_fill(self, step: dict[str, Any]) -> None:
        """Fill the whole table.

        **THE CONFIRMATION IS SUPPRESSED, NOT ANSWERED.** A modal
        `QMessageBox` inside a step spins its own event loop, so the next
        step is never scheduled and an unattended run stalls on a window
        with nobody to close it -- the same trap this file already records
        for `exec()` one row down. The threshold is raised for the run
        instead, which leaves the code path itself untouched.
        """
        from openchem.ui.panels import batch_panel as module

        panel = self._window._batch_panel
        original = module._CONFIRM_ABOVE
        module._CONFIRM_ABOVE = 1 << 30
        try:
            panel._run()
        finally:
            module._CONFIRM_ABOVE = original
        logger.warning("OPENCHEM_DRIVE: fill started -- %s", panel._status.text())

    def _do_batch_details(self, step: dict[str, Any]) -> None:
        """Open one molecule's detail view.

        `{"do": "batch_details", "row": 0}` -- by ROW of the results
        table, or `{"do": "batch_details", "molecule": "MPMI"}` by name,
        which is what to use before any table exists.

        The dialog is modal, so it is SHOWN rather than `exec`'d, for the
        reason the `lewis` step already documents: `exec()` spins its own
        event loop inside the handler and the run never continues.
        """
        from openchem.ui.panels.batch_panel import _UUID_ROLE

        panel = self._window._batch_panel
        uuid = None
        if "molecule" in step and panel._project is not None:
            wanted = str(step["molecule"])
            uuid = next(
                (m.uuid for m in panel._project.molecules if m.display_name == wanted), None
            )
            if uuid is None:
                logger.error("OPENCHEM_DRIVE: no molecule %r", wanted)
                return
        else:
            row = int(step.get("row", 0))
            item = panel._results.item(row, 0)
            if item is None:
                logger.error("OPENCHEM_DRIVE: no row %d in the results table", row)
                return
            uuid = item.data(_UUID_ROLE)
        self._batch_dialog = None
        original = type(panel)._present_details

        def capture(panel_self, molecule_uuid):
            from openchem.ui.dialogs.batch_detail_dialog import BatchDetailDialog

            type(panel_self)._present_details = original

            molecule = panel_self._project.find_molecule(molecule_uuid)
            dialog = BatchDetailDialog(
                panel_self._engine,
                molecule,
                panel_self._store,
                panel_self._current_structure_version(),
                panel_self,
            )
            dialog.show()
            self._batch_dialog = dialog
            self._dialog = dialog
            logger.warning(
                "OPENCHEM_DRIVE: details for %s -- %d retained result(s)",
                molecule.display_name,
                len(panel_self._store.for_molecule(
                    molecule_uuid, panel_self._current_structure_version()
                )) if panel_self._store else 0,
            )

        # **RESTORED BY THE CAPTURE, NOT IN A `finally`.** `_show_details`
        # starts a background run and RETURNS; `_present_details` is called
        # later, from the progress handler, once the results land. A
        # `finally` here puts the original back before that happens, so the
        # dialog is built by the real method, never captured, and the shot
        # step reports "no dialog open" for a step that worked perfectly.
        type(panel)._present_details = capture
        panel._show_details(uuid)

    def _do_batch_report(self, step: dict[str, Any]) -> None:
        """Dump what the Batch panel SHOWS -- picker counts and cells.

        The panel's own numbers rather than the code's, for the reason
        `align_report` exists: the reported defect was a table that looked
        healthy beside a view that was not.
        """
        panel = self._window._batch_panel
        tag = step.get("tag", "")
        descriptors, calculators = panel.selected_ids()
        logger.warning(
            "OPENCHEM_DRIVE: batch_report %s | ticked %d descriptor(s) %d calculator(s) "
            "| rows %d cols %d | store %d",
            tag, len(descriptors), len(calculators),
            panel._results.rowCount(), panel._results.columnCount(),
            len(panel._store) if panel._store else 0,
        )
        for row in range(min(panel._results.rowCount(), 4)):
            cells = []
            for column in range(min(panel._results.columnCount(), 8)):
                item = panel._results.item(row, column)
                cells.append("" if item is None else item.text())
            logger.warning("OPENCHEM_DRIVE: batch_report %s | %s", tag, " | ".join(cells))

    def _do_open_project(self, step: dict[str, Any]) -> None:
        """Load an .ocsproj without the file dialog.

        `{"do": "open_project", "path": "D:/.../MPMI.ocsproj"}`

        Goes through `OpenProjectCommand` and `_set_project`, the same two
        the File menu uses -- only the dialog is skipped, which is the rule
        every step in this file follows.
        """
        from pathlib import Path as _Path

        from openchem.commands.project_commands import OpenProjectCommand

        path = _Path(str(step.get("path", "")))
        if not path.is_file():
            logger.error("OPENCHEM_DRIVE: no project at %s", path)
            return
        command = OpenProjectCommand(self._window._services.project_service, path)
        self._window._undo_stack.push(command)
        if command.loaded_project is None:
            logger.error("OPENCHEM_DRIVE: could not load %s", path)
            return
        self._window._set_project(command.loaded_project)
        logger.warning(
            "OPENCHEM_DRIVE: opened %s -- %d molecule(s)",
            path.name,
            len(command.loaded_project.molecules),
        )

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

    def _do_inspect(self, step: dict[str, Any]) -> None:
        """Open the Calculator Inspector on a per-atom calculator's result.

        `{"do": "inspect", "id": "gasteiger_charge_at_ph"}`, then
        `{"do": "shot", "widget": "inspector"}`.

        **`show()`, NEVER `exec()`.** The panel's own `_open_inspector`
        ends in `exec()`, which spins an event loop inside the handler --
        the next step is never scheduled and an unattended run stalls on a
        window with nobody to close it. Same trap `lewis` documents.

        WHAT THIS DOES AND DOES NOT DRIVE, stated because it matters:
        it builds the real dialog from a real computed result, so what is
        photographed is the dialog as a user sees it. It does NOT go
        through the panel's reveal-and-click path, which is unchanged and
        covered by `tests/test_property_panel.py`.
        """
        from openchem.ui.dialogs.calculator_inspector_dialog import (
            CalculatorInspectorDialog,
        )
        from openchem.chem.calculation_input import canonical_conformer

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
        parameters = {p.name: p.default for p in definition.parameters}
        parameters.update(step.get("parameters") or {})
        mol = window._services.chemistry_engine.mol_from_model(molecule)
        result = definition.execution.compute(mol, molecule.uuid, parameters)
        best = canonical_conformer(molecule)
        self._inspector = CalculatorInspectorDialog(
            window._services.chemistry_engine,
            molecule,
            result,
            best.molblock if best is not None else None,
            window,
        )
        self._inspector.show()
        logger.warning(
            "OPENCHEM_DRIVE: inspect %s -> %r", calculator_id, getattr(result, "name", "")
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
        elif step.get("widget") == "inspector":
            if getattr(self, "_inspector", None) is None:
                logger.error("OPENCHEM_DRIVE: no inspector open; run {'do': 'inspect', ...}")
                return
            target = self._inspector
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

    def _do_screen_run(self, step: dict[str, Any]) -> None:
        """Press the real Run button on the open screening dialog, then dump
        what the REAL service was handed.

        `{"do": "dialog", "name": "VirtualScreeningDialog"}` then
        `{"do": "screen_run", "receptor": 0}`

        **THE PREP DICT IS THE HALF NO SCREENSHOT CAN CARRY**, which is why
        this exists beside a `shot` rather than instead of one. A screen that
        leaves the co-crystallised ligand sitting in the pocket it defined
        looks exactly like a screen that removes it -- same table, same
        progress bar, scores 4 kcal/mol out and a ranking that can invert.
        `is_stripped_residue` measured that; nothing on screen shows it.

        Read off `ScreeningService`'s own attributes AFTER the button press,
        so it is what the service received rather than what the dialog
        believes it sent. Those are set synchronously by `request_screen`, so
        no wait is needed for this line even though the docking that follows
        takes minutes.

        **THE BUTTON, not `_start`.** A disabled Run button is logged rather
        than clicked, for the reason `dock_run` gives: Qt silently ignores a
        click on a disabled control, so without that check the run reports a
        healthy step and screens nothing.
        """
        dialog = self._dialog
        if dialog is None or not hasattr(dialog, "_run"):
            logger.error(
                "OPENCHEM_DRIVE: screen_run -- no screening dialog is open; "
                "run {'do': 'dialog', 'name': 'VirtualScreeningDialog'} first"
            )
            return
        index = step.get("receptor")
        if index is not None and dialog._receptor.count():
            dialog._receptor.setCurrentIndex(int(index) % dialog._receptor.count())
        receptor_name = dialog._receptor.currentText()
        # THE FOUR SEARCH CONTROLS, driven through the widgets rather than
        # around them. Setting `service._search_options` directly would prove
        # the service works and say nothing about whether the dialog reads
        # its own combos -- which is the exact defect a mutation found here,
        # surviving every test until a guard drove the real controls.
        #
        # A value that matches nothing is LOGGED rather than ignored, because
        # a silently-unset combo photographs identically to a correctly-set
        # one and the run would report a healthy step against the defaults.
        for key, widget in (
            ("exhaustiveness", dialog._search.exhaustiveness),
            ("scoring_function", dialog._search.scoring_function),
            ("rescore_with", dialog._search.rescore_with),
        ):
            if key not in step:
                continue
            found = widget.findData(step[key])
            if found < 0:
                logger.error(
                    "OPENCHEM_DRIVE: screen_run -- %s=%r matches no item; leaving it alone",
                    key, step[key],
                )
                continue
            widget.setCurrentIndex(found)
        if "seed" in step:
            dialog._search.seed.setValue(int(step["seed"]))
        if not dialog._run.isEnabled():
            logger.error("OPENCHEM_DRIVE: screen_run -- the Run button is DISABLED; not clicked")
            return
        dialog._run.click()

        service = self._window._services.screening_service
        logger.warning(
            "OPENCHEM_DRIVE: screen_run receptor=%r queued=%d poses=%s replicates=%s "
            "prep=%r box=%s",
            receptor_name,
            service._total,
            service._num_poses,
            service._replicates,
            service._prep_options,
            None if service._box is None else service._box.center,
        )
        # WHAT THE SERVICE RECEIVED, not what the dialog believes it sent --
        # the same distinction the prep dict above is read for. And the
        # PROTOCOL beside it, because `resolved` is a flag no screenshot can
        # carry: a protocol showing the requested settings and one showing
        # what actually ran render identically until a result lands.
        protocol = service._protocol
        logger.warning(
            "OPENCHEM_DRIVE: screen_run search=%r protocol_resolved=%s "
            "requested_exhaustiveness=%r requested_scoring=%r rescore=%r seed=%r",
            service._search_options,
            None if protocol is None else protocol.resolved,
            None if protocol is None else protocol.requested_exhaustiveness,
            None if protocol is None else protocol.requested_scoring_function,
            None if protocol is None else protocol.rescore_with,
            None if protocol is None else protocol.protocol_seed,
        )
        logger.warning("OPENCHEM_DRIVE: screen_run status=%r", dialog._status.text())

    def _do_jobs_report(self, step: dict[str, Any]) -> None:
        """Dump what the Jobs panel SHOWS, plus whether it is still polling.

        `{"do": "jobs_report", "tag": "running"}`

        The polling state is the half no screenshot can carry, and it is the
        half this panel's bugs live in: a panel that leaked itself kept
        refreshing for the life of the process, and a visibility gate that
        never restarts the timer leaves a frozen list that looks exactly
        like an idle one. Both are `isActive()` and neither is visible.
        """
        window = self._window
        panel = window._jobs_panel
        dock = window._dock_by_panel_id("Jobs")
        tag = step.get("tag", "")
        table = panel._table
        rows = [
            " / ".join(
                (table.item(r, c).text() if table.item(r, c) is not None else "-")
                for c in range(3)
            )
            + (
                "  [Cancel enabled]"
                if getattr(table.cellWidget(r, 3), "isEnabled", lambda: False)()
                else "  [Cancel disabled]"
            )
            for r in range(table.rowCount())
        ]
        logger.warning(
            "OPENCHEM_DRIVE: jobs_report %s | dock visible=%s | panel visible=%s | "
            "polling=%s | rows=%d",
            tag,
            dock is not None and dock.isVisible(),
            panel.isVisible(),
            panel._timer.isActive(),
            table.rowCount(),
        )
        for row in rows:
            logger.warning("OPENCHEM_DRIVE: jobs_report %s | %s", tag, row)

    def _do_jobs_cancel(self, step: dict[str, Any]) -> None:
        """Press the real Cancel button in a row of the real table.

        `{"do": "jobs_cancel", "row": 0}`

        THE CONTROL, not the helper behind it. `JobsPanel._on_cancel_clicked`
        now reads which job it means off `sender()`, so calling it directly
        would pass `sender() is None` and prove nothing about the button
        being wired, which is exactly the thing that changed.
        """
        row = int(step.get("row", 0))
        button = self._window._jobs_panel._table.cellWidget(row, 3)
        if button is None:
            logger.error("OPENCHEM_DRIVE: jobs_cancel -- no button in row %d", row)
            return
        logger.warning(
            "OPENCHEM_DRIVE: jobs_cancel row %d (enabled=%s)", row, button.isEnabled()
        )
        button.click()

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

    def _do_visual_check(self, step: dict[str, Any]) -> None:
        """Run the geometric oracle against one surface and log its findings.

        `{"do": "visual_check", "surface": "properties", "tag": "at-minimum"}`

        **THIS IS THE HALF A SCREENSHOT CANNOT BE.** A crop shows a reader
        that something is wrong; this says WHICH widget and by how many
        pixels, in a line a diff can compare. It pairs with `shot` and never
        replaces it -- the same relationship `jobs_report` has, where the
        flag it carries is invisible to any picture.

        **A SCROLLING SURFACE IS JUDGED AGAINST ITS VIEWPORT**, never against
        its own content rectangle. Content legitimately extends past a
        viewport -- that is what scrolling IS -- so judging the content
        widget against itself would report nothing forever, which is the
        failure mode `horizontalScrollBar().maximum() == 0` already has.

        Surfaces: `properties` (the panel, against its scroll viewport),
        `window`, and any dialog `shot` can already reach -- `dialog`,
        `lewis`, `periodic`, `details`, `spatial`, `popout`.

        **A SURFACE WITH NO SINGLE SCROLL AREA IS JUDGED AGAINST ITS OWN
        RECTANGLE, WHICH MAKES THE OVERFLOW TERM NEARLY VACUOUS THERE** --
        a child is inside its parent by construction unless something
        positioned it outside. Said out loud rather than left to be
        discovered: on such a surface the useful predicates are the other
        three, and a clean overflow result is close to a tautology.
        """
        from PySide6.QtWidgets import QScrollArea

        from openchem.ui import visual_check

        name = str(step.get("surface", "properties"))
        tag = str(step.get("tag", name))
        root = self._surface(name)
        if root is None:
            return

        bounds = None
        areas = root.findChildren(QScrollArea)
        if len(areas) == 1:
            root = areas[0].viewport()
            bounds = root.rect()

        # `"tolerance": -1000` is how a run CONFIRMS THE ORACLE CAN STILL SAY
        # NO. Every surface in this application is clean today, and Qt clamps
        # a resize to each widget's own minimum, so no script can squeeze a
        # real panel into a real finding -- which leaves "0 findings" and
        # "the wiring is dead" indistinguishable from the log. Lowering the
        # tolerance makes every measured item report, which proves the
        # geometry reached the predicates and the findings reached the log.
        tolerance = int(step.get("tolerance", visual_check.DEFAULT_TOLERANCE))
        items = visual_check.painted_items(root, root)
        findings = visual_check.check_surface(root, bounds, root, tolerance)
        # THE POPULATION IS LOGGED EVEN WHEN NOTHING IS WRONG. "Nothing
        # overflowed" and "the walk found nothing to measure" are opposite
        # outcomes that read identically in an empty findings list, and the
        # second is how an over-broad exclusion reads as a clean run.
        logger.warning(
            "OPENCHEM_DRIVE: visual_check %s [%s] -- %d painted item(s), %d finding(s)",
            tag,
            name,
            len(items),
            len(findings),
        )
        for finding in findings:
            logger.warning("OPENCHEM_DRIVE:     %s", finding.describe())

    def _surface(self, name: str):
        """Resolve a surface name to a widget, or log why it could not be.

        A name that matches nothing is LOGGED rather than ignored. A silent
        no-op here would photograph the wrong thing while the log looked
        perfectly healthy, which is the wrong-panel-id trap this harness has
        already been caught by once.
        """
        if name == "properties":
            return self._window._property_panel
        if name == "window":
            return self._window
        attr = {
            "dialog": "_dialog",
            "lewis": "_lewis",
            "periodic": "_periodic",
            "details": "_details",
            "spatial": "_spatial",
            "popout": "_popout",
        }.get(name)
        if attr is None:
            logger.error("OPENCHEM_DRIVE: unknown visual_check surface %r", name)
            return None
        widget = getattr(self, attr, None)
        if widget is None:
            logger.error("OPENCHEM_DRIVE: no %s open for visual_check", name)
        return widget

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

    def _do_formulation(self, step: dict[str, Any]) -> None:
        """Add a stated formulation and show its report.

        `{"do": "formulation"}` uses ANFO, the case the whole feature
        exists for -- both components are refused by Kamlet-Jacobs'
        arbitrary on their own and the mixture lands inside it -- so a
        run with no arguments still exercises the interesting path. A
        `components` list of `[name, smiles, mass_fraction, dHf]` rows
        and a `density` override state a different recipe.

        **IT GOES THROUGH `_formulation_report_dialog`, WHICH IS THE
        PRODUCTION PATH**, rather than calling `build_formulation_report`
        here. Calling the builder directly would photograph a report the
        application never renders, which is the harness proving its own
        arithmetic instead of the feature -- the same distinction
        `jobs_cancel` draws by pressing the real button.

        `show()`, never `exec()`: a modal spins its own event loop inside
        this handler and an unattended run stalls with nobody to close
        the window.
        """
        from openchem.domain.formulation import FormulationComponent, FormulationModel

        window = self._window
        project = window._session.project
        if project is None:
            logger.error("OPENCHEM_DRIVE: no project to add a formulation to")
            return
        rows = step.get(
            "components",
            [
                ["Ammonium nitrate", "[NH4+].[N+](=O)([O-])[O-]", 0.945, -87.3],
                ["Fuel oil", "CCCCCCCCCCCC", 0.055, -83.9],
            ],
        )
        formulation = FormulationModel(
            display_name=str(step.get("name", "ANFO")),
            components=tuple(
                FormulationComponent(
                    display_name=str(row[0]),
                    smiles=str(row[1]),
                    mass_fraction=float(row[2]),
                    enthalpy_kcal_per_mol=float(row[3]),
                )
                for row in rows
            ),
            loading_density=float(step.get("density", 0.85)),
        )
        project.formulations.append(formulation)
        window._project_explorer.refresh()
        self._dialog = None
        dialog = window._formulation_report_dialog(formulation)
        dialog.setParent(window)
        dialog.setWindowFlag(Qt.WindowType.Dialog, True)
        if "width" in step:
            dialog.resize(int(step["width"]), int(step.get("height", dialog.height())))
        dialog.show()
        self._dialog = dialog
        logger.info(
            "OPENCHEM_DRIVE: formulation %r, %d components, rho0=%s",
            formulation.display_name,
            len(formulation.components),
            formulation.loading_density,
        )

    def _do_crystal(self, step: dict[str, Any]) -> None:
        """Import a CIF by PATH and show its report, with no file dialog.

        `{"do": "crystal", "path": "tests/fixtures/cif/1569411.cif"}`,
        then `{"do": "shot", "widget": "dialog"}`.

        **IT GOES THROUGH `crystal_report_dialog`, WHICH IS THE PRODUCTION
        PATH**, rather than calling `build_crystal_report` here: calling
        the builder directly would photograph a report the application
        never renders, which is the harness proving its own arithmetic
        instead of the feature.

        `show()`, never `exec()`, for the reason `_do_lewis` gives.
        """
        from pathlib import Path

        from openchem.chem.cif import CifError, read_cif
        from openchem.chem.crystal_report import build_crystal_report
        from openchem.domain.crystal import CrystalModel

        window = self._window
        project = window._session.project
        path = Path(str(step.get("path", "")))
        if project is None or not path.is_file():
            logger.error("OPENCHEM_DRIVE: no project, or no such CIF: %s", path)
            return
        text = path.read_text(encoding="utf-8", errors="replace")
        try:
            crystal = read_cif(text)
        except CifError as exc:
            logger.error("OPENCHEM_DRIVE: %s did not parse: %s", path.name, exc)
            return
        project.crystals.append(
            CrystalModel(
                display_name=crystal.name or path.stem,
                cif_text=text,
                source_name=path.name,
            )
        )
        window._project_explorer.refresh()
        self._dialog = None
        dialog = window.crystal_report_dialog(build_crystal_report(crystal), path.name)
        dialog.setParent(window)
        dialog.setWindowFlag(Qt.WindowType.Dialog, True)
        if "width" in step:
            dialog.resize(int(step["width"]), int(step.get("height", dialog.height())))
        if step.get("everything"):
            # The report opens with STRUCTURE and GEOMETRY collapsed and
            # the depth at Standard, which is how the crystal report has
            # always opened -- the cell volume and the density sit behind
            # the same fold. `{"everything": true}` is what lets a shot
            # show the rows rather than the headings.
            from PySide6.QtWidgets import QToolButton

            from openchem.ui.widgets.collapsible_section import CollapsibleSection
            from openchem.ui.widgets.fact_view import FactView

            view = dialog.findChild(FactView)
            if view is not None:
                view._detail.setCurrentIndex(view._detail.count() - 1)
                # A needle narrows the report to the rows worth
                # photographing -- a 44-fact report does not fit one
                # window, and the view expands every section while
                # filtering, which is what makes this enough on its own.
                needle = str(step.get("filter", ""))
                if needle:
                    view.search_box().setText(needle)
                for section in view.findChildren(CollapsibleSection):
                    button = section.findChild(QToolButton)
                    if button is not None and not button.isChecked():
                        button.click()
        dialog.show()
        self._dialog = dialog
        logger.info(
            "OPENCHEM_DRIVE: crystal %s, a=%.4f, %d operations, wavelength=%s",
            crystal.name or path.stem,
            crystal.lattice.a,
            len(crystal.operations),
            crystal.radiation_wavelength,
        )

    def _do_particle(self, step: dict[str, Any]) -> None:
        """Open the quark editor on a stated content.

        `{"do": "particle", "content": "u d s"}`, then
        `{"do": "shot", "widget": "dialog"}`. An antiquark is written
        `dbar`, matching the picker.

        **IT DRIVES THE COMBO BOXES, not `identify` directly.** Calling
        the arithmetic here would photograph a verdict the dialog never
        rendered -- and the defect this step exists to have caught was
        exactly a broken selection sitting behind correct arithmetic:
        the editor opened on `u u u` while every test passed, because
        `content()` read the boxes and was right about the wrong ones.
        """
        from openchem.domain.particle import Flavour
        from openchem.ui.dialogs.particle_dialog import ParticleDialog

        window = self._window
        spec = str(step.get("content", "u u d")).split()
        self._dialog = None
        dialog = ParticleDialog(window)
        try:
            dialog._meson.setChecked(len(spec) == 2)
            for slot, token in enumerate(spec[:3]):
                anti = token.endswith("bar")
                dialog._select(slot, Flavour(token[:-3] if anti else token), anti)
        except (ValueError, KeyError) as exc:
            logger.error("OPENCHEM_DRIVE: cannot compose %r: %s", spec, exc)
            dialog.deleteLater()
            return
        dialog.setWindowFlag(Qt.WindowType.Dialog, True)
        dialog.show()
        self._dialog = dialog
        logger.info(
            "OPENCHEM_DRIVE: particle %s -> %s | %s",
            " ".join(spec),
            dialog.verdict_text(),
            dialog.measured_text()[:80] or "(no measured values)",
        )

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

    def _do_scroll(self, step: dict[str, Any]) -> None:
        """Scroll the Properties panel, so content below the fold can be
        photographed.

        `{"do": "scroll", "to": "bottom"}` or `{"do": "scroll", "y": 900}`

        **A PANEL THAT SCROLLS HAS CONTENT NO SHOT COULD REACH.** Measured
        with a Lewis result on screen: viewport 396x580 against content
        396x2361, so five sixths of the panel is unphotographable from the
        top -- and this file's whole discipline is that a green suite plus
        a screenshot is what catches a rendering defect. `dump` reports
        that the content FITS; only a picture says what it looks like.

        Logs where it landed, because a request past the end is clamped
        and a silent clamp would make "I scrolled to the bottom" a claim
        about a position nobody checked.
        """
        from PySide6.QtWidgets import QScrollArea

        scroll = self._window._property_panel.findChild(QScrollArea)
        if scroll is None:
            logger.error("OPENCHEM_DRIVE: the Properties panel has no scroll area")
            return
        bar = scroll.verticalScrollBar()
        where = step.get("to")
        if where == "bottom":
            bar.setValue(bar.maximum())
        elif where == "top":
            bar.setValue(bar.minimum())
        else:
            bar.setValue(int(step.get("y", 0)))
        logger.warning(
            "OPENCHEM_DRIVE: scrolled to %d of %d", bar.value(), bar.maximum()
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
