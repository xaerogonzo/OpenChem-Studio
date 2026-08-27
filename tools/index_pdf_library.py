"""Map the local PDF library onto the identities `docs/sources.toml` claims.

`sources.toml` carries a `local` field on 55 of its 94 entries -- a
filename in Alex's `Sci Downloads`. That field is documented in the
registry itself as "NOT checked by any guard -- that folder is not in the
repo", which is honest and is also why it has been free to rot: the
library is ~275 files whose names come from wherever each was downloaded,
so collisions get ad-hoc distinguishing words bolted on
(`kamlet1968`, `kamlet1968part3`, `kamlet1968_2`, `kamlet1968_IV`) and
one entry points at `Drago & Wayland EC 1965.pdf`.

**THE FILENAME IS A LOCATOR, NEVER IDENTITY EVIDENCE.** It is the thing
that drifts. What a PDF carries INSIDE it -- a DOI, a title, an author and
a year -- is what says which work it is, and that is what this tool reads.

## What it establishes, and what it does not

**ARTIFACT IDENTITY, NEVER SCIENTIFIC CORRECTNESS.** It answers "this file
is that paper" and never "that paper supports this claim". That is the
same line `sources.toml`'s own `verification` field draws between
`citation` and `citation_and_claim`, and this tool must not be read as
moving an entry along it.

## DOI is the strongest key and emphatically not the only one

Measured over the 55 local-bearing entries, which is the whole reason the
fallbacks exist rather than a hedge:

    the declared DOI appears in the file      24 of 44 DOI entries
    the key's surname AND year appear         44 of 55
    the first words of the title appear       29 of 55
    NO evidence of any kind                    6 of 55

The 20 DOI entries whose DOI is absent are not extraction failures: 51 of
the 55 files have a usable text layer, so for most of them the DOI is
simply NOT PRINTED IN THE DOCUMENT -- assigned retroactively by a
publisher long after a 1965 or 1976 paper was typeset. A check that
demanded a DOI would therefore fail 45% of the DOI entries, and every one
of those failures would be false.

The six with nothing are three scans with no text layer at all
(`gutmann1976`, `bolovinos1984`, `kruszewski1972`), two BOOKS whose
identity lives on a cover page (`crc_handbook`, `langes15`), and
`ran2002`. They are reported `unresolved`. **Unresolved is not a
failure** -- "I could not tell" and "this is the wrong file" are different
answers and must not render alike.

## Why stdlib only, with no pymupdf

The searchable blob is the raw bytes plus every `FlateDecode` stream
inflated with `zlib`. Measured, that recovers the declared DOI for 24 of
44 against 16 for a raw-byte scan alone -- and of the 20 it still misses,
three have no text layer (an OCR problem, not a parsing one) and the rest
do not contain the string at all. So a real PDF text extractor buys
approximately nothing here, and this tool stays dependency-free and
runnable anywhere.

## Reference lists do not confuse it, and that was measured

A paper's bibliography contains other papers' DOIs, so "carries a DOI" is
only safe if contamination is rare. Over the 44:

    files containing ANOTHER registry entry's DOI      3
    ...of those, also containing their OWN DOI         3
    files carrying only a FOREIGN DOI                  0

So the mismatch signal -- a file carrying another entry's DOI while
missing its own -- fires zero times today and is what the check can say NO
with. No positional weighting is needed; it was considered and the
measurement retired it.

## Scope, which is a rule and not an aspiration

This identifies and validates local artifacts against identities the
registry ALREADY claims. It does not fetch metadata, does not query
Crossref, and does not repair the registry. Anything needing external
research is reported `unresolved` and left alone. **It is not a
bibliography manager**, and if it starts growing into one the right move
is to stop.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tomllib
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "docs" / "sources.toml"

#: Where the library lives. NEVER hardcoded -- it is one person's folder on
#: one machine, and baking the path in would make the tool useless to
#: anyone else and untestable everywhere.
LIBRARY_ENV = "OPENCHEM_PDF_LIBRARY"

#: How an identity was established, strongest first. This is the INDEX's
#: own vocabulary and deliberately adds no fourth value to `sources.toml`'s
#: three-valued `verification` -- that field is about whether a human
#: checked the SOURCE, this one is about whether a FILE is that source.
DOI_EXACT = "doi_exact"
BIBLIOGRAPHIC = "bibliographic"
AMBIGUOUS = "ambiguous"
UNRESOLVED = "unresolved"


def library_path(explicit: str | None = None) -> Path | None:
    """The library directory, or None when there is not one here.

    Returning None rather than raising is what lets `--check` SKIP on a
    machine with no library -- CI, every contributor who is not Alex --
    instead of failing for a non-finding. The caller says so out loud.
    """
    raw = explicit or os.environ.get(LIBRARY_ENV)
    if not raw:
        return None
    path = Path(raw).expanduser()
    return path if path.is_dir() else None


def searchable(raw: bytes) -> bytes:
    """The raw bytes plus every inflatable stream, as one blob.

    Not a text extractor and not trying to be: identity evidence is a DOI,
    a surname, a year or a few title words, and all of those survive as
    literal bytes inside a content stream. Decoding fonts to recover
    reading order would be a different program.
    """
    parts = [raw]
    for match in re.finditer(rb"stream\r?\n", raw):
        start = match.end()
        end = raw.find(b"endstream", start)
        if end == -1:
            continue
        try:
            parts.append(zlib.decompress(raw[start:end]))
        except zlib.error:
            # Not every stream is FlateDecode, and a truncated one is
            # ordinary. A stream we cannot inflate is simply not evidence.
            continue
    return b"\n".join(parts)


def _contains(blob: bytes, needle: str) -> bool:
    return re.search(re.escape(needle).encode("latin-1", "ignore"), blob, re.I) is not None


def key_surname_and_year(key: str) -> tuple[str, str] | None:
    """`gasteiger1980` -> `("gasteiger", "1980")`.

    The registry keys are `<surname><year>` by convention, which is a far
    more reliable place to get an author than parsing the `citation`
    prose. Keys that are not shaped that way (`crc_handbook`, `orca`)
    simply yield no evidence of this kind, which is the correct answer for
    them.
    """
    match = re.match(r"^([a-z]+)(?:_[a-z]+)*_?(\d{4})$", key)
    if not match:
        return None
    surname = match.group(1)
    return (surname, match.group(2)) if len(surname) >= 4 else None


def title_words(citation: str, limit: int = 3) -> list[str]:
    """The first few long words of the quoted title in a citation string."""
    match = re.search(r"[‘'\"]([^’'\"]{12,120})[’'\"]", citation)
    if not match:
        return []
    return re.findall(r"[A-Za-z]{5,}", match.group(1))[:limit]


def evidence_for(entry: dict, blob: bytes) -> list[str]:
    """Which kinds of identity evidence for `entry` this blob carries."""
    found: list[str] = []
    if entry.get("identifier_type") == "doi" and _contains(blob, entry["identifier"].strip()):
        found.append("doi")
    parts = key_surname_and_year(entry["key"])
    if parts and _contains(blob, parts[0]) and _contains(blob, parts[1]):
        found.append("surname_year")
    words = title_words(entry.get("citation", ""))
    if words and all(_contains(blob, word) for word in words):
        found.append("title")
    return found


def classify(entry: dict, blob: bytes, foreign_dois: list[tuple[str, str]]) -> dict:
    """One entry against one file: what the file says about its identity."""
    found = evidence_for(entry, blob)
    others = [key for key, doi in foreign_dois if key != entry["key"] and _contains(blob, doi)]

    if "doi" in found:
        confidence = DOI_EXACT
    elif others and not found:
        # Carries somebody else's DOI and no evidence of its own. Measured
        # at zero over the shipped registry, which is what makes it a
        # signal worth having rather than noise.
        confidence = AMBIGUOUS
    elif found:
        confidence = BIBLIOGRAPHIC
    else:
        confidence = UNRESOLVED

    return {
        "key": entry["key"],
        "file": entry["local"],
        "identifier_type": entry.get("identifier_type"),
        "identifier": entry.get("identifier"),
        "evidence": found,
        "foreign_dois": others,
        "confidence": confidence,
    }


def load_entries() -> list[dict]:
    return tomllib.loads(REGISTRY.read_text(encoding="utf-8"))["source"]


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_index(library: Path, entries: list[dict]) -> dict:
    """Classify every local-bearing entry against its file."""
    foreign = [
        (e["key"], e["identifier"].strip())
        for e in entries
        if e.get("identifier_type") == "doi" and e.get("identifier")
    ]
    records, missing = [], []
    for entry in entries:
        if not entry.get("local"):
            continue
        path = library / entry["local"]
        if not path.is_file():
            missing.append({"key": entry["key"], "file": entry["local"]})
            continue
        record = classify(entry, searchable(path.read_bytes()), foreign)
        record["sha256"] = _digest(path)
        record["bytes"] = path.stat().st_size
        records.append(record)
    return {"records": records, "missing": missing}


def duplicates(library: Path, records: list[dict]) -> dict:
    """Exact, DOI and near-bibliographic duplicates.

    The practical payoff: `kamlet1968` / `part3` / `_2` / `_IV` stop being
    a naming problem the moment identity comes from inside the file.
    """
    by_hash: dict[str, list[str]] = {}
    by_doi: dict[str, list[str]] = {}
    for record in records:
        by_hash.setdefault(record["sha256"], []).append(record["file"])
        if record["identifier_type"] == "doi" and record["identifier"]:
            by_doi.setdefault(record["identifier"].strip().lower(), []).append(record["file"])

    # Every file in the library, not only the referenced ones -- an exact
    # duplicate of something nothing references is still a duplicate.
    seen: dict[str, list[str]] = {}
    for path in sorted(library.glob("*.pdf")):
        seen.setdefault(_digest(path), []).append(path.name)

    return {
        "identical_bytes": {h: names for h, names in seen.items() if len(names) > 1},
        "shared_doi": {d: names for d, names in by_doi.items() if len(set(names)) > 1},
    }


def check(library: Path | None, entries: list[dict]) -> int:
    """Verify the registry's `local` claims. Skips loudly with no library."""
    if library is None:
        print(
            f"SKIPPED: no PDF library here. Set {LIBRARY_ENV} to check the "
            f"`local` field. This is not a pass -- nothing was verified."
        )
        return 0

    index = build_index(library, entries)
    counts: dict[str, int] = {}
    for record in index["records"]:
        counts[record["confidence"]] = counts.get(record["confidence"], 0) + 1

    print(f"library: {library}")
    print(f"checked {len(index['records'])} local-bearing entries")
    for name in (DOI_EXACT, BIBLIOGRAPHIC, AMBIGUOUS, UNRESOLVED):
        print(f"   {name:16s} {counts.get(name, 0)}")

    for record in index["records"]:
        if record["confidence"] == UNRESOLVED:
            print(f"   unresolved: {record['key']:22s} {record['file']}")
        elif record["confidence"] == AMBIGUOUS:
            print(
                f"   AMBIGUOUS : {record['key']:22s} {record['file']} "
                f"-- carries {record['foreign_dois']} and none of its own"
            )

    failures = 0
    for entry in index["missing"]:
        print(f"   MISSING   : {entry['key']:22s} {entry['file']}")
        failures += 1
    failures += counts.get(AMBIGUOUS, 0)

    # UNRESOLVED IS NOT COUNTED. "I could not tell" is not "this is wrong",
    # and conflating them would make the tool cry wolf on three scans and
    # two reference books that are exactly where they should be.
    if failures:
        print(f"\n{failures} problem(s): a named file is absent, or names another work.")
        return 1
    print("\nEvery named file is present and consistent with the entry that names it.")
    return 0


def find(library: Path | None, text: str) -> int:
    """Which file is that? Answers by content, not by filename."""
    if library is None:
        print(f"no library: set {LIBRARY_ENV}")
        return 1
    needle = text.strip()
    for path in sorted(library.glob("*.pdf")):
        if _contains(searchable(path.read_bytes()), needle):
            print(path.name)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--library", help=f"PDF directory (else ${LIBRARY_ENV})")
    parser.add_argument("--check", action="store_true", help="verify the registry's `local` claims")
    parser.add_argument("--duplicates", action="store_true", help="report duplicate files")
    parser.add_argument("--find", metavar="TEXT", help="which file contains TEXT")
    parser.add_argument("--out", help="write the manifest here instead of stdout")
    args = parser.parse_args(argv)

    library = library_path(args.library)
    entries = load_entries()

    if args.find:
        return find(library, args.find)
    if args.check:
        return check(library, entries)
    if library is None:
        print(f"SKIPPED: no PDF library here. Set {LIBRARY_ENV}.")
        return 0

    index = build_index(library, entries)
    if args.duplicates:
        print(json.dumps(duplicates(library, index["records"]), indent=2))
        return 0

    payload = json.dumps(index, indent=2, sort_keys=True)
    if args.out:
        Path(args.out).write_text(payload, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
