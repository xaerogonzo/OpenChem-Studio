"""The repeated parts of the External Tools dialog's tool tabs.

`ExternalToolsDialog` hand-built seven tabs, and four of them were two
tabs written twice:

* **pkasolver and ADMET** are the same tab. Both are "a Python
  interpreter, not an executable", and their setup services expose an
  identical surface (`default_install_root`, `interpreter_for`,
  `find_uv`, `find_fallback_python`, `describe_prerequisites`,
  `install(root, on_progress)`, a `SetupProgress` and an error class).
  Eight handler methods each, seven of which differed only in strings.
* **Java and the NMR shift database** are the same tab. Both OBTAIN a
  prerequisite rather than configure something the user already has:
  `describe_status()`, a confirm-then-run action, a Re-check, a Remove.

`_on_*_progress` was byte-identical in FIVE places.

What is genuinely singular stays in the dialog: Vina's two-phase
download, ORCA's no-download-is-possible tab, and the Storage tab, which
is not a sidecar at all. The rule this module is held to is the one this
codebase has applied when it declined `EmpiricalEstimator`,
`WorkflowExecution` and `HamiltonianResult` -- every class here has two
real callers today, not one plus a hypothesis.

Layout is deliberately NOT shared. The two families look different for a
reason: an interpreter sidecar leads with a path field and a form, an
obtainable prerequisite leads with a status line and has no path at all.
`ToolTab` holds the async install cycle; each subclass builds its own.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from openchem.plugins.async_task import run_async

# Secondary explanation, and a warning that is not an error. Named
# because the same two greys were pasted as literals into six labels.
MUTED = "color: #666666;"
CAUTION = "color: #8a6d3b;"


@dataclass(frozen=True)
class Note:
    """One explanatory paragraph under a tab's controls."""

    text: str
    style: str = ""


@dataclass(frozen=True)
class Blocked:
    """Why a primary action must not start, and how to say so.

    Severity is part of the data because the two real cases genuinely
    differ: "you already have Java" is good news and gets an information
    box, while "no uv and no suitable Python" is a warning. Collapsing
    them would report a satisfied prerequisite as a problem.
    """

    title: str
    message: str
    severity: str = "warning"


def progress_reporter(label: QLabel) -> Callable[[Any], None]:
    """Report a setup service's progress into `label`, from any thread.

    `setText` on a QLabel from a worker thread is not safe in general, so
    this hops back to the GUI thread via the single-shot-timer idiom Qt
    sanctions for cross-thread UI updates. Five sidecars each carried
    their own byte-identical copy of these four lines.
    """

    def report(progress: Any) -> None:
        QTimer.singleShot(
            0,
            lambda: label.setText(f"[{progress.step}/{progress.total}] {progress.message}..."),
        )

    return report


def _add_notes(layout: QVBoxLayout, parent: QWidget, notes: tuple[Note, ...]) -> None:
    for note in notes:
        label = QLabel(note.text, parent)
        label.setWordWrap(True)
        if note.style:
            label.setStyleSheet(note.style)
        layout.addWidget(label)


class PathRow(QWidget):
    """A path field, a Browse button, and the setting they both write.

    Browse asks for a FOLDER and finds the program inside it. A folder is
    far easier to point at than a file buried three levels down: a
    pkasolver interpreter sits at `pkasolver_env/.venv/Scripts/python.exe`,
    next to a `pkasolver/` directory that looks equally plausible, and
    picking wrong gives "[WinError 193] %1 is not a valid Win32
    application". Pointing at the environment -- or at the whole data
    folder -- is enough.

    The field and the setting are updated together, never separately.
    Four tabs wrote that pairing by hand and one of them (ORCA) had no
    status to refresh, which is how the two could drift.
    """

    def __init__(
        self,
        parent: QWidget,
        *,
        settings,
        setting_key: str,
        browse_title: str,
        finder: Callable[[Path], Path | None],
        description: str,
        on_changed: Callable[[], None] = lambda: None,
    ) -> None:
        super().__init__(parent)
        self._settings = settings
        self._setting_key = setting_key
        self._browse_title = browse_title
        self._finder = finder
        self._description = description
        self._on_changed = on_changed

        self.edit = QLineEdit(self)
        self.edit.setText(settings.get(setting_key, ""))
        self.edit.editingFinished.connect(self.commit)
        self.browse_button = QPushButton("Browse...", self)
        self.browse_button.clicked.connect(self._on_browse_clicked)

        layout = QHBoxLayout(self)
        # Zero margins so wrapping the row in a QWidget lines up exactly
        # as the bare QHBoxLayout it replaced did.
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.edit)
        layout.addWidget(self.browse_button)

    def text(self) -> str:
        return self.edit.text()

    def set_path(self, path: str) -> None:
        self.edit.setText(path)
        self.commit()

    def reload(self) -> None:
        """Re-read the setting, after something else changed it -- a
        removal clears the key, and the field must not keep showing a
        path that no longer exists."""
        self.edit.setText(self._settings.get(self._setting_key, ""))

    def commit(self) -> None:
        self._settings.set(self._setting_key, self.edit.text())
        self._on_changed()

    def _on_browse_clicked(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, self._browse_title)
        if not chosen:
            return
        found = self._finder(Path(chosen))
        if found is None:
            QMessageBox.warning(
                self,
                "Nothing found",
                f"No {self._description} was found in\n{chosen}\n\n"
                "Pick the folder the tool was installed into, or a folder above it.",
            )
            return
        self.set_path(str(found))


# kw_only so a subclass can add a REQUIRED field without every field it
# inherits needing a placeholder default just to satisfy ordering.
@dataclass(frozen=True, kw_only=True)
class _ToolBase:
    """Fields every obtainable tool tab needs. Not used directly."""

    key: str
    """`sidecar_inventory` component key -- what Remove operates on."""

    title: str
    action_label: str
    confirm_title: str
    confirm_body: Callable[[], str]
    run: Callable[[Callable[[Any], None]], Any]
    errors: type[Exception] | tuple[type[Exception], ...]
    success_title: str
    success_message: Callable[[Any], str]
    finished_status: Callable[[Any], str]
    failure_title: str
    failure_status_prefix: str
    remove_label: str
    notes: tuple[Note, ...] = ()
    blocked: Callable[[], Blocked | None] = lambda: None


@dataclass(frozen=True, kw_only=True)
class ManagedAsset(_ToolBase):
    """Something this app obtains for the user: a Java runtime, an index.

    No path field -- there is nothing for the user to configure, only
    something to fetch. The status line is the whole state.
    """

    describe_status: Callable[[], str]


@dataclass(frozen=True, kw_only=True)
class InterpreterSidecar(_ToolBase):
    """A Python environment this app builds and then talks to out of
    process, addressed by the interpreter path recorded in settings."""

    setting_key: str
    browse_title: str
    locate_root: Callable[[], Path]
    test_label: str
    testing_status: str
    describe_test: Callable[[str], str]
    test_errors: type[Exception] | tuple[type[Exception], ...]
    prerequisites: Callable[[], str]
    form_label: str = "Python interpreter:"


class ToolTab(QWidget):
    """The confirm -> disable -> run -> re-enable cycle, once.

    Refuse if a precondition says so; otherwise show what, from where and
    how big, and wait for an explicit yes -- the download policy every
    fetch in this dialog follows. Then disable the button so it cannot be
    started twice, stream progress into the status label from the worker
    thread, and re-enable whichever way it ends.
    """

    def __init__(
        self,
        descriptor: _ToolBase,
        parent: QWidget,
        *,
        remove_button_factory: Callable[[QWidget, str, str], QPushButton],
    ) -> None:
        super().__init__(parent)
        self.descriptor = descriptor

        self.status_label = QLabel(self._initial_status(), self)
        self.status_label.setWordWrap(True)
        self.setup_button = QPushButton(descriptor.action_label, self)
        self.setup_button.clicked.connect(self._on_setup_clicked)
        self.remove_button = remove_button_factory(self, descriptor.key, descriptor.remove_label)

    # --- Subclass hooks ------------------------------------------------

    def _initial_status(self) -> str:
        raise NotImplementedError

    def refresh(self) -> None:
        """Re-read this tab's state. Called after a removal elsewhere."""
        raise NotImplementedError

    def _on_install_finished(self, result: Any) -> None:
        self.status_label.setText(self.descriptor.finished_status(result))

    # --- The shared cycle ----------------------------------------------

    def _on_setup_clicked(self) -> None:
        blocked = self.descriptor.blocked()
        if blocked is not None:
            box = (
                QMessageBox.information
                if blocked.severity == "information"
                else QMessageBox.warning
            )
            box(self, blocked.title, blocked.message)
            return

        answer = QMessageBox.question(
            self,
            self.descriptor.confirm_title,
            self.descriptor.confirm_body(),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        self.setup_button.setEnabled(False)
        self.status_label.setText("Starting...")
        run_async(
            lambda: self.descriptor.run(progress_reporter(self.status_label)),
            self.descriptor.errors,
            self._finished,
            self._failed,
        )

    def _finished(self, result: Any) -> None:
        self.setup_button.setEnabled(True)
        self._on_install_finished(result)
        QMessageBox.information(
            self, self.descriptor.success_title, self.descriptor.success_message(result)
        )

    def _failed(self, message: str) -> None:
        self.setup_button.setEnabled(True)
        self.status_label.setText(f"{self.descriptor.failure_status_prefix}: {message}")
        QMessageBox.critical(self, self.descriptor.failure_title, message)


class ManagedAssetTab(ToolTab):
    """Java and the NMR shift database: status line, action, Re-check."""

    descriptor: ManagedAsset

    def __init__(
        self,
        descriptor: ManagedAsset,
        parent: QWidget,
        *,
        remove_button_factory: Callable[[QWidget, str, str], QPushButton],
    ) -> None:
        super().__init__(descriptor, parent, remove_button_factory=remove_button_factory)

        self.refresh_button = QPushButton("Re-check", self)
        self.refresh_button.clicked.connect(self.refresh)

        row = QHBoxLayout()
        row.addWidget(self.setup_button)
        row.addWidget(self.remove_button)
        row.addWidget(self.refresh_button)
        row.addStretch(1)

        layout = QVBoxLayout(self)
        layout.addWidget(self.status_label)
        layout.addLayout(row)
        _add_notes(layout, self, descriptor.notes)
        layout.addStretch(1)

    def _initial_status(self) -> str:
        return self.descriptor.describe_status()

    def refresh(self) -> None:
        self.status_label.setText(self.descriptor.describe_status())


class InterpreterSidecarTab(ToolTab):
    """pkasolver and ADMET: a path field, Locate, Test, and the notes.

    Test runs a REAL prediction rather than checking that a file exists
    -- an interpreter that imports nothing useful is configured and
    broken, and only running something catches that. It loads a model
    ensemble and takes a while, so it goes through `run_async` like the
    installs do.
    """

    descriptor: InterpreterSidecar

    def __init__(
        self,
        descriptor: InterpreterSidecar,
        parent: QWidget,
        *,
        settings,
        remove_button_factory: Callable[[QWidget, str, str], QPushButton],
    ) -> None:
        super().__init__(descriptor, parent, remove_button_factory=remove_button_factory)
        from openchem.services.sidecar_env import find_interpreter

        self.path_row = PathRow(
            self,
            settings=settings,
            setting_key=descriptor.setting_key,
            browse_title=descriptor.browse_title,
            finder=find_interpreter,
            description="Python interpreter",
            on_changed=self._on_path_changed,
        )

        self.locate_button = QPushButton("Locate Installed", self)
        self.locate_button.setToolTip(
            "Look where this app installs it, without asking you to find anything."
        )
        self.locate_button.clicked.connect(self._on_locate_clicked)
        self.test_button = QPushButton(descriptor.test_label, self)
        self.test_button.clicked.connect(self._on_test_clicked)

        prerequisites = QLabel(descriptor.prerequisites(), self)
        prerequisites.setWordWrap(True)
        prerequisites.setStyleSheet(MUTED)
        self.prerequisites_label = prerequisites

        form = QFormLayout()
        form.addRow(descriptor.form_label, self.path_row)
        form.addRow("Status:", self.status_label)

        row = QHBoxLayout()
        row.addWidget(self.setup_button)
        row.addWidget(self.remove_button)
        row.addWidget(self.locate_button)
        row.addWidget(self.test_button)
        row.addStretch()

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addLayout(row)
        layout.addWidget(prerequisites)
        _add_notes(layout, self, descriptor.notes)
        layout.addStretch(1)

    def _initial_status(self) -> str:
        # Deliberately not a real check on construction: verifying means
        # loading a model ensemble out of process, which is far too slow
        # to pay for merely opening the dialog.
        return "Not checked"

    def refresh(self) -> None:
        self.path_row.reload()
        self.status_label.setText("Not checked - press Test to verify")

    def _on_path_changed(self) -> None:
        self.status_label.setText("Not checked - press Test to verify")

    def _on_install_finished(self, interpreter: Any) -> None:
        self.path_row.set_path(str(interpreter))
        self.status_label.setText(self.descriptor.finished_status(interpreter))

    def _on_locate_clicked(self) -> None:
        """Look where this app would have installed it, with no dialog.

        The application put it there; it should not have to ask.
        """
        from openchem.services.sidecar_env import find_interpreter

        root = self.descriptor.locate_root()
        found = find_interpreter(root) if root.exists() else None
        if found is None:
            QMessageBox.information(
                self,
                "Not found automatically",
                f"No Python interpreter was found in\n{root}\n\n"
                "Use 'Set Up Automatically' to install it, or Browse if it is elsewhere.",
            )
            return
        self.path_row.set_path(str(found))
        self.status_label.setText(f"Found: {found} - press Test to verify")

    def _on_test_clicked(self) -> None:
        self.status_label.setText(self.descriptor.testing_status)
        path = self.path_row.text()
        run_async(
            lambda: self.descriptor.describe_test(path),
            self.descriptor.test_errors,
            self.status_label.setText,
            lambda message: self.status_label.setText(f"Test failed: {message}"),
        )
