"""Interpreter-path validation for the out-of-process sidecars.

Every case here is one a user actually hit or could hit from the External
Tools dialog. The `.codecov.yml` case is verbatim: that path really was
stored, and the only symptom was "[WinError 193] %1 is not a valid Win32
application".
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from openchem.services.sidecar_env import (
    interpreter_problem,
    recovery_hint,
    working_interpreter_in,
)


def test_a_real_interpreter_reports_no_problem():
    assert interpreter_problem(sys.executable) is None


def test_an_empty_path_is_reported_as_unconfigured():
    assert "No interpreter configured" in interpreter_problem("")
    assert "No interpreter configured" in interpreter_problem("   ")


def test_a_missing_path_says_so():
    assert "Nothing exists at" in interpreter_problem(str(Path("no") / "such" / "python.exe"))


def test_a_directory_points_at_what_to_pick_instead(tmp_path):
    problem = interpreter_problem(str(tmp_path))

    assert "is a folder" in problem
    assert ("Scripts" in problem) if os.name == "nt" else ("bin" in problem)


def test_the_real_codecov_yml_case_is_named_clearly(tmp_path):
    """The exact failure from the screenshot: a file from the cloned
    pkasolver repo stored as the interpreter."""
    yml = tmp_path / ".codecov.yml"
    yml.write_text("coverage: {}\n", encoding="utf-8")

    problem = interpreter_problem(str(yml))

    assert problem == ".codecov.yml is a text file, not a Python interpreter."


def test_a_binary_that_is_not_python_is_rejected(tmp_path):
    """Guards the case a name filter cannot: something that really does
    execute, but is not a Python."""
    if os.name != "nt":
        target = tmp_path / "notpython"
        target.write_text("#!/bin/sh\necho hello\n", encoding="utf-8")
        target.chmod(0o755)
        assert interpreter_problem(str(target)) is not None


def test_a_working_environment_is_found_and_offered(tmp_path):
    """The recovery path: the app installed the environment, so when the
    configured path is wrong it can say where the right one is."""
    # A REAL venv, not a copied python.exe: a bare copy has no DLLs or
    # stdlib beside it and will not run, so faking one would test the
    # wrong thing. pip is skipped to keep this quick.
    import venv

    venv.EnvBuilder(with_pip=False).create(tmp_path / ".venv")
    interpreter = tmp_path / ".venv" / (
        "Scripts/python.exe" if os.name == "nt" else "bin/python"
    )

    assert working_interpreter_in(tmp_path) == interpreter
    hint = recovery_hint(tmp_path)
    assert "A working interpreter was found at" in hint
    assert hint.isascii(), "must stay ASCII: this string reaches cp1252 consoles and logs"


def test_no_hint_when_there_is_nothing_to_suggest(tmp_path):
    """Empty rather than a sentence, so callers can concatenate it
    unconditionally."""
    assert recovery_hint(tmp_path) == ""
    assert working_interpreter_in(tmp_path) is None


# --- Finding an executable without making the user dig -------------------


def _fake_venv(root: Path) -> Path:
    """A real venv, since finding is validated by RUNNING what it finds."""
    import venv

    venv.EnvBuilder(with_pip=False).create(root / ".venv")
    return root / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def test_pointing_at_the_environment_folder_finds_the_interpreter(tmp_path):
    """The whole complaint: the interpreter is three levels down at
    .venv/Scripts/python.exe and nobody should have to know that."""
    from openchem.services.sidecar_env import find_interpreter

    expected = _fake_venv(tmp_path / "pkasolver_env")

    assert find_interpreter(tmp_path / "pkasolver_env") == expected


def test_pointing_at_a_folder_ABOVE_the_environment_still_finds_it(tmp_path):
    """Picking the whole data folder should work too -- it is the obvious
    thing to try."""
    from openchem.services.sidecar_env import find_interpreter

    expected = _fake_venv(tmp_path / "data" / "pkasolver_env")

    assert find_interpreter(tmp_path / "data") == expected


def test_the_decoy_package_directory_is_not_mistaken_for_the_interpreter(tmp_path):
    """pkasolver_env contains BOTH `.venv` and a `pkasolver/pkasolver/`
    clone. The screenshots that prompted this show someone browsing into
    the clone looking for an executable that was never there."""
    from openchem.services.sidecar_env import find_interpreter

    root = tmp_path / "pkasolver_env"
    expected = _fake_venv(root)
    decoy = root / "pkasolver" / "pkasolver"
    decoy.mkdir(parents=True)
    (decoy / "python.exe").write_text("not really an interpreter", encoding="utf-8")

    assert find_interpreter(root) == expected


def test_an_already_correct_file_is_accepted_unchanged(tmp_path):
    from openchem.services.sidecar_env import find_interpreter

    expected = _fake_venv(tmp_path / "env")

    assert find_interpreter(expected) == expected


def test_a_folder_with_nothing_in_it_reports_nothing(tmp_path):
    from openchem.services.sidecar_env import find_interpreter

    assert find_interpreter(tmp_path) is None


def test_a_versioned_executable_is_found_by_prefix(tmp_path):
    """Vina ships as `vina_1.2.7_win.exe`, so an exact-name match would
    find nothing at all."""
    from openchem.services.sidecar_env import find_program

    tools = tmp_path / "tools" / "vina"
    tools.mkdir(parents=True)
    binary = tools / ("vina_1.2.7_win.exe" if os.name == "nt" else "vina_1.2.7")
    binary.write_bytes(b"binary")

    assert find_program(tmp_path, ("vina",)) == binary


def test_searching_skips_the_directories_that_would_dominate_it(tmp_path):
    """A pkasolver clone holds thousands of files under .git, none of them
    what is being looked for."""
    from openchem.services.sidecar_env import _SKIP_DIRECTORIES, find_program

    assert ".git" in _SKIP_DIRECTORIES
    buried = tmp_path / ".git" / "objects"
    buried.mkdir(parents=True)
    (buried / "orca.exe").write_bytes(b"x")

    assert find_program(tmp_path, ("orca",)) is None


def test_the_search_depth_is_bounded(tmp_path):
    """Someone will point this at a drive root; it must not try to walk
    the disk."""
    from openchem.services.sidecar_env import MAX_SEARCH_DEPTH, find_program

    deep = tmp_path
    for level in range(MAX_SEARCH_DEPTH + 3):
        deep = deep / f"level{level}"
    deep.mkdir(parents=True)
    (deep / "orca.exe").write_bytes(b"x")

    assert find_program(tmp_path, ("orca",)) is None


def test_a_version_fragment_is_not_treated_as_a_file_extension():
    """`Path("vina_1.2.7").suffix` is `".7"`.

    So an allowlist of executable suffixes rejects exactly the
    released-binary naming `find_program` exists to handle, and the
    docstring's promise of prefix matching "because released binaries
    carry their version" was being undone one line later.

    ASSERTED HERE RATHER THAN ONLY THROUGH `find_program`, because that
    route only ever exercises the HOST platform's branch: on Windows the
    binary is `vina_1.2.7_win.exe`, whose `.exe` parses cleanly, so the
    bug was invisible until a Linux runner tried `vina_1.2.7`. This
    catches it from either side.
    """
    from pathlib import Path

    from openchem.services.sidecar_env import _looks_executable

    assert Path("vina_1.2.7").suffix == ".7", "the trap this guards is gone"

    # The platform-independent core: a versioned name with no extension is
    # the shape that was being rejected, and it must be accepted anywhere.
    assert _looks_executable(Path("vina_1.2.7"))
    assert _looks_executable(Path("orca"))
    # Still discriminating: a data file next to the binary is not it.
    assert not _looks_executable(Path("receptors.json"))

    # `.exe` IS PLATFORM-SPECIFIC AND THE FIRST VERSION OF THIS TEST
    # ASSERTED IT UNCONDITIONALLY, which is the same Windows-shaped
    # assumption the bug itself was. On POSIX a `.exe` is not an
    # executable shape, and the fallback there asks the executable bit --
    # which a name that does not exist on disk cannot have.
    if os.name == "nt":
        assert _looks_executable(Path("vina_1.2.7_win.exe"))
    else:
        assert not _looks_executable(Path("vina_1.2.7_win.exe"))
