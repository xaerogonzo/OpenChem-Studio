"""The WebGL gate: it must skip on a MEASURED absence and nothing else.

Four tests of the real 3Dmol viewer failed on CI for months and took the
whole suite red with them -- which silently disabled every step behind it,
including the naming benchmark that `CLAUDE.md` calls the arbiter of
naming quality. They were not broken. A GPU-less runner cannot give the
page a WebGL context, so `viewer` was never defined and the failure was
the environment's.

**The gate that already existed could not see that**, and the reason is
the point of this file: `QT_QPA_PLATFORM == "offscreen"` is a statement
about the Qt PLATFORM, not about WebGL. Measured on a developer machine,
`offscreen` grants two contexts through ANGLE/D3D11 -- so the platform
name and the capability disagree, and the tests really do run under
`offscreen` locally.

A capability gate is worth exactly as much as its ability to say NO, so
what is guarded here is that it still fails when it should:

- a measured PRESENCE yields no skip, so a genuine regression is still a
  failure rather than a green tick;
- a measured ABSENCE yields a reason that says so in words CI shows;
- the decision never consults the platform name again.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

import conftest


@pytest.fixture
def unmeasured():
    """Run with the session's cached WebGL answer set aside, and restore it.

    Restored rather than recomputed: the probe builds a Chromium page, and
    leaving the real answer discarded would make every later test in the
    session pay for it again.
    """
    saved = conftest._WEBGL.pop("result", None)
    yield
    conftest._WEBGL.pop("result", None)
    if saved is not None:
        conftest._WEBGL["result"] = saved


def test_a_measured_ABSENCE_skips_and_says_so_in_words_ci_shows(unmeasured):
    """The reason is the whole product here.

    `pytest -q -ra` prints it, so a person reading a CI log can tell "this
    environment has no GPU" from "somebody disabled a test", without
    opening the source.
    """
    conftest._WEBGL["result"] = (0, "getContext returned null on attempt 1")

    reason = conftest.webgl_skip_reason(app=None)

    assert reason is not None
    assert "no usable WebGL context available in this environment" in reason
    # The measured detail travels with it, so the log says WHY.
    assert "getContext returned null" in reason


def test_a_measured_PRESENCE_does_not_skip(unmeasured):
    """**The half that makes the gate worth having.**

    If this returned a reason whenever it was unsure, the four viewer
    tests would be permanently green-by-absence and the regressions they
    exist to catch would never be seen again.
    """
    conftest._WEBGL["result"] = (1, "ANGLE (some real renderer)")

    assert conftest.webgl_skip_reason(app=None) is None


def test_the_gate_never_reads_the_PLATFORM_NAME_again(unmeasured):
    """The original bug, asserted so it cannot come back.

    `QT_QPA_PLATFORM` is not WebGL: measured, `offscreen` grants two
    contexts on a machine with a GPU and none on a runner without one, so
    a gate keyed on the name is wrong in both directions -- it skips
    locally where the test would have run, and fails on CI where it
    should have skipped.

    Walked as an AST rather than grepped, because the prose above says
    QT_QPA_PLATFORM and a text search would flag its own explanation.

    **DOCSTRINGS ARE STRING CONSTANTS TOO**, and the first version of this
    guard failed on the explanation inside `_measure_webgl` rather than on
    any code -- the same self-flagging it was written to avoid, one level
    down. They are excluded by identity, not by position, so a docstring
    anywhere in a nested function is covered as well.
    """
    source = inspect.getsource(conftest._measure_webgl) + inspect.getsource(
        conftest.webgl_skip_reason
    )
    tree = ast.parse(inspect.cleandoc(source))

    docstrings = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if not isinstance(body, list) or not body:
            continue
        first = body[0]
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
            if isinstance(first.value.value, str):
                docstrings.add(id(first.value))

    names = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    }

    assert names, "nothing was inspected; the guard is not looking at anything"
    assert not any("QT_QPA_PLATFORM" in name for name in names), (
        "the gate is reading the platform name again; it must MEASURE"
    )


def test_an_inconclusive_probe_RAISES_rather_than_reporting_zero():
    """"I could not find out" is not "the prerequisite is absent".

    Turning the first into the second is how a real failure gets skipped
    silently, and it nearly happened while this was being written: the
    probe page was missing its closing script tag, so `__probe` was
    undefined and `runJavaScript` handed back `''`. Because that path
    raises, it surfaced as a loud error naming the empty result. Under a
    blanket `except Exception: return 0` it would have skipped all four
    viewer tests on every machine, and the gate would have looked like it
    worked.
    """
    tree = ast.parse(Path(conftest.__file__).read_text(encoding="utf-8"))
    probe = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_measure_webgl"
    )

    handlers = [node for node in ast.walk(probe) if isinstance(node, ast.ExceptHandler)]
    assert handlers == [], (
        "the probe swallows an exception; an inconclusive measurement must "
        "raise, not become a skip"
    )
    assert any(isinstance(node, ast.Raise) for node in ast.walk(probe)), (
        "the probe never raises, so it cannot report an inconclusive result"
    )


def test_the_grid_gate_skips_on_a_MEASURED_absence_too(unmeasured, monkeypatch):
    """What makes the gallery guards safe to run on the CI runner.

    The platform half of `grid_skip_reason` is an admitted gate -- see
    its docstring, and the ladder in `test_mol3d_viewer_backend.py`. On
    its own it says nothing about a machine running the `windows`
    platform with no GPU, which is exactly what a hosted runner is: the
    gallery guards would RUN there and FAIL, blaming the code for an
    absent prerequisite. Pairing it with the measured WebGL check is what
    turns that failure into a skip that names the reason.
    """
    monkeypatch.setattr(conftest, "grid_platform_is_offscreen", lambda: False)
    conftest._WEBGL["result"] = (0, "getContext returned null on attempt 1")

    reason = conftest.grid_skip_reason(app=None)

    assert reason is not None, (
        "a GPU-less non-offscreen machine would run the gallery guards and "
        "fail them for want of WebGL"
    )
    assert "no usable WebGL context available in this environment" in reason


def test_the_grid_gate_does_NOT_skip_when_both_conditions_are_met(unmeasured, monkeypatch):
    """The half that makes THAT gate worth having, same argument as above.

    A gate that cannot say yes turns every gallery regression into a
    silent skip -- which is the failure this whole file exists about,
    one feature along.
    """
    monkeypatch.setattr(conftest, "grid_platform_is_offscreen", lambda: False)
    conftest._WEBGL["result"] = (1, "ANGLE (some real renderer)")

    assert conftest.grid_skip_reason(app=None) is None


def test_no_test_file_derives_the_platform_gate_for_itself():
    """The grid gate had TWO private copies -- `_needs_a_display` in
    `test_mol3d_viewer_backend.py` and `_NEEDS_A_DISPLAY` in
    `test_spatial_annotations.py` -- and the gallery overlay would have
    made a third. A shared gate that leaves the copies in place has added
    to the drift rather than removed it.

    **Only the CONDITION of a `skipif` is inspected**, for the same
    reason `test_the_gate_never_reads_the_PLATFORM_NAME_again` walks an
    AST: a text search flags the prose explaining the rule, including
    this file's own. It also leaves the legitimate INVERSE gate alone --
    `test_a_gallery_that_cannot_be_built_is_reported` asks the shared
    `conftest.grid_platform_is_offscreen()` and names no environment
    variable, which is exactly the shape that should survive.
    """
    root = Path(__file__).resolve().parents[1]
    offenders: list[str] = []

    for path in sorted((root / "tests").glob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            attribute = node.func
            if not (isinstance(attribute, ast.Attribute) and attribute.attr == "skipif"):
                continue
            reads_platform = any(
                isinstance(inner, ast.Constant)
                and isinstance(inner.value, str)
                and "QT_QPA_PLATFORM" in inner.value
                for argument in [*node.args, *(kw.value for kw in node.keywords)]
                for inner in ast.walk(argument)
            )
            if reads_platform:
                offenders.append(f"{path.relative_to(root).as_posix()}:{node.lineno}")

    assert offenders == [], (
        f"{offenders} derive the platform gate inline again; use the shared "
        f"`grid_display` fixture, or `conftest.grid_platform_is_offscreen()` "
        f"for the inverse case"
    )


def test_the_four_viewer_tests_actually_request_the_gate():
    """Otherwise the gate exists and guards nothing.

    Named individually rather than counted: a count stays satisfied if
    somebody swaps one of these for an unrelated test that happens to take
    the fixture.
    """
    expected = {
        "tests/test_camera_orientation.py": [
            "test_the_matrix_matches_where_atoms_are_actually_drawn",
        ],
        "tests/test_mol3d_viewer_backend.py": [
            "test_a_gallery_that_cannot_be_built_is_reported",
        ],
    }
    root = Path(__file__).resolve().parents[1]

    for relative, names in expected.items():
        tree = ast.parse((root / relative).read_text(encoding="utf-8"))
        for name in names:
            function = next(
                node
                for node in ast.walk(tree)
                if isinstance(node, ast.FunctionDef) and node.name == name
            )
            arguments = {arg.arg for arg in function.args.args}
            assert "webgl" in arguments, (
                f"{relative}::{name} no longer requests the webgl gate"
            )
