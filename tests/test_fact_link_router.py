"""Every `FactLink` goes somewhere, and a dead one says so.

Following a link used to be an `if/elif` chain in `MainWindow` that handled
three targets and fell off the end for everything else -- so four emitted
links rendered a `>` button with a label promising an action and did nothing
when pressed. A silent no-op is indistinguishable from a broken control.

**THE EMITTED POPULATION IS DERIVED, NOT LISTED.** It comes from the producers
themselves, so a fifth link added tomorrow is checked without anybody
remembering this file exists.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from openchem.domain.report import FactLink
from openchem.ui.fact_link_router import FactLinkRouter, LinkOutcome

SRC = Path(__file__).resolve().parent.parent / "src" / "openchem"


def _emitted_targets() -> dict[str, str]:
    """Every `FactLink(target=...)` a producer constructs -> where.

    Literal targets only. A computed one cannot be checked statically, and
    `test_no_producer_computes_a_link_target` is what keeps that honest rather
    than letting this walk quietly under-report.
    """
    found: dict[str, str] = {}
    for path in SRC.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
                continue
            if node.func.id != "FactLink":
                continue
            for keyword in node.keywords:
                if keyword.arg == "target" and isinstance(keyword.value, ast.Constant):
                    found[keyword.value.value] = f"{path.relative_to(SRC)}:{node.lineno}"
    return found


def _router_targets() -> frozenset[str]:
    """What the shipped window can follow, read off `_build_fact_link_router`
    without constructing a window."""
    source = (SRC / "app" / "main_window.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_build_fact_link_router":
            return frozenset(
                key.value
                for call in ast.walk(node)
                if isinstance(call, ast.Dict)
                for key in call.keys
                if isinstance(key, ast.Constant)
            )
    raise AssertionError("_build_fact_link_router is gone")


def test_the_emitted_population_is_not_empty():
    """Asserts its own setup: a walk returning nothing makes the coverage
    guard below vacuously true."""
    emitted = _emitted_targets()
    assert len(emitted) >= 5, f"the walk found only {emitted}"


def test_every_emitted_link_target_has_a_handler():
    """**FOUR OF THESE WERE DEAD BUTTONS.** `calculator_inspector`,
    `nmr_view` and `atom_report` are constructed by the shipped atom, bond
    and molecule reports and matched nothing in the old chain."""
    emitted = _emitted_targets()
    handled = _router_targets()
    dead = {t: where for t, where in emitted.items() if t not in handled}
    assert not dead, (
        "these links render a button that does nothing: "
        + ", ".join(f"{t} ({where})" for t, where in sorted(dead.items()))
    )


def test_no_producer_computes_a_link_target():
    """The narrow half of the derived walk. A computed target cannot be
    checked statically, so the coverage guard above would under-report
    without noticing -- the green-suite-and-a-smaller-universe failure."""
    computed: list[str] = []
    for path in SRC.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
                continue
            if node.func.id != "FactLink":
                continue
            for keyword in node.keywords:
                if keyword.arg == "target" and not isinstance(keyword.value, ast.Constant):
                    computed.append(f"{path.relative_to(SRC)}:{node.lineno}")
    assert not computed, (
        "a computed FactLink target cannot be checked for a handler: "
        + ", ".join(computed)
    )


# --- the three outcomes --------------------------------------------------


def _link(target: str, **params) -> FactLink:
    return FactLink(target=target, params=params, label="Open Something")


def test_a_handler_that_opens_reports_opened():
    router = FactLinkRouter({"thing": lambda _params: True})
    result = router.follow(_link("thing"))
    assert result.outcome is LinkOutcome.OPENED
    assert result.opened
    assert result.message == "", "nothing to say when it worked"


def test_a_handler_that_declines_is_unavailable_and_says_so():
    """Returning False is how a handler says "I know this target and the
    thing it names is not here" -- so declining never needs an exception."""
    router = FactLinkRouter({"thing": lambda _params: False})
    result = router.follow(_link("thing"))
    assert result.outcome is LinkOutcome.UNAVAILABLE
    assert not result.opened
    assert "Open Something" in result.message
    assert result.message.strip(), "an unavailable viewer must still say something"


def test_an_unknown_target_is_a_visible_diagnostic_rather_than_silence():
    """**THE WHOLE POINT.** The old chain fell off the end here."""
    router = FactLinkRouter({"thing": lambda _params: True})
    result = router.follow(_link("nobody_wired_this"))
    assert result.outcome is LinkOutcome.UNKNOWN
    assert "nobody_wired_this" in result.message


def test_unavailable_and_unknown_are_different_outcomes():
    """Two, not one. A viewer that cannot open right now is a fact about this
    molecule's state; a target nobody wired is a defect. Collapsing them would
    make the second unreportable."""
    router = FactLinkRouter({"thing": lambda _params: False})
    assert router.follow(_link("thing")).outcome is LinkOutcome.UNAVAILABLE
    assert router.follow(_link("other")).outcome is LinkOutcome.UNKNOWN


def test_a_handler_that_raises_does_not_escape_the_click_path():
    """The reader gets a sentence rather than a traceback out of a click, and
    the log gets the traceback rather than a shrug."""

    def boom(_params):
        raise RuntimeError("viewer exploded")

    result = FactLinkRouter({"thing": boom}).follow(_link("thing"))
    assert result.outcome is LinkOutcome.UNAVAILABLE
    assert "Open Something" in result.message


def test_a_link_with_no_label_still_produces_a_sentence():
    """A producer may omit the label. The message must not become "Could not
    open ''"."""
    router = FactLinkRouter({})
    message = router.follow(FactLink(target="x", params={})).message
    assert message.strip()
    assert "''" not in message


def test_the_params_reach_the_handler_unchanged():
    seen: dict = {}
    router = FactLinkRouter({"thing": lambda params: seen.update(params) or True})
    router.follow(_link("thing", symbol="Fe", atom=7))
    assert seen == {"symbol": "Fe", "atom": 7}


def test_a_link_with_no_params_hands_the_handler_an_empty_mapping():
    """`params` defaults to a dict, but a producer could pass None. A handler
    doing `params.get(...)` must not have to guard."""
    seen: list = []
    router = FactLinkRouter({"thing": lambda params: seen.append(params) or True})

    class _Bare:
        target = "thing"
        params = None
        label = "x"

    assert router.follow(_Bare()).opened
    assert seen == [{}]


# --- the window's own handlers -------------------------------------------


def test_the_router_exposes_what_it_can_follow():
    """So a guard compares it against what producers emit rather than against
    a list somebody maintains."""
    router = FactLinkRouter({"a": lambda _p: True, "b": lambda _p: True})
    assert router.targets() == frozenset({"a", "b"})


def test_the_calculator_inspector_handler_accepts_both_shapes():
    """Two producers emit this target with different params: `atom_report`
    names a `calculator_id` (a per-atom dataset) and `molecule_report` a
    `descriptor_id` (a Properties row). Both mean "show me the tool this came
    from"; they differ in where that tool is.

    Asserted on the SOURCE because reaching either branch needs a real window
    with a project and a retained result, and this is a claim about the
    handler covering both shapes rather than about either destination.
    """
    source = (SRC / "app" / "main_window.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_link_to_calculator_inspector":
            body = ast.unparse(node)
            assert "calculator_id" in body
            assert "descriptor_id" in body
            return
    raise AssertionError("_link_to_calculator_inspector is gone")


@pytest.mark.parametrize(
    "handler",
    [
        "_link_to_periodic_table",
        "_link_to_structure_check",
        "_link_to_interactions",
        "_link_to_atom_report",
        "_link_to_calculator_inspector",
        "_link_to_nmr_view",
    ],
)
def test_every_handler_returns_a_bool_on_every_path(handler):
    """A handler that falls off its own end returns None, which the router
    reads as "did not open" -- correct, but only by accident. Every exit must
    be a deliberate answer.
    """
    source = (SRC / "app" / "main_window.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not (isinstance(node, ast.FunctionDef) and node.name == handler):
            continue
        returns = [n for n in ast.walk(node) if isinstance(n, ast.Return)]
        assert returns, f"{handler} returns nothing at all"
        for statement in returns:
            assert statement.value is not None, f"{handler} has a bare return"
        # And the last statement of the body is a return, so no path can fall
        # off the end.
        assert isinstance(node.body[-1], ast.Return), (
            f"{handler} can fall off its end and answer None by accident"
        )
        return
    raise AssertionError(f"{handler} is gone")
