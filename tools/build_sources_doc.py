"""Generate `docs/SOURCES.md` from `docs/sources.toml`.

Same split as `build_regulatory_rulesets.py`: the TOML is hand-edited and
reviewed, the Markdown is machine-owned and must not be edited. `--check`
verifies BOTH directions, and both are needed --

    a hand-edited SOURCES.md   is perfectly consistent with the hash it
                               carries, because that hash describes the
                               SOURCE, not itself
    a stale SOURCES.md         hashes correctly to an older sources.toml

so neither check sees the other's case. Until that pair exists, either can
ship through CI untouched.

**Output must be deterministic**, or `--check` becomes decorative. No
timestamps, no absolute paths, no dict iteration that depends on insertion
luck: entries are emitted in the order the TOML declares them (which is a
reviewed, meaningful order) and every derived set is sorted.

WHY TOML AND NOT YAML. The plan for this said YAML; PyYAML is not installed
and this project's dev dependency group is deliberately just pytest, with a
written comment explaining why scikit-learn is a group rather than an extra.
`tomllib` is stdlib from 3.11, which is this project's floor
(`requires-python = ">=3.11"`), and TOML is already what hand-edited config
uses here (`manifest.toml`, `pyproject.toml`). Same design, no new
dependency.

WHAT THIS TOOL DOES NOT DO. It does not validate the registry -- that is
`tests/test_sources_are_current.py`, which owns the schema, the closed
vocabularies and every relationship. A generator that also validated would
be a second implementation of the rules, and the two would drift.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "docs" / "sources.toml"
GENERATED = ROOT / "docs" / "SOURCES.md"

GENERATED_MARKER = "<!-- GENERATED FROM docs/sources.toml -- do not edit -->"
HASH_MARKER = "<!-- SOURCE SHA256: "

#: Section order and headings. A `kind` absent from here is a schema error
#: the test catches; the generator would rather fail loudly than silently
#: drop a source, so it raises instead of skipping.
SECTIONS = [
    ("literature", "Primary literature"),
    ("dataset", "Datasets"),
    ("legal", "Legal texts"),
    ("standard", "Standards"),
    ("reference_table", "Reference tables"),
    ("software", "Bundled and depended-on software"),
]

STATUS_LABEL = {
    "shipped": "shipped",
    "assessed_not_shipped": "**not shipped**",
    "reference_only": "reference only",
}

VERIFICATION_LABEL = {
    "unverified": "unverified",
    "citation": "citation",
    "citation_and_claim": "citation + claim",
}

PREAMBLE = """# Sources

Every primary source, dataset, legal text, standard and bundled library this
project rests on, with what uses it and how far it has been checked.

## What this registry is, and the three things it cannot do

It is a **provenance registry**, not a bibliography page. Each entry declares
its kind, whether it is shipped, how far it is verified, and what points at
it, so that `tests/test_sources_are_current.py` can ask real questions.

1. **It does not verify scientific claims.** The guards cannot catch a
   citation pointing at the wrong paper, a wrong table or page number, a
   changed URL, a superseded source, or a source that no longer supports the
   claim resting on it.
2. **It does not prove licence compatibility.** The licence guard proves a
   file is classified, a licence file exists, and the relationship is
   declared. It says nothing about whether that text is correct, current, or
   actually covers that artifact.
3. **Its initial completeness is not mechanically proven.** The guards
   establish consistency *after* the registry was populated. That every
   source was found rests on the reconstruction sweep that built it, not on
   anything a test can re-run.

## How to read the columns

**Verification** is three-valued on purpose. A citation can be right while
the number derived from it is wrong -- this project has shipped a fixture
labelled "verbatim from a real run" whose energies were typed from memory.

| value | means |
| --- | --- |
| `unverified` | nobody has checked this entry against the source itself |
| `citation` | the reference is right |
| `citation + claim` | the **number this project uses** was checked against the source |

**Used by** is descriptive, not the dependency oracle: a stale entry there is
tolerated by design. The operational fields -- `resource_path`,
`package_manifest`, `license_files`, `third_party_globs` -- are the
authoritative ones, and every one of them is checked.

**Local** names a file in the maintainer's own paper archive. It is recorded
so a later session can verify a citation without hunting, and it is **never
checked by any guard**, because that folder is not in the repository.

## Citing a source from prose

Write `[source:key]`, never a bare backtick -- these documents contain
thousands of backticked identifiers, so a guard reading every one as a source
key would need an enormous allowlist, or would teach the prose to look like
the test. The syntax is validated before it is resolved, so a malformed
reference fails rather than being silently skipped.
"""


def _load() -> list[dict]:
    return tomllib.loads(REGISTRY.read_text(encoding="utf-8"))["source"]


def _normalised(path: Path) -> str:
    """Text with line endings normalised to `\\n`.

    THE HASH MUST NOT DEPEND ON THE CHECKOUT'S LINE ENDINGS. This repository
    has `core.autocrlf=true` and no `.gitattributes`, so the same commit is
    CRLF in a Windows working tree and LF on a Linux CI runner. Hashing raw
    bytes -- which this did at first -- makes `--check` fail on CI for a
    reason that has nothing to do with content, which is the "a guard must
    not depend on the machine's configuration" rule this project has already
    paid for twice.

    Normalising newlines is the right granularity rather than a fudge: it
    still catches every content edit, including a reworded comment, and
    ignores only a platform artifact nobody reviewed.
    """
    return path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")


def _source_hash() -> str:
    """Hash the REGISTRY's text, not the parse.

    The parse would be stable across whitespace and comment edits, which
    sounds like a feature and is not: a reviewer's comment is part of what
    was reviewed, and a generated file claiming to describe a source it has
    not seen the current text of is exactly the drift `--check` exists for.
    """
    return hashlib.sha256(_normalised(REGISTRY).encode("utf-8")).hexdigest()


def _cell(text: str) -> str:
    """Make a value safe inside a Markdown table cell."""
    return " ".join(str(text).split()).replace("|", "\\|")


def _identifier_link(entry: dict) -> str:
    ident = entry["identifier"]
    if entry["identifier_type"] == "doi":
        return f"[{ident}](https://doi.org/{ident})"
    if entry["identifier_type"] == "url":
        return f"<{ident}>"
    return _cell(ident)


def _render_entry_detail(entry: dict) -> list[str]:
    """The prose block under an entry: only what the table cannot carry."""
    out: list[str] = []
    if entry["status"] != "shipped":
        out.append(f"**Why it is {STATUS_LABEL[entry['status']].strip('*')}.** "
                   f"{entry['reason'].strip()}")
    if entry.get("note"):
        out.append(entry["note"].strip())
    return out


def render() -> str:
    entries = _load()
    lines = [GENERATED_MARKER, f"{HASH_MARKER}{_source_hash()} -->", "", PREAMBLE.rstrip(), ""]

    by_kind: dict[str, list[dict]] = {}
    for entry in entries:
        by_kind.setdefault(entry["kind"], []).append(entry)

    unknown = sorted(set(by_kind) - {kind for kind, _ in SECTIONS})
    if unknown:
        raise SystemExit(f"unknown kind(s) in {REGISTRY.name}: {unknown}")

    lines += ["## Index", "", "| key | kind | status | verification |",
              "| --- | --- | --- | --- |"]
    for entry in sorted(entries, key=lambda e: e["key"]):
        lines.append(
            f"| [`{entry['key']}`](#{entry['key']}) | {entry['kind']} | "
            f"{STATUS_LABEL[entry['status']]} | "
            f"{VERIFICATION_LABEL[entry['verification']]} |"
        )
    lines.append("")

    for kind, heading in SECTIONS:
        group = by_kind.get(kind)
        if not group:
            continue
        lines += [f"## {heading}", ""]
        for entry in group:
            lines += [f"### {entry['key']}", "", f"<a id=\"{entry['key']}\"></a>", ""]
            lines.append(f"> {_cell(entry['citation'])}")
            lines.append("")

            facts = [
                ("Identifier", _identifier_link(entry)),
                ("Status", STATUS_LABEL[entry["status"]]),
                ("Verification", VERIFICATION_LABEL[entry["verification"]]),
            ]
            if entry.get("verified_date"):
                facts.append(("Verified", str(entry["verified_date"])))
            if entry.get("license"):
                facts.append(("Licence", _cell(entry["license"])))
            if entry.get("version"):
                facts.append(("Version", f"`{entry['version']}`"))
            if entry.get("package_name"):
                facts.append(("Package", f"`{entry['package_name']}`"))
            if entry.get("package_manifest"):
                facts.append(("Version source", f"`{entry['package_manifest']}`"))
            if entry.get("resource_path"):
                facts.append(("Bundled at", f"`{entry['resource_path']}`"))
            if entry.get("third_party_globs"):
                facts.append(("Third-party files",
                              ", ".join(f"`{g}`" for g in entry["third_party_globs"])))
            if entry.get("license_files"):
                facts.append(("Licence files",
                              ", ".join(f"`{f}`" for f in entry["license_files"])))
            if entry.get("our_files"):
                facts.append(("Ours, in the same place",
                              ", ".join(f"`{f}`" for f in entry["our_files"])))
            if entry.get("local"):
                facts.append(("Local copy", f"`{entry['local']}` (not checked)"))
            if entry.get("used_by"):
                facts.append(("Used by",
                              ", ".join(f"`{u}`" for u in entry["used_by"])))

            lines += ["| | |", "| --- | --- |"]
            lines += [f"| {label} | {value} |" for label, value in facts]
            lines.append("")

            for block in _render_entry_detail(entry):
                lines += [block, ""]

    return "\n".join(lines).rstrip() + "\n"


def check() -> int:
    """Both directions. Returns a process exit code."""
    if not GENERATED.exists():
        print(f"MISSING: {GENERATED.relative_to(ROOT)} has never been generated.")
        return 1

    current = _normalised(GENERATED)
    problems: list[str] = []

    # (1) Does the generated file record the hash of the source AS IT IS NOW?
    # Catches a sources.toml edited without regenerating.
    recorded = ""
    for line in current.splitlines():
        if line.startswith(HASH_MARKER):
            recorded = line[len(HASH_MARKER):].split()[0]
            break
    actual = _source_hash()
    if not recorded:
        problems.append("the generated file records no source hash at all")
    elif recorded != actual:
        problems.append(
            f"stale: generated from sources.toml @ {recorded[:12]}, "
            f"which is now {actual[:12]} -- re-run without --check"
        )

    # (2) Does regenerating produce byte-identical output? Catches a hand
    # edit, which check (1) cannot see: a hand-edited file still carries a
    # perfectly correct hash of its unchanged source.
    if current != render():
        problems.append(
            "the generated file does not match what sources.toml builds -- "
            "it was hand-edited, or the generator changed"
        )

    for problem in problems:
        print(f"SOURCES.md: {problem}")
    return 1 if problems else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check", action="store_true",
        help="verify the generated doc is current without writing it",
    )
    args = parser.parse_args()

    if args.check:
        code = check()
        if code == 0:
            print(f"SOURCES.md is current ({len(_load())} sources).")
        return code

    GENERATED.write_text(render(), encoding="utf-8")
    print(f"Wrote {GENERATED.relative_to(ROOT)} ({len(_load())} sources).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
