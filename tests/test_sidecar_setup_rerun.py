"""Re-running a sidecar installer must repair it, not fail on step one.

Both `admet_setup.install` and `pkasolver_setup.install` documented
themselves as safe to re-run -- pkasolver's said a partially-completed
setup "can be repaired by running it again rather than requiring manual
cleanup". Neither was, and the reason is easy to miss: `uv venv` exits
non-zero on a directory that already holds an environment ("A virtual
environment already exists ... Use --clear to replace it"). Only the
`python -m venv` fallback was genuinely idempotent, so whichever path a
developer happened to test decided whether the bug was visible.

The consequence is worse than a confusing error. A re-run is what a user
does after ANY later step fails, and it died before reaching the step
that had actually gone wrong -- so a ~1 GB environment that only needed
its verification retried could not be repaired from the UI at all.
"""

from __future__ import annotations

import pytest

from openchem.services import admet_setup, pkasolver_setup

SETUPS = pytest.mark.parametrize(
    ("module", "error"),
    [
        (admet_setup, admet_setup.AdmetSetupError),
        (pkasolver_setup, pkasolver_setup.PkasolverSetupError),
    ],
    ids=["admet", "pkasolver"],
)


def _fake_interpreter(root, module):
    """Create the interpreter file the installer looks for, so the root
    looks like an environment that is already built."""
    python = module.interpreter_for(root)
    python.parent.mkdir(parents=True, exist_ok=True)
    python.write_text("", encoding="utf-8")
    return python


def _stub_everything_but_the_venv_step(module, monkeypatch, tmp_path, commands, on_venv=None):
    """Neutralise every step except environment creation, which is what
    these tests are about.

    pkasolver's install does more than run commands -- it clones a repo,
    writes a .pth, and asks the interpreter for its own site-packages by
    executing it. That last one is why a placeholder interpreter file is
    not enough on its own: running it raises WinError 193 rather than
    anything to do with the behaviour under test.
    """
    monkeypatch.setattr(module, "find_uv", lambda: "uv")

    def fake_run(cmd, step):
        commands.append(list(cmd))
        if "venv" in cmd and on_venv is not None:
            on_venv()

    monkeypatch.setattr(module, "_run", fake_run)
    monkeypatch.setattr(module, "_verify", lambda python: None)
    if hasattr(module, "_site_packages_of"):
        site_packages = tmp_path / "site-packages"
        site_packages.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(module, "_site_packages_of", lambda python: site_packages)
    if hasattr(module, "shutil"):
        monkeypatch.setattr(module.shutil, "which", lambda name: f"/usr/bin/{name}")


@SETUPS
def test_an_existing_environment_is_reused_not_recreated(tmp_path, monkeypatch, module, error):
    """The regression. With an interpreter already present, no venv
    creation command may run -- that is the command that fails."""
    _fake_interpreter(tmp_path, module)
    commands: list[list[str]] = []
    _stub_everything_but_the_venv_step(module, monkeypatch, tmp_path, commands)

    module.install(tmp_path)

    venv_commands = [c for c in commands if "venv" in c]
    assert venv_commands == [], f"a built environment must not be recreated: {venv_commands}"


@SETUPS
def test_a_missing_environment_is_still_created(tmp_path, monkeypatch, module, error):
    """The reuse must not swallow the real first-install path."""
    commands: list[list[str]] = []
    _stub_everything_but_the_venv_step(
        module, monkeypatch, tmp_path, commands,
        on_venv=lambda: _fake_interpreter(tmp_path, module),
    )

    module.install(tmp_path)

    venv_commands = [c for c in commands if "venv" in c]
    assert len(venv_commands) == 1, "a fresh root must still build an environment"


@SETUPS
def test_a_half_created_environment_is_cleared_rather_than_refused(
    tmp_path, monkeypatch, module, error
):
    """Directory present, interpreter absent -- the shape a cancelled or
    crashed first attempt leaves behind. `uv venv` refuses this too, so
    the creation must pass --clear."""
    (tmp_path / ".venv").mkdir(parents=True)
    commands: list[list[str]] = []
    _stub_everything_but_the_venv_step(
        module, monkeypatch, tmp_path, commands,
        on_venv=lambda: _fake_interpreter(tmp_path, module),
    )

    module.install(tmp_path)

    venv_command = next(c for c in commands if "venv" in c)
    assert "--clear" in venv_command


@SETUPS
def test_a_failed_verification_leaves_the_environment_in_place(
    tmp_path, monkeypatch, module, error
):
    """The check is cheap and the build is not. A verification failure
    must not delete or invalidate what was built -- the dialog now keeps
    the path so the user can retry the check rather than rebuild ~1 GB."""
    python = _fake_interpreter(tmp_path, module)
    _stub_everything_but_the_venv_step(module, monkeypatch, tmp_path, [])
    monkeypatch.setattr(
        module, "_verify",
        lambda p: (_ for _ in ()).throw(error("Verification could not run: timed out")),
    )

    with pytest.raises(error, match="Verification"):
        module.install(tmp_path)

    assert python.is_file(), "the built environment must survive a failed check"
