"""The committed Ketcher bundle must match the source it was built from.

`tools/ketcher-host/src/main.jsx` is source we own; `resources/ketcher/dist/`
is its build output, committed so the app runs without a node toolchain.
**Editing the JSX does nothing until `npm run build` regenerates the dist**,
and forgetting that is silent: every test passes, the app starts, and the
feature simply is not there. It nearly shipped that way once.

WHY THIS IS A STRING CHECK AND NOT A REBUILD-AND-DIFF.

The obvious check is "rebuild in CI and fail if the output differs". It was
measured and rejected:

- The build IS byte-for-byte reproducible on one machine -- verified by
  snapshotting the dist, running `npm run build` again, and diffing: 5 files,
  zero differences, `git status` clean afterwards.
- But CI runs Linux with a different node, and reproducibility across
  toolchains is a far stronger claim than reproducibility on one. A single
  byte of difference from a minifier or path separator would fail every pull
  request for no real reason, and a check that cries wolf gets deleted.
- It would also mean installing node in CI purely to validate an artifact,
  adding about a minute to every run.

The bridge METHOD NAMES cannot be minified away -- they are property
accesses on an object supplied by Qt's WebChannel, so no minifier may rename
them (confirmed: all four appear intact in the 35 MB production bundle). That
makes them a reliable fingerprint of "was this bundle built from this
source", at no build cost and with no platform sensitivity.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_MAIN_JSX = _ROOT / "tools" / "ketcher-host" / "src" / "main.jsx"
_DIST = _ROOT / "src" / "openchem" / "resources" / "ketcher" / "dist"
_BACKEND = _ROOT / "src" / "openchem" / "ui" / "widgets" / "ketcher_editor_backend.py"

#: `bridgeObject.foo(` in the JSX -- the calls that end up inside the bundle.
_JSX_CALL = re.compile(r"bridgeObject\.([A-Za-z_][A-Za-z0-9_]*)\s*\(")
#: Bridge methods reached through the `INTERCEPTED` table rather than by
#: name -- `bridgeObject[INTERCEPTED[testid]]()`.
#:
#: **WITHOUT THIS THE GUARD SEES TWO OF NINE.** The interceptions were a
#: single hard-coded button, then a table; the table dispatches
#: dynamically, so `_JSX_CALL` stopped matching seven of them and the
#: test count went 16 -> 18 where it should have gone to 30. A guard
#: that silently narrows as the code generalises is worse than one that
#: was never written, because the count still goes up.
#:
#: **SCOPED TO THE TABLE, because it used to scan the whole file.** The
#: pattern is `key: 'value',`, which is ordinary JavaScript, so the first
#: object literal anybody added elsewhere in `main.jsx` was read as a
#: bridge method. The electron overlay's `{mode: 'off', ...}` did exactly
#: that and produced a confident failure about a `bridge.off()` that no
#: line of the file calls.
#:
#: Narrowing a guard is the more dangerous direction -- this file's own
#: docstring says so -- which is why `_bridge_slot_names` cross-checks
#: from the Python side and would fail if this scoping dropped a real
#: interception.
_JSX_TABLE_BLOCK = re.compile(r"const INTERCEPTED = \{(.*?)^\}", re.DOTALL | re.MULTILINE)
_JSX_TABLE_CALL = re.compile(r"^\s*'?[^']*'?\s*:\s*'([A-Za-z_][A-Za-z0-9_]*)',\s*$", re.MULTILINE)


def _bridge_slot_names(python_source: str) -> set[str]:
    """`_Bridge` methods named `...Requested` -- the interception slots.

    An INDEPENDENT source, used to notice the JSX parser narrowing. A
    parametrised guard shrinks silently when its input shrinks: measured,
    breaking `_bridge_names` took this file from 39 tests to 27 with
    nothing failing, because twelve tests simply stopped existing.
    """
    # `[A-Za-z0-9_]`, not `[A-Za-z_]`: `viewer3dRequested` carries a
    # DIGIT, and the first version of this regex silently missed it --
    # caught immediately by the cross-check below, which is the whole
    # point of having an independent source.
    return set(
        re.findall(r"^    def ([A-Za-z_][A-Za-z0-9_]*Requested)\(self\)",
                   python_source, re.MULTILINE)
    )


def _bridge_names(source: str) -> set[str]:
    """Every `_Bridge` method the JSX can reach, however it reaches it."""
    table = _JSX_TABLE_BLOCK.search(source)
    through_table = set(_JSX_TABLE_CALL.findall(table.group(1))) if table else set()
    return set(_JSX_CALL.findall(source)) | through_table
#: `__openchemBridge.foo(` in the Python file -- calls injected at runtime
#: through `runJavaScript`, which are NOT in the bundle and so are checked
#: only against the Python side.
_INJECTED_CALL = re.compile(r"__openchemBridge\.([A-Za-z_][A-Za-z0-9_]*)\s*\(")
#: A method on the `_Bridge` QObject. Qt matches these by name from JS.
_SLOT = re.compile(r"^    def ([A-Za-z_][A-Za-z0-9_]*)\(self", re.MULTILINE)


def jsx_source() -> str:
    return _MAIN_JSX.read_text(encoding="utf-8")


def bundle_text() -> str:
    """Every built JS asset, concatenated.

    Read as bytes and decoded loosely: the bundle carries minified content
    in several encodings' worth of escapes and is not guaranteed to be
    clean UTF-8.
    """
    parts = [
        path.read_bytes().decode("utf-8", errors="replace")
        for path in sorted((_DIST / "assets").glob("*.js"))
    ]
    return "".join(parts)


def test_the_source_and_the_bundle_both_exist():
    """Guards the guard. If either path moves, every assertion below turns
    vacuous rather than failing, which is the worst outcome for a check
    whose whole job is noticing absence."""
    assert _MAIN_JSX.exists(), f"missing {_MAIN_JSX}"
    assert (_DIST / "index.html").exists(), f"missing built bundle at {_DIST}"
    assert list((_DIST / "assets").glob("*.js")), "no JS assets in the bundle"


def test_the_jsx_actually_calls_the_bridge():
    """Another guard on the guard: if the JSX stopped using `bridgeObject`
    the extraction would find nothing and the staleness test would pass
    trivially forever."""
    assert _bridge_names(jsx_source()), "no bridgeObject calls found in main.jsx"


@pytest.mark.parametrize("name", sorted(_bridge_names(_MAIN_JSX.read_text(encoding="utf-8"))))
def test_every_bridge_call_in_the_source_is_present_in_the_built_bundle(name):
    """THE STALENESS CHECK.

    A bridge call added to `main.jsx` without re-running `npm run build`
    fails here, naming the method. That is exactly the mistake this exists
    for: `bondSelected` was written, the tests were green, and the bundle
    did not contain it until the build ran.

    These names survive minification because they are properties of an
    object Qt injects -- a minifier cannot know what the other side expects,
    so it must leave them alone.
    """
    assert name in bundle_text(), (
        f"main.jsx calls bridgeObject.{name}() but the committed bundle does "
        f"not contain it.\n\nThe dist is stale -- rebuild it:\n"
        f"    cd tools/ketcher-host && npm run build\n"
        f"(about a minute) and commit the regenerated "
        f"src/openchem/resources/ketcher/dist/."
    )


@pytest.mark.parametrize(
    "name",
    sorted(
        _bridge_names(_MAIN_JSX.read_text(encoding="utf-8"))
        | set(_INJECTED_CALL.findall(_BACKEND.read_text(encoding="utf-8")))
    ),
)
def test_every_bridge_call_has_a_python_method_to_receive_it(name):
    """The other direction: JS calling something Python does not implement.

    Qt's WebChannel matches by NAME, and a call to a method that does not
    exist fails silently in the page's console rather than raising anywhere
    a person will look -- which is why the Python slots are spelled in JS
    casing (`atomSelected`, not `atom_selected`) and carry a noqa for it.
    """
    slots = set(_SLOT.findall(_BACKEND.read_text(encoding="utf-8")))
    assert name in slots, (
        f"JS calls bridge.{name}() but no method of that name exists on "
        f"_Bridge in ketcher_editor_backend.py. WebChannel matches by name, "
        f"so this fails silently in the page rather than raising."
    )


def test_a_selection_is_never_forwarded_as_a_raw_ketcher_id():
    """The pool-id bug, guarded at the source where it is cheap to catch.

    `tests/test_ketcher_editor_backend.py` asserts the real behaviour against
    the real bundle, which costs a QtWebEngine page. This is the fast half:
    it fails the moment somebody "simplifies" the translation away, and it
    reads as a deliberate rule rather than as noise in a 35 MB diff.

    Ketcher's selection reports POOL IDS -- identity handles from a counter
    that only ever increments -- while the molfile is positional. Sending one
    where the other is expected made the Atom Inspector tell a user who had
    clicked a carbon to "pick a heavy atom".
    """
    source = jsx_source()

    for name, key in (("atomSelected", "atoms"), ("bondSelected", "bonds")):
        assert not re.search(rf"bridgeObject\.{name}\(\s*{key}\[", source), (
            f"main.jsx passes a raw Ketcher pool id to bridgeObject.{name}(). "
            f"Pool ids are not molfile positions -- they diverge as soon as "
            f"anything is deleted. Translate with molfilePosition() first."
        )
        assert f"bridgeObject.{name}(position)" in source, (
            f"expected bridgeObject.{name}() to forward a translated position"
        )

    assert "function molfilePosition(" in source, "molfilePosition() is gone"
    for pool in ("struct.atoms", "struct.bonds"):
        assert f"molfilePosition({pool}," in source, (
            f"{pool} selections are not being translated"
        )

    # INSERTION ORDER, NOT SORTED, and this is the one that would regress
    # silently. Undo re-inserts a deleted atom under its original id at the
    # END of the Map, so ids can run [1,2,3,4,5,0]; the molfile follows that
    # same order (measured: N O F S P C on a C-N-O-F-S-P chain with the
    # carbon deleted and restored), so sorting would be wrong in every
    # position while still producing entirely plausible indices.
    helper = source.split("function molfilePosition(")[1].split("\n}")[0]
    assert ".sort(" not in helper, (
        "molfilePosition() sorts the pool keys. The molfile follows the "
        "pool's INSERTION order, which undo can leave out of numeric order "
        "-- sorting reintroduces the off-by-one this function exists to fix."
    )


def test_the_bundle_index_points_at_a_file_that_exists():
    """A rebuild renames assets by content hash. If `index.html` were
    committed pointing at a file that was not, the editor would load blank
    -- the one failure mode of a hash-named bundle that is invisible until
    somebody opens the app.
    """
    html = (_DIST / "index.html").read_text(encoding="utf-8")
    referenced = re.findall(r'(?:src|href)="\./(assets/[^"]+)"', html)
    assert referenced, "index.html references no assets at all"
    for reference in referenced:
        assert (_DIST / reference).exists(), (
            f"index.html references {reference}, which is not in the bundle. "
            "A rebuild renames assets by content hash -- commit all of dist/, "
            "not just index.html."
        )


def test_the_jsx_parser_sees_every_interception_slot():
    """The guard above is parametrised over what the JSX parser finds, so
    if that parser narrows, tests VANISH rather than fail -- and the count
    going down is the only symptom. Measured: 39 -> 27 when the dispatch
    table stopped being read.

    `_Bridge`'s own `...Requested` slots are an independent source: every
    one exists to receive an interception, so the two sets must match.
    """
    from_jsx = {n for n in _bridge_names(_MAIN_JSX.read_text(encoding="utf-8"))
                if n.endswith("Requested")}
    from_python = _bridge_slot_names(_BACKEND.read_text(encoding="utf-8"))

    assert from_jsx == from_python, (
        f"only in the JSX: {sorted(from_jsx - from_python)}; "
        f"only in _Bridge: {sorted(from_python - from_jsx)}"
    )


#: The placement constants that must mean the same thing in both languages.
#: The JS places the dots; `chem/electron_layout.py` judges them. If the
#: two drift apart the judge starts failing a placement that obeyed the
#: rules it was actually given -- or worse, passing one that did not.
_SHARED_ELECTRON_CONSTANTS = (
    "MIN_SLOT_SEPARATION_DEGREES",
    "MIN_BOND_CLEARANCE_DEGREES",
    "SLOT_RADIUS_FRACTION",
    "PAIR_HALF_GAP_FRACTION",
    "LABEL_PADDING_FRACTION",
)


@pytest.mark.parametrize("name", _SHARED_ELECTRON_CONSTANTS)
def test_the_electron_constants_agree_across_the_language_boundary(name):
    """A source check, not an import: the JS cannot import Python.

    Same technique as the bridge names above and for the same reason --
    a value that drifts on one side of the boundary is exactly what
    nothing else would notice. The Python side is authoritative because
    it is the one with the tests that explain what each number is for.
    """
    from openchem.chem import electron_layout

    expected = getattr(electron_layout, name)
    pattern = re.compile(r"const %s = ([0-9.]+)" % name)
    found = pattern.search(_MAIN_JSX.read_text(encoding="utf-8"))

    assert found, (
        f"main.jsx declares no `const {name}`. The placement and the checker "
        f"share this value; drop it on one side and the judge is grading "
        f"against rules the page was never given."
    )
    assert float(found.group(1)) == pytest.approx(float(expected)), (
        f"{name} is {found.group(1)} in main.jsx and {expected} in "
        f"chem/electron_layout.py"
    )
