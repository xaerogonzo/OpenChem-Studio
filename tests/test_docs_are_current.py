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
from pathlib import Path

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
