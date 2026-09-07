"""One greek alpha killed an eight-hour docking run at 85%.

ChEMBL's assay description for `1ERE_CHEMBL5732098` says "estrogen receptor
alpha" with the LETTER. `sys.stdout.encoding` on this platform is cp1252,
which cannot encode U+03B1, so `print` raised `UnicodeEncodeError` and took
the run with it -- after every search it had already completed was safely on
disk. Measured over the built corpus: 58 of 1810 series carry a non-ASCII
assay description, 2 of them in the frozen 77.

**THE FUNCTION IS TESTED WITHOUT IMPORTING ITS MODULE**, because
`rank_power.py` imports Open Babel, the Vina configuration and the receptor
library at module scope -- none of which this question needs, and any of
which can be absent in an environment where the encoding rule still has to
hold. The source is parsed and the one function compiled out of it, which
also means the test fails if it is renamed or deleted rather than silently
testing a copy.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

BENCHMARK = (
    pathlib.Path(__file__).resolve().parent.parent
    / "benchmarks" / "docking" / "rank_power.py"
)

#: Every non-ASCII character found in the corpus's assay descriptions, plus
#: the replacement character -- which is ChEMBL's OWN mojibake arriving
#: intact, not something this project introduced.
FOUND_IN_THE_CORPUS = "μ\xb0αβ−\xd7\xc2\xaeλ\xb3\xbc\xce�"


def _module() -> ast.Module:
    return ast.parse(BENCHMARK.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def console_safe():
    """`console_safe` compiled out of the benchmark, with nothing else run."""
    tree = _module()
    wanted = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "console_safe"
    ]
    assert wanted, "rank_power.py no longer defines console_safe"
    namespace: dict = {}
    exec(compile(ast.Module(body=wanted, type_ignores=[]), "<rank_power>", "exec"),
         {"sys": __import__("sys")}, namespace)
    return namespace["console_safe"]


@pytest.mark.parametrize("codepage", ["cp1252", "cp437", "cp850", "ascii"])
@pytest.mark.parametrize("character", list(FOUND_IN_THE_CORPUS))
def test_every_character_the_corpus_carries_survives_being_printed(
    console_safe, monkeypatch, codepage, character
):
    """The real population, one case each, against four real consoles.

    **THE CONTRACT IS "SAFE FOR THIS STREAM", NOT "SAFE FOR ALL STREAMS"**,
    which the first version of this test got wrong: under pytest
    `sys.stdout.encoding` is utf-8, so `console_safe` correctly KEEPS the
    character, and demanding the result also encode as cp437 failed against
    working code. The stream has to be named for the question to mean
    anything.

    Four codepages because `CLAUDE.md` records that cp1252 is the wrong one to
    assert against on its own -- cp437 and cp850 are stricter, and an em dash
    passes a cp1252 check while still rendering as a replacement character on
    a real console.

    One case per character rather than a representative: a single alpha would
    pass while a mu still crashed, which is close to what happened -- the run
    cleared eight MAO-B series carrying a mu and died on the first alpha.
    """
    class _Stream:
        encoding = codepage

    monkeypatch.setattr("sys.stdout", _Stream())
    rendered = console_safe(f"ER-{character} binding")
    rendered.encode(codepage)  # must not raise, which is the whole point
    assert rendered.startswith("ER-")


def test_it_asks_the_STREAM_rather_than_assuming_ascii(console_safe, monkeypatch):
    """A UTF-8 console must keep the character, not lose it to a hardcoded floor.

    `CLAUDE.md` records that cp1252 is the wrong codepage to assert against --
    a real console is often cp437 or cp850, which are stricter. The cure is to
    encode through the stream's OWN encoding rather than to pick one, so this
    degrades further on a stricter console and not at all on a UTF-8 one.
    """
    class _Stream:
        encoding = "utf-8"

    monkeypatch.setattr("sys.stdout", _Stream())
    assert console_safe("ER-α") == "ER-α"


def test_a_stream_with_no_encoding_still_gets_an_answer(console_safe, monkeypatch):
    """A redirected stream can report `encoding` as None.

    Falling through to `None` would raise inside the very helper that exists
    to stop a print raising, which is the failure mode installed in its own
    cure.
    """
    class _Stream:
        encoding = None

    monkeypatch.setattr("sys.stdout", _Stream())
    assert console_safe("ER-α").startswith("ER-")


def test_the_assay_description_is_printed_THROUGH_it():
    """The wiring, not the helper -- testing a helper is not testing the wiring.

    Asserted on the source because the print happens inside a function that
    needs a receptor, a Vina binary and a docking provider to reach.
    """
    for node in ast.walk(_module()):
        if not isinstance(node, ast.Call):
            continue
        if not (isinstance(node.func, ast.Name) and node.func.id == "print"):
            continue
        printed = ast.unparse(node)
        if "assay_description" in printed:
            assert "console_safe" in printed, (
                "the assay description reaches print() raw again -- one greek "
                f"letter ends the run: {printed}"
            )
            return
    pytest.fail("no print of assay_description found; has the line moved?")
