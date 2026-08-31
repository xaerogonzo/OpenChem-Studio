"""A file dialog opens where you last were, per purpose.

`File > Open Project` opened at the process working directory -- the
repository root, when the app is launched from a checkout -- because
`QFileDialog.getOpenFileName` was called with no `dir` argument at all and
Qt falls back to the CWD. Nothing anywhere remembered a directory.

**SEPARATE MEMORIES, NOT ONE.** A project library and a structure folder are
different places, so importing a PDB must not move the Open Project dialog
to wherever that PDB lived. `test_the_kinds_do_not_share_one_memory` is the
narrow half and the load-bearing one: a single shared key satisfies every
other assertion in this file.

**THE DECISION IS A PURE FUNCTION AND THE DIALOG IS NOT.** Everything below
the wiring section tests `dialog_start_directory` / `remember_chosen_path` /
`suggested_save_path` directly, which is the two-level split
`ui/visual_check.py` already uses -- the part worth testing is the choice of
directory, and a `QFileDialog` cannot be driven headlessly anyway.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path

import pytest
from PySide6.QtCore import QStandardPaths

from openchem.app.settings import (
    DIRECTORY_KINDS,
    Settings,
    dialog_start_directory,
    remember_chosen_path,
    suggested_save_path,
)
from openchem.bootstrap import build_service_container

MAIN_WINDOW = Path(__file__).resolve().parent.parent / "src" / "openchem" / "app" / "main_window.py"


@pytest.fixture
def settings() -> Settings:
    """Redirected to this test's own INI by the autouse `isolated_settings`
    fixture in conftest -- see `tests/test_settings_isolation.py`."""
    return Settings(build_service_container().event_bus)


# ---------------------------------------------------------------------------
# The closed vocabulary
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("kind", sorted(DIRECTORY_KINDS))
def test_a_known_kind_round_trips(settings, kind, tmp_path):
    settings.set_last_directory(kind, str(tmp_path))
    assert settings.last_directory(kind) == str(tmp_path)


def test_an_unknown_kind_raises_rather_than_creating_a_key(settings, tmp_path):
    """FAIL CLOSED. A typo'd kind that silently got its own settings key
    would make the dialog stop remembering anything, with nothing anywhere
    going red -- the same reason the DEFERRALS parse refuses `**OPNE**`
    instead of skipping it.
    """
    with pytest.raises(ValueError):
        settings.set_last_directory("porject", str(tmp_path))
    with pytest.raises(ValueError):
        settings.last_directory("porject")


def test_the_kinds_do_not_share_one_memory(settings, tmp_path):
    """THE NARROW HALF. One shared key passes every other test here.

    This is the whole reason the memory is per purpose: importing a molecule
    must not move where Open Project starts.
    """
    projects = tmp_path / "projects"
    molecules = tmp_path / "molecules"
    projects.mkdir()
    molecules.mkdir()

    settings.set_last_directory("project", str(projects))
    settings.set_last_directory("molecule", str(molecules))

    assert dialog_start_directory(settings, "project") == str(projects)
    assert dialog_start_directory(settings, "molecule") == str(molecules)


# ---------------------------------------------------------------------------
# Where a dialog starts
# ---------------------------------------------------------------------------


def test_a_remembered_directory_is_offered_back(settings, tmp_path):
    settings.set_last_directory("project", str(tmp_path))
    assert dialog_start_directory(settings, "project") == str(tmp_path)


def test_with_nothing_remembered_it_falls_back_to_DOCUMENTS(settings):
    """Asserted against the DERIVED location, never a hardcoded path.

    A literal would be a claim about this machine -- the failure mode
    `initial_right_dock_width` records, where `offscreen` reports an 800 px
    screen and a fitted constant stops meaning anything. "Some fallback
    happened" is too weak to catch a fallback to the CWD, which is the
    behaviour being replaced; this is the bound that is actually checkable.
    """
    expected = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.DocumentsLocation
    )
    start = dialog_start_directory(settings, "project")

    assert start == expected
    # ...and NOT the working directory, which is the behaviour being
    # replaced. Without this the test could pass vacuously on a platform
    # where `writableLocation` answers "" -- both sides empty, nothing
    # asserted, and the defect fully intact.
    assert start and start != os.getcwd()


def test_a_remembered_directory_that_no_longer_exists_is_discarded(settings, tmp_path):
    """A folder since moved or deleted must not be handed to Qt.

    Worse than the default it replaced: the dialog opens somewhere
    arbitrary rather than somewhere wrong-but-predictable.
    """
    gone = tmp_path / "since-deleted"
    gone.mkdir()
    settings.set_last_directory("project", str(gone))
    gone.rmdir()

    expected = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.DocumentsLocation
    )
    assert dialog_start_directory(settings, "project") == expected


def test_a_remembered_FILE_would_not_be_offered_as_a_directory(settings, tmp_path):
    """Belt and braces on the storage rule below: even if a file path
    reached the store, it is not a directory and so is not returned."""
    a_file = tmp_path / "project.ocsproj"
    a_file.write_text("{}", encoding="utf-8")
    settings.set_last_directory("project", str(a_file))

    assert dialog_start_directory(settings, "project") != str(a_file)


# ---------------------------------------------------------------------------
# What gets remembered
# ---------------------------------------------------------------------------


def test_the_PARENT_of_the_chosen_file_is_stored(settings, tmp_path):
    """The directory, never the file itself.

    A stored file path would be handed to the next dialog as its starting
    directory, which Qt cannot open.
    """
    chosen = tmp_path / "DimethylTryptamines.ocsproj"
    chosen.write_text("{}", encoding="utf-8")

    remember_chosen_path(settings, "project", str(chosen))

    assert settings.last_directory("project") == str(tmp_path)


def test_a_cancelled_dialog_records_nothing(settings, tmp_path):
    """Qt returns "" when the user backs out. Without this, cancelling Save
    would move the remembered directory as surely as completing it."""
    settings.set_last_directory("project", str(tmp_path))

    remember_chosen_path(settings, "project", "")

    assert settings.last_directory("project") == str(tmp_path)


# ---------------------------------------------------------------------------
# The suggested save name
# ---------------------------------------------------------------------------


def test_a_save_dialog_is_seeded_with_a_name_in_the_remembered_directory(
    settings, tmp_path
):
    settings.set_last_directory("project", str(tmp_path))

    suggested = suggested_save_path(settings, "project", "Tryptamines", ".ocsproj")

    assert suggested == str(tmp_path / "Tryptamines.ocsproj")


def test_a_name_that_is_not_a_legal_FILENAME_is_made_into_one(settings, tmp_path):
    """A project may legitimately be called "5-HT2A / 6WGT".

    Left alone, the separator turns the suggestion into a path into a
    directory that does not exist, and the dialog opens nowhere useful.
    """
    settings.set_last_directory("project", str(tmp_path))

    suggested = suggested_save_path(settings, "project", "5-HT2A / 6WGT", ".ocsproj")

    assert Path(suggested).parent == tmp_path
    assert "/" not in Path(suggested).name
    assert Path(suggested).name.endswith(".ocsproj")


def test_a_nameless_project_falls_back_to_the_bare_directory(settings, tmp_path):
    """Rather than suggesting a file called ".ocsproj"."""
    settings.set_last_directory("project", str(tmp_path))

    assert suggested_save_path(settings, "project", "   ", ".ocsproj") == str(tmp_path)


# ---------------------------------------------------------------------------
# The wiring, per call site
# ---------------------------------------------------------------------------
#
# A CORRECT HELPER WITH ONE CALL SITE OMITTING `dir` IS THE FAILURE THIS
# GUARDS. "Testing a helper is not testing the wiring" is on record three
# times in this project, so each dialog is checked individually rather than
# the family being covered by one example.
#
# BOTH INSTRUMENTS ARE USED, AND THE QUESTION THAT DECIDED IT WAS MEASURED.
# The session that first wrote this could not determine whether PySide6
# admits a patch on `QFileDialog`'s static methods -- `QMenu.exec` is on
# record here as un-patchable, being a C++ slot -- so it asserted on the
# source alone. It IS patchable: measured, `monkeypatch.setattr(QFileDialog,
# "getOpenFileName", staticmethod(fake))` takes, the fake runs, and the real
# `dir` argument is readable from it.
#
# So the behavioural guards below drive the actual window and read what
# reaches Qt, which is the stronger claim and the one matching the report
# ("the dialog opens in the repo root"). The AST guards are KEPT beside
# them rather than replaced: they cover all six call sites for the price of
# a parse, where a behavioural test needs a real MainWindow, and they cannot
# fail for environmental reasons. Same shape as
# `test_a_selection_is_never_forwarded_as_a_raw_ketcher_id`.

#: Every dialog that must remember, and which memory it uses.
_EXPECTED_DIALOGS = {
    "_open_project": "project",
    "_save_project": "project",
    "_import_molecule": "molecule",
    "_export_molecule": "molecule",
    "_import_crystal": "macromolecule",
    "_import_macromolecule": "macromolecule",
}

_SEEDERS = {"dialog_start_directory", "suggested_save_path"}


def _called_function_name(node: ast.Call) -> str:
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return ""


def _dialog_calls_in(function: ast.FunctionDef) -> list[ast.Call]:
    return [
        node
        for node in ast.walk(function)
        if isinstance(node, ast.Call)
        and _called_function_name(node) in {"getOpenFileName", "getSaveFileName"}
    ]


@pytest.fixture(scope="module")
def window_functions() -> dict[str, ast.FunctionDef]:
    tree = ast.parse(MAIN_WINDOW.read_text(encoding="utf-8"))
    return {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
    }


def test_the_walk_finds_every_dialog_it_is_supposed_to_check(window_functions):
    """ASSERTS ITS OWN SETUP, so this file cannot go vacuous.

    A renamed method or a moved dialog would otherwise leave the guards
    below iterating an empty set and passing while checking nothing -- the
    "green suite, smaller universe" failure this project records repeatedly.
    """
    missing = sorted(name for name in _EXPECTED_DIALOGS if name not in window_functions)
    assert not missing, f"main_window.py no longer defines {missing}"

    without_a_dialog = sorted(
        name
        for name in _EXPECTED_DIALOGS
        if not _dialog_calls_in(window_functions[name])
    )
    assert not without_a_dialog, (
        f"expected a QFileDialog call in {without_a_dialog}"
    )


@pytest.mark.parametrize("name, kind", sorted(_EXPECTED_DIALOGS.items()))
def test_every_dialog_is_given_a_starting_directory(window_functions, name, kind):
    """The `dir` argument, positionally third, from one of the seeders.

    Qt's own signature is (parent, caption, dir, filter), and passing no
    `dir` is exactly the defect: it silently means "the working directory".
    """
    for call in _dialog_calls_in(window_functions[name]):
        assert len(call.args) >= 3, (
            f"{name}: QFileDialog call passes no starting directory, so it "
            f"opens at the process working directory"
        )
        seed = call.args[2]
        assert isinstance(seed, ast.Call) and _called_function_name(seed) in _SEEDERS, (
            f"{name}: the starting directory should come from one of "
            f"{sorted(_SEEDERS)}, got {ast.dump(seed)[:80]}"
        )


@pytest.mark.parametrize("name, kind", sorted(_EXPECTED_DIALOGS.items()))
def test_every_dialog_records_where_the_user_went(window_functions, name, kind):
    """Seeding without recording remembers the first directory forever."""
    calls = [
        node
        for node in ast.walk(window_functions[name])
        if isinstance(node, ast.Call)
        and _called_function_name(node) == "remember_chosen_path"
    ]
    assert calls, f"{name} never calls remember_chosen_path"


@pytest.mark.parametrize("name, kind", sorted(_EXPECTED_DIALOGS.items()))
def test_every_dialog_uses_the_memory_meant_for_it(window_functions, name, kind):
    """A molecule import writing the `project` memory would move the Open
    Project dialog, which is the exact behaviour the split exists to
    prevent -- and every other guard here would still pass."""
    used = {
        node.args[1].value
        for node in ast.walk(window_functions[name])
        if isinstance(node, ast.Call)
        and _called_function_name(node) in _SEEDERS | {"remember_chosen_path"}
        and len(node.args) >= 2
        and isinstance(node.args[1], ast.Constant)
    }
    assert used == {kind}, f"{name} should use only the {kind!r} memory, used {used}"


# ---------------------------------------------------------------------------
# The wiring, behaviourally -- what actually reaches Qt
# ---------------------------------------------------------------------------


def _build_window(tmp_path):
    """A real MainWindow, with the plugin directories pointed at nothing.

    Not closed and not deleted: `conftest.py` retains every MainWindow for
    the session on purpose, and destroying one is recorded here as
    corrupting the heap.
    """
    from openchem.app.main_window import MainWindow
    from openchem.app.session import SessionManager
    from openchem.bootstrap import build_service_container

    services = build_service_container()
    settings = Settings(services.event_bus)
    settings.set("plugins/project_directory", str(tmp_path / "no_plugins_here"))
    settings.set("plugins/user_directory", str(tmp_path / "no_user_plugins_here"))
    return MainWindow(services, settings, SessionManager())


def test_open_project_really_offers_Qt_the_remembered_directory(qapp, tmp_path, monkeypatch):
    """THE REPORTED COMPLAINT, asserted end to end.

    `File > Open Project` started in the repo root every time, because the
    call passed no `dir` at all and Qt falls back to the process working
    directory. This reads the argument Qt was handed, from the real window,
    rather than the source that constructs it.

    The dialog is made to CANCEL -- an empty result -- so nothing is loaded
    and the assertion is purely about where it was told to open.
    """
    from PySide6.QtWidgets import QFileDialog

    library = tmp_path / "Molecules"
    library.mkdir()
    window = _build_window(tmp_path)
    window._settings.set_last_directory("project", str(library))

    # Not what is under test, and a modal here would hang an unattended run.
    monkeypatch.setattr(
        type(window), "_confirm_discarding_unsaved_changes", lambda self: True
    )
    seen: dict[str, object] = {}
    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileName",
        staticmethod(
            lambda parent=None, caption="", dir="", *a, **k: (
                seen.__setitem__("dir", dir),
                ("", ""),
            )[1]
        ),
    )

    window._open_project()

    assert "dir" in seen, "the open dialog was never reached"
    assert Path(seen["dir"]) == library, (
        f"Open Project was told to start in {seen['dir']!r} rather than the "
        f"remembered {str(library)!r}"
    )


def test_save_project_really_seeds_Qt_with_a_name_in_that_directory(qapp, tmp_path, monkeypatch):
    """The second call site, separately.

    A correct helper with ONE call site quietly omitting `dir` is this
    project's recorded "testing a helper is not testing the wiring" failure,
    so Open and Save each get their own assertion rather than one standing
    for the family.
    """
    from PySide6.QtWidgets import QFileDialog

    library = tmp_path / "Molecules"
    library.mkdir()
    window = _build_window(tmp_path)
    window._settings.set_last_directory("project", str(library))

    seen: dict[str, object] = {}
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        staticmethod(
            lambda parent=None, caption="", dir="", *a, **k: (
                seen.__setitem__("dir", dir),
                ("", ""),
            )[1]
        ),
    )

    window._save_project()

    assert "dir" in seen, "the save dialog was never reached"
    assert Path(seen["dir"]).parent == library, (
        f"Save Project was seeded with {seen['dir']!r}, which is not in the "
        f"remembered directory {str(library)!r}"
    )
