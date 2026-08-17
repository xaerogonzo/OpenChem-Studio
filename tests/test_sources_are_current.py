"""The sources registry may not drift from what the repository actually uses.

`docs/sources.toml` records every primary source, dataset, legal text,
standard and bundled library this project rests on. This file is what stops
it becoming a bibliography page nobody maintains -- the same argument as
`test_docs_are_current.py`, one layer along: an audit produces a list that
rots again in three months, a test cannot.

**`source_key` is the primary invariant; the DOI sweep is a backstop.** A
DOI check alone covers 16 of 53 sources and would leave every prose citation
-- the CRC Handbook, the CWC schedules, IUPAC 2013 -- free to rot while this
file stayed green. So the authoritative relationship is a declared key
(`source_key` in a data file, `[source:key]` in prose) and the DOI sweep only
catches a citation that bypassed the registry entirely. It is never a licence
to auto-create a row: the registry is a reviewed inventory, not a DOI
scraper.

WHAT THESE GUARDS CANNOT DO, stated here rather than left to be discovered:

- They cannot tell you a citation points at the RIGHT paper, a table number
  is right, a URL still resolves, or a source still supports the claim
  resting on it. `test_docs_are_current.py` admits the same kind of limit
  about hardcoded predicates.
- They cannot prove licence COMPATIBILITY. `test_every_bundled_file_is_declared_and_licensed`
  proves a file is classified, a licence file exists and the relationship is
  declared. Whether that text is correct, current, or actually covers that
  artifact is a human question.
- They cannot prove the registry is COMPLETE. They check consistency after
  population; that every source was found rests on the reconstruction sweep
  that built it.
- `local` is never checked. It names a file in the maintainer's own paper
  archive, which is not in the repository, so no run here can resolve it. A
  check that cannot run is worse than an admitted gap.
"""

from __future__ import annotations

import json
import re
import tomllib
from datetime import date
from functools import lru_cache
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "docs" / "sources.toml"
GENERATED = ROOT / "docs" / "SOURCES.md"

SCHEMA_VERSION = 1

KINDS = {"literature", "dataset", "legal", "standard", "software", "reference_table"}
STATUSES = {"shipped", "assessed_not_shipped", "reference_only"}
IDENTIFIER_TYPES = {"doi", "url", "isbn", "treaty", "standard", "license", "bibliographic"}
VERIFICATIONS = {"unverified", "citation", "citation_and_claim"}

REQUIRED = ("key", "kind", "citation", "identifier_type", "identifier", "status", "verification")
OPTIONAL = (
    "reason", "note", "used_by", "local", "verified_date", "license", "version",
    "resource_path", "third_party_globs", "license_files", "our_files",
    "package_name", "package_manifest",
)

#: A key is an identifier, so it is constrained rather than trusted to human
#: discipline. Without this, `Avdeef2020`, `avdeef-2020` and `avdeef2020`
#: slowly become three identifiers for one source.
KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")

#: `[source:key]`, and NOT a bare backtick. These documents contain thousands
#: of backticked identifiers -- filenames, symbols, calculator ids -- so a
#: guard reading every one as a source key would need an enormous allowlist,
#: or would teach the prose to look like the test.
SOURCE_REF_RE = re.compile(r"\[source:([^\]]*)\]")

#: Anything shaped like a source reference, so a MALFORMED one fails instead
#: of being skipped by the strict pattern into a false clean state. Same
#: fail-closed lesson as the `**OPNE**` marker in the DEFERRALS parse: a typo
#: must be an error, never "nothing matched".
SOURCE_REF_LOOSE_RE = re.compile(r"\[\s*sou?r?ce?\s*:[^\]]*\]", re.I)

DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Za-z0-9]+")

SWEPT_SUFFIXES = {".py", ".json", ".md", ".toml", ".cff", ".yml", ".yaml"}

#: Directories holding somebody else's text. Their DOIs and their prose
#: belong to the bundler or the depositor, not to us.
SKIP_DIRS = {"vendor", "resources", "dist", "build", "node_modules", ".venv", ".git", "__pycache__"}

#: The registry is the AUTHORITY, not evidence that the authority is
#: referenced. Sweeping it would make the reverse-DOI and reachability checks
#: partly self-satisfying.
SKIP_FILES = {REGISTRY, GENERATED}

#: Files that DEFINE or document the `[source:key]` syntax, and so
#: necessarily contain examples of it. Explaining a pattern is not citing a
#: source.
#:
#: THESE ARE EXCLUDED FROM THE REFERENCE SWEEP ONLY, NOT FROM THE DOI SWEEP,
#: and the split is the point. CLAUDE.md documents the syntax *and* cites
#: sixteen real DOIs; excluding it wholesale to silence its own examples
#: would quietly drop the most citation-dense file in the repository out of
#: the backstop. A file can be an authority on one question and evidence on
#: another.
SYNTAX_DOCUMENTING_FILES = {
    Path(__file__).resolve(),
    ROOT / "tools" / "build_sources_doc.py",
    ROOT / "CLAUDE.md",
}


@lru_cache(maxsize=1)
def _registry() -> dict:
    return tomllib.loads(REGISTRY.read_text(encoding="utf-8"))


def _entries() -> list[dict]:
    return _registry()["source"]


def _keys() -> set[str]:
    return {e["key"] for e in _entries()}


def canonicalise_doi(raw: str) -> str:
    """Normalise a DOI as it really appears in this tree.

    A named function rather than an inline regex because the tree genuinely
    holds `10.1021/acs.jcim.0c00701):` and `10.6084/m9.figshare.1176994.`,
    plus `https://doi.org/` and `doi:` prefixes and mixed case. A naive
    pattern reports both of those as missing from a registry that contains
    them.
    """
    doi = raw.strip()
    for prefix in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "doi:"):
        if doi.lower().startswith(prefix):
            doi = doi[len(prefix):]
    doi = doi.rstrip(").,;:'\"]>")
    # A trailing ")" that closes a bracket opened OUTSIDE the DOI is
    # punctuation; one that closes a bracket inside it is part of the name,
    # as in `10.1016/0022-2852(84)90051-1`.
    while doi.count("(") < doi.count(")"):
        doi = doi[: doi.rfind(")")].rstrip(").,;:")
    return doi.lower()


@lru_cache(maxsize=1)
def _swept_files() -> tuple[Path, ...]:
    """Repository text that may cite a source.

    Excludes `.cif` by EXTENSION rather than excluding the fixtures
    directory: a deposition's header carries the depositor's own DOI, which
    is not our citation -- but `tests/fixtures/cif/SOURCES.md` beside them is
    ours and must be swept.
    """
    out = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix not in SWEPT_SUFFIXES:
            continue
        if any(part in SKIP_DIRS for part in path.relative_to(ROOT).parts):
            continue
        if path in SKIP_FILES:
            continue
        out.append(path)
    return tuple(sorted(out))


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


# ---------------------------------------------------------------------------
# 1-2  the registry's own shape
# ---------------------------------------------------------------------------


def test_the_registry_declares_a_schema_version_this_file_understands():
    """So a future format is rejected rather than read as the current one."""
    assert _registry().get("schema_version") == SCHEMA_VERSION


@pytest.mark.parametrize("entry", _entries(), ids=lambda e: e["key"])
def test_every_entry_matches_the_schema(entry):
    missing = [field for field in REQUIRED if not entry.get(field)]
    assert not missing, f"{entry.get('key', '?')} is missing {missing}"

    unknown = set(entry) - set(REQUIRED) - set(OPTIONAL)
    assert not unknown, f"{entry['key']} carries unknown field(s) {sorted(unknown)}"

    assert entry["kind"] in KINDS, f"{entry['key']}: kind {entry['kind']!r}"
    assert entry["status"] in STATUSES, f"{entry['key']}: status {entry['status']!r}"
    assert entry["identifier_type"] in IDENTIFIER_TYPES, (
        f"{entry['key']}: identifier_type {entry['identifier_type']!r}"
    )
    assert entry["verification"] in VERIFICATIONS, (
        f"{entry['key']}: verification {entry['verification']!r}"
    )

    # Conditional contracts. Each of these is a pair that must not drift
    # apart: a date on an unverified row claims a check nobody made.
    if entry["verification"] == "unverified":
        assert not entry.get("verified_date"), (
            f"{entry['key']} is unverified but carries a verified_date"
        )
    else:
        assert isinstance(entry.get("verified_date"), date), (
            f"{entry['key']} is {entry['verification']} but has no valid verified_date"
        )

    if entry["kind"] == "software":
        assert entry.get("resource_path") or entry.get("package_manifest"), (
            f"{entry['key']} is software but declares neither resource_path "
            f"nor package_manifest, so nothing about it can be checked"
        )
    if entry.get("version"):
        assert entry.get("package_manifest"), (
            f"{entry['key']} states a version with no package_manifest to check it against"
        )


def test_every_key_is_unique_and_normalised():
    keys = [e["key"] for e in _entries()]
    duplicated = sorted({k for k in keys if keys.count(k) > 1})
    assert not duplicated, f"duplicate keys: {duplicated}"

    malformed = sorted(k for k in keys if not KEY_RE.match(k))
    assert not malformed, f"keys must match {KEY_RE.pattern}: {malformed}"


def test_every_unshipped_source_gives_its_reason():
    """Otherwise the category becomes a graveyard of papers with no
    explanation -- and the whole point of recording a rejected source is that
    a deferral's reasons rot independently of its verdict.
    """
    silent = [
        e["key"] for e in _entries()
        if e["status"] != "shipped" and not str(e.get("reason", "")).strip()
    ]
    assert not silent, f"{silent} are not shipped and do not say why"


# ---------------------------------------------------------------------------
# 3  source references: syntax first, then resolution
# ---------------------------------------------------------------------------


def _reference_swept_files() -> tuple[Path, ...]:
    return tuple(p for p in _swept_files() if p not in SYNTAX_DOCUMENTING_FILES)


def _source_refs() -> list[tuple[Path, str]]:
    found = []
    for path in _reference_swept_files():
        for match in SOURCE_REF_RE.finditer(_read(path)):
            found.append((path, match.group(1)))
    return found


def test_every_source_reference_is_well_formed():
    """Fail closed: a malformed reference must be an error, never a miss.

    `[srouce:x]` and `[source: x]` are both invisible to the strict pattern,
    so without this the resolution test below reports a clean state for a
    reference that resolves to nothing.
    """
    bad = []
    for path in _reference_swept_files():
        text = _read(path)
        strict = {m.group(0) for m in SOURCE_REF_RE.finditer(text)}
        for loose in SOURCE_REF_LOOSE_RE.finditer(text):
            token = loose.group(0)
            if token not in strict:
                bad.append(f"{_rel(path)}: {token}")
    assert not bad, "malformed source references (want exactly `[source:key]`):\n" + "\n".join(bad)


def test_every_source_reference_resolves():
    keys = _keys()
    unresolved = sorted({
        f"{_rel(path)}: [source:{ref}]"
        for path, ref in _source_refs()
        if ref not in keys
    })
    assert not unresolved, "source references naming no registry entry:\n" + "\n".join(unresolved)


# ---------------------------------------------------------------------------
# 4  shipped data tables
# ---------------------------------------------------------------------------

#: JSON directly under `chem/data/` that is NOT a scientific data table, each
#: with the reason. Anything added here needs one -- an unexplained exemption
#: is how a guard gets hollowed out.
DATA_FILES_WITHOUT_A_SOURCE: dict[str, str] = {}

#: THE UNDERSCORE IS LOAD-BEARING, and a plain `source_key` broke two
#: loaders when this was first written. `oxidation_states.electronegativity_table`
#: and `checkers.valence.hypervalent_rules` both read their file's TOP LEVEL
#: as the data map and drop keys beginning with an underscore -- the latter
#: says so in its own docstring ("Keys beginning with an underscore are
#: documentation for whoever opens the file"). A plain key is therefore
#: indistinguishable from an element symbol, and 43 tests failed with
#: `TypeError: string indices must be integers`.
#:
#: Files that nest their data under a named key (`elements`, `radii`,
#: `solutes`) would tolerate either spelling. One name everywhere is worth
#: more than the shortest name in each file.
SOURCE_KEY_FIELD = "_source_key"
SUPPLEMENTARY_FIELD = "_supplementary_source_keys"

#: The walk is deliberately NON-RECURSIVE. `chem/data/` holds 7 top-level
#: tables and 8 more JSON files under `regulatory/`, and those take a
#: different rule entirely:
#:
#:   regulatory/sources/*.json    already carry per-rule provenance --
#:                                `legal.quote` holds the regulation's own
#:                                words and `legal.cited_identifiers` its
#:                                printed CAS numbers, governed by their own
#:                                README and build. A second provenance
#:                                mechanism beside a working one is how two
#:                                accounts drift apart.
#:   regulatory/generated/*.json  machine-owned; hand-editing them is
#:                                forbidden by their own contract and
#:                                detected by that build's --check.
DATA_DIR = ROOT / "src" / "openchem" / "chem" / "data"


def _data_tables() -> list[Path]:
    return sorted(DATA_DIR.glob("*.json"))


def test_the_data_walk_sees_the_files_it_is_meant_to():
    """Assert the setup, so this cannot pass by finding nothing.

    If `chem/data/*.json` ever returned an empty list -- a moved directory, a
    renamed package -- every per-file check below would pass vacuously.
    """
    names = {p.name for p in _data_tables()}
    assert len(names) >= 7, f"expected the shipped data tables, found {sorted(names)}"
    assert "ionic_radii.json" in names
    assert not any(p.parent != DATA_DIR for p in _data_tables()), "the walk must not recurse"


@pytest.mark.parametrize("path", _data_tables(), ids=lambda p: p.name)
def test_every_shipped_data_table_declares_its_source(path):
    if path.name in DATA_FILES_WITHOUT_A_SOURCE:
        pytest.skip(DATA_FILES_WITHOUT_A_SOURCE[path.name])

    payload = json.loads(_read(path))
    key = payload.get(SOURCE_KEY_FIELD)
    assert key, (
        f"{path.name} ships scientific data and declares no {SOURCE_KEY_FIELD}. "
        f"Add one naming an entry in docs/sources.toml, or classify the file "
        f"in DATA_FILES_WITHOUT_A_SOURCE with a reason."
    )
    keys = _keys()
    assert key in keys, f"{path.name}: {SOURCE_KEY_FIELD} {key!r} names no registry entry"

    for extra in payload.get(SUPPLEMENTARY_FIELD, []):
        assert extra in keys, f"{path.name}: supplementary key {extra!r} names no registry entry"


# ---------------------------------------------------------------------------
# 5  operational paths
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _tracked_files() -> frozenset[str]:
    """Everything git tracks, as posix-relative paths.

    AN INCONCLUSIVE PROBE RAISES RATHER THAN RETURNING AN EMPTY SET, the
    same rule the `webgl` fixture follows: "I could not find out" is not
    "nothing is tracked", and a blanket except here would turn the guard
    below into a silent pass on any machine where git is missing.
    """
    import subprocess

    result = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(f"could not list tracked files: {result.stderr.strip()}")
    tracked = frozenset(p for p in result.stdout.split("\0") if p)
    if len(tracked) < 100:
        raise RuntimeError(f"git ls-files returned only {len(tracked)} paths; refusing to believe it")
    return tracked


def test_every_used_by_path_is_tracked_in_git():
    """`used_by` may be stale, but it may not name a file only YOU have.

    TRACKED, not merely existing, and that distinction is why this test
    exists at all. Three entries first pointed at
    `benchmarks/solubility/data/*manifest.json`, which are real files in a
    working tree that has run the benchmark and are **gitignored** -- so
    they resolve for the author and for nobody else. A clean checkout
    caught it; the author's machine never would have.

    It also sidesteps a weakness in the sibling check:
    `test_docs_are_current._repo_files` walks the whole tree with
    `rglob("*")`, `.venv/` included, so a cited path resolves if anything
    in site-packages happens to match it -- which is why `docs/ROADMAP.md`
    can cite a bare `setup.py` and pass on a machine with numpy installed.
    Asking git removes the environment from the question entirely.
    """
    tracked = _tracked_files()
    problems = []
    for entry in _entries():
        for path in entry.get("used_by", []):
            if path.endswith("/"):
                continue
            if path in tracked:
                continue
            # A directory is a legitimate target (the vendored namer is
            # cited as a package, not a file).
            if any(t.startswith(path.rstrip("/") + "/") for t in tracked):
                continue
            problems.append(f"{entry['key']}: used_by {path} is not tracked by git")
    assert not problems, "\n".join(problems)


def test_every_operational_source_path_exists():
    """`used_by` is descriptive and deliberately NOT checked here.

    The operational fields are the ones anything depends on, and a stale one
    is a broken check rather than a stale note. `test_docs_are_current.py`
    covers the backticked paths in the generated Markdown, which is not the
    same claim: it cannot see a glob, and it cannot see a path that appears
    only in a field this file renders differently.
    """
    problems = []
    for entry in _entries():
        base = ROOT / entry["resource_path"] if entry.get("resource_path") else None
        if base is not None and not base.is_dir():
            problems.append(f"{entry['key']}: resource_path {entry['resource_path']} is not a directory")
            continue
        if entry.get("package_manifest") and not (ROOT / entry["package_manifest"]).is_file():
            problems.append(f"{entry['key']}: package_manifest {entry['package_manifest']} does not exist")
        if base is None:
            continue
        for field in ("license_files", "our_files"):
            for name in entry.get(field, []):
                if not (base / name).exists():
                    problems.append(f"{entry['key']}: {field} entry {name} does not exist under {entry['resource_path']}")
        for glob in entry.get("third_party_globs", []):
            if not list(base.glob(glob)):
                problems.append(f"{entry['key']}: third_party_glob {glob!r} matches nothing under {entry['resource_path']}")
    assert not problems, "\n".join(problems)


# ---------------------------------------------------------------------------
# 6-7  the DOI backstop
# ---------------------------------------------------------------------------


def _registry_dois() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for entry in _entries():
        if entry["identifier_type"] == "doi":
            out.setdefault(canonicalise_doi(entry["identifier"]), []).append(entry["key"])
    return out


def test_registry_dois_are_unique_after_normalisation():
    shared = {doi: keys for doi, keys in _registry_dois().items() if len(keys) > 1}
    # Two entries MAY share a DOI when they describe different parts of one
    # publication -- the measured and predicted halves of the Abraham paper
    # are the case here -- so this asserts they are deliberate, not absent.
    for doi, keys in shared.items():
        kinds = {e["kind"] for e in _entries() if e["key"] in keys}
        statuses = {e["status"] for e in _entries() if e["key"] in keys}
        assert len(kinds) > 1 or len(statuses) > 1, (
            f"{doi} is claimed by {keys}, which differ in neither kind nor status "
            f"-- that is a duplicate row, not a deliberate split"
        )


def test_every_doi_cited_in_the_tree_is_in_the_registry():
    """The legacy-citation backstop: a DOI in prose with no registry entry
    means a citation bypassed the registry. It is NOT a licence to
    auto-create a row.
    """
    known = set(_registry_dois())
    missing: dict[str, set[str]] = {}
    for path in _swept_files():
        for raw in DOI_RE.findall(_read(path)):
            doi = canonicalise_doi(raw)
            if doi not in known:
                missing.setdefault(doi, set()).add(_rel(path))
    report = "\n".join(f"  {doi}  cited by {sorted(paths)}" for doi, paths in sorted(missing.items()))
    assert not missing, f"DOIs cited but not registered in docs/sources.toml:\n{report}"


# ---------------------------------------------------------------------------
# 8  reachability, defined per kind
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _keys_referenced_outside_the_registry() -> frozenset[str]:
    referenced = {ref for _, ref in _source_refs()}
    for path in _data_tables():
        payload = json.loads(_read(path))
        if payload.get(SOURCE_KEY_FIELD):
            referenced.add(payload[SOURCE_KEY_FIELD])
        referenced.update(payload.get(SUPPLEMENTARY_FIELD, []))
    return frozenset(referenced)


def test_a_shipped_source_is_reachable():
    """A shipped source must be connected to something outside the registry.

    DEFINED PER KIND, because a software source's real relationship is a
    bundle and a manifest rather than a prose citation -- Ketcher would
    otherwise be a permanent false positive. And the registry never satisfies
    its own reachability test: `sources.toml` and `SOURCES.md` are excluded
    from the sweep that feeds this.
    """
    referenced = _keys_referenced_outside_the_registry()
    orphans = []
    for entry in _entries():
        if entry["status"] != "shipped":
            continue
        if entry["kind"] == "software":
            # Satisfied by its operational declaration, checked separately.
            continue
        if entry["key"] not in referenced:
            orphans.append(entry["key"])
    assert not orphans, (
        "shipped sources nothing outside the registry points at -- add a "
        f"`[source:key]` where each is first named, or a data-file source_key: {orphans}"
    )


# ---------------------------------------------------------------------------
# 9  bundled third-party files
# ---------------------------------------------------------------------------

RESOURCE_ROOT = ROOT / "src" / "openchem" / "resources"


def _software_entries() -> list[dict]:
    return [e for e in _entries() if e["kind"] == "software" and e.get("resource_path")]


def test_every_bundled_file_is_declared_and_licensed():
    """Three directions, and the filesystem walk is the load-bearing one.

    Driving discovery from the registry alone means a bundle nobody
    registered is INVISIBLE, which is precisely how
    `chem/crystal_report.inapplicable_calculators` rotted into 27 wrong
    entries. So the walk finds the files and the registry explains them.

    FILE-LEVEL, because directory-level is already wrong on this tree:
    `resources/viewer3d/` holds `3Dmol-min.js` (theirs) beside `viewer.html`
    (entirely ours, carrying this project's own gallery overlay). A
    directory check would also pass unchanged if a second library were
    dropped in beside the first.
    """
    problems = []

    declared_dirs = {}
    for entry in _software_entries():
        base = ROOT / entry["resource_path"]
        if not base.is_dir():
            continue
        declared_dirs[base.resolve()] = entry

        # (2) every declared glob matches something, and (3) a licence exists
        matched = {p.resolve() for glob in entry.get("third_party_globs", []) for p in base.glob(glob)}
        if not matched:
            problems.append(f"{entry['key']}: declares third-party files but matches none on disk")
        elif not entry.get("license_files"):
            problems.append(f"{entry['key']}: bundles third-party files and declares no licence file")
        else:
            # Existence is checked here as well as in
            # `test_every_operational_source_path_exists`, and the overlap is
            # deliberate. This is the guard that CLAIMS bundled code is
            # licensed; without it, deleting a licence file leaves that claim
            # standing and only a different test objects. A guard that says
            # "licensed" while the file is absent is the "looks legally
            # complete" problem this registry exists to stop moving up a
            # level.
            for name in entry["license_files"]:
                if not (base / name).is_file():
                    problems.append(
                        f"{entry['key']}: bundles third-party files under "
                        f"{entry['resource_path']} but its declared licence "
                        f"{name} is missing"
                    )

    # (1) every resource directory is declared at all
    for child in sorted(p for p in RESOURCE_ROOT.iterdir() if p.is_dir()):
        if child.resolve() not in declared_dirs:
            problems.append(
                f"undeclared bundled resource directory {_rel(child)} -- add a "
                f"software entry to docs/sources.toml saying whose it is"
            )

    # (1b) every FILE under a declared directory is classified as theirs or
    # ours. This is what catches a second library dropped in beside the first.
    for base, entry in declared_dirs.items():
        theirs = {p.resolve() for glob in entry.get("third_party_globs", []) for p in base.rglob(glob)}
        theirs |= {p.resolve() for glob in entry.get("third_party_globs", []) for p in base.glob(glob)}
        for glob in entry.get("third_party_globs", []):
            if glob.endswith("/**"):
                theirs |= {p.resolve() for p in (base / glob[:-3]).rglob("*")}
        ours = {(base / name).resolve() for name in entry.get("our_files", [])}
        ours |= {(base / name).resolve() for name in entry.get("license_files", [])}
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            resolved = path.resolve()
            if resolved in theirs or resolved in ours:
                continue
            if any(parent in theirs for parent in resolved.parents):
                continue
            problems.append(
                f"undeclared third-party/resource file {_rel(path)} -- classify it "
                f"in {entry['key']}'s third_party_globs or our_files"
            )

    assert not problems, "\n".join(problems)


# ---------------------------------------------------------------------------
# 10  bundled software versions, where they are actually recoverable
# ---------------------------------------------------------------------------


def test_the_ketcher_lockfile_matches_its_registry_entry():
    """Read the LOCKFILE, not `package.json`.

    `package.json` happens to pin exactly (`"3.17.0"`, no caret), so either
    would agree today -- but the lockfile is what resolves WITH AN INTEGRITY
    HASH, and so is the artifact that actually proves what was installed. A
    declaration is a request; a lockfile is a result.

    THIS PROVES THE LOCKFILE, NOT THE BUNDLE. The committed dist carries no
    version string anywhere, so nothing here can prove `resources/ketcher/dist`
    was built from this resolution -- the same gap
    `test_ketcher_bundle_is_current.py` already lives with ("it catches a
    forgotten rebuild, not a broken one").

    Mol* and 3Dmol get no such test on purpose, and the reason is a trap
    rather than laziness: grepping `molstar.js` for a version yields
    `18.3.1`, which is REACT's version inside the bundle. A guard built on
    that would pin the wrong library while looking authoritative.
    """
    entry = next(e for e in _entries() if e["key"] == "ketcher")
    lock = json.loads(_read(ROOT / entry["package_manifest"]))
    node = lock["packages"][f"node_modules/{entry['package_name']}"]

    assert node["version"] == entry["version"], (
        f"{entry['package_manifest']} resolves {entry['package_name']} "
        f"{node['version']}, registry says {entry['version']}"
    )
    assert re.match(r"^sha(256|512)-[A-Za-z0-9+/=]+$", node.get("integrity", "")), (
        f"{entry['package_name']} has no valid integrity hash, so the "
        f"resolution proves nothing"
    )


# ---------------------------------------------------------------------------
# 11  the generated document
# ---------------------------------------------------------------------------


def test_the_ketcher_third_party_notices_are_current():
    """The bundled dependencies' notices must track the lockfile.

    A notices file that lists what the dependencies USED to be is worse than
    none: it reads as attribution while attributing the wrong thing. The
    generator's own `--check` compares the recorded lockfile hash against the
    lockfile as it stands, which is what catches a dependency bump landing
    without a regeneration.

    ITS SECOND HALF NEEDS `node_modules/` AND CI HAS NONE, so the tool skips
    the regenerate-and-compare there and says so on stdout rather than
    passing silently. The hash half runs everywhere and is the one that
    matters for staleness.
    """
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "build_ketcher_notices.py"), "--check"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_the_generated_doc_is_current():
    """Both directions, via the tool itself rather than a second
    implementation of its rules.
    """
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "build_sources_doc.py"), "--check"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
