"""The docs may not cite things that no longer exist.

At this size the danger is no longer bad code but a remembered assumption
that stopped being true. CLAUDE.md has drifted before -- it once carried
132 lines contradicting the four sections above them -- and this session
alone found two claims that had quietly become false (`CoordinationShell`
"discards positions", and metallocenes being recognised "only in the
ionic drawing").

**This is a guard, not a report.** An audit produces a list that rots
again in three months; a test cannot. Same direction as
`test_every_dock_the_window_builds_has_a_help_topic`: check what the
documents actually say against what actually exists.

Measured when it was written: 170 file paths and 26 test names cited
across five documents, and **zero genuinely stale**. Both initial hits
were the scanner misreading a legitimate reference, which is why the
allowlists below exist and why each entry carries its reason -- an
unexplained exemption is how a guard gets hollowed out.

**IT COVERED 6 OF THE 17 MARKDOWN FILES IN THE REPO**, which a sweep
found by listing them rather than by trusting the list. README.md and
QUICKSTART.md are the first things anybody reads and neither was
guarded. All 15 that cite anything are covered now; the two that do not
(CHANGELOG.md, CODE_OF_CONDUCT.md) are left out because adding a file
with nothing to check makes the list look more thorough than it is.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Callable

import pytest

_ROOT = Path(__file__).resolve().parent.parent

DOCS = [
    "CLAUDE.md",
    "README.md",
    "BASIC_INSTRUCTIONS.md",
    "CONTRIBUTING.md",
    "docs/ARCHITECTURE.md",
    "docs/NAVIGATION_AUDIT.md",
    "docs/SCIENTIFIC_LIMITATIONS.md",
    "docs/USER_GUIDE.md",
    "docs/PLUGIN_SDK.md",
    "docs/QUICKSTART.md",
    "docs/README.md",
    "docs/ROADMAP.md",
    "docs/VALIDATION.md",
    "docs/DREIDING_ASSESSMENT.md",
    "docs/SELF_HOSTED_RUNNER.md",
]

#: Backticked paths that deliberately do NOT resolve in this repo, each
#: with the reason. Anything added here needs one.
ALLOWED_MISSING_PATHS = {
    # A path inside the upstream molstar npm package, cited to say where
    # our viewer.html was adapted from. It is not ours and never will be.
    "build/viewer/embedded.html",
    # The three STOUT modules, named by ROADMAP.md on the line that says
    # "Deleted:". A document recording a removal has to be able to say
    # what it removed, and the absence is the point rather than a stale
    # reference -- the same reason `test_highlighting_survives_a_repaint`
    # is allowed below.
    "chem/stout_providers.py",
    "chem/stout_runner.py",
    "services/stout_setup.py",
}

#: Test names cited as HISTORY rather than as tests to go and find.
ALLOWED_MISSING_TESTS = {
    # CLAUDE.md names this one while explaining that it asserted nothing
    # -- "a repaint test in which no repaint occurred" -- and says so
    # itself: "That name is history, not a test to go and find; all four
    # were rewritten." Removing the name would remove the lesson.
    "test_highlighting_survives_a_repaint",
}

_PATH_RE = re.compile(r"`([A-Za-z0-9_./-]+\.(?:py|json|html|md|toml|ps1|jsx|cif|yml))`")


def _repo_files() -> set[str]:
    return {
        str(p.relative_to(_ROOT)).replace("\\", "/")
        for p in _ROOT.rglob("*")
        if p.is_file()
    }


def _known_test_names() -> tuple[set[str], set[str]]:
    """Test FUNCTIONS and test FILE stems, because the docs cite both.

    Conflating them is what made the first version of this scan report 26
    false positives -- `test_batch_panel` is a file, not a function.
    """
    functions: set[str] = set()
    stems: set[str] = set()
    for path in (_ROOT / "tests").rglob("test_*.py"):
        stems.add(path.stem)
        functions |= set(
            re.findall(r"def (test_\w+)", path.read_text(encoding="utf-8", errors="replace"))
        )
    return functions, stems


def _cited_tests(text: str) -> set[str]:
    """Test names a document refers to.

    Three shapes have to be handled or the check cries wolf:
    a name wrapped across two lines as `` `..._` `` + `` `...` ``, a
    `file.py::name` reference, and a wildcard stem like
    `test_main_window_*.py`. All three were false positives once.
    """
    joined = re.sub(r"_`\s*\n\s*`", "_", text)
    names = set(re.findall(r"`([a-zA-Z0-9_.:]*test_[a-z0-9_]+)`?", joined))
    resolved = set()
    for raw in names:
        name = raw.split("::")[-1].removesuffix(".py")
        if not name.startswith("test_") or name.endswith("_"):
            continue  # a wildcard, not a name
        resolved.add(name)
    return resolved


@pytest.mark.parametrize("doc", DOCS)
def test_every_file_a_doc_cites_still_exists(doc):
    """A doc pointing at a deleted module sends a reader somewhere that
    does not exist, and reads as authoritative while doing it."""
    text = (_ROOT / doc).read_text(encoding="utf-8")
    files = _repo_files()
    basenames = {f.rsplit("/", 1)[-1] for f in files}

    missing = []
    for cited in sorted(set(_PATH_RE.findall(text))):
        normalised = cited.lstrip("./")
        if normalised in ALLOWED_MISSING_PATHS:
            continue
        if normalised in files or any(f.endswith("/" + normalised) for f in files):
            continue
        # A bare filename is cited constantly ("see `engine.py`") and is
        # a real reference as long as something by that name exists.
        if normalised.rsplit("/", 1)[-1] in basenames:
            continue
        missing.append(cited)

    assert not missing, (
        f"{doc} cites files that do not exist: {missing}. Fix the reference, or "
        "add it to ALLOWED_MISSING_PATHS with the reason."
    )


@pytest.mark.parametrize("doc", DOCS)
def test_every_test_a_doc_names_still_exists(doc):
    """A doc citing a test as evidence is making a claim that the test
    holds. If the test is gone the claim has nothing behind it."""
    text = (_ROOT / doc).read_text(encoding="utf-8")
    functions, stems = _known_test_names()

    missing = sorted(
        name
        for name in _cited_tests(text)
        if name not in functions
        and name not in stems
        and name not in ALLOWED_MISSING_TESTS
    )

    assert not missing, (
        f"{doc} names tests that do not exist: {missing}. Fix the reference, or "
        "add it to ALLOWED_MISSING_TESTS with the reason."
    )


def test_claude_md_has_no_duplicate_headings():
    """CLAUDE.md's own drift check, as an assertion rather than a shell
    one-liner nobody remembers to run. It once carried 132 lines that
    duplicated the four sections above them and reached the OPPOSITE
    conclusions -- an all-caps "DO NOT FIX THE MENU LAMBDAS" sitting
    directly below "the menu lambdas ARE fixed now"."""
    headings = re.findall(
        r"^#{2,5} (.+)$", (_ROOT / "CLAUDE.md").read_text(encoding="utf-8"), re.MULTILINE
    )

    duplicates = sorted({h for h in headings if headings.count(h) > 1})

    assert not duplicates, f"CLAUDE.md has repeated headings: {duplicates}"


def test_every_allowlist_entry_is_explained():
    """An exemption without a reason is how a guard gets hollowed out --
    the next person deletes the check rather than the entry."""
    source = Path(__file__).read_text(encoding="utf-8")
    for name in ("ALLOWED_MISSING_PATHS", "ALLOWED_MISSING_TESTS"):
        block = source.split(f"{name} = {{", 1)[1].split("}", 1)[0]
        entries = [line for line in block.splitlines() if line.strip().startswith('"')]
        comments = [line for line in block.splitlines() if line.strip().startswith("#")]
        assert len(comments) >= len(entries), f"{name} has an unexplained entry"


# ---------------------------------------------------------------------------
# A DEFERRAL THAT STOPPED BEING TRUE
#
# The checks above ask whether a document cites something that EXISTS. They
# cannot ask whether a document's CLAIM is still true, and that is the failure
# mode this project actually has. Four claims went stale underneath them:
#
#   ROADMAP  "ensemble alignment ... needs its own panel"   the panel shipped
#   ROADMAP  "reaction templates -- Deferred, still" (x3)   the namespace shipped
#   ARCH     "hydrophobic contact detection is a real gap"  it shipped, and
#                                                           ROADMAP had already
#                                                           corrected the same
#                                                           claim, so the two
#                                                           documents disagreed
#   ARCH     "IUPAC Name ... withheld on a morphine deriv"  does not reproduce
#
# Same shape as `inapplicable_calculators` rotting into 27 wrong entries
# behind a `len(names) > 10` assertion: a maintained list, and nothing
# bringing anybody back to it.
#
# SCOPE IS `docs/ARCHITECTURE.md`'s Known TODOs SECTION ONLY. It declares a
# closed three-word vocabulary at its head, which makes it the one place in
# the docs where deferral status is structured data rather than prose.
# ROADMAP's `- [ ]` bullets are free-form planning text; parsing them would
# produce tests whose only purpose is proving a TODO still exists. Same
# instinct as `applies_to` being a closed vocabulary while `category` stayed
# a free string.
# ---------------------------------------------------------------------------

_KNOWN_TODOS_HEADING = "## Known TODOs"
_MARKERS = {"OPEN", "DECISION", "SETTLED"}


@dataclass(frozen=True)
class Deferral:
    """One claim in Known TODOs, and how you would know it had gone stale.

    `unbuilt` answers "is the thing still not built?" and is MANDATORY for
    both OPEN and DECISION -- a DECISION whose feature shipped anyway is
    stale even when its recorded reason is still perfectly true, and
    conflating those two questions is how this table would rot in turn.

    `reason` answers "is the recorded reason for deferring still true?" and
    belongs to DECISION alone -- OPEN means "not built, and nobody has
    decided not to", so there is no recorded reason that could go stale.
    Only some reasons are countable: "there is still no concrete fourth
    plugin" is `len(shipped plugins) < 4`; "the cause was never established"
    is not checkable by anything. Where a DECISION's reason is not
    countable, `reason` is None and `manual` must say why -- the same rule
    `test_every_allowlist_entry_is_explained` already enforces above.
    """

    claim: str
    unbuilt: Callable[[], bool]
    reason: Callable[[], bool] | None = None
    manual: str = ""


@lru_cache(maxsize=1)
def _src_text() -> str:
    """Every first-party Python source, concatenated.

    `vendor/` is excluded: it is 5,000-line upstream code that no claim here
    is about, and reading it costs far more than it informs.
    """
    root = _ROOT / "src" / "openchem"
    return "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in sorted(root.rglob("*.py"))
        if "vendor" not in path.parts
    )


def _defines(symbol: str) -> bool:
    return re.search(rf"^\s*(class|def)\s+{re.escape(symbol)}\b", _src_text(), re.M) is not None


def _shipped_plugins() -> list[str]:
    """Directories under `plugins/` that are real plugins."""
    root = _ROOT / "plugins"
    return sorted(p.name for p in root.iterdir() if (p / "manifest.toml").is_file())


def _plugins_registering_reactions(root: Path) -> list[str]:
    found = []
    if not root.is_dir():
        return found
    for manifest in root.rglob("manifest.toml"):
        source = "\n".join(
            p.read_text(encoding="utf-8", errors="replace")
            for p in manifest.parent.rglob("*.py")
        )
        if "reactions.register" in source:
            found.append(manifest.parent.name)
    return sorted(found)


#: Every OPEN and DECISION item in Known TODOs, with the predicate that says
#: it is still true. `test_every_marked_item_has_a_predicate_or_a_reason`
#: fails if a marked item arrives without an entry here, so this cannot
#: silently fall behind the document.
DEFERRALS: list[Deferral] = [
    Deferral(
        claim="`SimilarityService` doesn't exist yet",
        unbuilt=lambda: not _defines("SimilarityService"),
    ),
    Deferral(
        claim="plugin loading has no async/background state",
        unbuilt=lambda: not any(
            _defines(name)
            for name in ("ToolbarProvider", "ContextMenuProvider", "RemoteServicePlugin")
        ),
        # "there is still no concrete fourth plugin whose actual requirements
        # would tell us what these abstractions should look like" -- countable.
        reason=lambda: len(_shipped_plugins()) < 4,
    ),
    Deferral(
        claim="`MacromoleculeModel` only stores raw PDB/mmCIF text",
        # The claim is that chains/residues are DERIVED rather than stored.
        # It goes stale the moment the model grows a field caching them,
        # which is the exact thing the entry argues against.
        unbuilt=lambda: not re.search(
            r"class MacromoleculeModel\b(?:.|\n)*?\n\s*(chains|residues)\s*:",
            _src_text(),
        ),
    ),
    Deferral(
        claim="has no missing-residue",
        unbuilt=lambda: "import pdbfixer" not in _src_text(),
        manual="The reason is a measurement, not a countable fact: zero of 49 "
        "curated receptors have a chain break within 10 A of their site, and "
        "rebuilding 4DAJ's side chains landed a median 2.30 A from the same "
        "residues observed in its sister chains. Re-deriving that needs the "
        "receptor library and a PDBFixer run; it is recorded in "
        "chem/docking_providers.py's class docstring instead.",
    ),
    Deferral(
        claim="a derived IUPAC name that fails its OPSIN round trip",
        # The decision is that MISMATCH stays withheld, i.e. the provider
        # still RAISES rather than returning a name with a caveat.
        unbuilt=lambda: "RoundTrip.MISMATCH:\n        raise NamingError" in _src_text(),
        # "it fires once in 181 and that once is metformin" is a benchmark
        # result, re-derived by benchmarks/naming/round_trip_paths.py rather
        # than by importing OPSIN and Java into the test suite.
        manual="Re-measuring it needs OPSIN, a JVM and a 3-minute corpus scan. "
        "benchmarks/naming/round_trip_paths.py is the instrument; the three "
        "code paths are held apart by tests in tests/test_naming_providers.py.",
    ),
    Deferral(
        claim="a calculation cannot be ADDRESSED to a crystal",
        unbuilt=lambda: re.search(
            r"class CalculationRequest\b(?:.|\n)*?\n\s*molecule_uuid\s*:", _src_text()
        )
        is not None
        and not re.search(
            r"class CalculationRequest\b(?:.|\n)*?\n\s*structure_uuid\s*:", _src_text()
        ),
        manual="There is no separate reason to check: the decision IS the field, "
        "and `unbuilt` reads it directly. If `molecule_uuid` ever becomes "
        "`structure_uuid`, every calculator's `applies_to` declaration becomes "
        "load-bearing at runtime, which is what "
        "test_a_calculation_cannot_even_be_ADDRESSED_to_a_crystal exists to say.",
    ),
    Deferral(
        claim="the 3D viewer rendered a black half-height",
        # Nothing to check: it is a symptom with no established cause and no
        # symbol that would prove it fixed. Left OPEN deliberately so that
        # if it returns, the harness is named here rather than rediscovered.
        unbuilt=lambda: True,
        manual="No cause was ever established, so there is no code fact that "
        "could go stale. It is recorded so a recurrence finds the harness "
        "(spikes/crystallography/render_reproducibility.ps1) rather than "
        "starting over; only a human seeing it again can close it.",
    ),
]


def _known_todos_section() -> str:
    text = (_ROOT / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8")
    assert _KNOWN_TODOS_HEADING in text, (
        f"docs/ARCHITECTURE.md has no {_KNOWN_TODOS_HEADING!r} heading. If it was "
        "renamed, rename it here too -- this guard reads that section and a "
        "silently empty section would pass every check below."
    )
    after = text.split(_KNOWN_TODOS_HEADING, 1)[1]
    return re.split(r"^## ", after, maxsplit=1, flags=re.M)[0]


def _marked_bullets() -> list[tuple[str, str]]:
    """`(marker, whole bullet text)` for every marked bullet, or an error.

    FAIL CLOSED. A bullet this cannot classify is an error, never a skip:
    the failure worth designing against is the guard reporting "every OPEN
    item is guarded" precisely BECAUSE it did not recognise one of them.
    """
    section = _known_todos_section()
    blocks = [b for b in re.split(r"^(?=- \*\*)", section, flags=re.M) if b.startswith("- **")]

    raw = len(re.findall(r"^- \*\*", section, re.M))
    assert len(blocks) == raw, (
        f"{raw} bullets start with '- **' but {len(blocks)} were split out. "
        "A malformed bullet would vanish silently."
    )

    out = []
    for block in blocks:
        match = re.match(r"- \*\*([^*]+)\*\*", block)
        assert match, f"could not read a marker from: {block.splitlines()[0]!r}"
        # "OPEN (partly)" and "OPEN, cause unknown" are the same marker
        # wearing a qualifier, so classification takes the first word.
        marker = re.split(r"[ ,(]", match.group(1).strip(), maxsplit=1)[0]
        assert marker in _MARKERS, (
            f"unknown marker {marker!r} in: {block.splitlines()[0]!r}. "
            f"The vocabulary is {sorted(_MARKERS)} -- a typo here would make this "
            "guard skip the item rather than check it."
        )
        out.append((marker, block))
    return out


def test_no_deferred_claim_has_gone_stale():
    """A deferral that stopped being true is worse than no deferral: it
    reads as authoritative while sending somebody to build what exists."""
    stale = []
    for deferral in DEFERRALS:
        if not deferral.unbuilt():
            stale.append(f"{deferral.claim!r} -- the thing it says is not built now EXISTS")
        elif deferral.reason is not None and not deferral.reason():
            stale.append(f"{deferral.claim!r} -- the recorded REASON no longer holds")

    assert not stale, "docs/ARCHITECTURE.md carries claims that are no longer true:\n" + "\n".join(
        f"  - {s}" for s in stale
    )


def test_every_marked_item_has_a_predicate_or_a_reason():
    """Fail closed on both sides: the parse and the mapping.

    The one thing this CANNOT catch is a predicate hardcoded to return
    True. That is an acknowledged limit rather than something to solve
    with a second copy of the same implementation -- the `manual` field
    exists so such an entry has to say out loud that it is one.
    """
    section = _known_todos_section()

    bullets = _marked_bullets()

    for deferral in DEFERRALS:
        occurrences = section.count(deferral.claim)
        assert occurrences == 1, (
            f"the claim {deferral.claim!r} occurs {occurrences} times in Known TODOs, "
            "expected exactly 1. Zero means the wording changed and the predicate "
            "silently stopped guarding anything; more than one means it is ambiguous."
        )
        # The `reason` obligation belongs to DECISION alone. OPEN means "not
        # built, and nobody has decided not to" -- there is no recorded reason
        # to go stale, so demanding one would be demanding an explanation for
        # something the document never claimed.
        marker = next(m for m, block in bullets if deferral.claim in block)
        if marker == "DECISION" and deferral.reason is None:
            assert deferral.manual, (
                f"{deferral.claim!r} is a DECISION with no reason predicate and no "
                "explanation of why it cannot have one. An exemption without a "
                "reason is how a guard gets hollowed out."
            )

    unguarded = []
    for marker, block in _marked_bullets():
        if marker == "SETTLED":
            continue
        if not any(d.claim in block for d in DEFERRALS):
            unguarded.append(block.splitlines()[0])

    assert not unguarded, (
        "these Known TODOs items have no entry in DEFERRALS, so nothing would "
        "notice them going stale:\n" + "\n".join(f"  {u}" for u in unguarded)
    )
