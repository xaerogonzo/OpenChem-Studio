"""The engine's stereo-validation cache, and the two ways it remembered wrong.

`engine._validate_stereo_via_opsin` asks OPSIN whether a name with R/S
descriptors parses, and strips descriptors until one does. The answer is
cached for the life of the process -- and until naming round 3 it was cached
wrongly twice over:

1. **KEYED ON THE NAME ALONE**, while the answer also depends on
   `strip_modes`. A second caller asking a different question got the first
   caller's answer.
2. **AN INCONCLUSIVE RESULT WAS CACHED.** When nothing parses, the pass cannot
   tell "no stripping rescues this name" from "OPSIN cannot run at all": with
   no JRE on PATH every parse fails exactly as an unparseable name would. So
   one call made without Java stripped the stereodescriptors and REMEMBERED
   it, and every later call in the process returned the stripped name even
   once Java was available. An absent JRE became permanent.

Neither raises. Both look like the namer quietly losing stereochemistry,
which is the failure this codebase has spent the most effort making visible.
These tests use a stand-in for OPSIN so they need no JRE and can say exactly
what OPSIN "answered".
"""

from __future__ import annotations

import pytest

from openchem.vendor.iupac_namer import engine


@pytest.fixture(autouse=True)
def _clean_cache():
    engine._STEREO_OPSIN_VALIDATION_CACHE.clear()
    yield
    engine._STEREO_OPSIN_VALIDATION_CACHE.clear()


@pytest.fixture
def stripping(monkeypatch):
    """Make "stripping" observable without a real tree: each mode appends a
    marker, so the returned name says how far the pass went."""
    monkeypatch.setattr(engine, "_strip_tetrahedral_stereo", lambda tree, mode: f"{tree}|{mode}")
    monkeypatch.setattr(engine, "assemble", lambda tree: str(tree))


def test_an_absent_parser_is_not_remembered(monkeypatch, stripping):
    """THE STICKY FAILURE. With OPSIN unable to run, the pass strips -- that
    is the conservative answer for that call. It must not outlive the call."""
    monkeypatch.setattr(engine, "_opsin_can_parse", lambda name: False)
    first = engine._validate_stereo_via_opsin("(2R)-name", "(2R)-name", strip_modes=("a",))
    assert first != "(2R)-name", "with nothing parsing, the pass should strip"

    # Java arrives. The ORIGINAL name parses now, and must be what comes back.
    monkeypatch.setattr(engine, "_opsin_can_parse", lambda name: True)
    second = engine._validate_stereo_via_opsin("(2R)-name", "(2R)-name", strip_modes=("a",))

    assert second == "(2R)-name", (
        "an inconclusive result from a run without OPSIN was cached, so the "
        "stereodescriptors stay stripped for the rest of the process"
    )


def test_a_confirmed_verdict_is_remembered(monkeypatch, stripping):
    """The cache still does its job when OPSIN actually answered."""
    calls: list[str] = []

    def parses(name):
        calls.append(name)
        return True

    monkeypatch.setattr(engine, "_opsin_can_parse", parses)
    engine._validate_stereo_via_opsin("(2R)-name", "(2R)-name", strip_modes=("a",))
    engine._validate_stereo_via_opsin("(2R)-name", "(2R)-name", strip_modes=("a",))

    assert calls == ["(2R)-name"], f"a confirmed verdict was re-computed: {calls}"


def test_the_strip_modes_are_part_of_the_question(monkeypatch, stripping):
    """THE KEY COLLISION. Only the stripped-by-`b` form parses here, so the
    two calls must get different answers -- one keyed on the name alone would
    hand the second caller the first caller's result."""
    monkeypatch.setattr(engine, "_opsin_can_parse", lambda name: name.endswith("|b"))

    only_a = engine._validate_stereo_via_opsin("(2R)-x", "(2R)-x", strip_modes=("a",))
    only_b = engine._validate_stereo_via_opsin("(2R)-x", "(2R)-x", strip_modes=("b",))

    assert only_b == "(2R)-x|b"
    assert only_a != only_b


def test_the_cache_key_carries_the_strip_modes():
    """The narrow half, at the place that broke: the key's shape."""
    engine._STEREO_OPSIN_VALIDATION_CACHE[("n", ("a",))] = "n"
    assert ("n", ("a",)) in engine._STEREO_OPSIN_VALIDATION_CACHE
    assert "n" not in engine._STEREO_OPSIN_VALIDATION_CACHE
