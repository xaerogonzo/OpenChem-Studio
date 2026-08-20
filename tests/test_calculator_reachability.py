"""Every calculator runs, and every declared provider is reachable.

**THE GAP THIS EXISTS TO CLOSE WAS REAL AND LASTED A WHOLE RELEASE.**
PR #41 shipped `chem/hlb.py`, `chem/tsei.py`, `chem/polarizability_miller.py`
and `chem/gutmann.py` -- four modules, each correct, each guarded by its own
test file, each with a `docs/sources.toml` entry -- and **not one of them
was reachable from anything a user could press.** Measured against the live
registry rather than by grep, because a dynamic import would make a text
search lie: 51 calculators backed by 27 modules, and none of the four
among them.

Every test that existed passed. "Shipped" had come to mean "the file
exists" rather than *source -> registry -> UI*.

So this file checks BOTH directions:

    forward   every registered calculator's compute is importable and
              callable, from the LIVE registry rather than a list
    reverse   every module that DECLARES itself user-facing is reachable
              from some registered calculator

The reverse direction is the one that was missing.

**USER-FACING IS DECLARED, NEVER INFERRED FROM LIVING UNDER `chem/`.**
That inference is `inapplicable_calculators` again -- a rule keyed on
something incidental, which rotted into 27 wrong entries because nothing
forced anybody back to it. A module says so about itself with a
`USER_FACING_PROVIDER` string naming the surface it reaches, and this
file reads the declaration. An exemption LIST would be the same blocklist
in a new place.

**WHAT THIS DOES NOT CLAIM.** A module without the marker is not asserted
to be internal; it is simply not making a claim. That is the same scope
`DEFERRALS` has in `tests/test_docs_are_current.py`, and it is why the
marker is worth adding to a module the day somebody notices it should be
user-facing rather than being back-filled across the tree by a script.
"""

from __future__ import annotations

import ast
import importlib
from functools import lru_cache
from pathlib import Path

import pytest

from openchem.chem.descriptor_providers import CALCULATOR_DEFINITIONS

_SRC = Path(__file__).resolve().parent.parent / "src" / "openchem"
_MARKER = "USER_FACING_PROVIDER"


# --- forward: everything registered actually runs ---------------------------


@pytest.mark.parametrize(
    "definition", CALCULATOR_DEFINITIONS, ids=lambda d: d.calculator_id
)
def test_every_registered_calculator_has_a_callable_compute(definition):
    """Enumerated from the LIVE registry, never from a list beside it."""
    execution = definition.execution
    assert execution is not None, f"{definition.calculator_id} declares no execution"
    assert callable(execution.compute), (
        f"{definition.calculator_id}'s compute is not callable"
    )


# --- reverse: everything declared is reachable ------------------------------


@lru_cache(maxsize=1)
def _import_graph() -> dict[str, set[str]]:
    """`{module: modules it imports}` over first-party source.

    **EVERY `Import` NODE, AT ANY DEPTH.** Two of the four modules this
    guard was written for are reached through a DEFERRED import inside a
    function body -- `electronic_properties` imports Miller inside its
    dispatch, and `lewis` imports Gutmann inside the line builder -- so a
    walk restricted to module-level imports would report both unreachable
    and be wrong about it.

    `vendor/` is excluded: 5,000-line upstream code that no claim here is
    about.
    """
    graph: dict[str, set[str]] = {}
    for path in sorted(_SRC.rglob("*.py")):
        if "vendor" in path.parts:
            continue
        name = "openchem." + ".".join(
            path.relative_to(_SRC).with_suffix("").parts
        ).removesuffix(".__init__")
        edges: set[str] = set()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.startswith("openchem"):
                    edges.add(node.module)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("openchem"):
                        edges.add(alias.name)
        graph[name] = edges
    return graph


@lru_cache(maxsize=1)
def _reachable_from_the_registry() -> set[str]:
    """Every module transitively reachable from a registered compute."""
    graph = _import_graph()
    seen: set[str] = set()
    stack = [
        definition.execution.compute.__module__
        for definition in CALCULATOR_DEFINITIONS
        if definition.execution and definition.execution.compute
    ]
    while stack:
        module = stack.pop()
        if module in seen:
            continue
        seen.add(module)
        stack.extend(graph.get(module, ()))
    return seen


@lru_cache(maxsize=1)
def _declared_providers() -> dict[str, str]:
    """`{module: what it says it provides}` for every declared provider.

    Read from the SOURCE rather than by importing every module, so a
    module that is unreachable AND unimportable still shows up as a
    failure of this guard rather than as a collection error somewhere
    else.
    """
    out: dict[str, str] = {}
    for path in sorted(_SRC.rglob("*.py")):
        if "vendor" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if _MARKER not in text:
            continue
        name = "openchem." + ".".join(
            path.relative_to(_SRC).with_suffix("").parts
        ).removesuffix(".__init__")
        module = importlib.import_module(name)
        value = getattr(module, _MARKER, "")
        out[name] = str(value)
    return out


def test_there_are_declared_providers_to_check():
    """THE SETUP ASSERTION. A guard whose population is empty passes
    vacuously, and this one's population is a marker somebody has to
    remember to write -- exactly the thing that can silently go to zero."""
    assert len(_declared_providers()) >= 4, (
        "no module declares USER_FACING_PROVIDER, so the reverse check below "
        "is asserting nothing"
    )


@pytest.mark.parametrize(
    "module", sorted(_declared_providers()), ids=lambda m: m.split(".")[-1]
)
def test_every_declared_provider_is_reachable_from_a_calculator(module):
    """The check that was missing while four modules sat unreachable."""
    assert module in _reachable_from_the_registry(), (
        f"{module} declares itself user-facing and nothing a user can press "
        "reaches it. Either register a calculator that consumes it, or -- if it "
        "really is internal -- delete the USER_FACING_PROVIDER declaration and "
        "say so in the module docstring."
    )


@pytest.mark.parametrize(
    "module", sorted(_declared_providers()), ids=lambda m: m.split(".")[-1]
)
def test_every_declaration_names_the_surface_it_reaches(module):
    """A bare `True` records nothing. The string is what makes the failure
    above actionable and what a reader checks against the registry."""
    text = _declared_providers()[module]
    assert len(text) > 20, f"{module}'s declaration says nothing useful: {text!r}"


def test_the_reachability_walk_follows_a_deferred_import():
    """THE LOAD-BEARING HALF, and it is not the blanket one.

    Two of the four declared providers are reached ONLY through an import
    inside a function body. A walk restricted to module-level imports
    reports both unreachable and is wrong about it, so this asserts the
    specific edge rather than trusting the blanket check above -- which
    would pass just as happily if the graph were built some other way.
    """
    graph = _import_graph()
    assert "openchem.chem.polarizability_miller" in graph[
        "openchem.chem.electronic_properties"
    ], "the deferred Miller import is not in the graph"
    assert "openchem.chem.gutmann" in graph["openchem.chem.lewis"], (
        "the deferred Gutmann import is not in the graph"
    )

    # ... and the setup assertion: those really are deferred, not
    # module-level, so this test is about the case it names.
    for path, needle in (
        ("chem/electronic_properties.py", "from openchem.chem.polarizability_miller import"),
        ("chem/lewis.py", "from openchem.chem.gutmann import"),
    ):
        source = (_SRC / path).read_text(encoding="utf-8")
        assert f"\n{needle}" not in source, (
            f"{path} now imports it at module level, so this test no longer "
            "exercises the deferred-import case"
        )


def test_a_module_nothing_reaches_would_fail_this():
    """THE ARM THAT SAYS NO. Without it, "every declared provider is
    reachable" passes on a graph that reports everything reachable --
    which is the green-suite-and-a-smaller-universe failure this project
    has recorded before, in mirror image.
    """
    reachable = _reachable_from_the_registry()
    assert "openchem.chem.descriptor_providers" in reachable
    assert "openchem.app.main_window" not in reachable, (
        "the window is reachable from a calculator, which means the walk is "
        "returning everything and the guard above cannot fail"
    )
