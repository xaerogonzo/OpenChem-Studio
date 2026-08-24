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
guarded. Every file that cites anything is covered now.

**CHANGELOG.md WAS EXCLUDED FOR A REASON THAT STOPPED BEING TRUE**, which
is the same rot this whole file exists to catch, caught in the file's own
docstring. The reason recorded here was that it cited nothing, so adding
it "makes the list look more thorough than it is". A later sweep measured
it: one backticked path (`docs/VALIDATION.md`). One is not nothing, a
changelog only accumulates references, and the check is free -- so it is
in. CODE_OF_CONDUCT.md is the only remaining exclusion and genuinely
cites nothing.
"""

from __future__ import annotations

import re
import subprocess
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
    "CHANGELOG.md",
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
    "docs/SOLVENT_SOLUBILITY_ASSESSMENT.md",
    # GENERATED from docs/sources.toml. It is checked here anyway, and that
    # is not redundant with its own generator: this asks whether the paths
    # it cites still EXIST, which `build_sources_doc.py --check` never does
    # -- that only asks whether the file is current with respect to its
    # source. A registry can be perfectly regenerated and still name a
    # module deleted last week.
    "docs/SOURCES.md",
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
    # The two staged-migration fixtures, deleted when the help-contract
    # debt reached zero and named by CLAUDE.md's account of WHY they
    # existed. Same reason as the STOUT modules above: a document
    # recording a removal has to be able to say what it removed, and the
    # reason those fixtures were needed -- that `missing` cannot be a
    # failure while a migration is in flight -- outlives the files.
    #
    # THEY PASSED THIS GUARD WHILE UNCOMMITTED. `_repo_files` asks
    # `git ls-files`, so a deleted-but-unstaged file is still tracked and
    # still resolves; the citation only broke once the deletion was
    # committed. Worth knowing before trusting a green docs run taken
    # mid-change.
    "tooltip_migration_debt.json",
    "tooltip_completed_surfaces.json",
    # tinygraph's own build file, named by ROADMAP.md while explaining why
    # that dependency cannot be installed on Windows ("a `setup.py` passing
    # GCC/Clang flags that MSVC rejects"). Somebody else's file, like the
    # molstar path above.
    #
    # IT IS ONLY LISTED HERE BECAUSE THE WALK WAS FIXED. While `_repo_files`
    # used `rglob`, this resolved silently against numpy's
    # `numpy/_core/tests/examples/cython/setup.py` inside `.venv`.
    "setup.py",
}

#: Test names cited as HISTORY rather than as tests to go and find.
ALLOWED_MISSING_TESTS = {
    # CLAUDE.md names this one while explaining that it asserted nothing
    # -- "a repaint test in which no repaint occurred" -- and says so
    # itself: "That name is history, not a test to go and find; all four
    # were rewritten." Removing the name would remove the lesson.
    "test_highlighting_survives_a_repaint",
    # The two staged-migration guards, deleted when the help-contract debt
    # reached zero. CLAUDE.md's suite entry names both while explaining
    # that they existed only because `missing` could not be a failure
    # mid-migration, and that `test_every_control_carries_a_help_contract`
    # replaced them. Same reason as the repaint name above: removing the
    # citation would remove the lesson.
    "test_the_migration_debt_never_grows",
    "test_a_finished_surface_does_not_regress",
}

_PATH_RE = re.compile(r"`([A-Za-z0-9_./-]+\.(?:py|json|html|md|toml|ps1|jsx|cif|yml))`")


@lru_cache(maxsize=1)
def _repo_files() -> frozenset[str]:
    """Every file the REPOSITORY contains, asked of git.

    THIS USED TO WALK THE WHOLE TREE WITH `rglob`, WHICH MADE THE CHECK
    ANSWER ABOUT THE MACHINE RATHER THAN THE REPOSITORY. Measured when this
    was fixed: `rglob` returned **38,680** files against git's **1,021** --
    97% of what a citation was being matched against was `.venv`,
    `node_modules`, `build`, `dist` and `__pycache__`.

    That matters because of the basename fallback below: a bare `foo.py`
    resolves if ANY file anywhere is called `foo.py`. So `docs/ROADMAP.md`
    could cite a bare `setup.py` -- which this repository does not contain
    -- and pass on any machine with numpy installed, because numpy ships
    `numpy/_core/tests/examples/cython/setup.py`. The guard was green for a
    reason that had nothing to do with the repository.

    Asking git removes the environment from the question entirely, and is
    the same move `test_sources_are_current.test_every_used_by_path_is_tracked_in_git`
    already makes.

    AN INCONCLUSIVE PROBE RAISES rather than returning an empty set. "I
    could not ask git" is not "the repository is empty", and a blanket
    except here would turn every citation check into a silent pass -- the
    failure mode this whole file exists to prevent, installed in its own
    foundation.

    ONE WORKFLOW CONSEQUENCE, and it is the correct behaviour rather than a
    wart: a doc may not cite a file until that file is TRACKED. Writing a
    new tool and documenting it in the same commit now fails until the tool
    is staged. Under the old walk an uncommitted file resolved happily --
    which is exactly the class of thing this change exists to stop, since a
    reader of the repository cannot see a file that is not in it.
    """
    result = subprocess.run(
        ["git", "ls-files", "-z"], cwd=_ROOT, capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(f"could not list repository files: {result.stderr.strip()}")
    files = frozenset(p for p in result.stdout.split("\0") if p)
    if len(files) < 200:
        raise RuntimeError(
            f"git ls-files returned only {len(files)} paths, which cannot be this "
            f"repository -- refusing to check citations against it"
        )
    return files


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


def test_the_citation_check_only_sees_the_repository():
    """The file list must be the repository, not the machine.

    Guarding the FIX rather than the symptom, because the symptom was a
    green test. `_repo_files` walked the whole tree with `rglob` for most of
    this file's life, and the only visible consequence was that
    `docs/ROADMAP.md` could cite a `setup.py` this repository does not have
    and pass -- resolved against numpy's copy inside `.venv`.

    Reverting to `rglob` would restore that silently, so this asserts the
    two properties that distinguish the two enumerations: nothing from a
    build or environment directory is in the list, and the count is of the
    right ORDER. 38,680 files against 1,021 is not a subtle difference.
    """
    files = _repo_files()

    # `dist` is deliberately NOT in this set: `resources/ketcher/dist/` is a
    # committed, shipped bundle, and the first version of this guard failed
    # on it. An environment directory is one git does not track; a build
    # OUTPUT can be a perfectly legitimate part of the repository.
    intruders = sorted(
        f for f in files
        if any(part in {".venv", "node_modules", "__pycache__", ".git", ".pytest_cache"}
               for part in f.split("/"))
    )
    assert not intruders[:20], (
        f"the citation check is matching against non-repository files, so a "
        f"cited path can resolve against something nobody ships: {intruders[:20]}"
    )

    # A tracked repository of this project's size. The bound is loose on
    # purpose -- it is here to catch an enumeration that has silently gained
    # tens of thousands of entries, not to pin a file count that moves with
    # every commit.
    assert 200 < len(files) < 5000, (
        f"{len(files)} files: this is not the tracked repository. An `rglob` "
        f"walk of this tree returns roughly 38,000."
    )


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


def _uvvis_reference_is_unsourced() -> bool:
    """Is `benchmarks/uvvis/` still declining to score the two open values?

    Reads the reference rather than a list of ids, so it answers about the
    data the benchmark actually uses. Both halves must still be open for
    the ARCHITECTURE entry to remain true.
    """
    import json

    molecules = json.loads(
        (_ROOT / "benchmarks" / "uvvis" / "reference.json").read_text(encoding="utf-8")
    )["molecules"]
    benzene_open = any(
        t["f"]["kind"] == "unsourced" for t in molecules["benzene"]["transitions"]
    )
    pyridine_open = any(not t["verified"] for t in molecules["pyridine"]["transitions"])
    return benzene_open and pyridine_open


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
        claim="consumes a particle",
        # The feature would announce itself as a module: there is no way
        # to edit quark content without a type for it. Watching for the
        # word in first-party source is therefore the honest `unbuilt`
        # test -- and it fails the day somebody adds one, which is the
        # point.
        unbuilt=lambda: "quark" not in _src_text().lower(),
        manual=(
            "The reason is a judgement about product shape, not a countable "
            "fact. 'Every layer below the UI is built on atoms as the smallest "
            "unit' is true of `chem/`, `domain/`, the calculator registry and "
            "the file formats today, and no single expression distinguishes "
            "that from a codebase that had grown a particle model -- the "
            "`unbuilt` predicate above is what would notice that. Stating an "
            "uncheckable reason as uncheckable is the rule this table already "
            "applies to 'the cause was never established'."
        ),
    ),
    # "`SimilarityService` doesn't exist yet" lived here and is gone, because
    # its entry is SETTLED now. Worth noting HOW it went stale: the recorded
    # `unbuilt` predicate was still perfectly true -- no class of that name
    # is defined anywhere -- while the CLAIM around it had been false for
    # months, because Tanimoto similarity shipped in `chem/clustering.py` and
    # reached `ui/dialogs/batch_analysis_dialog.py` without anyone naming a
    # service. A predicate that watches for one SPELLING of a capability
    # cannot see the capability arriving under another, which is the same
    # shape as the solubility entry directly below.
    # "the solubility predictor answers for water only" lived here and is
    # gone, because its entry is SETTLED now and SETTLED items carry no
    # predicate. It went stale within the day and exactly as designed: the
    # guard failed the moment `SOLVENTS` stopped being a one-entry literal,
    # which is what forced the entry to be rewritten rather than left
    # arguing against a feature that had just shipped. Note the recorded
    # REASON would never have caught it -- it watched for a Platts
    # descriptor implementation, and what landed was a lookup table, which
    # is precisely the route that reason had ruled out.
    # "nothing sets a starting width for the right-hand dock" lived here and
    # is gone, because its entry is SETTLED now and SETTLED items carry no
    # predicate. It went stale within the hour and exactly as designed: the
    # guard failed the moment `resizeDocks` appeared in `src/`, which is what
    # forced the entry to be rewritten rather than left describing a version
    # of the application that no longer existed.
    # "regulatory screening has no date awareness" lived here and is gone,
    # because its entry is SETTLED now and SETTLED items carry no predicate.
    # It went stale exactly as designed: the guard fails the moment
    # `def screen(...)` grows an `as_of`, which is what forced the entry to
    # be rewritten rather than left describing the previous version.
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


# ---------------------------------------------------------------------------
# A calculator's DESCRIPTION is user-facing prose, and it goes stale
# ---------------------------------------------------------------------------
# `property_panel._calculator_help` GENERATES each calculator's help
# contract from `CalculatorDefinition.description`, so a description is not
# a comment -- it is the tooltip a user reads on hover, and the one place
# this application tells somebody a method is unavailable.
#
# **IT HAD ALREADY ROTTED, UNAIDED, AND THE FILE KNEW.**
# `topology_analysis`'s description said the Szeged index was "deliberately
# omitted" while `chem/topology_analysis.py`'s own docstring, twenty lines
# from the compute function, said "The SZEGED INDEX is now included,
# validated by a THEOREM". Two statements about one quantity, in one
# feature, disagreeing -- and the one a user reads was the wrong one.
#
# THE CLAIM IS DECLARED, NEVER DETECTED. A first draft scanned descriptions
# for negative phrasing and was abandoned: "is not offered", "is unavailable"
# and "does not provide" are one claim in three shapes, and deciding whether
# a sentence asserts unavailability is prose analysis, which is exactly what
# `help_tooltip.py` refuses to do for tooltips. So each claim is registered
# below with a predicate over CODE, in the shape `DEFERRALS` above already
# uses.
#
# SCOPE IS AVAILABILITY OF AN EXTERNAL METHOD, NOT OUR OWN SCOPE.
# `orbital_electronegativity` says the pi component "is not offered -- it
# needs a separate pi-charge iteration". That is a statement about OpenChem
# behaviour, it is still true, and it deliberately has no entry here. Same
# split `help_tooltip.py` draws between an external scientific fact
# (`source_key`) and an OpenChem behaviour (neither).


@dataclass(frozen=True)
class CalculatorClaim:
    """One "we do not offer X" sentence in a calculator's description.

    `fragment` must occur EXACTLY ONCE in that description. Zero means the
    wording changed and this predicate silently stopped guarding anything,
    which is the fail-open hole
    `test_every_marked_item_has_a_predicate_or_a_reason` already closes for
    Known TODOs.

    `unbuilt` is a fact about CODE. Re-reading the prose to decide whether
    the prose is true would be circular.
    """

    calculator_id: str
    fragment: str
    unbuilt: Callable[[], bool]


def _calculator_descriptions() -> dict[str, str]:
    """`{calculator_id: description}` from the LIVE registry.

    Not a list kept beside it: `inapplicable_calculators` rotted into 27
    wrong entries precisely because nothing forced anybody back to a
    hand-maintained copy.
    """
    from openchem.chem.descriptor_providers import CALCULATOR_DEFINITIONS

    return {d.calculator_id: d.description for d in CALCULATOR_DEFINITIONS}


#: Every live availability claim, with the predicate that says it is still
#: true.
#:
#: **TWO ENTRIES WERE RETIRED BY THIS GUARD'S OWN FIRST RUN**, which is
#: the record worth keeping rather than the entries themselves.
#: `polarizability` said "Miller's method is not offered -- its parameters
#: are not published in ChemAxon's docs"; `topology_analysis` said Szeged
#: and the steric index "are deliberately omitted". Both were false when
#: this list was written -- Szeged had been computed for months -- and
#: both descriptions are rewritten now, so their fragments occur zero
#: times and the entries had to go with them. A retired claim leaves this
#: list; the guard is what forced it.
CALCULATOR_CLAIMS: list[CalculatorClaim] = [
    CalculatorClaim(
        calculator_id="griffin_hlb",
        fragment="Davies' HLB is not offered",
        unbuilt=lambda: not _defines("davies_hlb"),
    ),
]


def test_no_calculator_description_claims_something_that_now_exists():
    """A tooltip saying a method is unavailable, beside the method.

    This is the guard the Szeged/TSEI sentence needed and did not have.
    """
    descriptions = _calculator_descriptions()
    stale = []
    for claim in CALCULATOR_CLAIMS:
        text = descriptions.get(claim.calculator_id)
        assert text is not None, (
            f"no calculator {claim.calculator_id!r} is registered, so the claim "
            f"{claim.fragment!r} guards nothing. If it was renamed, rename it here."
        )
        if not claim.unbuilt():
            stale.append(
                f"{claim.calculator_id}: {claim.fragment!r} -- the thing it says "
                "is not offered now EXISTS in first-party source"
            )

    assert not stale, (
        "these calculator descriptions are shown to users as tooltips and are no "
        "longer true:\n" + "\n".join(f"  - {s}" for s in stale)
    )


def test_every_calculator_claim_still_matches_its_description_exactly_once():
    """A reworded sentence must break loudly, not detach silently."""
    descriptions = _calculator_descriptions()
    for claim in CALCULATOR_CLAIMS:
        text = descriptions.get(claim.calculator_id, "")
        occurrences = text.count(claim.fragment)
        assert occurrences == 1, (
            f"{claim.calculator_id}: the fragment {claim.fragment!r} occurs "
            f"{occurrences} times in its description, expected exactly 1. Zero "
            "means the wording changed and the predicate stopped guarding "
            "anything; more than one means it is ambiguous."
        )


#: Shapes an unavailability claim about an EXTERNAL method tends to take.
#: A CANDIDATE DETECTOR, never a semantic oracle -- see the test below.
_AVAILABILITY_SHAPES = (
    r"is not offered",
    r"are not offered",
    r"deliberately omitted",
    r"could not be reproduced",
    r"no reference value was found",
)


def test_a_description_that_looks_like_an_availability_claim_is_registered():
    """A CANDIDATE DETECTOR. It does not decide whether a sentence is TRUE.

    Pretending natural language is a type system is how a check like this
    decays into `NEGATIVE_WORDS = {"not", "omitted", ...}` and starts
    flagging "this estimator is intentionally absent" as a scientific
    claim. The patterns above are narrow and literature-shaped on purpose,
    and the failure below asks the author to CLASSIFY the sentence -- it
    never asserts the sentence is false.

    `test_no_calculator_description_claims_something_that_now_exists` is
    the guard with teeth; this one only stops a new claim being written
    without one.
    """
    registered = {c.calculator_id for c in CALCULATOR_CLAIMS}
    unclassified = []
    for calculator_id, text in _calculator_descriptions().items():
        if calculator_id in registered:
            continue
        for shape in _AVAILABILITY_SHAPES:
            if re.search(shape, text, re.I):
                unclassified.append(f"{calculator_id}: matched {shape!r}")
                break

    assert not unclassified, (
        "these descriptions read like a claim that some external method is "
        "unavailable, and nothing would notice them going stale. Either add a "
        "CalculatorClaim with a code predicate, or -- if the sentence is about "
        "OpenChem's own scope rather than a method's availability, as "
        "orbital_electronegativity's pi-component note is -- reword it so it "
        "does not read as one:\n" + "\n".join(f"  - {u}" for u in unclassified)
    )


def test_the_known_stale_szeged_claim_is_gone():
    """THE REGRESSION TEST FOR THE HISTORICAL CASE, at BOTH locations.

    `topology_analysis` shipped a description lumping Szeged together with
    TSEI as "deliberately omitted" while its own module docstring said
    Szeged was included and theorem-validated. A targeted assertion rather
    than a general prose-analysis framework, for the reason `decline_total`
    and `DEFERRALS` are both narrow: the general version is a
    prose-analysis subsystem nobody asked for.
    """
    from openchem.chem import topology_analysis

    description = _calculator_descriptions()["topology_analysis"]
    docstring = topology_analysis.__doc__ or ""

    assert "Szeged" in description, (
        "Szeged is computed and reported; the description must say so rather "
        "than being silent about it."
    )
    assert not re.search(r"Szeged[^.]{0,120}omitted", description, re.I), (
        "the description still says Szeged is omitted. It is computed -- "
        "`chem/topology_analysis.py` validates it against Gutman's theorem."
    )
    assert "SZEGED INDEX is now included" in docstring, (
        "the module docstring's own account of Szeged has moved; the two "
        "statements this test relates are no longer the same two."
    )
    assert not re.search(r"Szeged[^.]{0,120}(absent|not (computed|reported))",
                         docstring.split("SZEGED INDEX is now included")[-1], re.I), (
        "the module docstring now contradicts itself about Szeged."
    )


def test_the_candidate_detector_can_say_no():
    """THE ARM THAT MAKES THE DETECTOR WORTH HAVING.

    `test_a_description_that_looks_like_an_availability_claim_is_registered`
    passes when nothing matches, which is also what it does if the patterns
    stop matching anything at all. This asserts it fires on a description
    shaped like a real claim -- and it did, on its first run: the Griffin
    HLB calculator was written with "Davies' HLB is not offered" in its
    description and the detector caught it before a human did.
    """
    synthetic = "Some quantity by the usual method. Pauling's method is not offered."
    assert any(re.search(shape, synthetic, re.I) for shape in _AVAILABILITY_SHAPES)

    # ... and it must NOT fire on a statement about OpenChem's own scope,
    # which is the distinction the whole registry rests on.
    scope = _calculator_descriptions()["orbital_electronegativity"]
    assert "pi component" in scope.lower()
    assert not any(re.search(shape, scope, re.I) for shape in _AVAILABILITY_SHAPES), (
        "orbital_electronegativity's own-scope note now reads as an availability "
        "claim, which would demand a code predicate for something no external "
        "method is missing"
    )


# ---------------------------------------------------------------------------
# The user guide documents CATEGORIES, and nothing related it to the registry
# ---------------------------------------------------------------------------
# `docs/USER_GUIDE.md`'s "Categories worth knowing about" table is where a
# reader finds out a calculator exists at all. It is written at the CATEGORY
# level, and its row labels are prose -- `Quantum (Huckel)` for `quantum`,
# `Structure Generators` for `structures`, `ADMET / Regulatory` for two
# categories at once -- so no rule could ever have derived one from the other.
#
# **AND SO A CATEGORY FELL OUT.** `lewis` has had two calculators and no row
# in that table for as long as the table has existed. Nothing noticed,
# because nothing was looking.
#
# **THE SAME FAILURE IS ALREADY ON RECORD.** CLAUDE.md: a documentation sweep
# "found four shipped features with no user-facing documentation at all, and
# an LED section missing from `SCIENTIFIC_LIMITATIONS.md` -- the file that
# exists precisely to say what the app cannot honestly tell you". It happened
# again, to the four calculators the previous branch made reachable.
#
# THE MAPPING IS DECLARED AND CHECKED BOTH WAYS. Inferring the row from the
# category is what has never worked; a LIST of documented categories is the
# blocklist `inapplicable_calculators` rotted into. So each category names its
# row, every category in the LIVE registry must have one, and every row must
# be claimed -- the same shape `DEFERRALS` and `CALCULATOR_CLAIMS` use.

_GUIDE_TABLE_HEADING = "### Categories worth knowing about"

#: `registry category -> the row label in the guide's table`.
#:
#: **THERE ARE TWO CATEGORY VOCABULARIES AND THE TABLE DOCUMENTS BOTH.**
#: `CalculatorDefinition.category` names the 17 a calculator can be filed
#: under; `_DESCRIPTOR_SPECS`'s fourth field names the ones a plain
#: descriptor row uses, and two of those -- `medicinal_chemistry` and
#: `physicochemical` -- exist ONLY there, because Lipinski, QED and
#: molecular weight are published by the descriptor service rather than by
#: a registered calculator.
#:
#: Covering both is strictly better than exempting the second: an exemption
#: list would stop noticing the day a new descriptor category arrived, which
#: is the rot this whole guard is written against.
#:
#: The regulatory screen is filed under `admet` and has no category of its
#: own -- the narrow guard below caught that being invented here on its
#: first run.
CATEGORY_ROWS: dict[str, str] = {
    "admet": "ADMET / Regulatory",
    "medicinal_chemistry": "Medicinal Chemistry",
    "physicochemical": "Physicochemical",
    "charge": "Charge",
    "electronic": "Electronic Properties",
    "geometry": "Geometry (3D)",
    "identity": "Identity",
    "lewis": "Lewis acid/base",
    "lipophilicity": "Lipophilicity",
    "naming": "Naming",
    "nmr": "NMR",
    "pka": "pKa",
    "quantum": "Quantum (Hückel)",
    "solubility": "Solubility",
    "stereochemistry": "Stereochemistry",
    "structures": "Structure Generators",
    "substructure": "Substructure Search",
    "surface": "Surface Area",
    "topology": "Topology",
}

#: Rows that document something real and belong to NEITHER vocabulary.
#: Empty, and that is the point: both vocabularies are enumerated, so a row
#: needing an exemption would mean the guard had stopped covering something.
#: Kept rather than deleted because the day a row legitimately documents
#: something outside both, it must arrive with a written reason --
#: `test_every_allowlist_entry_is_explained` applies the same rule to the
#: path allowlists above.
_ROWS_WITHOUT_A_CATEGORY: dict[str, str] = {}


def _guide_category_rows() -> list[str]:
    """The row labels in the guide's category table, in document order."""
    text = (_ROOT / "docs" / "USER_GUIDE.md").read_text(encoding="utf-8")
    assert text.count(_GUIDE_TABLE_HEADING) == 1, (
        f"docs/USER_GUIDE.md has no unique {_GUIDE_TABLE_HEADING!r} heading. If it "
        "was renamed, rename it here too -- this guard reads that table and a "
        "silently missing one would pass every check below."
    )
    table = re.split(r"^#{2,4} ", text.split(_GUIDE_TABLE_HEADING, 1)[1], maxsplit=1, flags=re.M)[0]
    rows = [m.group(1).strip() for m in re.finditer(r"^\| ([^|]+) \|", table, re.M)]
    assert rows and rows[0] == "Category", (
        f"the table's first column no longer starts with a 'Category' header: {rows[:2]}"
    )
    return [r for r in rows[1:] if not set(r) <= set("-: ")]


def _registry_categories() -> set[str]:
    """Every category a user-visible result can be filed under, from BOTH
    vocabularies, read live rather than listed."""
    from openchem.chem.descriptor_providers import (
        CALCULATOR_DEFINITIONS,
        _DESCRIPTOR_SPECS,
    )

    return {d.category for d in CALCULATOR_DEFINITIONS} | {
        spec[3] for spec in _DESCRIPTOR_SPECS
    }


def test_every_registry_category_has_a_row_in_the_user_guide():
    """THE DIRECTION THAT WAS MISSING, and the one `lewis` fell through.

    Enumerated from the LIVE registry rather than from a list beside it --
    the direction `test_every_dock_the_window_builds_has_a_help_topic`
    already goes, and the opposite of the one `inapplicable_calculators`
    rotted in.
    """
    from openchem.chem.descriptor_providers import (
        CALCULATOR_DEFINITIONS,
        _DESCRIPTOR_SPECS,
    )

    rows = set(_guide_category_rows())
    missing = []
    for category in sorted(_registry_categories()):
        label = CATEGORY_ROWS.get(category)
        if label is None:
            names = [d.display_name for d in CALCULATOR_DEFINITIONS if d.category == category]
            names += [s[1] for s in _DESCRIPTOR_SPECS if s[3] == category]
            missing.append(f"{category!r} has no entry in CATEGORY_ROWS ({len(names)}: {names})")
        elif label not in rows:
            missing.append(f"{category!r} maps to {label!r}, which is not a row in the table")

    assert not missing, (
        "these calculator categories are not documented in the user guide's "
        '"Categories worth knowing about" table, so nothing tells a reader the '
        "calculators in them exist:\n" + "\n".join(f"  - {m}" for m in missing)
    )


def test_every_mapping_names_a_category_that_still_exists():
    """The narrow half. Without it, a renamed category leaves a mapping
    pointing at nothing while the test above passes on the rows that are
    left -- which reads as coverage and is a smaller universe."""
    live = _registry_categories()
    stale = sorted(c for c in CATEGORY_ROWS if c not in live)
    assert not stale, (
        f"CATEGORY_ROWS maps categories the registry no longer has: {stale}. "
        "A renamed category must be renamed here too, or this guard silently "
        "stops covering it."
    )


def test_every_row_in_the_table_is_claimed():
    """The third direction: a row for a category that has gone away is prose
    telling a reader about calculators that no longer exist."""
    claimed = set(CATEGORY_ROWS.values()) | set(_ROWS_WITHOUT_A_CATEGORY)
    unclaimed = [r for r in _guide_category_rows() if r not in claimed]
    assert not unclaimed, (
        "these rows in the guide's category table belong to no registry "
        "category and are not explained in _ROWS_WITHOUT_A_CATEGORY:\n"
        + "\n".join(f"  - {r}" for r in unclaimed)
    )


def test_every_unmapped_row_says_why():
    """An exemption without a reason is how a guard gets hollowed out.

    The set is empty today because both vocabularies are enumerated. This
    stays so that the first row to need an exemption has to justify itself
    rather than being added silently.
    """
    for row, reason in _ROWS_WITHOUT_A_CATEGORY.items():
        assert len(reason) > 30, f"{row!r} is exempted without a real reason: {reason!r}"


def test_both_category_vocabularies_are_read():
    """THE SETUP ASSERTION, and it is load-bearing.

    `_registry_categories` unions two sources, and reverting it to the
    calculator half alone would still pass every test above -- the rows for
    `medicinal_chemistry` and `physicochemical` would simply stop being
    required, which is the green-suite-and-a-smaller-universe failure this
    project has recorded before. So the two descriptor-only categories are
    asserted by name.
    """
    live = _registry_categories()
    from openchem.chem.descriptor_providers import CALCULATOR_DEFINITIONS

    calculator_only = {d.category for d in CALCULATOR_DEFINITIONS}
    assert {"medicinal_chemistry", "physicochemical"} <= live
    assert not {"medicinal_chemistry", "physicochemical"} & calculator_only, (
        "these are now calculator categories too, so the descriptor half of "
        "the union is no longer what makes them appear -- re-point this "
        "assertion at whatever is descriptor-only now, or drop it"
    )


#: The four the previous branch made reachable, and the words that would have
#: to appear for a reader to find each. NARROW ON PURPOSE -- see the test.
_RESCUED_FEATURES = {
    "Griffin HLB": "HLB",
    "Cao-Liu TSEI": "TSEI",
    "Gutmann donicity": "Gutmann",
    "Miller polarizability": "Miller",
}


@pytest.mark.parametrize("feature,needle", sorted(_RESCUED_FEATURES.items()))
@pytest.mark.parametrize("doc", ["docs/USER_GUIDE.md", "docs/SCIENTIFIC_LIMITATIONS.md"])
def test_the_rescued_features_are_documented(doc, feature, needle):
    """THE TARGETED HALF, in the shape of `test_the_known_stale_szeged_claim_is_gone`.

    These four shipped correct, guarded and sourced in one branch, were made
    reachable in the next, and appeared in NEITHER user-facing document. The
    category guard above would not have caught it -- their categories all had
    rows already.

    **DELIBERATELY NOT A GENERAL RULE.** "Every calculator's display name
    appears in the guide" measures 20 of 53 today, and closing that would mean
    rewriting prose to satisfy a regex rather than documenting anything. This
    names four features and asks only that a reader can find them.
    """
    text = (_ROOT / doc).read_text(encoding="utf-8")
    assert needle in text, (
        f"{feature} is not mentioned in {doc}. It is reachable from the "
        "Properties panel and the command palette, so a user can run it and "
        "has nowhere to read what it does or where it stops."
    )


def test_every_section_of_the_user_guide_is_a_topic():
    """A  SECTION WITH NO ANCHOR IS NOT A TOPIC, so the Help window
    does not LIST it and it cannot be addressed by .

    Four were missing, and the worst was  -- the section
    carrying the calculator category table, i.e. the reference for
    everything the application computes. ,
     and 
    were the others.

    **THE PRECISE CLAIM IS "NOT LISTED", NOT "UNREACHABLE".** Measured:
    the search still finds text in an unanchored section, attributing it to
    the PRECEDING topic. So the cost is a section a user cannot browse to
    and cannot be sent to, not content that has vanished -- worth stating,
    because the stronger version is the one that sounds better and is
    wrong.

    **SCOPED TO USER_GUIDE.md, where the invariant is real.** Every one of
    its 26 sections is user-facing help. QUICKSTART.md is deliberately at 2
    of 9 -- the rest are developer setup ("From source", "Running the
    tests", "Building a distributable"), which is not help. And
    SCIENTIFIC_LIMITATIONS.md sits at 12 of 18 today; that is a
    pre-existing state this guard deliberately does NOT claim either way,
    rather than sweeping six sections into scope under cover of a fix for
    something else.
    """
    text = (_ROOT / "docs" / "USER_GUIDE.md").read_text(encoding="utf-8")
    anchored = {
        m.group(1).strip()
        for m in re.finditer(r"<!--\s*help:[a-z0-9-]+\s*-->\s*\n#{2,3} (.+)", text)
    }
    orphans = [
        m.group(1).strip()
        for m in re.finditer(r"^## (.+)$", text, re.M)
        if m.group(1).strip() not in anchored
    ]
    assert not orphans, (
        "these user-guide sections carry no `<!-- help:... -->` anchor, so the "
        "Help window does not list them and nothing can link to them:\n"
        + "\n".join(f"  - ## {o}" for o in orphans)
    )


def test_every_dock_help_button_opens_its_own_section():
    """**"THE TOPIC EXISTS" IS NOT "THE TOPIC IS RIGHT"**, and that gap is
    what let this ship.

    `test_every_dock_the_window_builds_has_a_help_topic` checks that each
    dock's key resolves. `properties` resolved perfectly -- to
    `## Finding your way around`, because the anchor sat above the wrong
    heading. Eleven `help_anchor="properties"` references across five
    modules -- the dock's `?` button, the Help menu, the panel's tooltips,
    the collapsible sections, the pop-out host -- all opened the navigation
    section instead of the Properties documentation.

    THE ORACLE IS THE DOCK'S OWN NAME, derived rather than declared: a dock
    called `Atom_Inspector` should open a section whose title contains
    "Atom Inspector". Where the section is deliberately named something
    else, `_DOCK_TOPIC_TITLES` says so with the reason -- which is the same
    rule `test_every_allowlist_entry_is_explained` applies above.
    """
    from openchem.app.main_window import HELP_TOPIC_BY_DOCK
    from openchem.help import topics

    by_key = {t.key: t.title for t in topics()}
    wrong = []
    for dock, key in sorted(HELP_TOPIC_BY_DOCK.items()):
        title = by_key.get(key)
        assert title is not None, f"{dock} opens {key!r}, which is not a topic"
        expected = _DOCK_TOPIC_TITLES.get(dock)
        if expected is not None:
            if title != expected:
                wrong.append(f"{dock} opens {title!r}, expected {expected!r}")
        elif dock.replace("_", " ").lower() not in title.lower():
            wrong.append(
                f"{dock} opens {title!r}, which does not name the dock -- either "
                "move the anchor, or record the difference in _DOCK_TOPIC_TITLES"
            )

    assert not wrong, "these help buttons open the wrong section:\n" + "\n".join(
        f"  - {w}" for w in wrong
    )


#: Docks whose section is deliberately titled something other than the dock.
#: Each says why, so a MISPLACED anchor cannot hide here as a naming choice.
_DOCK_TOPIC_TITLES: dict[str, str] = {
    "Project_Explorer": "Projects and molecules",  # the panel is the tree; the
    # section covers projects AND the molecules in them, which is what a
    # reader opening it wants.
    "Structure_Check": "The structure checker",  # the same words with an
    # article, which the derived rule cannot match on.
    "Batch": "Batch mode",
    "Console": "Jobs and the console",  # one section covers both docks
    # deliberately -- they are two views of the same queue.
    "Jobs": "Jobs and the console",
    "Quantum_Chemistry": "Quantum chemistry",  # case differs only.
}


def test_the_guide_states_the_real_number_of_calculators():
    """A COUNT IN PROSE ROTS THE MOMENT A CALCULATOR IS REGISTERED, and
    this one had: the guide said 51 while the registry held 53, because the
    branch below added Griffin HLB and the Cao-Liu TSEI projection.

    Derived from the live registry, so it cannot drift again. The
    neighbouring "25 collapsible categories" is deliberately NOT guarded
    here -- the panel's section count needs a built widget to measure and
    it was not measured when this was written, so asserting it would be
    asserting a number nobody checked. Recorded as unverified rather than
    guessed at.
    """
    from openchem.chem.descriptor_providers import CALCULATOR_DEFINITIONS

    text = (_ROOT / "docs" / "USER_GUIDE.md").read_text(encoding="utf-8")
    match = re.search(r"covering \*\*(\d+) registered calculators\*\*", text)
    assert match, (
        "docs/USER_GUIDE.md no longer states the calculator count in the shape "
        "this guard reads. If the sentence was reworded, reword the pattern too "
        "-- a count nothing checks is a count that rots."
    )
    assert int(match.group(1)) == len(CALCULATOR_DEFINITIONS), (
        f"the guide says {match.group(1)} registered calculators and the "
        f"registry holds {len(CALCULATOR_DEFINITIONS)}"
    )
