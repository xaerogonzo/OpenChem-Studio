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

So this file checks THREE directions:

    forward   every registered calculator's compute is importable and
              callable, from the LIVE registry rather than a list
    reverse   every module that DECLARES itself user-facing is reachable
              from some registered calculator
    wide      every first-party module is statically reachable from
              `openchem.main`, or declares the non-import surface that
              reaches it

The reverse direction is the one that was missing. **The wide one is what
makes this a standing invariant rather than a spot-check** -- until it
existed the file checked the four modules that declare
`USER_FACING_PROVIDER` and nothing else, so a FIFTH unreachable module was
invisible unless somebody remembered to declare it. That is the same
"somebody remembers" failure the file is written against, one level up
from where it was being fought.

**THE INVARIANT IS STATIC IMPORT REACHABILITY, NOT "THE APPLICATION RUNS
THIS MODULE".** `_import_graph` is an AST walk over `import` statements. A
module can be genuinely used without appearing in one -- a script path
handed to another interpreter, `importlib`, plugin discovery, generated
registration -- and this project already has three such modules, which is
what makes the distinction concrete rather than pedantic. Nothing here
should ever be read as proof that the application EXECUTES anything.

Measured when the wide direction landed:

    first-party modules                        277
    statically reachable from openchem.main    274
    script_path (a separate interpreter)         2   admet_runner, pka_runner
    tooling (the suite and tools/, not the app)  1   tooltip_inventory

**USER-FACING IS DECLARED, NEVER INFERRED FROM LIVING UNDER `chem/`.**
That inference is `inapplicable_calculators` again -- a rule keyed on
something incidental, which rotted into 27 wrong entries because nothing
forced anybody back to it. A module says so about itself with a
`USER_FACING_PROVIDER` string naming the surface it reaches, and this
file reads the declaration. An exemption LIST would be the same blocklist
in a new place.

`REACHED_BY` is the same instinct pointed the other way, and its two
halves are deliberately different kinds of thing: the KIND before the
colon is a CLOSED vocabulary, so a typo cannot read as a new mechanism,
and the REASON after it is free text, so a new instance of a known
mechanism needs no code change. Exactly the split between `applies_to`
and `category`.

**WHAT THIS DOES NOT CLAIM.** A module without `USER_FACING_PROVIDER` is
not asserted to be internal; it is simply not making a claim. That is the
same scope `DEFERRALS` has in `tests/test_docs_are_current.py`, and it is
why the marker is worth adding to a module the day somebody notices it
should be user-facing rather than being back-filled across the tree by a
script.
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


class RelativeImportRefused(RuntimeError):
    """A relative import the walk cannot resolve, refused rather than dropped.

    **MEASURED BEFORE IT WAS WRITTEN: this codebase contains ZERO relative
    imports** -- no `ast.ImportFrom` with a non-zero `level` anywhere under
    `src/openchem`, vendor excluded. So resolving them would be machinery
    and fixtures for a case that does not exist, which is how a walk grows
    a second untested code path.

    Silently DROPPING one is the other failure, and it is the fail-open
    one: an edge the walk cannot see reads as an edge that is not there,
    and this whole file exists to stop "unreachable" being said about
    something that is reached. So an unresolvable import raises, naming
    the file. Same shape as the `**OPNE**` marker refusal and the
    inconclusive-probe rule -- *"I could not resolve this"* is not
    *"there is no edge here"*.
    """


def _with_parents(target: str) -> set[str]:
    """`a.b.c` -> {a, a.b, a.b.c}.

    **IMPORTING `a.b.c` IMPORTS `a.b`.** Without this a package's
    `__init__` reads unreachable while every consumer imports a submodule
    of it -- measured on `chem/regulatory/__init__.py`, which nothing
    imports by name because every importer wants `regulatory.engine`.
    """
    parts = target.split(".")
    return {".".join(parts[:i]) for i in range(1, len(parts) + 1)}


def _edges_from_source(text: str, label: str) -> set[str]:
    """First-party import edges in one module's source.

    Split out from the file walk so the relative-import refusal can be
    exercised on a snippet, rather than by writing a file into the tree
    to see the guard fire.
    """
    edges: set[str] = set()
    for node in ast.walk(ast.parse(text, filename=label)):
        if isinstance(node, ast.ImportFrom):
            if node.level:
                raise RelativeImportRefused(
                    f"{label} uses a relative import, which this walk does "
                    "not resolve. Rewrite it as an absolute import, or teach "
                    "_edges_from_source to resolve it -- but do not let it "
                    "pass silently, or a real edge disappears from the graph."
                )
            if not (node.module and node.module.startswith("openchem")):
                continue
            # BOTH the package AND each name under it. `from openchem.chem
            # import nmr_hybrid` names a MODULE, and recording only
            # `node.module` was the blind spot that reported two reachable
            # modules as unreachable. A name that is a CLASS rather than a
            # module yields a key no module has, which `graph.get(...)`
            # answers with nothing -- harmless, and deliberately not
            # "tidied" into a filesystem check, which would make the graph
            # depend on what is on disk rather than on what the source says.
            for alias in node.names:
                if alias.name != "*":
                    edges |= _with_parents(f"{node.module}.{alias.name}")
            edges |= _with_parents(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("openchem"):
                    edges |= _with_parents(alias.name)
    return edges


def _module_name(path: Path) -> str:
    """The dotted name of a first-party file.

    **THE ROOT PACKAGE KEYED WRONG UNTIL THIS WAS ITS OWN FUNCTION.**
    `removesuffix` binds to the `join`, not to the concatenation, so
    `"openchem." + "__init__".removesuffix(".__init__")` is
    `openchem.__init__` -- every SUBpackage came out right
    (`chem.regulatory.__init__` -> `chem.regulatory`) and only
    `src/openchem/__init__.py` did not, which is exactly the one nothing
    would notice.
    """
    parts = path.relative_to(_SRC).with_suffix("").parts
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(("openchem", *parts))


@lru_cache(maxsize=1)
def _import_graph() -> dict[str, set[str]]:
    """`{module: first-party modules it imports}`, STATICALLY.

    **EVERY `Import` NODE, AT ANY DEPTH.** Two of the four modules this
    guard was written for are reached through a DEFERRED import inside a
    function body -- `electronic_properties` imports Miller inside its
    dispatch, and `lewis` imports Gutmann inside the line builder -- so a
    walk restricted to module-level imports would report both unreachable
    and be wrong about it.

    **THIS IS AN AST WALK, NOT RUNTIME REACHABILITY**, and the difference
    is not academic here: `chem/admet_runner.py` and `chem/pka_runner.py`
    are handed to another interpreter as script paths and are correctly
    absent from this graph. Anything reading a green result as "the
    application executes every module" is reading it wrong.

    `vendor/` is excluded: 5,000-line upstream code that no claim here is
    about.
    """
    graph: dict[str, set[str]] = {}
    for path in sorted(_SRC.rglob("*.py")):
        if "vendor" in path.parts:
            continue
        graph[_module_name(path)] = _edges_from_source(
            path.read_text(encoding="utf-8"), str(path)
        )
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


def test_the_walk_follows_a_from_package_import():
    """THE BLIND SPOT THAT REPORTED TWO REACHABLE MODULES AS UNREACHABLE.

    `from openchem.chem import nmr_hybrid` names a MODULE, and the walk
    used to record `node.module` only -- so the edge landed on the
    PACKAGE and the submodule was never reached. Measured before the fix,
    rooted on the registry and the UI: `element_palettes` and
    `nmr_hybrid` both read unreachable, and both are plainly reached.

    The specific edge, not the blanket, for the reason the deferred-import
    guard beside this one gives: a blanket check passes just as happily if
    the graph were built some other way.
    """
    graph = _import_graph()
    assert "openchem.chem.nmr_hybrid" in graph[
        "openchem.ui.panels.quantum_chemistry_panel"
    ], "the `from openchem.chem import nmr_hybrid` edge is not in the graph"

    # ... and the setup assertion: it really is written that way, so this
    # test is about the case it names rather than passing for some other
    # reason once somebody rewrites the import.
    source = (_SRC / "ui" / "panels" / "quantum_chemistry_panel.py").read_text(
        encoding="utf-8"
    )
    assert "from openchem.chem import nmr_database, nmr_hybrid" in source, (
        "that import has been rewritten, so this test no longer exercises "
        "the from-package-import case it was written for"
    )


def test_the_walk_marks_a_parent_package_reachable():
    """Importing `a.b.c` imports `a.b`.

    `chem/regulatory/__init__.py` is imported by name by NOTHING -- every
    consumer wants `regulatory.engine` or `regulatory.loader` -- so
    without the parent rule it reads unreachable while being imported on
    every screening run.

    Asserts the RULE and its instance: the prefix set is what the graph is
    built from, and the engine edge is what makes it matter here.
    """
    assert _with_parents("a.b.c") == {"a", "a.b", "a.b.c"}

    graph = _import_graph()
    importers = {m for m, e in graph.items() if "openchem.chem.regulatory.engine" in e}
    assert importers, "nothing imports regulatory.engine, so this proves nothing"
    assert all("openchem.chem.regulatory" in graph[m] for m in importers), (
        "an importer of regulatory.engine does not reach the package itself"
    )


def test_the_root_package_keys_as_openchem():
    """`removesuffix` binds to the `join`, not to the concatenation.

    So `src/openchem/__init__.py` used to key as `openchem.__init__`.
    Every SUBpackage came out right -- `chem.regulatory.__init__` ->
    `chem.regulatory` -- and only the root did not, which is exactly the
    one nothing would notice. Both arms, because a fix that renamed every
    package would be worse than the bug.
    """
    assert _module_name(_SRC / "__init__.py") == "openchem"
    assert _module_name(_SRC / "chem" / "regulatory" / "__init__.py") == (
        "openchem.chem.regulatory"
    )
    assert _module_name(_SRC / "chem" / "hlb.py") == "openchem.chem.hlb"

    graph = _import_graph()
    assert "openchem" in graph
    assert "openchem.__init__" not in graph


def test_a_relative_import_is_refused_rather_than_dropped():
    """AN EDGE THE WALK CANNOT SEE READS AS AN EDGE THAT IS NOT THERE.

    That is the fail-open direction, and this whole file exists to stop
    "unreachable" being said about something that is reached -- so an
    import the walk cannot resolve raises instead of being skipped.

    **THE SECOND ARM IS WHY THERE IS NO RESOLVER.** Measured over all
    first-party source: ZERO relative imports. Resolution machinery and
    fixtures for a case the tree does not contain is a second untested
    code path; a refusal is one line and cannot be wrong. If that count
    ever stops being zero, this fails and names the file, which is the
    moment to decide between rewriting the import and teaching the walk.
    """
    for snippet in ("from . import foo\n", "from ..chem import bar\n"):
        with pytest.raises(RelativeImportRefused):
            _edges_from_source(snippet, "snippet.py")

    # An ABSOLUTE import of the same shape is accepted, so the refusal is
    # about `level` and not about `ImportFrom`.
    assert "openchem.chem.hlb" in _edges_from_source(
        "from openchem.chem import hlb\n", "snippet.py"
    )

    relative = [
        str(path.relative_to(_SRC))
        for path in sorted(_SRC.rglob("*.py"))
        if "vendor" not in path.parts
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, ast.ImportFrom) and node.level
    ]
    assert not relative, (
        f"{relative} use relative imports. The walk refuses them, so the "
        "graph is now incomplete -- rewrite them as absolute, or teach "
        "_edges_from_source to resolve them."
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


# --- the wide direction: every module is reachable, or says why not ---------


#: The application's real entry point -- `python -m openchem.main`.
#:
#: **ONE ROOT, AND THAT IS THE WHOLE POINT.** An earlier draft rooted on
#: this PLUS every registry compute, which is a loophole rather than
#: belt-and-braces: a compute module forced in as a root is DECLARED
#: reachable rather than SHOWN to be, so a broken registration would still
#: pass. Measured, the extra roots also bought nothing -- `openchem.main`
#: alone gives the identical answer, and
#: `test_the_registry_is_statically_reachable_from_the_entry_point`
#: asserts the property those roots were quietly assuming.
_ENTRY_POINT = "openchem.main"

#: Why a module can be legitimately absent from the import graph. CLOSED,
#: because a typo in a free-form kind would read as a silent exemption --
#: the same reason `applies_to` is a closed vocabulary while `category` is
#: not. The REASON after the colon is free text, because a new instance of
#: a known mechanism needs no code change.
_ENTRY_SURFACES = frozenset({"script_path", "tooling"})

_REACHED_BY = "REACHED_BY"


@lru_cache(maxsize=1)
def _statically_reachable() -> set[str]:
    """Every module reachable from the entry point by following imports."""
    graph = _import_graph()
    seen: set[str] = set()
    stack = [_ENTRY_POINT]
    while stack:
        module = stack.pop()
        if module in seen:
            continue
        seen.add(module)
        stack.extend(graph.get(module, ()))
    return seen


@lru_cache(maxsize=1)
def _declared_entry_surfaces() -> dict[str, str]:
    """`{module: its REACHED_BY string}`, read from SOURCE.

    Source rather than `importlib`, for the reason `_declared_providers`
    gives one function up -- and here it is load-bearing rather than
    merely tidy: `admet_runner` and `pka_runner` are written to run under
    a DIFFERENT interpreter with different packages installed, so
    importing them to read a constant would be importing a module this
    environment is not the environment for.
    """
    out: dict[str, str] = {}
    for path in sorted(_SRC.rglob("*.py")):
        if "vendor" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if _REACHED_BY not in text:
            continue
        for node in ast.walk(ast.parse(text, filename=str(path))):
            if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == _REACHED_BY for t in node.targets
            ):
                out[_module_name(path)] = str(ast.literal_eval(node.value))
    return out


def test_the_registry_is_statically_reachable_from_the_entry_point():
    """The property the old registry roots were assuming rather than
    checking.

    If a calculator's compute module were reachable ONLY because the test
    added it as a root, a broken registration would pass a guard whose
    whole subject is reachability. It is not: the registry is reached from
    `openchem.main` by ordinary imports, so it needs no root of its own.
    """
    reachable = _statically_reachable()
    assert _ENTRY_POINT in reachable
    assert "openchem.chem.descriptor_providers" in reachable, (
        "the calculator registry is not reachable from the entry point, so "
        "no calculator is -- which is a far larger finding than this test"
    )
    for definition in CALCULATOR_DEFINITIONS:
        if definition.execution and definition.execution.compute:
            module = definition.execution.compute.__module__
            assert module in reachable, (
                f"{definition.calculator_id} computes in {module}, which the "
                "entry point cannot reach"
            )


def test_every_module_is_statically_reachable_or_declares_why_not():
    """THE WIDE DIRECTION, and the one that makes this a standing
    invariant rather than a spot-check.

    Until this existed the file checked only the modules that DECLARE
    `USER_FACING_PROVIDER` -- four of them -- so a fifth unreachable
    module was invisible unless somebody remembered to declare it. That
    is the "somebody remembers" failure the whole file is written
    against, one level up from where it was being fought.

    **STATIC IMPORT REACHABILITY, NOT "THE APPLICATION RUNS THIS".** A
    module can be genuinely used without an import edge, which is why
    `REACHED_BY` exists at all rather than this being a bare assertion.
    """
    unreachable = set(_import_graph()) - _statically_reachable()
    undeclared = sorted(unreachable - set(_declared_entry_surfaces()))

    assert not undeclared, (
        f"{undeclared} are not statically reachable from {_ENTRY_POINT} and "
        "do not say why. Either wire it to something a user can reach, or -- "
        "if it is entered by a non-import surface -- declare "
        f"{_REACHED_BY} on the module as '<kind>: <reason>', kind in "
        f"{sorted(_ENTRY_SURFACES)}."
    )


def test_a_declared_entry_surface_is_not_an_unconditional_exemption():
    """THE NARROW HALF, AND IT IS THE LOAD-BEARING ONE.

    Without it the marker becomes a way to turn a red guard green: write
    `REACHED_BY` on any module and it stops being checked. That is
    `inapplicable_calculators` in a new costume, and it is the mutation
    this pair exists to catch -- measured, adding the marker to a
    reachable module fails HERE and nowhere else.

    So a declared module must genuinely be unreachable, derived from the
    walk rather than trusted.
    """
    reachable = _statically_reachable()
    declared = _declared_entry_surfaces()
    assert declared, "nothing declares an entry surface, so this proves nothing"

    wrong = sorted(m for m in declared if m in reachable)
    assert not wrong, (
        f"{wrong} declare {_REACHED_BY} and ARE statically reachable. The "
        "declaration is for a module the import graph genuinely cannot see; "
        "on a reachable module it exempts something that needs no exemption "
        "and hides the next real one."
    )


@pytest.mark.parametrize(
    "module", sorted(_declared_entry_surfaces()), ids=lambda m: m.split(".")[-1]
)
def test_a_declared_entry_surface_names_a_known_kind_and_a_reason(module):
    """The CLOSED half and the FREE half, checked separately.

    A typo'd kind must fail rather than read as a new mechanism -- the
    `**OPNE**` lesson, where an unknown marker skipped instead of failing.
    The reason after it is prose and is held only to the non-empty floor
    `USER_FACING_PROVIDER` already sits on: this file does not grade
    English.
    """
    kind, _, reason = _declared_entry_surfaces()[module].partition(":")

    assert kind in _ENTRY_SURFACES, (
        f"{module} declares kind {kind!r}, which is not one of "
        f"{sorted(_ENTRY_SURFACES)}. Add it there deliberately if it is a "
        "real new mechanism; a kind nobody recognises must not read as one."
    )
    assert reason.strip(), f"{module} names a kind but no reason"


def test_the_two_sidecar_runners_are_the_script_path_case():
    """ASSERTING ITS OWN SETUP, because the pair above is vacuous if
    nothing is declared -- and because these two are the reason the
    static-versus-runtime distinction is concrete here rather than
    theoretical.

    Both are handed to a DIFFERENT interpreter as a path. They are the
    fixture demonstrating that an absent import edge is not an absent
    user, and they are in production rather than in a test.
    """
    declared = _declared_entry_surfaces()
    for module, importer in (
        ("openchem.chem.admet_runner", "chem/admet_providers.py"),
        ("openchem.chem.pka_runner", "chem/pka_providers.py"),
    ):
        assert declared.get(module, "").startswith("script_path:"), (
            f"{module} no longer declares the script-path surface"
        )
        # ... and the surface really is a PATH: the caller names the file
        # rather than importing it.
        runner = module.split(".")[-1]
        source = (_SRC / importer).read_text(encoding="utf-8")
        assert f"{runner}.py" in source, (
            f"{importer} no longer names {runner}.py, so the declared "
            "mechanism is not the one in the source"
        )
