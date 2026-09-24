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
      {"do": "menu",             "text": "Rotate 3D"},  THIS app's menu
      {"do": "picture",          "index": 0, "path": "..."},  the real
                                                 export, not a screenshot
      {"do": "rotate_report",    "tag": "entered"},     tick, button
                                                       AND the page
      {"do": "key",              "key": "F7"},          a REAL key, at
      {"do": "key", "key": "Escape", "focus": "canvas"}  the focus widget
      {"do": "key", "key": "Comma", "modifiers": "ctrl", "focus": "canvas",
                    "close_modal_after_ms": 1500}  a shortcut that opens a
                                                   modal: named, then closed
      {"do": "control",          "name": "railHidesPanels", "value": false}
                                              a named control of the open
                                              dialog, operated for real
      {"do": "geometry_report",  "tag": "flat"},        z spread AND the
                                                       conformers
      {"do": "select_atom",      "atom": 4}    the inspector ROW, plus
                                              what the CANVAS selected
      {"do": "selection_report"}               the canvas selection alone
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
      {"do": "qc_run",           "calc_type": "NMR (raw shielding)",
                                 "method": "HF-3c"}   the REAL Run button,
                                                      and the identity the
                                                      SERVICE was handed
      {"do": "inspector_report", "expect_spectrum": "stale"}   asserts it
      {"do": "atom_numbers",     "mode": "locants", "tag": "on"}  the View
                                              menu's mode, and what the PAGE
                                              drew, by molfile position
      {"do": "process_report",   "modules": ["openchem.chem.engine"]}  pid,
                                              HEAD, and where each module
                                              was imported from
      {"do": "log_report",       "tag": "after-draw"}   what the APPLICATION
                                              logged so far (WARNING and up),
                                              de-duplicated by where it happened
      {"do": "expect_clean",     "allow": ["substring"]}   FAILS the run if the
                                              application logged an unallowed
                                              ERROR; never a pass on its own
      {"do": "expect_results",   "expect": {"solubility": "inapplicable",
                                            "fragment_counts": {"facts_contain": ["Nitro"]}}}
                                              what the panels HOLD, so a clean
                                              log cannot pass by silence
      {"do": "expect_offered",   "hidden": ["detonation"], "footer": "1 calculator ..."}
                                              which calculators the Properties
                                              launcher OFFERS, by row visibility
      {"do": "expect_help",      "topic": "calc-joback-properties"}
                                              which help topic is in FRONT
      {"do": "chip",             "calculator": "detonation", "expect": {"status": "needs_input"}}
                                              PRESS a status chip, and assert
                                              where it went (see `_do_chip`)
      {"do": "service_row",      "calculator": "orca.nmr", "expect": {"panel": "Quantum_Chemistry", "calc_type": "nmr"}}
                                              PRESS a Properties row that opens
                                              another panel, and assert which
                                              panel came forward and what it chose
      {"do": "tool_setup",       "tool": "pkasolver"}
                                              the window half of a "Needs setup"
                                              press (see `_do_tool_setup`)
      {"do": "expect_inspectors", "count": 2, "titles": ["QEq"], "apart": true}
                                              how many Calculator Inspectors
                                              are OPEN, side by side
      {"do": "edit_burst",       "grow": "CCO", "edits": 12, "gap_ms": 150}   or   "structures": [a, b]
                                              what a burst of structural edits
                                              COSTS the application (recorded,
                                              never asserted)
      {"do": "quit"}                          ends in a VERDICT and an exit status
    ]

**THE RUN ENDS IN A VERDICT, NOT A SCREENSHOT.** `drive_ledger` keeps every
WARNING-and-above record the application logs, de-duplicated by origin, and
`quit` (or the last step) writes `<script>.report.json` beside the script --
`OPENCHEM_DRIVE_REPORT` names another path -- and exits non-zero when the run
failed: a driver failure (`no molecule selected`, `EXPECT ... FAILED`, a step
that raised), a failed `expect_*`, or an ERROR the application logged that no
`allow` excuses. `{"do": "quit", "tolerate_errors": true}` opts out of the last
for a script that provokes an error on purpose. The report carries the run's
identity (commit, script hash, lockfile hash, Qt/RDKit/Ketcher versions, and the
byte range of `logs/openchem.log` the run wrote) so two runs cannot be confused.

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
from PySide6.QtWidgets import QDialog, QVBoxLayout, QWidget

from openchem.app.drive_ledger import ErrorLedger, RunIdentity, log_file_size, write_report

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

    def __init__(
        self, window: QWidget, steps: list[dict[str, Any]], report_path: Path | None = None
    ) -> None:
        super().__init__()
        self._window = window
        self._steps = steps
        self._index = 0
        #: What the application logged (see `drive_ledger`). Built here but
        #: attached to the root logger only in `start()` and only for a real
        #: scripted run, so constructing a driver in a test leaves nothing
        #: behind on the process's logging.
        self._ledger = ErrorLedger()
        self._identity: RunIdentity | None = None
        #: The `expect_*` steps' outcomes, kept apart from the ledger: a failed
        #: assertion is the SCRIPT's verdict, not something the application said.
        self._assertions: list[dict[str, Any]] = []
        #: Numbers a step measured (`edit_burst`), by tag. Not assertions: a baseline
        #: is recorded so a later change can be compared against it, and nothing here
        #: passes or fails on a number.
        self._measurements: dict[str, Any] = {}
        #: Substrings excusing an application ERROR, gathered from every
        #: `expect_clean` and from `quit`.
        self._allow: list[str] = []
        self._report_path = report_path
        self._verdict: int | None = None
        #: The Lewis dialog a `lewis` step opened, so a later `shot` can
        #: grab it. Held rather than looked up: it is parented to the
        #: window and finding it by type would be one more place that can
        #: pick the wrong one once a second dialog exists.
        self._lewis: QWidget | None = None

    def start(self) -> None:
        logger.warning("OPENCHEM_DRIVE: %d step(s) from %s", len(self._steps), _DRIVE_SCRIPT)
        if _DRIVE_SCRIPT:
            # A real scripted run: attach the ledger and say which run this is.
            self._identity = RunIdentity.capture(_DRIVE_SCRIPT)
            logging.getLogger().addHandler(self._ledger)
            if self._report_path is None:
                self._report_path = Path(
                    os.environ.get("OPENCHEM_DRIVE_REPORT") or Path(_DRIVE_SCRIPT).with_suffix(".report.json")
                )
        self._answer_modal_boxes()
        # THE WINDOW IS THE CONTEXT OBJECT, NOT THE DRIVER, and it is the
        # right one for a reason beyond `_Driver` being a plain class Qt
        # would refuse: every step acts on that window, so a window that
        # is gone means a script with nothing left to drive. Qt cancels a
        # context-bound shot when the context dies, which ends the chain
        # instead of running the remaining steps against a freed window.
        # `self._window` is safe to reach for here -- `main.py` hangs the
        # driver off the window, so the driver never outlives it.
        QTimer.singleShot(_DEFAULT_AFTER_MS, self._window, self._run_next)

    def _answer_modal_boxes(self) -> None:
        """Answer every `QMessageBox` in the log instead of on screen.

        **THE RULE THIS FILE ALREADY STATES, ONE STEP FURTHER OUT.** A step
        that opens a modal must not `exec()` it, because that spins its own
        event loop and the next step is never scheduled. But the modal that
        actually stopped a run was not opened by a step at all: pressing
        Rotate 3D on a flat drawing makes the WINDOW ask "generate a 3D
        structure for it?", and the run sat on that question with nobody to
        answer it. Measured -- the script ran 12 of 27 steps and the rest
        were reported as though they had simply produced nothing.

        So the harness answers them. **The answer is logged**, which is the
        point: a question the application asked is a fact about the run, and
        one that silently vanished would be worse than the block. `"modal"`
        in the script picks the button; the default is No, because No is the
        answer that changes nothing.
        """
        from PySide6.QtWidgets import QMessageBox

        answer = str(os.environ.get("OPENCHEM_DRIVE_MODAL", "no")).lower()
        button = {
            "yes": QMessageBox.StandardButton.Yes,
            "no": QMessageBox.StandardButton.No,
            "ok": QMessageBox.StandardButton.Ok,
        }.get(answer, QMessageBox.StandardButton.No)

        def answered(kind):
            def stub(parent, title, text, *args, **kwargs):
                logger.warning(
                    "OPENCHEM_DRIVE: modal %s %r -- %r, answered %s",
                    kind, title, text, answer,
                )
                return button
            return stub

        for kind in ("question", "warning", "information", "critical"):
            setattr(QMessageBox, kind, staticmethod(answered(kind)))

    def _run_next(self) -> None:
        if self._index >= len(self._steps):
            logger.warning("OPENCHEM_DRIVE: script complete")
            # A script that ends without `quit` still gets its verdict and its
            # report; the app stays up so somebody can look at the window.
            self._finish()
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

    def _do_qc_run(self, step: dict[str, Any]) -> None:
        """Press the Quantum Chemistry panel's Run button, for real, and log the
        identity the SERVICE was handed.

        `{"do": "qc_run", "calc_type": "NMR (raw shielding)", "method": "HF-3c",
        "boltzmann": false, "after_ms": 120000}`

        **WHAT THE SERVICE RECEIVED, read off its own job record** --
        `_active_jobs` or `_boltzmann_runs`, both set synchronously by the
        request -- rather than what the panel believes it sent, the distinction
        `screen_run` reads its prep dict for. It is also REMEMBERED, so a later
        `inspector_report` with `expect_spectrum` can assert that the spectrum
        it holds carries exactly this identity rather than trusting a banner:
        a generic "stale" line would read the same if the wrong conformer
        happened to be compared against the current one.

        The panel's own combos and checkbox are SET, then the button is
        clicked, for the reason `dock_run` sets its spin box. The panel's
        molecule combo is pointed at the Properties selection first; nothing
        else moves it, and without that the run computes whatever the combo
        last held.

        ORCA runs for real, so give the step an `after_ms` long enough for the
        job to finish before any report that expects its spectrum.
        """
        from openchem.ui.molecule_combo import select

        panel = getattr(self._window, "_quantum_chemistry_panel", None)
        if panel is None:
            logger.error("OPENCHEM_DRIVE: qc_run -- no Quantum Chemistry panel on this window")
            return
        molecule_uuid = self._window._property_panel._selected_molecule_uuid
        if not select(panel._molecule_combo, molecule_uuid):
            logger.error("OPENCHEM_DRIVE: qc_run -- the selected molecule is not in the panel's combo")
            return
        calc_type = step.get("calc_type")
        if calc_type is not None:
            index = panel._calc_type_combo.findText(str(calc_type))
            if index < 0:
                logger.error("OPENCHEM_DRIVE: qc_run -- calc_type %r matches no item", calc_type)
                return
            panel._calc_type_combo.setCurrentIndex(index)
        if step.get("method") is not None:
            panel._method_combo.setCurrentText(str(step["method"]))
        panel._boltzmann_check.setChecked(bool(step.get("boltzmann", False)))
        if not panel._run_button.isEnabled():
            logger.error("OPENCHEM_DRIVE: qc_run -- the Run button is DISABLED; not clicked")
            return
        panel._run_button.click()

        service = panel._quantum_chemistry_service
        record = service._boltzmann_runs.get(molecule_uuid) or service._active_jobs.get(molecule_uuid)
        if record is None:
            logger.error(
                "OPENCHEM_DRIVE: qc_run -- no job was started; status=%r", panel._status_label.text()
            )
            return
        self._qc_submitted = (record.calculation_input, record.input_fingerprint)
        logger.warning(
            "OPENCHEM_DRIVE: qc_run submitted input=%s fingerprint=%s method=%r status=%r",
            record.calculation_input,
            record.input_fingerprint[:12],
            record.method_basis,
            panel._status_label.text(),
        )

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

    _AREAS = {
        "left": Qt.DockWidgetArea.LeftDockWidgetArea,
        "right": Qt.DockWidgetArea.RightDockWidgetArea,
        "top": Qt.DockWidgetArea.TopDockWidgetArea,
        "bottom": Qt.DockWidgetArea.BottomDockWidgetArea,
    }

    def _dock(self, panel_id: str):
        from PySide6.QtWidgets import QDockWidget

        dock = self._window.findChild(QDockWidget, panel_id)
        if dock is None:
            logger.error("OPENCHEM_DRIVE: no dock %r", panel_id)
        return dock

    def _do_dock_move(self, step: dict[str, Any]) -> None:
        """Put a dock in an area, as a user's drop would leave it.

        `{"do": "dock_move", "panel": "Results", "area": "top"}`
        `{"do": "dock_move", "panel": "Results", "beside": "Properties",
          "orientation": "vertical"}`   -- a split next to another dock

        Calls `addDockWidget` / `splitDockWidget` on the window directly,
        OUTSIDE the window's own arranging guard, so it reaches the same
        `dockLocationChanged` a real drop does -- which is the signal the
        rail's "user-placed" rule is built on.
        """
        dock = self._dock(str(step["panel"]))
        if dock is None:
            return
        dock.setFloating(False)
        beside = step.get("beside")
        if beside:
            other = self._dock(str(beside))
            if other is None:
                return
            orientation = (
                Qt.Orientation.Vertical if step.get("orientation", "vertical") == "vertical"
                else Qt.Orientation.Horizontal
            )
            other.show()
            self._window.splitDockWidget(other, dock, orientation)
        else:
            self._window.addDockWidget(self._AREAS[str(step.get("area", "right"))], dock)
        dock.show()
        # `"width"` / `"height"`: the size a user's drag would leave, so a
        # layout complaint can be reproduced at the size it was reported at.
        # A split's default share is whatever Qt picks, and the first run at
        # it gave Results 132 px where the report showed about 380.
        if "width" in step:
            self._window.resizeDocks([dock], [int(step["width"])], Qt.Orientation.Horizontal)
        if "height" in step:
            self._window.resizeDocks([dock], [int(step["height"])], Qt.Orientation.Vertical)

    def _do_dock_resize(self, step: dict[str, Any]) -> None:
        """`{"do": "dock_resize", "panel": "Results", "width": 380}` -- resize
        without moving, for a dock already where it should be."""
        dock = self._dock(str(step["panel"]))
        if dock is None:
            return
        if "width" in step:
            self._window.resizeDocks([dock], [int(step["width"])], Qt.Orientation.Horizontal)
        if "height" in step:
            self._window.resizeDocks([dock], [int(step["height"])], Qt.Orientation.Vertical)

    def _do_dock_tabify(self, step: dict[str, Any]) -> None:
        """`{"do": "dock_tabify", "panel": "Results", "onto": "Properties"}`"""
        dock, onto = self._dock(str(step["panel"])), self._dock(str(step["onto"]))
        if dock is None or onto is None:
            return
        dock.setFloating(False)
        onto.show()
        self._window.tabifyDockWidget(onto, dock)
        dock.show()

    def _do_dock_float(self, step: dict[str, Any]) -> None:
        """`{"do": "dock_float", "panel": "Properties", "on": true}`"""
        dock = self._dock(str(step["panel"]))
        if dock is not None:
            dock.setFloating(bool(step.get("on", True)))
            dock.show()

    def _do_reset_layout(self, step: dict[str, Any]) -> None:
        """`{"do": "reset_layout"}` -- the real View > Reset Panel Layout."""
        self._window.reset_panel_layout()

    def _do_dock_report(self, step: dict[str, Any]) -> None:
        """Every dock's area, state and rectangle -- and which ones OVERLAP.

        `{"do": "dock_report", "tag": "after-move"}`

        **THE OVERLAP IS THE POINT.** The reported screenshot showed the
        Results title bar painted on top of the Project Explorer's
        ("Resjdts Explorer"), which no screenshot comparison can name but a
        rectangle intersection can. Visible, docked (not floating) docks only;
        a floating window overlapping the main window is its whole purpose.
        """
        report = self._window.dock_layout_report()
        logger.warning("OPENCHEM_DRIVE: dock_report %s %s", step.get("tag", ""), json.dumps(report))

    def _do_reader_layout_report(self, step: dict[str, Any]) -> None:
        """`{"do": "reader_layout_report", "tag": "beside"}` -- how much of the
        Results reader is FACTS, in rows a person can read.

        **ROWS, NOT PIXELS.** The reported defect was the fact list squeezed
        to about two rows between a 35-name summary and a caveat paragraph;
        "the scroll area is 60 px" means nothing across fonts and DPI, while
        "2 rows fully visible" is the complaint itself. Pixels are logged
        beside it for the record.
        """
        from PySide6.QtCore import QPoint, QRect

        from openchem.ui.widgets.fact_view import _FactRow

        reader = self._window._property_panel._attached_reader
        if reader is None:
            logger.error("OPENCHEM_DRIVE: reader_layout_report -- no reader")
            return
        view = reader._view

        def on_screen(widget) -> QRect:
            """The part of `widget` no ancestor clips away, in global
            coordinates. EVERY ancestor, not the nearest scroll area: the
            dock wraps the reader in a scroll area of its own, and measured
            against the inner one alone a squeezed reader reported 49 whole
            rows inside a 2198 px viewport while the screen showed none."""
            rect = QRect(widget.mapToGlobal(QPoint(0, 0)), widget.size())
            parent = widget.parentWidget()
            while parent is not None:
                rect = rect.intersected(QRect(parent.mapToGlobal(QPoint(0, 0)), parent.size()))
                parent = parent.parentWidget()
            return rect

        rows = view._container.findChildren(_FactRow)
        whole = 0
        for row in rows:
            if not row.isVisible():
                continue
            if on_screen(row).size() == row.size():
                whole += 1
        viewport = view._area.viewport()
        reader_visible = on_screen(reader)
        clipped_right = reader_visible.width() < reader.width()
        properties_dock = self._dock("Properties")
        logger.warning(
            "OPENCHEM_DRIVE: reader_layout %s rows_whole=%d rows_total=%d facts_on_screen_h=%d "
            "summary_h=%d summary_truncated=%s status_h=%d status_truncated=%s "
            "controls_stacked=%s reader_w=%d reader_visible_w=%d reader_min_h=%d reader_visible_h=%d clipped=%s "
            "properties_visible=%s selected=%s",
            step.get("tag", ""),
            whole,
            len(rows),
            on_screen(viewport).height(),
            view._summary.height(),
            # getattr: the step also runs against a build BEFORE the notes
            # folded, which is how the defect is reproduced before the fix
            # is judged.
            getattr(view._summary, "is_truncated", lambda: None)(),
            view._status.height(),
            getattr(view._status, "is_truncated", lambda: None)(),
            getattr(view, "controls_are_stacked", lambda: None)(),
            reader.width(),
            reader_visible.width(),
            reader.minimumSizeHint().height(),
            reader_visible.height(),
            clipped_right or reader_visible.height() < reader.height(),
            bool(properties_dock is not None and properties_dock.isVisible()),
            self._window._property_panel._selected_molecule_uuid,
        )
        # **THE CHROME, PIECE BY PIECE**, because "the reader's minimum is
        # 208 against 190" does not say which rows to give back. Every row
        # between the dock's top edge and the facts, with where it sits in the
        # HOST and what it asks for, so a fold is chosen from the numbers.
        host = getattr(self._window, "_results_host", None)
        pieces = [
            ("popout_button", getattr(host, "_pop_out_button", None)),
            ("results_filter", getattr(reader, "_selector_search", None)),
            ("showing_row", getattr(getattr(reader, "_focus_box", None), "parentWidget", lambda: None)()),
            ("visuals", getattr(reader, "_visuals", None)),
            ("title", getattr(view, "_title", None)),
            ("summary", getattr(view, "_summary", None)),
            ("controls", getattr(view, "_controls", None)),
            ("facts_area", getattr(view, "_area", None)),
            ("status", getattr(view, "_status", None)),
        ]
        chrome = []
        for name, widget in pieces:
            if widget is None:
                continue
            top = widget.mapTo(host, QPoint(0, 0)).y() if host is not None else -1
            chrome.append(
                f"{name}:vis={int(widget.isVisible())},y={top},h={widget.height()},"
                f"min={widget.minimumSizeHint().height()}"
            )
        logger.warning(
            "OPENCHEM_DRIVE: reader_chrome %s host_h=%s host_min_h=%s %s",
            step.get("tag", ""),
            None if host is None else host.height(),
            None if host is None else host.minimumSizeHint().height(),
            " ".join(chrome),
        )

    def _do_fact_rows_report(self, step: dict[str, Any]) -> None:
        """`{"do": "fact_rows_report", "tag": "docked", "label": "Finding"}` --
        each value row in the Results reader against the height its TEXT needs
        at the width the row has. `label` and `min_chars` narrow the rows.

        **THE ROW CANNOT BE ASKED.** `QLabel.heightForWidth` never answers below
        the label's own minimum height -- measured, a label held at 1608 px
        answers 1608 at a width where its text needs 250. Value rows held a
        fixed height until 2026-09-14, and this step has to measure a build from
        before that as honestly as one after, so it never takes the row's own
        answer. `needs_h` is the row's arithmetic with that floor lifted for the
        one call; `probe_h` is a fresh label given the same text, font and
        margins, which never touches the row. The two agreeing is what says the
        measurement is Qt's and not this step's.

        `stated_for_w` is the widest width at which the text still needs the
        height the row HAS. A row sized for its own width reports its width; a
        height left over from a narrower layout reports that narrower width.
        """
        from PySide6.QtWidgets import QLabel

        from openchem.ui.widgets.fact_view import _FACT_PROPERTY, _FactRow

        reader = self._window._property_panel._attached_reader
        if reader is None:
            logger.error("OPENCHEM_DRIVE: fact_rows_report -- no reader")
            return
        wanted_label = step.get("label")
        min_chars = int(step.get("min_chars", 0))
        probe = QLabel()
        probe.setWordWrap(True)
        rows_seen = over = 0
        try:
            for row in reader._view._container.findChildren(_FactRow):
                fact = row.property(_FACT_PROPERTY)
                label = str(getattr(fact, "label", "?"))
                # `isVisibleTo`, not `isVisible`: a row in a collapsed section
                # has never been laid out and its geometry means nothing.
                if not row.isVisibleTo(reader) or len(row.text()) < min_chars:
                    continue
                if wanted_label is not None and label != wanted_label:
                    continue
                rows_seen += 1
                width, height = row.width(), row.height()
                held = row.minimumHeight()
                row.setMinimumHeight(0)
                try:
                    needs_h = row.heightForWidth(width)
                finally:
                    row.setMinimumHeight(held)
                probe.setFont(row.font())
                probe.setTextFormat(row.textFormat())
                probe.setAlignment(row.alignment())
                probe.setMargin(row.margin())
                probe.setIndent(row.indent())
                probe.setContentsMargins(row.contentsMargins())
                probe.setText(row.text())
                probe_h = probe.heightForWidth(width)
                low, high, stated_for_w = 1, width, 0
                while low <= high:
                    middle = (low + high) // 2
                    if probe.heightForWidth(middle) >= height:
                        stated_for_w, low = middle, middle + 1
                    else:
                        high = middle - 1
                line_h = max(1, row.fontMetrics().lineSpacing())
                if height - needs_h >= line_h:
                    over += 1
                logger.warning(
                    "OPENCHEM_DRIVE:   fact_row %r source=%r chars=%d w=%d h=%d needs_h=%d "
                    "probe_h=%d line_h=%d lines_needed=%.1f lines_held=%.1f stated_for_w=%d",
                    label,
                    str(getattr(fact, "source", "")),
                    len(row.text()),
                    width,
                    height,
                    needs_h,
                    probe_h,
                    line_h,
                    needs_h / line_h,
                    height / line_h,
                    stated_for_w,
                )
        finally:
            probe.deleteLater()
        logger.warning(
            "OPENCHEM_DRIVE: fact_rows %s rows=%d over_by_a_line=%d",
            step.get("tag", ""),
            rows_seen,
            over,
        )

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
        `{"do": "batch_select", "clear": true}`

        The category form goes through the GROUP'S OWN CHECK BOX rather
        than ticking each leaf, because the thing worth exercising is the
        propagation -- setting the leaves directly would drive a path the
        user never takes.

        **`clear` EXISTS BECAUSE THE SELECTION OUTLIVES THE PROCESS.**
        `BatchPanel` persists its ticked property ids under
        `batch/selected_property_ids` and restores them on construction, so
        one committed script's selection leaks into the next script's run
        and a table quietly grows columns nobody asked for. Measured: a
        scope benchmark ticking `lewis_adduct` alone came back with a
        Substance-classification column from the benchmark before it.
        A committed script must construct its own state; clear first.
        """
        panel = self._window._batch_panel
        if step.get("clear"):
            panel._clear_selection()
            logger.warning("OPENCHEM_DRIVE: cleared the property selection")
            if "property" not in step and "category" not in step:
                return
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

    def _do_batch_settings(self, step: dict[str, Any]) -> None:
        """Configure one calculator for the next batch run.

        `{"do": "batch_settings", "id": "lewis_adduct",
          "parameters": {"partner_smiles": "N"}}`

        **IT DOES NOT OPEN THE DIALOG**, and that is the one thing this
        step does differently from a real double-click. A modal `exec()`
        inside a handler spins its own event loop, so the next step is
        never scheduled and an unattended run stalls on a window with
        nobody to close it -- the trap `lewis` already documents. What it
        DOES exercise is the panel's own store and the request that reads
        it, which is where the defect was: the parameters never left the
        panel at all.

        The registered defaults are filled in first, so a step naming one
        parameter does not silently blank the rest -- which is what the
        real dialog does, since every widget reports a value.
        """
        panel = self._window._batch_panel
        calculator_id = str(step.get("id", ""))
        definition = panel._registry.get(calculator_id)
        if definition is None:
            logger.error("OPENCHEM_DRIVE: no calculator %r in the registry", calculator_id)
            return
        resolved = {p.name: p.default for p in definition.parameters}
        unknown = set(step.get("parameters", {})) - set(resolved)
        if unknown:
            logger.error(
                "OPENCHEM_DRIVE: %s has no parameter(s) %s -- have %s",
                calculator_id,
                sorted(unknown),
                sorted(resolved),
            )
        resolved.update(step.get("parameters", {}))
        panel._calculator_parameters[calculator_id] = resolved
        logger.warning(
            "OPENCHEM_DRIVE: batch settings %s = %s", calculator_id, resolved
        )

    def _do_batch_molecules(self, step: dict[str, Any]) -> None:
        """Narrow which molecules Fill table will cover.

        `{"do": "batch_molecules", "names": ["Aspirin", "Caffeine"]}`
        `{"do": "batch_molecules", "all": true}`
        `{"do": "batch_molecules", "none": true}`

        **DRIVES THE REAL LIST WIDGET**, for the reason `jobs_cancel`
        presses the real button: the scope is read back off the ticks, so
        a step that called `selected_molecules` or set some private field
        would prove the resolver works and say nothing about whether the
        control is wired to it.

        A name matching nothing is LOGGED rather than ignored. A silently
        unticked molecule photographs identically to a correctly ticked
        one, and the whole point of the scope is that it changes what runs
        without changing what the panel looks like.

        THE RESOLVED SCOPE IS LOGGED BESIDE THE SHOT, because that is the
        half no picture carries: a panel scoped to two molecules and one
        scoped to five are the same image until the table lands.
        """
        panel = self._window._batch_panel
        panel._molecule_section.set_expanded(True)
        if step.get("all"):
            panel._select_all_molecules()
        elif step.get("none"):
            panel._clear_molecule_selection()
        else:
            wanted = [str(name) for name in step.get("names", [])]
            labels = {
                panel._molecules.item(index).text(): panel._molecules.item(index)
                for index in range(panel._molecules.count())
            }
            for name, item in labels.items():
                item.setCheckState(
                    Qt.CheckState.Checked if name in wanted else Qt.CheckState.Unchecked
                )
            for name in wanted:
                if name not in labels:
                    logger.error(
                        "OPENCHEM_DRIVE: no molecule %r in the scope list -- have %s",
                        name,
                        sorted(labels),
                    )
        logger.warning(
            "OPENCHEM_DRIVE: batch scope %d of %d -- %s | label %r",
            len(panel.selected_molecules()),
            panel._molecules.count(),
            [m.display_name for m in panel.selected_molecules()],
            panel._scope_label.text(),
        )

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
        self._window._set_project(command.loaded_project, command.loaded_results)
        logger.warning(
            "OPENCHEM_DRIVE: opened %s -- %d molecule(s)",
            path.name,
            len(command.loaded_project.molecules),
        )

    def _do_save_project(self, step: dict[str, Any]) -> None:
        """Save without the file dialog.

        `{"do": "save_project", "path": "C:/tmp/saved.ocsproj"}`

        Through `MainWindow.save_project_to`, which is everything the File
        menu's Save does once a path is chosen -- including the retained
        results, which is what a save-then-reopen check is checking.
        """
        from pathlib import Path as _Path

        path = _Path(str(step.get("path", "")))
        self._window.save_project_to(path)
        logger.warning("OPENCHEM_DRIVE: saved %s (%d bytes)", path, path.stat().st_size if path.exists() else -1)

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
        # `"reveal": false` skips the reveal, so no Calculator Inspector window
        # is left open for the rest of an unattended run. It USED to be
        # load-bearing for a worse reason: the reveal ran `exec()` inside the
        # bus handler and starved every later subscriber (the Atom Inspector
        # got the dataset 67 s late, at quit). `PropertyPanel._reveal_after_dispatch`
        # fixed that, and the inspector is MODELESS now, so a reveal blocks
        # nothing -- but each one still opens a window (and a Chromium process),
        # and `expect_inspectors` is what counts them.
        if step.get("reveal", True):
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

        **`show()`, NEVER `exec()`.** `exec()` spins an event loop inside the
        handler -- the next step is never scheduled and an unattended run
        stalls on a window with nobody to close it. Same trap `lewis`
        documents. (The panel's own `_open_inspector` used to end in `exec()`
        and is modeless now; this step still builds the dialog itself so it
        can be photographed without the panel's title, cap and raise logic.)

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
        # THE INPUT THE CALCULATOR DECLARES, through the registry. This read
        # the drawing for every calculator, so a 3D one was handed a flat
        # structure and the inspector photographed its refusal; and calling
        # `execution.compute` directly skipped the registry's dropping of
        # greyed-out parameters.
        from openchem.chem.calculation_input import resolve_calculation_input

        engine = window._services.chemistry_engine
        mol = resolve_calculation_input(engine, molecule, definition.calculation_input).mol
        result = window._services.calculator_registry.compute(calculator_id, mol, molecule.uuid, parameters)
        best = canonical_conformer(molecule)
        self._inspector = CalculatorInspectorDialog(
            window._services.chemistry_engine,
            molecule,
            result,
            best.molblock if best is not None else None,
            window,
            # **THE CALLBACK THE REAL PATH PASSES.** Without it the dialog
            # HIDES its "Add to Project" button, so a driven run would have
            # photographed a dialog missing a control the application shows
            # -- and reported the absence as a product fact.
            on_add_structure=window._add_generated_structure,
        )
        self._inspector.show()
        logger.warning(
            "OPENCHEM_DRIVE: inspect %s -> %r", calculator_id, getattr(result, "name", "")
        )

    def _do_inspect_report(self, step: dict[str, Any]) -> None:
        """What the open Calculator Inspector is drawing, in words a screenshot cannot give.

        `{"do": "inspect_report", "tag": "ph", "select_row": 0, "filter": "N"}`

        Logs which structure the panes use (`structure=effective_structure`
        or the legacy stored conformer), its atom count and net charge, the
        2D pane's placement note and label count, the table's rows, and the
        dialog's size. `filter` and `select_row` drive the REAL table widgets,
        then report the atom the selection stands for. The 3D page's own
        label state arrives asynchronously in a second log line.
        """
        dialog = getattr(self, "_inspector", None)
        view = getattr(dialog, "_view", None)
        if view is None or not hasattr(view, "_structure_source"):
            logger.error("OPENCHEM_DRIVE: inspect_report needs an `inspect` step on a per-atom result")
            return
        tag = step.get("tag", "")
        if "filter" in step:
            view._table_filter.setText(str(step["filter"]))
        if "select_row" in step and getattr(view, "_table", None) is not None:
            view._table.selectRow(int(step["select_row"]))
        engine = self._window._services.chemistry_engine
        shown = view._conformer_molblock
        atoms = charge = None
        if shown:
            try:
                mol = engine.mol_from_molblock(shown)
                atoms, charge = mol.GetNumAtoms(), sum(a.GetFormalCharge() for a in mol.GetAtoms())
            except Exception:  # noqa: BLE001 - a report must not stop the run
                pass
        labels_2d = len(view._layer_2d.atom_labels or {}) if view._layer_2d is not None else 0
        rows = view._table_proxy.rowCount() if getattr(view, "_table_proxy", None) is not None else None
        logger.warning(
            "OPENCHEM_DRIVE: inspect_report[%s] structure=%s atoms=%s formal_charge=%s placement=%r "
            "labels_2d=%d table_rows=%s selected_atom=%s emphasised_2d=%s size=%dx%d",
            tag, view._structure_source, atoms, charge, view._placement_label.text(), labels_2d, rows,
            view.selected_atom(), view._emphasised, dialog.width(), dialog.height(),
        )
        view._viewer3d._page.runJavaScript(
            "window.openchemViewer.labelState()",
            lambda state: logger.warning("OPENCHEM_DRIVE: inspect_report[%s] page=%s", tag, state),
        )
        if step.get("png"):
            # THE PAGE'S OWN RENDERING. A Qt grab of the dialog came back with
            # the 3D pane blank, and the 3D pane was exactly what needed looking
            # at: 3Dmol draws its labels into the WebGL canvas, so this has them.
            target = Path(str(step["png"]))

            def save(data_url: str) -> None:
                import base64

                size, _, data_url = (data_url or "").partition("|")
                logger.warning("OPENCHEM_DRIVE: inspect_report[%s] container=%s", tag, size)
                if not data_url or "," not in data_url:
                    logger.error("OPENCHEM_DRIVE: inspect_report[%s] no canvas image", tag)
                    return
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(base64.b64decode(data_url.split(",", 1)[1]))
                logger.warning("OPENCHEM_DRIVE: inspect_report[%s] wrote %s", tag, target)

            view._viewer3d._page.runJavaScript("viewer.resize(); viewer.render(); JSON.stringify([document.getElementById('viewer-container').clientWidth, document.getElementById('viewer-container').clientHeight]) + '|' + viewer.pngURI()", save)

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
        elif step.get("widget") == "results":
            if getattr(self, "_results", None) is None:
                logger.error("OPENCHEM_DRIVE: no results window open; run {'do': 'results'}")
                return
            target = self._results
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
        elif step.get("widget") == "inspectors":
            # **EVERY OPEN CALCULATOR INSPECTOR IN ONE PICTURE, AT THEIR REAL RELATIVE
            # POSITIONS.** A single-widget grab cannot show whether two windows overlap,
            # which is the whole question when they are meant to stand side by side; a
            # screen grab would photograph whatever else is on the desktop. Each is
            # grabbed and painted onto one canvas, oldest first, so the newest is on top.
            from PySide6.QtGui import QColor, QPainter, QPixmap

            shown = []
            for reference in self._window._property_panel._inspector_windows.values():
                window = reference()
                try:
                    if window is not None and window.isVisible():
                        shown.append((window.x(), window.y(), window.grab()))
                except RuntimeError:
                    continue
            if not shown:
                logger.error("OPENCHEM_DRIVE: no inspector windows open; nothing to photograph")
                return
            left = min(x for x, _y, _pic in shown)
            top = min(y for _x, y, _pic in shown)
            right = max(x + pic.width() for x, _y, pic in shown)
            bottom = max(y + pic.height() for _x, y, pic in shown)
            canvas = QPixmap(right - left, bottom - top)
            canvas.fill(QColor("#888888"))
            painter = QPainter(canvas)
            for x, y, pic in shown:
                painter.drawPixmap(x - left, y - top, pic)
            painter.end()
            canvas.save(str(path))
            logger.warning("OPENCHEM_DRIVE: wrote %s (%d inspector window(s))", path, len(shown))
            return
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
        elif step.get("widget") == "results_list":
            # **THE DROPPED-DOWN LIST, WHICH NO WINDOW GRAB CAN REACH.** A
            # closed combo box paints one row, and its popup is a separate
            # top-level window, so neither `grab()` on the dialog nor
            # `PrintWindow` on the application captures the thing worth
            # looking at -- the section headings, and whether bold and
            # greyed read as unselectable rather than as broken entries.
            #
            # `view()` IS an ordinary widget, so grabbing it renders the
            # rows directly. `showPopup()` first, because an unshown view
            # has not been laid out and grabs at its default size -- the
            # trap this file records for `repaint()` and `resize()`.
            if getattr(self, "_results", None) is None:
                logger.error("OPENCHEM_DRIVE: no results window open; run {'do': 'results'}")
                return
            box = self._results._focus_box
            box.showPopup()
            target = box.view()
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

    def _do_results(self, step: dict[str, Any]) -> None:
        """Show the results reader, optionally focused on one report.

        `{"do": "results", "focus": "elemental_analysis"}`, then
        `{"do": "shot", "widget": "results"}`.

        **IT GOES THROUGH THE PANEL'S OWN ROUTE, NOT THE READER'S API.**
        Calling `set_reports` on the view here would prove the view renders
        and say nothing about the thing that changed: which reports the
        panel hands it, which version it compares them against, and whether
        the reader is the one that later results land in. That is the
        `jobs_cancel` rule -- press the control, not the handler behind it.

        It LOGS what the reader is showing, because two of this feature's
        states photograph identically. A reader with one calculator's facts
        and one focused on a calculator OUT OF SIX look the same in a
        screenshot, and a stale badge is a few pixels of text.
        """
        panel = self._window._property_panel
        if step.get("close"):
            # **RETURNS A DETACHED READER RATHER THAN DESTROYING ONE.** The
            # reader is persistent now, so there is no close -- what this
            # step meant (put it away and prove the position survives) is
            # `return_home`, and the position has to survive that too.
            self._window._results_host.return_home()
            self._results = None
            logger.warning("OPENCHEM_DRIVE: results tag=%s RETURNED", step.get("tag", ""))
            return
        panel._show_in_reader(focus=str(step.get("focus") or ""))
        window = panel._attached_reader
        if window is None:
            logger.error("OPENCHEM_DRIVE: no results reader attached to the panel")
            return
        self._results = window
        # **WHERE THE READER IS, WHICH NO SCREENSHOT CARRIES.** A docked
        # reader and a detached one holding the same report photograph
        # almost identically, and `reveal_results` picks between three
        # outcomes -- raise, do nothing, detach -- that differ only in
        # which window the pixels end up in. So the flag is logged, and
        # the detached window is handed to `shot widget=popout`, which
        # otherwise only knows about a window the HARNESS opened.
        host = getattr(self._window, "_results_host", None)
        detached = bool(host is not None and host.is_popped_out())
        if detached:
            self._popout = host.window()
        logger.warning(
            "OPENCHEM_DRIVE: results reader detached=%s dock_hidden=%s",
            detached,
            self._window._results_dock.isHidden(),
        )
        # THE SELECTOR SEARCH, TYPED INTO THE REAL BOX. `setText` is what a
        # user's keystrokes reach, and it fires the handler that rebuilds and
        # remembers -- calling `_rebuild_focus_box` here would prove the list
        # can be filtered and say nothing about the control being wired to it.
        if "search" in step:
            window._selector_search.setText(str(step.get("search") or ""))
        merged = window.merged()
        # **THE OPEN BUTTON'S WORDS, because that is the whole of what a row
        # offers.** A result kind that has a viewer and a row that SAYS so are
        # different states, and they photograph the same at this size -- which
        # is how "there's no way to work on a tautomer" was reported by
        # someone whose screen was showing the button that does it.
        logger.warning(
            "OPENCHEM_DRIVE: results open_button visible=%s text=%r",
            window._open_button.isVisible(),
            window._open_button.text(),
        )
        logger.warning(
            "OPENCHEM_DRIVE: results tag=%s reports=%d facts=%d charts=%d "
            "focus=%r stale=%s version=%s",
            step.get("tag", ""),
            len(merged.reports),
            len(merged.facts),
            len(merged.charts()),
            window.focus(),
            list(merged.stale_report_ids()),
            merged.structure_version,
        )
        for report in merged.reports:
            logger.warning(
                "OPENCHEM_DRIVE:   %s (%s) facts=%d charts=%d%s",
                merged.name_for(report.report_id),
                report.report_id,
                len(report.facts),
                len(getattr(report, "charts", ()) or ()),
                " STALE" if merged.is_stale(report) else "",
            )
        self._log_results_selector(window)
        self._log_results_visualizations(window)
        self._log_results_copy(window)
        if "open_visual" in step:
            self._press_visual_open(window, int(step.get("open_visual") or 0))

    def _log_results_visualizations(self, window: Any) -> None:
        """What the reader offers to SHOW, and what it offers to OPEN.

        **THREE OF THIS FEATURE'S STATES PHOTOGRAPH IDENTICALLY**, which is
        the `jobs_report` rule applied to a list of pictures. A result with no
        visualizations, one whose section failed to build, and one whose rows
        drew with no type label are all "a window with facts in it" in a
        screenshot; and whether the result-level Open button is up is a few
        pixels of text.
        """
        from PySide6.QtWidgets import QPushButton

        button = window._open_button
        logger.warning(
            "OPENCHEM_DRIVE:   open_button visible=%s text=%r",
            button.isVisible(),
            button.text(),
        )
        section = window._visuals
        layout = window._visuals_layout
        rows = []
        for index in range(1, layout.count()):
            row = layout.itemAt(index).widget()
            if row is None:
                continue
            inner = row.layout()
            texts = [
                inner.itemAt(i).widget().text()
                for i in range(inner.count())
                if inner.itemAt(i).widget() is not None
                and hasattr(inner.itemAt(i).widget(), "text")
            ]
            rows.append(texts)
        logger.warning(
            "OPENCHEM_DRIVE:   visualizations visible=%s rows=%d openable=%d",
            section.isVisible(),
            len(rows),
            len(section.findChildren(QPushButton)),
        )
        for texts in rows:
            logger.warning("OPENCHEM_DRIVE:     %s", " | ".join(texts))

    def _press_visual_open(self, window: Any, index: int) -> None:
        """Press a REAL Open button in the Visualizations list.

        The button, not the handler behind it -- `_on_visual_open_clicked`
        reads which annotation it means off `sender()`, so calling it directly
        passes `sender() is None` and proves nothing about the wiring. The
        same argument `jobs_cancel` makes.

        A DISABLED or absent button is logged rather than clicked: Qt ignores
        a click on one silently, so without this the run reports a healthy
        step and opens nothing, which is the wrong-panel-id trap in another
        costume.
        """
        from PySide6.QtWidgets import QPushButton

        buttons = window._visuals.findChildren(QPushButton)
        if index >= len(buttons):
            logger.error(
                "OPENCHEM_DRIVE: open_visual=%d but only %d openable rows",
                index, len(buttons),
            )
            return
        buttons[index].click()
        # WHETHER IT IS MODAL, which is the whole point of 1f and which no
        # screenshot distinguishes: a modal and a modeless dialog look the
        # same, and the modal one silently blocks everything behind it.
        from PySide6.QtWidgets import QApplication

        opened = [
            w for w in QApplication.topLevelWidgets()
            if type(w).__name__ == "SpatialResultDialog" and w.isVisible()
        ]
        logger.warning(
            "OPENCHEM_DRIVE:   spatial dialogs open=%d modal=%s",
            len(opened),
            [w.isModal() for w in opened],
        )

    def _log_results_copy(self, window: Any) -> None:
        """Try the four Copy formats on whatever is focused, and say so.

        **PRESSING COPY IS THE ONLY WAY TO FIND OUT, AND NO SCREENSHOT
        SHOWS IT.** `report_format` dispatches on type and used to fall off
        the end into the ATOM branch, so the two reader entries that are not
        a `ReportResult` -- the all-results view and Molecular Properties --
        raised `AttributeError: ... has no attribute 'atom_index'` out of the
        click path. The window looks perfectly healthy either way.

        The FORMATTER rather than the button, deliberately and unlike
        `jobs_cancel`: `_on_copy_clicked` writes to the system clipboard, and
        a diagnostic run must not overwrite whatever Alex has in it.
        """
        from openchem.ui.report_format import format_report

        report = window._view.report()
        if report is None:
            logger.warning("OPENCHEM_DRIVE: results copy -- nothing to copy")
            return
        outcomes = []
        for fmt in ("Plain text", "Markdown", "JSON", "CSV"):
            try:
                text = format_report(report, fmt)
                outcomes.append(f"{fmt}={len(text)}ch")
            except Exception as error:  # noqa: BLE001 - the point is to report it
                outcomes.append(f"{fmt}=RAISED {type(error).__name__}")
        logger.warning(
            "OPENCHEM_DRIVE: results copy subject=%s %s",
            type(report).__name__,
            " ".join(outcomes),
        )

    def _log_results_selector(self, window: Any) -> None:
        """Dump the "Showing" list row by row.

        **A COMBO BOX SHOWS ONE ROW WHEN IT IS CLOSED**, so a screenshot of
        this window carries no information about the list at all -- and the
        two things worth checking are precisely inside it: that a section
        heading is present for every group and for no empty one, and that a
        heading is DISABLED. The second is `jobs_report`'s rule exactly: a
        selectable heading and an unselectable one render identically until
        somebody arrows onto it.

        Popping the list open would not help either. It is a separate
        top-level window, so `PrintWindow` on the application does not
        capture it.
        """
        from openchem.ui.widgets.results_view import GROUP_HEADING

        box = window._focus_box
        model = box.model()
        rows = []
        for index in range(box.count()):
            heading = box.itemData(index) == GROUP_HEADING
            enabled = True
            item = model.item(index) if hasattr(model, "item") else None
            if item is not None:
                enabled = bool(item.isEnabled())
            rows.append(
                "[{}]{}{}".format(
                    box.itemText(index),
                    " HEADING" if heading else "",
                    "" if enabled else " disabled",
                )
            )
        logger.warning(
            "OPENCHEM_DRIVE: results selector rows=%d current=%r %s",
            box.count(),
            box.currentText(),
            " ".join(rows),
        )

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

    def _do_restructure(self, step: dict[str, Any]) -> None:
        """`{"do": "restructure", "order": "reverse"}` -- the same structure with
        its molfile atoms renumbered, through the REAL `EditStructureCommand`.

        **WHAT AN ERASE-AND-REDRAW EMITS, WITHOUT DRAWING.** No step can add
        an atom on the canvas, and the command is where the conformers are
        kept or cleared, so the command is what is driven: canonical SMILES is
        unchanged, so `_invalidate_stale_conformers` keeps every conformer
        while the drawing's atom order moves. Logged: SMILES and conformer
        count either side, and both element orders.
        """
        from openchem.chem.atom_identity import element_order, renumbered_molblock
        from openchem.commands.molecule_commands import EditStructureCommand

        window = self._window
        molecule = window._session.project.find_molecule(window._property_panel._selected_molecule_uuid)
        if molecule is None or not molecule.molblock:
            logger.error("OPENCHEM_DRIVE: restructure needs a selected molecule with a drawing")
            return
        before = (molecule.canonical_smiles, len(molecule.conformers), element_order(molecule.molblock))
        renumbered = renumbered_molblock(molecule.molblock, step.get("order", "reverse"))
        window._undo_stack.push(
            EditStructureCommand(window._services.chemistry_engine, molecule, renumbered, window._services.event_bus)
        )
        window._editor.set_molecule(molecule)
        logger.warning(
            "OPENCHEM_DRIVE: restructure smiles %r -> %r conformers %d -> %d elements %s -> %s",
            before[0], molecule.canonical_smiles, before[1], len(molecule.conformers),
            "".join(before[2]), "".join(element_order(molecule.molblock)),
        )

    def _do_per_atom_report(self, step: dict[str, Any]) -> None:
        """`{"do": "per_atom_report", "property": "geometry_partial_charge"}` --
        for every DRAWN atom: its element, the value the Atom Inspector would
        show for it, and the element of the conformer atom that value was
        computed for.

        **THE INSPECTOR'S OWN LOOKUP, NOT A RECONSTRUCTION.** Values come
        from the panel's context through `atom_report.collect_per_atom_data`,
        the function that builds the facts a user reads. A drawn O paired
        with a conformer H is a wrong-atom display whatever the screenshot
        looks like, and `freshness` says whether the panel would show it.
        """
        from openchem.chem.atom_identity import element_order
        from openchem.chem.atom_report import collect_per_atom_data
        from openchem.chem.calculation_input import canonical_conformer

        panel = self._window._atom_inspector_panel
        prop = str(step.get("property", "geometry_partial_charge"))
        model, mol = panel._molecule()
        if model is None:
            logger.error("OPENCHEM_DRIVE: per_atom_report has no molecule")
            return
        held = panel._context_for(model.uuid)
        dataset = held["per_atom"].get(prop)
        calculation_input, fingerprint = held["inputs"].get(("per_atom", prop), ("", ""))
        freshness = panel._freshness(model, calculation_input, fingerprint, {}) if dataset is not None else "absent"
        # The panel's OWN context, projector included -- what a user reads.
        context = panel._current_context(model)
        drawn = element_order(model.molblock or "")
        conformer = canonical_conformer(model)
        computed_on = element_order(conformer.molblock) if conformer is not None else []
        # Which conformer atom a shown number came from, found by the NUMBER,
        # so the check does not share the projection's own index logic.
        origin = {}
        for c, v in (dataset.values.items() if dataset is not None else ()):
            origin.setdefault(round(v, 12), set()).add(computed_on[c] if c < len(computed_on) else "-")
        rows, mismatches = [], 0
        projection = context["project"](dataset) if dataset is not None else None
        for index, element in enumerate(drawn):
            facts = [f for f in collect_per_atom_data(mol, index, {"per_atom": {prop: dataset}, "project": context["project"]})
                     if f.source == prop] if dataset is not None else []
            shown = facts[0].value if facts else None
            sources = origin.get(round(shown, 12), {"?"}) if shown is not None else {"-"}
            mismatches += int(shown is not None and element not in sources)
            rows.append(f"{index}:{element}<-{'/'.join(sorted(sources))}={'' if shown is None else f'{shown:+.4f}'}"
                        + ("" if not facts or facts[0].value is not None else "(not shown)"))
        ok_state = step.get("expect_mismatches")
        message = (f"OPENCHEM_DRIVE: per-atom {step.get('tag', '')} {prop} freshness={freshness} "
                   f"policy={getattr(projection, 'policy', '')} refusal={getattr(projection, 'refusal', '')} "
                   f"mismatches={mismatches} rows={' '.join(rows)}")
        if ok_state is not None:
            ok = (mismatches > 0) == bool(ok_state)
            (logger.warning if ok else logger.error)("%s EXPECT mismatches=%s %s", message, bool(ok_state), "ok" if ok else "FAILED")
        else:
            logger.warning(message)

    def _do_select_atom(self, step: dict[str, Any]) -> None:
        """Pick an Atom Inspector ROW, and ask the canvas what it selected.

        `{"do": "select_atom", "atom": 4}`

        **THE TABLE ROW, NOT `select_atom()` BEHIND IT.** The panel's own
        `select_atom` is the INBOUND door -- the 3D viewer's click lands
        there -- and the path under test starts one step later, at
        `_on_row_selected` reading the table's selection. Driving the
        method would exercise the same emit and prove nothing about the
        row being what emits it, which is the `jobs_cancel` rule.

        The read-back is the point and comes from the PAGE, because a
        selection is a few highlighted pixels and the failure it guards
        against is a plausible-looking one. `poolOrder` is logged with it:
        on an edited structure the pool ids and the molfile positions
        diverge, and that divergence is the whole reason this step exists.
        A STRING, because `runJavaScript` marshals primitives only.
        """
        wanted = int(step.get("atom", 0))
        panel = self._window._atom_inspector_panel
        table = panel._atom_table
        for row in range(table.rowCount()):
            cell = table.item(row, 0)
            if cell is not None and cell.data(Qt.ItemDataRole.UserRole) == wanted:
                table.selectRow(row)
                logger.warning(
                    "OPENCHEM_DRIVE: inspector row %d selected for atom %d", row, wanted
                )
                break
        else:
            logger.error(
                "OPENCHEM_DRIVE: no inspector row holds atom %d (%d rows, subject %s)",
                wanted, table.rowCount(), panel._subject,
            )
            return
        self._report_editor_selection()

    def _report_editor_selection(self) -> None:
        self._window._editor._backend._page.runJavaScript(
            "window.openchemSelection ? window.openchemSelection.report()"
            " : '{\"ready\": false, \"missing\": true}'",
            lambda value: logger.warning("OPENCHEM_DRIVE: canvas selection %s", value),
        )

    def _do_selection_report(self, step: dict[str, Any]) -> None:
        """`{"do": "selection_report"}` -- what the canvas has selected now.

        Separate from `select_atom` so the EDITOR -> inspector direction,
        and a plain erase with nothing selected, can be read too.
        """
        self._report_editor_selection()

    def _do_result_report(self, step: dict[str, Any]) -> None:
        """`{"do": "result_report", "calculator": "geometry_partial_charge",
        "expect_refusal": "REFUSE_NOT_CONVERGED"}` -- what Properties holds for
        one calculator: its method, state, refusal code and the message a user
        reads.

        **A REFUSAL AND A MISSING RESULT PHOTOGRAPH ALIKE.** "Not applicable"
        on the row says a refusal happened, not which one; a run that meant to
        show non-convergence and instead hit "no 3D conformer" would look
        identical. With `expect_refusal` the code is asserted (ERROR on
        failure, so a run's outcome is one grep); `"expect_refusal": ""`
        asserts a computed result.
        """
        panel = self._window._property_panel
        # BOTH HOLDINGS. Per-atom datasets and spectra are retained in
        # `_retained_results`; a `ReportResult` (the dipole, every
        # fact-list calculator) lives in `_reports`. Reading only the first
        # made a computed dipole and a missing one log alike: `{}`.
        retained = {**(getattr(panel, "_reports", {}) or {}), **(getattr(panel, "_retained_results", {}) or {})}
        calculator = str(step.get("calculator", ""))
        matching = {key: result for key, result in retained.items() if calculator and calculator in key}
        rows = {}
        for key, result in matching.items():
            provenance = getattr(result, "provenance", None)
            parameters = dict(getattr(provenance, "parameters", {}) or {})
            rows[key] = {
                "name": getattr(result, "name", ""),
                "method": getattr(result, "method", "") or getattr(provenance, "method", ""),
                "state": str(getattr(result, "cache_state", "")),
                "inapplicable": bool(getattr(result, "inapplicable", False)),
                "refusal": parameters.get("refusal", ""),
                "charge_model": parameters.get("charge_model", ""),
                "summary": getattr(result, "error_summary", "") or "",
                # The producer's own sentence, which the reader shows as its "Finding" row -- how an
                # Ionescu result says it is an extrapolation, logged so a run can grep for it.
                "finding": parameters.get("summary", ""),
                "error": getattr(result, "error", "") or "",
                "facts": [f"{f.label}={f.display_value}" for f in (getattr(result, "facts", ()) or ())][:1]
                + [f.display_value for f in (getattr(result, "facts", ()) or ()) if "mean absolute error" in f.display_value],
            }
            # `"all_facts": true` -- every fact, for a result whose facts ARE
            # the answer (Fragment Counts: one per count). The first-fact
            # default above logged "Tertiary Amine (4)" and nothing after it.
            if step.get("all_facts"):
                rows[key]["facts"] = [f.display_value for f in (getattr(result, "facts", ()) or ())]
                rows[key]["category_labels"] = parameters.get("category_labels", {})
        if "expect_refusal" in step:
            wanted = str(step["expect_refusal"])
            ok = bool(rows) and all(row["refusal"] == wanted for row in rows.values())
            (logger.warning if ok else logger.error)(
                "OPENCHEM_DRIVE: EXPECT refusal %r for %s %s -- %s",
                wanted, calculator, "ok" if ok else "FAILED", json.dumps(rows),
            )
        logger.warning("OPENCHEM_DRIVE: result %s %s", step.get("tag", ""), json.dumps(rows))

    def _do_inspector_report(self, step: dict[str, Any]) -> None:
        """`{"do": "inspector_report", "tag": "after-edit"}` -- what the Atom
        Inspector is SHOWING for its subject: title, the pinned line, and
        every fact as label=value.

        **THE PINNED LINE IS THE POINT.** A per-atom result computed for an
        earlier structure is withheld and NAMED there; a screenshot shows a
        missing row and a sentence, which is exactly the pair that reads as
        "never computed" if one of them fails. Logged as text so a run can
        assert on both.
        """
        panel = self._window._atom_inspector_panel
        facts = panel._facts
        report = getattr(facts, "_report", None)
        rows = [
            f"{fact.label}={fact.value_with_units}" for fact in getattr(report, "facts", ()) or ()
        ]
        # Every HELD per-atom result and what the panel decides about it, so
        # "not on screen" can be told apart from "never arrived".
        from openchem.chem.calculation_input import input_fingerprint
        from openchem.domain.calculator import DRAWING

        model, _mol = panel._molecule()
        held = {}
        # Spectra WITH their identities: the input kind, the fingerprint the
        # spectrum carries and the current one for that kind, so "stale"
        # can be checked against WHAT it is stale relative to.
        identity: dict[str, dict[str, str]] = {}
        if model is not None:
            context = panel._context_for(model.uuid)
            cache: dict = {}
            for key in context["per_atom"]:
                calculation_input, fingerprint = context["inputs"].get(("per_atom", key), ("", ""))
                held[key] = panel._freshness(model, calculation_input, fingerprint, cache)
            for key in context["spectra"]:
                calculation_input, fingerprint = context["inputs"].get(("spectra", key), ("", ""))
                state = panel._freshness(model, calculation_input, fingerprint, cache)
                held[f"spectrum:{key}"] = state
                try:
                    current = input_fingerprint(panel._engine, model, calculation_input or DRAWING)
                except Exception:  # noqa: BLE001 - an unresolvable input is reported as such
                    current = ""
                identity[key] = {
                    "input": calculation_input,
                    "held": fingerprint[:12],
                    "current": current[:12],
                    "state": state,
                }
        expected = step.get("expect_spectrum")
        if expected:
            # THE ASSERTION, logged at ERROR when it fails so a run's outcome
            # is one grep. Every held spectrum must be in the expected state
            # AND carry exactly the identity the last `qc_run` submitted -- a
            # stale mark over a different identity is the failure this checks.
            submitted = getattr(self, "_qc_submitted", None)
            ok = (
                bool(identity)
                and submitted is not None
                and all(
                    entry["state"] == expected
                    and entry["input"] == submitted[0]
                    and entry["held"] == submitted[1][:12]
                    for entry in identity.values()
                )
            )
            (logger.warning if ok else logger.error)(
                "OPENCHEM_DRIVE: EXPECT spectrum %s %s -- submitted=%s identity=%s",
                expected,
                "ok" if ok else "FAILED",
                None if submitted is None else [submitted[0], submitted[1][:12]],
                json.dumps(identity),
            )
        # `"expect_per_atom": {"contains": "geometry_partial_charge", "state": "stale"}`
        # -- the per-atom counterpart of `expect_spectrum`: every held per-atom
        # result whose key contains the text must be in that state, and at
        # least one must be held, so a result that never arrived cannot pass.
        wanted = step.get("expect_per_atom")
        if wanted:
            matching = {key: state for key, state in held.items() if wanted["contains"] in key and not key.startswith("spectrum:")}
            ok = bool(matching) and all(state == wanted["state"] for state in matching.values())
            (logger.warning if ok else logger.error)(
                "OPENCHEM_DRIVE: EXPECT per-atom %s %s %s -- held=%s",
                wanted["contains"], wanted["state"], "ok" if ok else "FAILED", json.dumps(matching),
            )
        # And what PROPERTIES holds, which is the other half of "never
        # arrived": a result there and not here was missed by this panel.
        properties = sorted(getattr(self._window._property_panel, "_retained_results", {}) or {})
        logger.warning(
            "OPENCHEM_DRIVE: inspector %s title=%r pinned=%r held=%s identity=%s properties=%s facts=%s",
            step.get("tag", ""),
            panel.title_text(),
            facts._summary.text(),
            json.dumps(held),
            json.dumps(identity),
            json.dumps(properties),
            json.dumps(rows),
        )

    def _do_units(self, step: dict[str, Any]) -> None:
        """`{"do": "units", "key": "mg_per_ml", "tag": "mg"}` -- choose a unit
        in the reader's Units COMBO, then log what the reader shows.

        **THE COMBO, NOT `set_rendering`.** A user picks an entry; the index
        change is what the view is wired to, so that is what is driven. With
        no `key` it only reports. The log carries the chart's y label and the
        unit-bearing fact rows, because "the unit changed" and "the numbers
        changed with it" photograph the same at a glance.
        """
        view = self._window._results_view._view
        box = view._rendering_box
        key = step.get("key")
        if key:
            index = box.findData(str(key))
            if index < 0:
                logger.error("OPENCHEM_DRIVE: units -- no entry %r (offered: %s)", key,
                             [box.itemData(i) for i in range(box.count())])
                return
            box.setCurrentIndex(index)
        shown = view._report
        charts = getattr(shown, "charts", ()) or ()
        rows = [
            f"{fact.label}={fact.value_with_units}"
            for fact in getattr(shown, "facts", ()) or ()
            if getattr(fact, "rendering", "")
        ]
        logger.warning(
            "OPENCHEM_DRIVE: units %s offered=%s visible=%s current=%s problem=%r "
            "chart_y=%r first_y=%s rows=%s",
            step.get("tag", ""),
            [box.itemText(i) for i in range(box.count())],
            not view._rendering_widget.isHidden(),
            view.rendering(),
            view.rendering_problem(),
            charts[0].y_label if charts else None,
            (charts[0].series[0].points[0][1] if charts and charts[0].series else None),
            json.dumps(rows),
        )

    def _do_chart_cursor(self, step: dict[str, Any]) -> None:
        """`{"do": "chart_cursor", "x": 7.4}` -- CLICK the reader's first line
        chart where `x` is, and log the kept reading beside the scalar fact.

        A real mouse click (`QTest.mouseClick`) at the pixel for `x`, so what
        is measured is the widget's own press handler snapping to a sample --
        the `jobs_cancel` rule. The log puts the reading's numbers next to the
        report's "LogD at pH" fact, because "the cursor at the chosen pH is the
        scalar" is the claim, and a screenshot shows two numbers that merely
        look alike.
        """
        from PySide6.QtCore import QPoint
        from PySide6.QtTest import QTest

        from openchem.ui.widgets.line_chart_widget import LineChartWidget

        view = self._window._results_view._view
        charts = [w for w in view.chart_widgets() if isinstance(w, LineChartWidget)]
        if not charts:
            logger.error("OPENCHEM_DRIVE: chart_cursor -- the reader shows no line chart")
            return
        widget = charts[0]
        widget.window().raise_()
        rect = widget._plot_rect()
        x_min, x_max = widget._x_range()
        fraction = (float(step["x"]) - x_min) / (x_max - x_min)
        pixel = QPoint(int(rect.left() + fraction * rect.width()), int(rect.center().y()))
        QTest.mouseClick(widget, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, pixel)
        pinned = widget.pinned_x()
        scalar = [
            f"{fact.label}={fact.value!r}"
            for fact in getattr(view._report, "facts", ()) or ()
            if fact.label.startswith("LogD at pH")
        ]
        logger.warning(
            "OPENCHEM_DRIVE: chart_cursor asked=%s pinned=%r readout=%s at_pinned=%r scalar=%s",
            step["x"], pinned,
            json.dumps(widget.readout_lines(pinned) if pinned is not None else []),
            widget.readout_at(pinned) if pinned is not None else None,
            scalar,
        )

    def _do_picture(self, step: dict[str, Any]) -> None:
        """Export the reader's Nth chart through the REAL export path.

        `{"do": "picture", "index": 0, "path": "C:/tmp/chart.png"}`

        **NOT A SCREENSHOT OF THE PANEL.** A `shot` photographs the dock and
        would look identical whether the export works or writes a blank
        file, which is the failure mode the export's refusals exist for. So
        this drives `picture_export` itself against the widget the reader
        actually built, and logs what came back -- including whether the
        widget offered a vector form, which no picture can carry.

        The menu is NOT exec'd: `QMenu.exec` spins its own event loop and
        stalls an unattended run, and monkeypatching it does not help
        because it is a C++ slot. The actions it would have called are
        called directly; what is under test is the export, and the menu's
        own assembly is covered by `tests/test_picture_export.py`.
        """
        from openchem.ui.picture_export import is_blank, raster_source, vector_source

        import pathlib as _pathlib

        # `chart_widgets()` reads the charts back OFF THE SECTIONS, so this
        # cannot pass against a chart that never reached the display -- the
        # reason that accessor exists rather than walking the report.
        widgets = self._window._results_view._view.chart_widgets()
        index = int(step.get("index", 0))
        if index >= len(widgets):
            logger.error(
                "OPENCHEM_DRIVE: picture -- the reader has %d chart(s), asked for %d",
                len(widgets), index,
            )
            return
        widget = widgets[index]
        image = raster_source(widget)
        svg = vector_source(widget)
        logger.warning(
            "OPENCHEM_DRIVE: picture %d %s %dx%d blank=%s vector=%s",
            index, type(widget).__name__, image.width(), image.height(),
            is_blank(image), bool(svg),
        )
        path = step.get("path")
        if path:
            image.save(str(path), "PNG")
            logger.warning("OPENCHEM_DRIVE: wrote %s", path)
        if svg and step.get("svg_path"):
            _pathlib.Path(str(step["svg_path"])).write_text(svg, encoding="utf-8")
            logger.warning("OPENCHEM_DRIVE: wrote %s", step["svg_path"])

    def _do_menu(self, step: dict[str, Any]) -> None:
        """Trigger one of THIS application's menu entries, by its text.

        `{"do": "menu", "text": "Rotate 3D"}`

        Distinct from `editor_action`, which presses one of KETCHER's
        toolbar buttons. This walks the real `QMenuBar` and triggers the
        real `QAction`, so what is measured includes the enabled state and
        whatever the action is connected to -- `_do_cip` does the same walk
        and this generalises it rather than adding a third copy.

        Logs the action's own checked state AFTER triggering, because for a
        checkable entry that is the thing most likely to be wrong and the
        thing no screenshot of a closed menu can carry.
        """
        wanted = str(step["text"])
        # `"prefix": true` for an entry whose text names what it acts on --
        # `QUndoStack.createUndoAction` reads "Undo <last command>", so the
        # exact text of Edit > Undo is not known before the run.
        prefix = bool(step.get("prefix"))
        for menu_action in self._window.menuBar().actions():
            menu = menu_action.menu()
            if menu is None:
                continue
            for action in _walk_actions(menu):
                text = action.text().replace("&", "")
                if not (text.startswith(wanted) if prefix else text == wanted):
                    continue
                action.trigger()
                logger.warning(
                    "OPENCHEM_DRIVE: menu %r triggered -- enabled=%s checkable=%s checked=%s",
                    wanted, action.isEnabled(), action.isCheckable(), action.isChecked(),
                )
                return
        logger.error("OPENCHEM_DRIVE: no menu entry named %r", wanted)

    def _do_rotate_report(self, step: dict[str, Any]) -> None:
        """`{"do": "rotate_report"}` -- the tick, the button AND the page.

        The whole of 5c is that the first two must agree, and they are two
        different widgets in two different places on screen: a shot showing
        the banner says nothing about the tick inside a closed menu.

        **AND BOTH OF THEM AGREEING PROVED NOTHING ABOUT THE THIRD.** The
        mode shipped with no way out because leaving un-checked the button
        and the tick and told the PAGE nothing -- so the overlay stayed up,
        `inset:0`, swallowing every click, while both controls correctly
        reported "off". That is the state this step could not see and now
        reads directly: is `.openchem-rotate` still in the document.
        """
        window = self._window
        action = getattr(window, "_rotate_action", None)
        tag = step.get("tag", "")
        menu_checked = None if action is None else action.isChecked()
        button_checked = window._editor.rotation_active()

        def report(overlay_present):
            logger.warning(
                "OPENCHEM_DRIVE: rotate %s menu_checked=%s button_checked=%s "
                "page_overlay=%s agree=%s",
                tag,
                menu_checked,
                button_checked,
                overlay_present,
                menu_checked == button_checked == bool(overlay_present),
            )

        from PySide6.QtWidgets import QApplication

        logger.warning(
            "OPENCHEM_DRIVE: rotate %s escape_enabled=%s active_window=%s focus=%s",
            tag,
            window._editor._rotate_escape.isEnabled(),
            type(QApplication.activeWindow()).__name__,
            type(QApplication.focusWidget()).__name__,
        )
        window._editor._backend._page.runJavaScript(
            "!!document.querySelector('.openchem-rotate')", report
        )

    def _do_key(self, step: dict[str, Any]) -> None:
        """Press a real key at whatever currently has focus.

        `{"do": "key", "key": "F7"}` / `{"do": "key", "key": "Escape"}`

        **`QTest.keyClick`, NOT `sendEvent`.** A shortcut is matched by
        Qt's shortcut map on the way IN from the platform, so an event
        posted straight at a widget runs the widget's handler and no
        shortcut at all -- which would make every one of these pass while
        the key did nothing in the running app.

        **AND IT AIMS AT THE FOCUS WIDGET**, because that is the whole
        question here: `QWebEngineView` renders out of process and accepts
        `ShortcutOverride` for keys the page claims, so "F7 works" and "F7
        works once you have clicked on the canvas" are different answers
        and only one of them is any use.
        """
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication

        name = str(step.get("key", "Escape"))
        key = getattr(Qt, f"Key_{name}", None)
        if key is None:
            logger.warning("OPENCHEM_DRIVE: key %s -- no such key", name)
            return
        # `"modifiers": "ctrl"` (or "ctrl+shift"), for a shortcut such as
        # Ctrl+, -- a bare key could not ask whether one reaches the window.
        modifiers = Qt.KeyboardModifier.NoModifier
        for modifier in filter(None, str(step.get("modifiers", "")).lower().split("+")):
            modifiers |= {
                "ctrl": Qt.KeyboardModifier.ControlModifier,
                "shift": Qt.KeyboardModifier.ShiftModifier,
                "alt": Qt.KeyboardModifier.AltModifier,
            }[modifier]
        # `"close_modal_after_ms": 1500` -- for a key that opens a modal WINDOW.
        # `keyClick` does not return until that window's own `exec()` loop
        # does, so the next step would never be scheduled. Timers still fire
        # inside that loop, so one set now names the modal and closes it.
        if "close_modal_after_ms" in step:
            QTimer.singleShot(int(step["close_modal_after_ms"]), self._window, self._close_modal)
        where = step.get("focus")
        if where == "canvas":
            self._window._center_tabs.setCurrentWidget(self._window._editor)
            self._window._editor._backend.widget().setFocus()
        elif where == "explorer":
            # A REAL widget elsewhere in the window. Leaving focus wherever
            # it happened to be is not the same test: a run with focus
            # NOWHERE reports `focusWidget() is None`, which is a state a
            # person using the application is never in.
            self._window._project_explorer.setFocus()
        target = QApplication.focusWidget() or self._window
        # THE ACTIVE WINDOW IS LOGGED because a window shortcut matches only
        # while its window is active. A run behind another application has
        # none, and then "the key opened nothing" says nothing about the key.
        active = QApplication.activeWindow()
        logger.warning(
            "OPENCHEM_DRIVE: key %s%s -> %s (active window %s)",
            f"{step['modifiers']}+" if step.get("modifiers") else "",
            name,
            type(target).__name__,
            type(active).__name__ if active is not None else None,
        )
        QTest.keyClick(target, key, modifiers)

    def _close_modal(self) -> None:
        """Name the modal window a key opened, then close it. See `_do_key`.

        None is logged too: "the key opened nothing" is the answer to find
        out, when a web page may claim the key before the window's shortcut
        sees it.
        """
        from PySide6.QtWidgets import QApplication

        modal = QApplication.activeModalWidget()
        logger.warning(
            "OPENCHEM_DRIVE: modal open -> %s %r",
            type(modal).__name__ if modal is not None else None,
            modal.windowTitle() if modal is not None else "",
        )
        if modal is not None:
            modal.close()

    def _do_close_dialog(self, _step: dict[str, Any]) -> None:
        """`{"do": "close_dialog"}` -- close what the last `dialog` step opened.

        An open dialog is a window of its own and can be the ACTIVE one, and
        a window shortcut on the main window does not fire while it is. A
        `key` step testing one needs the dialog gone first.
        """
        if getattr(self, "_dialog", None) is not None:
            self._dialog.close()
            self._dialog = None
        logger.warning("OPENCHEM_DRIVE: dialog closed")

    def _do_control(self, step: dict[str, Any]) -> None:
        """Operate one named control of the open dialog, as a person would.

        `{"do": "control", "name": "railHidesPanels", "value": false}`
        `{"do": "control", "name": "maxRevisionsKept", "value": 3}`

        By OBJECT NAME, in the dialog the last `dialog` step opened. A check
        box is set, a spin box is set and its edit FINISHED (a spin box that
        acts on commit acts on that), and a button is clicked. What the
        control then reads is logged beside what was asked, so a control
        that refused the value -- a bound, a question answered No -- says so.
        """
        from PySide6.QtWidgets import QAbstractButton, QCheckBox, QSpinBox, QWidget

        dialog = getattr(self, "_dialog", None)
        name = str(step.get("name", ""))
        if dialog is None:
            logger.error("OPENCHEM_DRIVE: control %s -- no dialog is open", name)
            return
        widget = dialog.findChild(QWidget, name)
        if isinstance(widget, QCheckBox):
            widget.setChecked(bool(step["value"]))
            now = widget.isChecked()
        elif isinstance(widget, QSpinBox):
            widget.setValue(int(step["value"]))
            widget.editingFinished.emit()
            now = widget.value()
        elif isinstance(widget, QAbstractButton):
            widget.click()
            now = "clicked"
        else:
            logger.error(
                "OPENCHEM_DRIVE: control %s -- %s", name,
                "no such control" if widget is None else f"cannot operate a {type(widget).__name__}",
            )
            return
        logger.warning(
            "OPENCHEM_DRIVE: control %s asked %r, now %r", name, step.get("value"), now
        )

    def _do_geometry_report(self, step: dict[str, Any]) -> None:
        """`{"do": "geometry_report", "tag": "after-layout"}`

        Is the DRAWING flat, and are the generated conformers still there.
        **Two different stores, and the distinction is the whole point of
        the back-to-2D work**: redrawing the drawing flat must not throw
        away the conformers the 3D viewer is showing, and zeroing the z
        column is only half of "it is 2D again".
        """
        molecule = self._window._current_molecule()
        if molecule is None:
            logger.warning("OPENCHEM_DRIVE: geometry %s -- no molecule", step.get("tag", ""))
            return
        lines = (molecule.molblock or "").splitlines()
        spread = None
        if len(lines) >= 5:
            try:
                count = int(lines[3][:3])
                zs = [float(lines[4 + i][20:30]) for i in range(count)]
                spread = round(max(zs) - min(zs), 4)
            except (IndexError, ValueError):
                spread = "unreadable"
        logger.warning(
            "OPENCHEM_DRIVE: geometry %s z_spread=%s conformers=%d smiles=%s",
            step.get("tag", ""),
            spread,
            len(molecule.conformers),
            molecule.canonical_smiles,
        )

    def _do_adopt(self, step: dict[str, Any]) -> None:
        """Press the 3D viewer's real "Use in 2D Editor" button.

        `{"do": "adopt"}`

        **THE BUTTON, NOT `_adopt_conformer`.** The handler behind it reads
        the conformer ON SCREEN and takes one camera snapshot, and both of
        those are the thing worth driving -- calling the window's method
        with a molblock chosen here would skip exactly the part that has
        been wrong before.
        """
        self._window._center_tabs.setCurrentWidget(self._window._viewer3d)
        self._window._viewer3d._use_button.click()

    def _do_structure_pick(self, step: dict[str, Any]) -> None:
        """Pick the Nth structure in a set result and press the REAL button.

        `{"do": "structure_pick", "id": "tautomers", "index": 1}`

        **THE GRID CELL AND THE BUTTON, not the callback behind them.** What
        is being asked here is whether a reader can get a generated tautomer
        into the editor at all, and the answer lives in which controls exist
        and what pressing them leaves on screen -- not in whether a method
        works when called directly.
        """
        from openchem.ui.dialogs.calculator_inspector_dialog import CalculatorInspectorDialog

        dialog = getattr(self, "_inspector", None)
        if dialog is None:
            logger.error("OPENCHEM_DRIVE: structure_pick needs an `inspect` step first")
            return
        grid = dialog._view
        index = int(step.get("index", 0))
        grid._on_cell_clicked(index)
        buttons = [
            b.text()
            for b in dialog.findChildren(type(dialog._add_button))
            if b.text()
        ]
        before = len(self._window._session.project.molecules)
        dialog._add_button.click()
        after = len(self._window._session.project.molecules)
        logger.warning(
            "OPENCHEM_DRIVE: structure_pick index=%d buttons=%s molecules %d -> %d "
            "centre_tab=%r selected=%r",
            index,
            buttons,
            before,
            after,
            self._window._center_tabs.tabText(self._window._center_tabs.currentIndex()),
            self._window._session.project.molecules[-1].display_name,
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

        Surfaces: `properties`, `batch` and `compare` (each panel, against
        its scroll viewport -- see `_enclosing_scroll_area` for why the
        three do not find that viewport the same way), `window`, and any
        dialog `shot` can already reach -- `dialog`, `lewis`, `periodic`,
        `details`, `spatial`, `popout`.

        **A SURFACE WITH NO SINGLE SCROLL AREA IS JUDGED AGAINST ITS OWN
        RECTANGLE, WHICH MAKES THE OVERFLOW TERM NEARLY VACUOUS THERE** --
        a child is inside its parent by construction unless something
        positioned it outside. Said out loud rather than left to be
        discovered: on such a surface the useful predicates are the other
        three, and a clean overflow result is close to a tautology.
        """
        from PySide6.QtCore import QPoint, QRect
        from PySide6.QtWidgets import QScrollArea

        from openchem.ui import visual_check

        name = str(step.get("surface", "properties"))
        tag = str(step.get("tag", name))
        root = self._surface(name)
        if root is None:
            return

        # THE SCROLL AREA IS SOMETIMES INSIDE THE SURFACE AND SOMETIMES
        # AROUND IT, and the difference decides whether the overflow term
        # measures anything at all. `PropertyPanel` builds its own
        # (`property_panel.py` does `panel.findChild(QScrollArea)`), so the
        # viewport is a DESCENDANT. `BatchPanel` and `ComparisonPanel` are
        # handed to `MainWindow._wrap_scrollable`, so their viewport is an
        # ANCESTOR -- and a downward-only search finds none, leaves `bounds`
        # at None, and judges the panel against its own rectangle, which is
        # the near-tautology this step's docstring already warns about.
        bounds = None
        areas = root.findChildren(QScrollArea)
        if len(areas) == 1:
            root = areas[0].viewport()
            bounds = root.rect()
        else:
            enclosing = self._enclosing_scroll_area(root)
            if enclosing is not None:
                # Mapped INTO the surface's own coordinates rather than
                # taken as `viewport.rect()`: the walk reports item
                # geometry in `space` coordinates, and with the panel
                # scrolled down by N its origin sits at -N in the
                # viewport, so an unmapped rect would judge every row
                # against a window N pixels off.
                viewport = enclosing.viewport()
                bounds = QRect(root.mapFrom(viewport, QPoint(0, 0)), viewport.size())

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

    @staticmethod
    def _enclosing_scroll_area(widget):
        """The `QScrollArea` this widget is the scrolled CONTENT of, if any.

        Deliberately not "the nearest scroll-area ancestor": a panel holding
        a `QTableWidget` sits under that table's own viewport for some
        descendants, and answering with it would judge the panel against a
        window belonging to one of its children. `area.widget() is widget`
        is the question that means "this area scrolls THIS surface".
        """
        from PySide6.QtWidgets import QScrollArea

        parent = widget.parentWidget()
        while parent is not None:
            if isinstance(parent, QScrollArea) and parent.widget() is widget:
                return parent
            parent = parent.parentWidget()
        return None

    def _surface(self, name: str):
        """Resolve a surface name to a widget, or log why it could not be.

        A name that matches nothing is LOGGED rather than ignored. A silent
        no-op here would photograph the wrong thing while the log looked
        perfectly healthy, which is the wrong-panel-id trap this harness has
        already been caught by once.
        """
        if name == "properties":
            return self._window._property_panel
        if name == "results":
            # The reader itself, never the dock or the scroll wrapper around
            # it: the oracle maps painted items into the surface's own
            # rectangle, and handing it the wrapper would measure the
            # viewport rather than the thing laid out inside it.
            return self._window._results_view
        if name == "batch":
            return self._window._batch_panel
        if name == "compare":
            return self._window._comparison_panel
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
            from openchem.domain.structure_resolution import ResolvedStructure
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

    def _do_depiction(self, step: dict[str, Any]) -> None:
        """Open a declared DEPICTION in a FactView, with a structure to draw on.

        `{"do": "depiction", "calculator": "lewis_sites", "smiles": "CS(C)=O"}`,
        then `{"do": "shot", "widget": "dialog"}`.

        **IT SUPPLIES THE RENDER CONTEXT THE WAY A HOST DOES**, through
        `FactView.set_structure_resolver`, rather than handing the widget
        a molblock directly. The annotation carries atom indices and no
        geometry on purpose, so the thing worth photographing is whether
        the resolution actually happens -- a view with no resolver draws a
        sentence, which is correct and is NOT the picture.

        It LOGS what was declared and whether a picture resulted, because
        the three states photograph identically at a glance: nothing
        declared, declared with no structure to draw on, and drawn.
        """
        from openchem.domain.molecule import MoleculeModel
        from openchem.domain.report import valid_chart_annotation
        from openchem.domain.structure_resolution import ResolvedStructure
        from openchem.ui.widgets.depiction_widget import DepictionWidget
        from openchem.ui.widgets.fact_view import FactView

        self._dialog = None
        registry = self._window._services.calculator_registry
        wanted = str(step.get("calculator", ""))
        definition = registry.get(wanted)
        compute = getattr(getattr(definition, "execution", None), "compute", None)
        if compute is None:
            logger.error("OPENCHEM_DRIVE: no in-process calculator %r", wanted)
            return

        # THROUGH THE ENGINE, never `import rdkit` -- `app/` and `ui/` may
        # not import a chemistry toolkit directly, which
        # `tests/test_layering.py` holds and which caught the first draft
        # of this step. `_do_smiles` goes the same way.
        engine = self._window._services.chemistry_engine
        molecule = MoleculeModel(display_name=str(step.get("smiles", "")))
        try:
            engine.set_structure_from_smiles(molecule, str(step.get("smiles", "")))
        except Exception as exc:
            logger.error("OPENCHEM_DRIVE: could not build %r: %s", step.get("smiles"), exc)
            return
        molblock = molecule.molblock
        mol = engine.mol_from_molblock(molblock)
        report = compute(mol, "drive-uuid", dict(step.get("parameters") or {}))

        charts = tuple(getattr(report, "charts", ()) or ())
        logger.warning(
            "OPENCHEM_DRIVE: depiction tag=%s calculator=%s facts=%d charts=%d",
            step.get("tag", ""),
            wanted,
            len(report.facts),
            len(charts),
        )
        for chart in charts:
            layer = getattr(chart, "layer", None)
            logger.warning(
                "OPENCHEM_DRIVE:   chart %s valid=%s atoms=%s labels=%s",
                type(chart).__name__,
                valid_chart_annotation(chart),
                None if layer is None else layer.atom_colors,
                None if layer is None else layer.atom_labels,
            )

        dialog = QDialog(self._window)
        dialog.setWindowTitle(f"{report.name} - declared depiction")
        dialog.resize(520, 640)
        view = FactView(dialog)
        # Takes the REPORT now, not a uuid -- see `set_structure_resolver`.
        # This harness resolves unconditionally because it is showing the
        # depiction it was asked to show; a production host refuses a stale
        # one, which is what `resolve_structure_for_report` is for.
        view.set_structure_resolver(lambda _report: ResolvedStructure.of(molblock))
        view.set_report(report, title=report.name)
        layout = QVBoxLayout(dialog)
        layout.addWidget(view)
        dialog.show()
        self._dialog = dialog

        drawn = [w for w in view.chart_widgets() if isinstance(w, DepictionWidget)]
        logger.warning(
            "OPENCHEM_DRIVE:   rendered depiction widgets=%d drawing=%s",
            len(drawn),
            [w.is_drawing() for w in drawn],
        )

    def _do_crystal_report(self, step: dict[str, Any]) -> None:
        """Open a CIF's crystal report, for a screenshot of its chart.

        `{"do": "crystal_report", "path": "tests/fixtures/cif/1504676.cif"}`,
        then `{"do": "shot", "path": "...", "widget": "dialog"}`.

        **IT GOES THROUGH `MainWindow.crystal_report_dialog`**, which
        already returns the dialog UNSHOWN precisely so a run can drive
        and photograph it. Building a `FactView` here instead would prove
        the widget renders and say nothing about whether the window a
        user opens carries the chart -- and "the report declares no
        chart" survived seven guards on the builder before a test asked
        the report itself.

        **IT LOGS WHAT THE REPORT DECLARED**, because three states of
        this feature photograph identically once the chart section is
        scrolled past: no chart declared, a chart declared and refused by
        the validator, and a chart drawn. `charts=0` and a log line
        naming the caption are the halves no crop can carry.
        """
        from openchem.chem.cif import read_cif
        from openchem.chem.crystal_report import build_crystal_report
        from openchem.domain.report import valid_chart_annotation

        self._dialog = None
        path = Path(str(step["path"]))
        if not path.is_absolute():
            path = Path.cwd() / path
        if not path.is_file():
            logger.error("OPENCHEM_DRIVE: no CIF at %s", path)
            return
        report = build_crystal_report(read_cif(path.read_text(encoding="utf-8")))
        charts = tuple(getattr(report, "charts", ()) or ())
        logger.warning(
            "OPENCHEM_DRIVE: crystal_report tag=%s file=%s facts=%d charts=%d",
            step.get("tag", ""),
            path.name,
            len(report.facts),
            len(charts),
        )
        # **THE CHARGE ROWS BY NAME, BECAUSE THEY ARE THE ONE SECTION THAT
        # CAN BE ABSENT FOR FOUR DIFFERENT REASONS** -- computed, refused
        # for disorder, refused for an element, or skipped over the report's
        # atom budget -- and a screenshot of a scrolled report shows the
        # same nothing for the last three. `value=None` separates a refusal
        # from a result; the display string says which refusal.
        for fact in report.facts:
            if "EQeq" in fact.label or fact.label in ("  Charge balance",):
                logger.warning(
                    "OPENCHEM_DRIVE:   charges label=%r value=%r %s",
                    fact.label, fact.value, fact.display_value,
                )
        for chart in charts:
            logger.warning(
                "OPENCHEM_DRIVE:   chart valid=%s sticks=%d x=%r desc=%s title=%r",
                valid_chart_annotation(chart),
                len(chart.sticks),
                f"{chart.x_label} {chart.x_units}".strip(),
                chart.x_descending,
                chart.title,
            )
            logger.warning("OPENCHEM_DRIVE:   caption %s", chart.caption)
        dialog = self._window.crystal_report_dialog(report, path.name)
        dialog.show()
        self._dialog = dialog

        # **A SECTION THE READER WOULD HAVE TO CLICK, OPENED SO A SHOT CAN
        # SEE IT.** The crystal report opens with Identity expanded and
        # Structure -- 35 facts, the charges among them -- collapsed, which
        # is exactly the state `FactView`'s own comment records four facts
        # hiding behind. Driven through `set_expanded` on the real section
        # the real dialog built, so what is photographed is the widget a
        # click would have opened.
        wanted = step.get("expand")
        text = step.get("filter")
        if wanted or text:
            from openchem.ui.widgets.fact_view import FactView

            view = dialog.findChild(FactView)
            # THE FILTER BOX ITSELF, not `_render` behind it: typing is what a
            # reader does to reach one row of a 59-fact report, and the
            # rendering that follows is the thing a shot is being taken of.
            if text:
                view.search_box().setText(str(text))
                logger.warning("OPENCHEM_DRIVE:   filtered %r", text)
            sections = getattr(view, "_sections", {})
            section = sections.get(str(wanted)) if wanted else None
            if wanted and section is None:
                logger.error("OPENCHEM_DRIVE: no report section %r; have %s",
                             wanted, sorted(sections))
            elif section is not None:
                section.set_expanded(True)
                logger.warning("OPENCHEM_DRIVE:   expanded %r -> %s",
                               wanted, section.is_expanded())

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
            dialog_names,
            iter_dialog_fixtures,
        )

        window = self._window
        wanted = str(step.get("name", ""))
        # CLEARED FIRST, and this is not tidiness. A `shot` step targets
        # `self._dialog`, so a step that fails while the previous dialog is
        # still held photographs THAT one and the run looks healthy -- the
        # same silent no-op the `panel` step's wrong-id trap produces, and
        # the reason this file says to read the shot rather than the log.
        # And CLOSED, not only dropped: a script opening one dialog per page
        # left every earlier one open on screen, each a window of its own.
        if getattr(self, "_dialog", None) is not None:
            self._dialog.close()
        self._dialog = None
        fixture = next((f for f in iter_dialog_fixtures() if f.name == wanted), None)
        if fixture is None:
            logger.error(
                "OPENCHEM_DRIVE: no dialog %r (have %s)",
                wanted,
                dialog_names(),
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
        # `"section": "results"` -- the Settings window's pages are a list,
        # not tabs, so `tab` below cannot reach them. By id, through the
        # window's own `show_section`, which RAISES on an unknown one; the
        # refusal is logged, never photographed as page 0.
        wanted_section = str(step.get("section", ""))
        if wanted_section:
            show_section = getattr(dialog, "show_section", None)
            if show_section is None:
                logger.error("OPENCHEM_DRIVE: %s has no sections", wanted)
            else:
                try:
                    show_section(wanted_section)
                except ValueError as exc:
                    logger.error("OPENCHEM_DRIVE: %s", exc)
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
            "OPENCHEM_DRIVE: dialog %s open at %dx%d, tab %r, section %r",
            wanted,
            dialog.width(),
            dialog.height(),
            wanted_tab or "(default)",
            dialog.current_section() if hasattr(dialog, "current_section") else "(none)",
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

    def _do_atom_numbers(self, step: dict[str, Any]) -> None:
        """`{"do": "atom_numbers", "mode": "locants"}` -- the View menu's
        Atom Numbers mode, then what the PAGE drew.

        The mode is set through `MoleculeEditorWidget.set_atom_number_mode`,
        which is what the menu action calls, and the report comes from the
        page rather than from Python: the failure this guards against is a
        number drawn on the atom one position over, which no screenshot
        shows and which Python's own view of the labels cannot see. The two
        id spaces agree on a freshly loaded structure and diverge after an
        edit, so the interesting run is the one with an `erase` in it.
        """
        window = self._window
        editor = window._editor
        mode = str(step.get("mode", "off"))
        editor.set_atom_number_mode(mode)
        tag = step.get("tag", mode)
        backend = editor._backend
        report = getattr(backend, "atom_number_report", None)
        if report is None:
            logger.error("OPENCHEM_DRIVE: this backend cannot report atom numbers")
            return
        report(
            lambda state: logger.warning(
                "OPENCHEM_DRIVE: atom_numbers[%s] mode=%s page=%s", tag, mode, state
            )
        )

    def _do_process_report(self, step: dict[str, Any]) -> None:
        """`{"do": "process_report", "modules": ["openchem.chem.engine"]}` --
        which process this is, and which source tree each named module came from.

        **A MIXED-MODULE PROCESS LOOKS EXACTLY LIKE A CODE BUG.** Measured
        2026-09-17: an app left running across a merge raised
        `render_2d_svg() got an unexpected keyword argument 'emphasised_atom'`,
        because `engine.py` was imported before the merge and the inspector
        dialog after it. The traceback named a real call and a real
        signature; only the module paths and the commit say whether the
        process and the checkout agree. Modules not yet imported are imported
        here, which is what the dialog's own lazy import would do.
        """
        import importlib
        import subprocess
        import sys

        head = ""
        try:
            head = subprocess.run(
                ["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            ).stdout.strip()
        except Exception:  # noqa: BLE001 - a report must not stop the run
            pass
        logger.warning(
            "OPENCHEM_DRIVE: process_report pid=%d cwd=%s head=%s python=%s",
            os.getpid(), os.getcwd(), head or "?", sys.executable,
        )
        for name in step.get("modules") or []:
            try:
                module = importlib.import_module(str(name))
                logger.warning("OPENCHEM_DRIVE: process_report module %s -> %s", name, module.__file__)
            except Exception as exc:  # noqa: BLE001
                logger.error("OPENCHEM_DRIVE: process_report module %s failed: %s", name, exc)

    # -- the verdict ---------------------------------------------------------

    def _record_assertion(self, step: str, tag: str, ok: bool, detail: str) -> bool:
        self._assertions.append({"step": step, "tag": tag, "ok": ok, "detail": detail})
        return ok

    def _do_log_report(self, step: dict[str, Any]) -> None:
        """`{"do": "log_report", "tag": "after-draw"}` -- what the APPLICATION
        has logged so far, de-duplicated by where it happened.

        Read-only: it asserts nothing. `expect_clean` is the assertion.
        """
        logger.warning("OPENCHEM_DRIVE: log_report[%s]", step.get("tag", ""))
        for line in self._ledger.summary_lines(self._allow):
            logger.warning("OPENCHEM_DRIVE: ledger %s", line)

    def _do_expect_clean(self, step: dict[str, Any]) -> None:
        """`{"do": "expect_clean", "allow": ["substring", ...], "warnings": false}`
        -- FAILS the run if the application has logged an ERROR that nothing in
        `allow` excuses (with `"warnings": true`, a WARNING too).

        **NEVER A PASS ON ITS OWN.** A ledger is empty when logging is off,
        when the failing code never ran, and when the script never drew the
        molecule that breaks it. Pair it with `expect_results`, which asserts
        what the panels HOLD; together they say "it ran, it produced this, and
        it said nothing was wrong".

        `allow` accumulates across the run: an excuse given here also covers
        the final verdict, so a known error is named once.
        """
        self._allow.extend(str(a) for a in step.get("allow") or [])
        unexpected = self._ledger.unexpected(self._allow, include_warnings=bool(step.get("warnings")))
        tag = str(step.get("tag", ""))
        if not self._record_assertion(
            "expect_clean", tag, not unexpected,
            "; ".join(f"x{e.count} {e.text()}" for e in unexpected) or "no unexpected application errors",
        ):
            logger.error(
                "OPENCHEM_DRIVE: EXPECT clean FAILED[%s] -- %d unexpected: %s",
                tag, len(unexpected), "; ".join(f"x{e.count} {e.text()}" for e in unexpected)[:600],
            )
        else:
            logger.warning("OPENCHEM_DRIVE: EXPECT clean ok[%s]", tag)

    def _do_expect_results(self, step: dict[str, Any]) -> None:
        """`{"do": "expect_results", "expect": {"<calculator or alert id>": ...}}`
        -- what Properties HOLDS for the selected molecule, asserted.

        Each entry is a status name, a list of acceptable ones, or an object:

            "status"        one name or a list, from `RESULT_STATUSES`
            "not_status"    names that must NOT be the status
            "refusal"       the refusal code ("" asserts a computed result)
            "missing_inputs" the calculator's own parameter names a NEEDS_INPUT
                            result must name, in any order and no others --
                            what the chip's click target is built from
            "partial"       true/false: whether the result recorded that it
                            SKIPPED something (`domain.completeness`); an
                            entry with no record at all is not partial
            "facts_contain" substrings that must each appear in some `label=value`
            "facts_absent"  substrings that must appear in none

        **THIS IS THE HALF THAT KEEPS `expect_clean` HONEST.** A molecule whose
        alerts silently never arrived logs an ERROR, but one whose alerts
        arrive EMPTY logs nothing, and the panel is what shows the difference.
        A calculator still running is named as such and is not called a failure:
        give the step before it more `after_ms`.
        """
        panel = self._window._property_panel
        tag = str(step.get("tag", ""))
        problems: list[str] = []
        for calculator_id, wanted in (step.get("expect") or {}).items():
            spec = {"status": wanted} if isinstance(wanted, (str, list)) else dict(wanted)
            status = panel._status_for(calculator_id)
            result = panel._result_for(calculator_id)
            provenance = getattr(result, "provenance", None)
            parameters = dict(getattr(provenance, "parameters", {}) or {})
            facts = [
                f"{getattr(f, 'label', '')}={getattr(f, 'display_value', '')}"
                for f in (getattr(result, "facts", ()) or ())
            ]
            allowed = spec.get("status")
            allowed = [allowed] if isinstance(allowed, str) else list(allowed or [])
            if allowed and status not in allowed:
                hint = " (still running: give the step before this more after_ms)" if status == "running" else ""
                problems.append(f"{calculator_id}: status {status!r}, wanted {allowed}{hint}")
            if status in (spec.get("not_status") or []):
                problems.append(f"{calculator_id}: status is {status!r}, which was ruled out")
            if "refusal" in spec and parameters.get("refusal", "") != spec["refusal"]:
                problems.append(
                    f"{calculator_id}: refusal {parameters.get('refusal', '')!r}, wanted {spec['refusal']!r}"
                )
            if "partial" in spec:
                from openchem.domain.completeness import is_partial

                if is_partial(result) != bool(spec["partial"]):
                    problems.append(
                        f"{calculator_id}: partial is {is_partial(result)}, wanted {bool(spec['partial'])}"
                    )
            if "missing_inputs" in spec:
                from openchem.domain.refusal_kinds import missing_inputs_of

                named = sorted(item.parameter for item in missing_inputs_of(result))
                if named != sorted(spec["missing_inputs"]):
                    problems.append(
                        f"{calculator_id}: names missing inputs {named}, wanted {sorted(spec['missing_inputs'])}"
                    )
            for needle in spec.get("facts_contain") or []:
                if not any(needle in fact for fact in facts):
                    problems.append(f"{calculator_id}: no fact contains {needle!r} (facts: {facts[:8]})")
            for needle in spec.get("facts_absent") or []:
                if any(needle in fact for fact in facts):
                    problems.append(f"{calculator_id}: a fact contains {needle!r}, which was ruled out")
        if self._record_assertion("expect_results", tag, not problems, "; ".join(problems) or "as expected"):
            logger.warning("OPENCHEM_DRIVE: EXPECT results ok[%s]", tag)
        else:
            logger.error("OPENCHEM_DRIVE: EXPECT results FAILED[%s] -- %s", tag, "; ".join(problems)[:800])

    def _do_edit_burst(self, step: dict[str, Any]) -> None:
        """`{"do": "edit_burst", "structures": ["CCO", "CCCO"], "edits": 20, "gap_ms": 150, "tag": "..."}`
        -- what a person DRAWING costs the application, measured.

        **THIS IS THE BASELINE A DEBOUNCED RECOMPUTE HAD TO BEAT, AND NOW THE PROOF
        THAT IT DID.** Every canvas edit runs the parse, the SMILES, the InChI and
        InChIKey and used to fan `MoleculeChanged` out to every descriptor provider, so
        drawing a molecule lagged. This records what that costs: the latency of each edit's
        synchronous part, the longest stretch the event loop was blocked, and how many
        recalculations one burst caused.

        It applies each edit by calling `MoleculeEditorWidget.apply_edited_molblock` --
        the very method the editor calls once Ketcher has reported a molfile, so the
        measurement cannot drift from what drawing does -- either growing a structure
        (`grow`, a NEW structure each edit: what drawing is) or alternating between
        `structures` (undo/redo, which the result store replays). **WHAT IT DOES NOT
        MEASURE**: Ketcher's own JS and the bridge back to Python, which a debounce does
        not touch. Recorded, in the log and in the report's `measurements`; nothing is
        asserted on a number, because these depend on the machine. The structure is
        restored afterwards.

        `"recalc": {"mode": 0, "quiet_ms": 800}` sets the recalculation policy for the
        burst (0 while drawing, 1 after a pause, 2 only when asked) and RESTORES the
        person's own setting afterwards; without it the setting in force is measured.
        After the last edit the step waits out the pause, so the recomputation the burst
        earned is counted; with "only when I ask" it presses Recalculate Now only if
        `"then_recalculate": true`.
        """
        import statistics
        import time

        from PySide6.QtWidgets import QApplication

        from openchem.chem.engine import ChemistryEngine
        from openchem.events.events import (
            AlertComputed,
            DescriptorComputed,
            MoleculeChanged,
            PerAtomDataComputed,
            ResultRecorded,
        )
        from openchem.services.descriptor_service import DescriptorService, _DescriptorComputeTask

        tag = str(step.get("tag", ""))
        window = self._window
        editor = window._editor
        molecule = window._session.project.find_molecule(window._property_panel._selected_molecule_uuid)
        if molecule is None or not molecule.molblock:
            logger.error("OPENCHEM_DRIVE: edit_burst needs a selected molecule with a drawing")
            return
        engine = window._services.chemistry_engine
        edits = int(step.get("edits", 20))
        grow = str(step.get("grow", ""))
        if grow:
            # A NEW STRUCTURE EVERY EDIT, which is what drawing is: `base + "C" * n`.
            # Alternating two structures is dominated by the result store REPLAYING what it
            # already holds (measured: one recompute for twenty edits), which is undo and
            # redo, not drawing -- so both are measured, and named for what they are.
            structures = [grow + "C" * (i + 1) for i in range(edits)]
        else:
            structures = [str(x) for x in step.get("structures") or []]
        if len(structures) < 2:
            logger.error("OPENCHEM_DRIVE: edit_burst needs two structures to alternate between, or `grow`")
            return
        molblocks = [engine.mol_to_molblock(engine.mol_from_smiles(smiles)) for smiles in structures]
        gap_s = int(step.get("gap_ms", 150)) / 1000.0
        # THE PERSON'S OWN SETTING IS PUT BACK. A benchmark that leaves the recalculation
        # policy changed would change how the application behaves for the next run.
        from openchem.app.settings import RECALC_MODE, RECALC_QUIET_MS

        settings = window._settings
        kept_policy = (settings.preference(RECALC_MODE), settings.preference(RECALC_QUIET_MS))
        wanted = step.get("recalc") or {}
        if "mode" in wanted:
            settings.set_preference(RECALC_MODE, int(wanted["mode"]))
        if "quiet_ms" in wanted:
            settings.set_preference(RECALC_QUIET_MS, int(wanted["quiet_ms"]))
        policy = settings.recalc_policy()
        original_molblock = molecule.molblock
        bus = window._services.event_bus

        counts = {"molecule_changed": 0, "descriptor_events": 0, "results_recorded": 0}
        bus.subscribe(MoleculeChanged, lambda e: counts.__setitem__("molecule_changed", counts["molecule_changed"] + 1))
        for event_type in (DescriptorComputed, AlertComputed, PerAtomDataComputed):
            bus.subscribe(event_type, lambda e: counts.__setitem__("descriptor_events", counts["descriptor_events"] + 1))
        bus.subscribe(ResultRecorded, lambda e: counts.__setitem__("results_recorded", counts["results_recorded"] + 1))

        # Counted by wrapping, and put back in the `finally`: the wrappers must not
        # outlive the measurement.
        calls = {"request_descriptors": 0, "descriptor_tasks": 0, "canonicalize": 0}
        originals = {
            "request_descriptors": DescriptorService.request_descriptors,
            "descriptor_tasks": _DescriptorComputeTask.run,
            "canonicalize": ChemistryEngine.canonicalize,
        }

        def counting(name, function):
            def wrapper(*args, **kwargs):
                calls[name] += 1
                return function(*args, **kwargs)
            return wrapper

        DescriptorService.request_descriptors = counting("request_descriptors", originals["request_descriptors"])
        _DescriptorComputeTask.run = counting("descriptor_tasks", originals["descriptor_tasks"])
        ChemistryEngine.canonicalize = counting("canonicalize", originals["canonicalize"])

        # The event loop's own heartbeat: a 5 ms timer whose gaps say how long the
        # loop was blocked. Gaps are measured between firings, so a blocked edit shows
        # as one long gap, which is what "the canvas froze" is.
        gaps: list[float] = []
        last = [time.perf_counter()]

        def beat() -> None:
            now = time.perf_counter()
            gaps.append((now - last[0]) * 1000.0)
            last[0] = now

        heartbeat = QTimer()
        heartbeat.setInterval(5)
        heartbeat.timeout.connect(beat)

        def pump(seconds: float) -> None:
            deadline = time.perf_counter() + seconds
            while time.perf_counter() < deadline:
                QApplication.processEvents()
                time.sleep(0.002)

        latencies: list[float] = []
        pushed = 0
        started = time.perf_counter()
        # `"profile": true` runs the burst under cProfile and logs where the time went --
        # the GUI thread's own work (event delivery, the reader's rebuilds) included,
        # because that is the thread a person is waiting on. It slows the run, so the
        # numbers it prints are proportions, not the burst's latency.
        profiler = None
        if step.get("profile"):
            import cProfile

            profiler = cProfile.Profile()
            profiler.enable()
        try:
            heartbeat.start()
            last[0] = time.perf_counter()
            for index in range(edits):
                molblock = molblocks[index] if grow else molblocks[(index + 1) % len(molblocks)]
                t0 = time.perf_counter()
                editor.apply_edited_molblock(molblock)
                pushed += 1
                latencies.append((time.perf_counter() - t0) * 1000.0)
                pump(gap_s)
            # THE RECOMPUTATION THE BURST EARNED. With a pause it has not started yet when
            # the last edit lands, so wait the pause out (plus a margin) before counting.
            delay = policy.delay_ms()
            scheduler = window._services.recalc_scheduler
            if delay is None and step.get("then_recalculate") and scheduler is not None:
                scheduler.recalculate_now()
            elif delay is not None:
                pump(delay / 1000.0 + 0.5)
            # What the burst left in flight: worker results still arriving on the GUI thread.
            from PySide6.QtCore import QThreadPool

            QThreadPool.globalInstance().waitForDone(60_000)
            pump(0.5)
        finally:
            if profiler is not None:
                profiler.disable()
            heartbeat.stop()
            settings.set_preference(RECALC_MODE, int(kept_policy[0]))
            settings.set_preference(RECALC_QUIET_MS, int(kept_policy[1]))
            DescriptorService.request_descriptors = originals["request_descriptors"]
            _DescriptorComputeTask.run = originals["descriptor_tasks"]
            ChemistryEngine.canonicalize = originals["canonicalize"]
            for _ in range(pushed):
                editor._undo_stack.undo()
            molecule.molblock = original_molblock
            editor.set_molecule(molecule)
        total_ms = (time.perf_counter() - started) * 1000.0
        if profiler is not None:
            import io
            import pstats

            for sort, limit in (("cumulative", 45), ("tottime", 20)):
                out = io.StringIO()
                stats = pstats.Stats(profiler, stream=out).sort_stats(sort)
                stats.print_stats("openchem", limit) if sort == "cumulative" else stats.print_stats(limit)
                logger.warning("OPENCHEM_DRIVE: edit_burst[%s] profile by %s\n%s", tag, sort, out.getvalue())

        ordered = sorted(latencies)

        def percentile(fraction: float) -> float:
            return ordered[min(len(ordered) - 1, int(fraction * len(ordered)))] if ordered else 0.0

        stalls = [g - 5.0 for g in gaps if g > 5.0]
        result = {
            "mode": "new structure each edit" if grow else "alternating (results replayed)",
            "recalc": {"mode": int(policy.mode), "quiet_ms": policy.quiet_ms},
            "edits": edits, "gap_ms": int(step.get("gap_ms", 150)),
            "edit_ms": {
                "median": round(statistics.median(latencies), 1) if latencies else 0.0,
                "p95": round(percentile(0.95), 1), "max": round(max(latencies), 1) if latencies else 0.0,
            },
            "loop_blocked_ms": {
                "max": round(max(stalls), 1) if stalls else 0.0,
                "over_30ms": sum(1 for g in stalls if g > 30.0),
                "over_100ms": sum(1 for g in stalls if g > 100.0),
            },
            **counts, **calls, "total_ms": round(total_ms),
        }
        self._measurements[tag or "edit_burst"] = result
        logger.warning("OPENCHEM_DRIVE: edit_burst[%s] %s", tag, json.dumps(result))

    def _do_expect_help(self, step: dict[str, Any]) -> None:
        """`{"do": "expect_help", "topic": "calc-joback-properties"}` -- which help
        topic is in front, asserted.

        Looks at the help window a Settings page or a calculator dialog opened
        (a CHILD of that dialog, because a modal dialog blocks any other window),
        and failing that at the main window's own. "It opened" is not the claim:
        the claim is that it opened ON the section it should have.
        """
        tag = str(step.get("tag", ""))
        wanted = str(step.get("topic", ""))
        candidates = []
        dialog = getattr(self, "_dialog", None)
        page = getattr(dialog, "calculators_page", None)
        for owner in (page, dialog, self._window):
            for attribute in ("_help_window", "_help_dialog"):
                window = getattr(owner, attribute, None)
                if window is not None:
                    candidates.append(window)
        shown = [w for w in candidates if w.isVisible()]
        found = str(getattr(shown[0], "_current_key", "")) if shown else ""
        ok = bool(shown) and found == wanted
        detail = "as expected" if ok else (
            f"help window shows {found!r}" if shown else "no help window is open"
        ) + f", wanted {wanted!r}"
        if self._record_assertion("expect_help", tag, ok, detail):
            logger.warning("OPENCHEM_DRIVE: EXPECT help ok[%s]", tag)
        else:
            logger.error("OPENCHEM_DRIVE: EXPECT help FAILED[%s] -- %s", tag, detail)

    def _do_chip(self, step: dict[str, Any]) -> None:
        """`{"do": "chip", "calculator": "detonation", "expect": {...}}` -- press one
        calculator's status chip, and assert WHERE THE PRESS WENT.

            "status"    the launcher word the chip must be showing first
            "needed"    (needs_input) substrings the settings dialog's "Needs:" line carries
            "focus"     (needs_input) the parameter the cursor was put on
            "shot"      a path to photograph the dialog to, before it is closed
            "tool"      (needs_setup) the External Tools tab Settings must open on

        The chip is a real `QPushButton`, so this presses it (`click()`): the panel's own
        handler reads `sender()`, and calling the handler directly would prove nothing
        about the wiring. Pressing opens a MODAL dialog whose `exec()` does not return
        until it closes, so a timer inspects and closes it -- the same shape as `key`'s
        `close_modal_after_ms`, for the same reason.

        **THE SETUP CASE IS ONLY AS GOOD AS THE MACHINE**: it needs the calculator to be
        unconfigured (the experimental NMR database not built, no pKa sidecar). On a
        machine where it is set up the chip reads Ready and the step fails its `status`
        check by saying so, which is the truthful answer rather than a skipped one.
        """
        tag = str(step.get("tag", ""))
        calculator_id = str(step["calculator"])
        expect = dict(step.get("expect") or {})
        panel = self._window._property_panel
        chip = panel._calculator_status.get(calculator_id)
        if chip is None:
            logger.error("OPENCHEM_DRIVE: chip: no chip for %r", calculator_id)
            return
        status = panel._status_for(calculator_id)
        wanted = expect.get("status")
        if wanted is not None and status != wanted:
            detail = f"{calculator_id} chip reads {status!r}, wanted {wanted!r}"
            self._record_assertion("chip", tag, False, detail)
            logger.error("OPENCHEM_DRIVE: EXPECT chip FAILED[%s] -- %s", tag, detail)
            return
        self._chip_expectation = (tag, calculator_id, expect)
        QTimer.singleShot(int(step.get("inspect_after_ms", 700)), self._window, self._inspect_chip_modal)
        chip.click()

    def _do_reveal_row(self, step: dict[str, Any]) -> None:
        """`{"do": "reveal_row", "calculator": "orca.nmr"}` -- scroll a Properties row into view.

        A photograph of the launcher shows only what the scroll area does, and the sections at
        the bottom (Docking, Quantum Chemistry) are below the fold in a docked column. Works for
        a registry row and for a row that opens another panel; the section is expanded first.
        """
        from PySide6.QtWidgets import QScrollArea

        panel = self._window._property_panel
        calculator_id = str(step["calculator"])
        widget = panel._service_rows.get(calculator_id) or panel._calculator_rows.get(calculator_id)
        if widget is None:
            logger.error("OPENCHEM_DRIVE: reveal_row: no row for %r", calculator_id)
            return
        definition = self._window._services.calculator_registry.get(calculator_id)
        section = panel._sections.get(definition.category) if definition is not None else None
        if section is not None:
            section.set_expanded(True)
        ancestor = widget.parentWidget()
        while ancestor is not None and not isinstance(ancestor, QScrollArea):
            ancestor = ancestor.parentWidget()
        if ancestor is not None:
            ancestor.ensureWidgetVisible(widget, 0, 40)
        logger.warning("OPENCHEM_DRIVE: revealed the row of %s", calculator_id)

    def _do_service_row(self, step: dict[str, Any]) -> None:
        """`{"do": "service_row", "calculator": "orca.nmr", "expect": {"panel": "...", "calc_type": "..."}}`
        -- press the Properties row of a calculator that is run from another panel, and assert
        WHERE THE PRESS WENT.

            "panel"      the rail id of the panel that must now be showing
            "calc_type"  (Quantum_Chemistry) the calculation type code its combo must hold

        A real `click()` on the real button: the panel's handler reads `sender()`, and the
        window's routing is what is being checked, so calling either directly would prove
        nothing about the wiring. Nothing is run -- opening the panel is all a row does.
        """
        from openchem.ui.panels.quantum_chemistry_panel import CALC_TYPE_LABELS

        tag = str(step.get("tag", ""))
        calculator_id = str(step["calculator"])
        expect = dict(step.get("expect") or {})
        window = self._window
        button = window._property_panel._service_rows.get(calculator_id)
        if button is None:
            logger.error("OPENCHEM_DRIVE: service_row: no row for %r", calculator_id)
            return
        button.click()
        problems: list[str] = []
        wanted_panel = expect.get("panel")
        if wanted_panel:
            dock = window._dock_by_panel_id(str(wanted_panel))
            if dock is None or dock.isHidden():
                problems.append(f"panel {wanted_panel!r} is not showing")
        if "calc_type" in expect:
            chosen = CALC_TYPE_LABELS.get(window._quantum_chemistry_panel._calc_type_combo.currentText())
            if chosen != expect["calc_type"]:
                problems.append(f"the panel holds calculation {chosen!r}, wanted {expect['calc_type']!r}")
        ok = not problems
        detail = "as expected" if ok else "; ".join(problems)
        if self._record_assertion("service_row", tag, ok, detail):
            logger.warning("OPENCHEM_DRIVE: EXPECT service_row ok[%s] %s", tag, calculator_id)
        else:
            logger.error("OPENCHEM_DRIVE: EXPECT service_row FAILED[%s] -- %s", tag, detail)

    def _do_tool_setup(self, step: dict[str, Any]) -> None:
        """`{"do": "tool_setup", "tool": "pkasolver"}` -- what a "Needs setup" chip press
        asks the WINDOW for, without needing a calculator that is actually unconfigured.

        `chip` is the honest test of a press, and it can only assert "Needs setup" on a
        machine where the calculator is unset-up; here pkasolver and the NMR database are
        both installed, so the chip reads Ready. This emits the panel's own
        `tool_setup_requested` -- exactly what the chip's handler emits -- so the WINDOW
        half is still exercised for real: the signal reaches `MainWindow`, which opens
        Settings > External Tools on that tab. What it does not prove is the press
        itself, which `tests/test_status_chip_routes.py` does.
        """
        tag = str(step.get("tag", ""))
        tool = str(step["tool"])
        self._chip_expectation = (tag, f"tool_setup:{tool}", {"tool": tool})
        QTimer.singleShot(int(step.get("inspect_after_ms", 700)), self._window, self._inspect_chip_modal)
        self._window._property_panel.tool_setup_requested.emit(tool)

    def _inspect_chip_modal(self) -> None:
        """Inspect and close the modal a chip press opened. See `_do_chip`."""
        from PySide6.QtWidgets import QApplication, QLabel

        tag, calculator_id, expect = self._chip_expectation
        modal = QApplication.activeModalWidget()
        problems: list[str] = []
        kind = type(modal).__name__ if modal is not None else None
        if modal is None:
            problems.append("no dialog opened")
        elif "tool" in expect:
            tool = modal.external_tools.current_tool() if hasattr(modal, "external_tools") else None
            if kind != "SettingsDialog":
                problems.append(f"opened {kind}, wanted SettingsDialog")
            elif tool != expect["tool"]:
                problems.append(f"Settings opened on tool {tool!r}, wanted {expect['tool']!r}")
        else:
            if kind != "CalculatorSettingsDialog":
                problems.append(f"opened {kind}, wanted CalculatorSettingsDialog")
            else:
                notice = next(
                    (w for w in modal.findChildren(QLabel) if w.objectName() == "calculatorNeededInputs"), None
                )
                text = notice.text() if notice is not None else ""
                for wanted in expect.get("needed") or []:
                    if wanted not in text:
                        problems.append(f"the Needs line lacks {wanted!r} (it says {text!r})")
                if "focus" in expect and modal.focus_parameter != expect["focus"]:
                    problems.append(f"cursor on {modal.focus_parameter!r}, wanted {expect['focus']!r}")
        ok = not problems
        detail = "as expected" if ok else "; ".join(problems)
        detail += f" (opened {kind})"
        if self._record_assertion("chip", tag, ok, detail):
            logger.warning("OPENCHEM_DRIVE: EXPECT chip ok[%s] %s -> %s", tag, calculator_id, kind)
        else:
            logger.error("OPENCHEM_DRIVE: EXPECT chip FAILED[%s] -- %s", tag, detail)
        if modal is not None and expect.get("shot"):
            path = Path(str(expect["shot"]))
            path.parent.mkdir(parents=True, exist_ok=True)
            modal.grab().save(str(path))
            logger.warning("OPENCHEM_DRIVE: wrote %s", path)
        if modal is not None:
            modal.close()

    def _do_expect_inspectors(self, step: dict[str, Any]) -> None:
        """`{"do": "expect_inspectors", "count": 2, "titles": ["QEq", "EEM"], "apart": true}`
        -- how many Calculator Inspector windows are OPEN, and what they say, asserted.

            "count"     exactly this many live, visible inspector windows
            "titles"    substrings each of which some open window's title carries
            "apart"     no two open windows share a top-left corner. **TWO WINDOWS AT ONE
                        POSITION ARE ONE WINDOW**: the first run of this step passed on
                        count and titles while both opened at (360, 128), the second
                        covering the first completely.

        The panel keeps its inspectors by result identity in weak references, so this
        reads what a person would see -- a window that is still visible -- and never
        counts one that closed. Two windows with the same title are two results
        opened side by side, which is a pass; one window a second request raised is
        `count` 1, which is how "the same result is one window" is asserted.
        """
        panel = self._window._property_panel
        tag = str(step.get("tag", ""))
        titles: list[str] = []
        corners: list[tuple[int, int]] = []
        for reference in panel._inspector_windows.values():
            window = reference()
            try:
                if window is not None and window.isVisible():
                    titles.append(str(window.windowTitle()))
                    corners.append((window.x(), window.y()))
            except RuntimeError:
                continue  # deleted on close
        problems: list[str] = []
        if step.get("apart") and len(set(corners)) != len(corners):
            problems.append(f"windows share a corner: {corners}")
        if "count" in step and len(titles) != int(step["count"]):
            problems.append(f"{len(titles)} inspector window(s) open, wanted {int(step['count'])}")
        for wanted in step.get("titles") or []:
            if not any(str(wanted) in title for title in titles):
                problems.append(f"no open inspector titled like {wanted!r}")
        ok = not problems
        detail = "as expected" if ok else "; ".join(problems)
        detail += f" (open: {titles} at {corners})"
        if self._record_assertion("expect_inspectors", tag, ok, detail):
            logger.warning("OPENCHEM_DRIVE: EXPECT inspectors ok[%s] %s at %s", tag, titles, corners)
        else:
            logger.error("OPENCHEM_DRIVE: EXPECT inspectors FAILED[%s] -- %s", tag, detail)

    def _do_expect_offered(self, step: dict[str, Any]) -> None:
        """`{"do": "expect_offered", "offered": [...], "hidden": [...], "footer": "..."}`
        -- which calculators the Properties launcher is OFFERING, asserted.

            "offered"   calculator ids whose row AND section are on offer
            "hidden"    ids whose row must exist and be withdrawn (or whose
                        section is)
            "footer"    the exact text of the "N hidden by default" link, or ""
                        to assert there is none

        **ON OFFER IS NOT ON SCREEN.** A collapsed section hides its content,
        so `isVisibleTo` answers "no" for every calculator in a section nobody
        has expanded -- true, and not what is being asked. This reads the
        EXPLICIT hide of the row and of its section, which is what withdrawing
        a calculator sets and collapsing does not.
        """
        panel = self._window._property_panel
        tag = str(step.get("tag", ""))

        def on_offer(calculator_id: str) -> bool | None:
            row = panel._calculator_rows.get(calculator_id)
            if row is None:
                return None
            for category, ids in panel._section_calculators.items():
                if calculator_id in ids:
                    section = panel._sections.get(category)
                    if section is not None and section.isHidden():
                        return False
            return not row.isHidden()

        problems: list[str] = []
        for calculator_id in step.get("offered") or []:
            state = on_offer(calculator_id)
            if state is None:
                problems.append(f"{calculator_id}: no row at all")
            elif not state:
                problems.append(f"{calculator_id}: not offered, wanted offered")
        for calculator_id in step.get("hidden") or []:
            state = on_offer(calculator_id)
            if state is None:
                problems.append(f"{calculator_id}: no row to be hidden")
            elif state:
                problems.append(f"{calculator_id}: offered, wanted hidden")
        if "footer" in step:
            link = panel._hidden_link
            shown = link.text() if not link.isHidden() else ""
            if shown != step["footer"]:
                problems.append(f"footer reads {shown!r}, wanted {step['footer']!r}")
        if self._record_assertion("expect_offered", tag, not problems, "; ".join(problems) or "as expected"):
            logger.warning("OPENCHEM_DRIVE: EXPECT offered ok[%s]", tag)
        else:
            logger.error("OPENCHEM_DRIVE: EXPECT offered FAILED[%s] -- %s", tag, "; ".join(problems)[:800])

    def _finish(self, *, tolerate_errors: bool = False) -> int:
        """End the run: log the verdict, write the report, return the exit status.

        Idempotent -- the last step and `quit` both reach it -- and it detaches
        the ledger, so nothing logged after the verdict is counted against it.
        """
        if self._verdict is not None:
            return self._verdict
        unexpected = [] if tolerate_errors else self._ledger.unexpected(self._allow)
        failed = [a for a in self._assertions if not a["ok"]]
        driver_failures = self._ledger.driver_failures
        code = 1 if (unexpected or failed or driver_failures) else 0
        self._verdict = code
        logging.getLogger().removeHandler(self._ledger)
        for line in self._ledger.summary_lines(self._allow):
            logger.warning("OPENCHEM_DRIVE: ledger %s", line)
        logger.warning(
            "OPENCHEM_DRIVE: VERDICT %s -- %d unexpected app error(s), %d failed assertion(s) of %d, "
            "%d driver failure(s)%s",
            "PASS" if code == 0 else "FAIL", len(unexpected), len(failed), len(self._assertions),
            len(driver_failures), " (errors tolerated)" if tolerate_errors else "",
        )
        if self._report_path is not None:
            from openchem.app.logging_setup import log_file_path

            identity = (self._identity.to_dict() if self._identity else {})
            payload = {
                "verdict": "PASS" if code == 0 else "FAIL",
                "exit_code": code,
                "tolerate_errors": tolerate_errors,
                "run": identity,
                "steps": {"in_script": len(self._steps), "run": self._index},
                "log_file": {
                    "path": str(log_file_path()), "start": identity.get("log_start", 0),
                    "end": log_file_size(),
                },
                "assertions": self._assertions,
                "measurements": self._measurements,
                "ledger": self._ledger.to_dict(self._allow),
            }
            if write_report(self._report_path, payload):
                logger.warning("OPENCHEM_DRIVE: report written to %s", self._report_path)
            else:
                logger.warning("OPENCHEM_DRIVE: could not write the report to %s", self._report_path)
        return code

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
        # The verdict FIRST, while the window and its panels are still there to
        # be asked, and before anything below can log.
        self._allow.extend(str(a) for a in step.get("allow") or [])
        code = self._finish(tolerate_errors=bool(step.get("tolerate_errors")))
        # Nothing is worth saving from a scripted run, and a dirty session
        # is what raises the modal.
        self._window._session.mark_clean()
        self._window._undo_stack.clear()
        QApplication.instance().exit(code)
