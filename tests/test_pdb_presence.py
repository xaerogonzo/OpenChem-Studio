"""The leakage bound's lookup, and the HTTP 204 that means ABSENT.

RCSB answers a zero-hit chemical-component search with **204 and an empty
body**, so the obvious `except Exception: return None` reads "this compound is
not in the PDB" as a failure -- and folding failure and absence together
biases the leakage split OPTIMISTIC, because the excluding arm then quietly
contains compounds nobody could resolve.

**TWO FIXTURES CANNOT SEE THAT DEFECT.** A 200-with-hits and a 204-empty pair
is satisfied by "treat 204 as unresolved" AND by "treat every non-200 as
absent" -- the first mutation makes the ABSENT case vanish into UNRESOLVED and
the second makes a timeout look like a clean exclusion, and a two-valued test
distinguishes neither. It takes THREE: a hit, a real absence, and a fault.
"""

from __future__ import annotations

import importlib.util
import io
import sys
from pathlib import Path
from urllib.error import HTTPError

import pytest

_MODULE = Path(__file__).resolve().parents[1] / "benchmarks" / "docking" / "pdb_presence.py"

#: A well-formed key that is not any particular compound. The SHAPE has to be
#: right or `lookup` refuses it before any request, which is itself a case
#: below.
WELL_FORMED = "AAAAAAAAAAAAAA-BBBBBBBBBB-C"


def _module():
    spec = importlib.util.spec_from_file_location("_bench_pdb_presence", _MODULE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # REGISTERED BEFORE EXECUTION. A dataclass or Enum defined in a module
    # loaded by path raises `AttributeError: 'NoneType' object has no attribute
    # '__dict__'` without this, because it resolves its own `__module__`
    # through `sys.modules`. Same recipe as
    # `tests/test_conformer_benchmark_overlap.py`.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _Response(io.BytesIO):
    """Just enough of an HTTP response for `lookup` to read."""

    def __init__(self, body: bytes, status: int = 200) -> None:
        super().__init__(body)
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *_exc) -> bool:
        return False


@pytest.fixture
def presence(monkeypatch):
    module = _module()

    def serve(response):
        def fake_open(url, timeout=None, headers=None):  # noqa: ARG001
            if isinstance(response, Exception):
                raise response
            return response()

        monkeypatch.setattr(module, "open_url", fake_open)

    module.serve = serve
    return module


def test_a_hit_is_PRESENT_and_names_the_component(presence):
    """The identifier travels with the verdict, because a reader auditing a
    PRESENT row wants to see WHICH component -- an id is checkable against
    RCSB by hand where a bare boolean is not."""
    presence.serve(lambda: _Response(b'{"result_set": [{"identifier": "8NU"}]}'))

    verdict, components = presence.lookup(WELL_FORMED)

    assert verdict is presence.PdbPresence.PRESENT
    assert components == ["8NU"]


def test_a_204_with_an_empty_body_is_ABSENT_and_not_a_failure(presence):
    """THE TRAP. `json.loads(b"")` raises, so a blanket except turns RCSB's
    own way of saying "nothing matched" into "I could not find out" -- and
    every compound would then leave the excluding arm of the leakage split."""
    presence.serve(lambda: _Response(b"", status=204))

    verdict, components = presence.lookup(WELL_FORMED)

    assert verdict is presence.PdbPresence.ABSENT
    assert components == []


def test_a_204_delivered_as_an_HTTPError_is_ALSO_absent(presence):
    """Some stacks raise 204 rather than returning it, and both routes have to
    mean the same thing -- otherwise the verdict depends on the urllib
    version rather than on the compound."""
    presence.serve(HTTPError("u", 204, "No Content", {}, None))

    verdict, _ = presence.lookup(WELL_FORMED)

    assert verdict is presence.PdbPresence.ABSENT


def test_a_server_fault_is_UNRESOLVED_and_never_ABSENT(presence):
    """THE THIRD FIXTURE, and the one that makes the pair above a test rather
    than a coincidence. A 503 or a timeout says nothing about the compound,
    and calling it ABSENT would put an unchecked molecule into the arm that
    claims to exclude training data."""
    presence.serve(HTTPError("u", 503, "Service Unavailable", {}, None))

    verdict, _ = presence.lookup(WELL_FORMED)

    assert verdict is presence.PdbPresence.UNRESOLVED


def test_a_timeout_is_UNRESOLVED(presence):
    presence.serve(TimeoutError("took too long"))

    assert presence.lookup(WELL_FORMED)[0] is presence.PdbPresence.UNRESOLVED


def test_a_200_with_an_empty_result_set_is_a_real_absence(presence):
    """A complete answer that found nothing. Distinct from the 204 route only
    in how RCSB chose to say it, and it must not be UNRESOLVED."""
    presence.serve(lambda: _Response(b'{"result_set": []}'))

    assert presence.lookup(WELL_FORMED)[0] is presence.PdbPresence.ABSENT


def test_an_unparseable_body_is_UNRESOLVED(presence):
    """A 200 carrying something that is not JSON is a broken answer, not an
    absence -- the same distinction as the fault case, arriving through the
    parser instead of the socket."""
    presence.serve(lambda: _Response(b"<html>gateway error</html>"))

    assert presence.lookup(WELL_FORMED)[0] is presence.PdbPresence.UNRESOLVED


@pytest.mark.parametrize(
    "key",
    ["", "not-a-key", "AAAA-BBBB-C", "AAAAAAAAAAAAAA-BBBBBBBBBB", "AAAAAAAAAAAA12-BBBBBBBBBB-C"],
)
def test_a_malformed_key_is_UNRESOLVED_without_asking_anybody(presence, key):
    """CHECKED HERE RATHER THAN INFERRED FROM THE REPLY, because RCSB would
    answer 204 for a key that cannot match anything -- indistinguishable from
    a real absence. A key this module could not have looked up correctly must
    not be recorded as an exclusion.

    The request is never made: the fake raises if it is reached.
    """
    presence.serve(AssertionError("a malformed key must not reach the network"))

    assert presence.lookup(key)[0] is presence.PdbPresence.UNRESOLVED


def test_the_verdict_is_three_valued(presence):
    """Guarding the vocabulary itself. Collapsing this to a bool is the change
    that would silently re-introduce the 204 defect, and it would look like a
    simplification."""
    assert len(list(presence.PdbPresence)) == 3
