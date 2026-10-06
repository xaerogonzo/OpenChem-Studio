"""A local full-text index of the PDF library, so a paper is FOUND instead of re-opened.

WHY. `docs/research/literature.toml` records the papers that were READ, and `docs/sources.toml` the ones
something shipped from. Neither can answer "which held paper has a measured solubility for PGDN?" -- that
question used to be answered by opening every PDF and matching text, 728 files and a 2,643-page handbook
at a time. This reads each PDF once, keeps its text page by page in a SQLite full-text index, and answers
in a second.

LOCAL ONLY, ON PURPOSE. The index is a file next to the library (`<library>.index.sqlite`), never in the
repository: the library holds far more than this project uses, and a public repo should carry records of
the papers we actually relied on (the literature manifest), not a catalogue of everything on a disk.
`tools/index_literature.py` still checks the curated records against their hashes; this is the other half.

    uvx --with pymupdf python tools/library_index.py update              # index new and changed files
    uvx --with pymupdf python tools/library_index.py search "propylene glycol dinitrate | PGDN" --near solub
    python tools/library_index.py show "Aqueous Solubility....pdf" 164   # one page, to read its table
    python tools/library_index.py stats
    python tools/library_index.py stub "Aqueous Solubility....pdf"        # a draft literature.toml entry

`update` needs `pymupdf` (not a project dependency: the usual throwaway environment, `uvx --with pymupdf`);
every other command reads only the index. The library is `--library`, else `OPENCHEM_PDF_LIBRARY`, else the
maintainer's `D:/Xaero Stuff/Documents/Sci Downloads`.

WHAT AN INDEX CANNOT TELL YOU. A PDF with no text layer (a scan) is indexed as EMPTY and listed by `stats`,
never as "no match": a search that silently skips a scanned book answers "not found" about a book that
may well contain it. And a hit is a page to READ, not a value: tables extract as running text, so
`show` prints the page and the number is read off it, against the paper's own table.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sqlite3
import sys
import time
from collections.abc import Iterable, Iterator
from pathlib import Path

DEFAULT_LIBRARY = Path(r"D:\Xaero Stuff\Documents\Sci Downloads")

#: Fewer characters per page than this and the file is treated as having no text layer. A real article page
#: carries thousands; a scan with a stray page number carries a few.
SCANNED_CHARS_PER_PAGE = 100

#: How many leading pages are read for the printed DOI. A paper prints its own on page one; a book may print it
#: on a later front-matter page, and a reference list further in holds OTHER papers' DOIs, which is the trap.
DOI_PAGES = 2

_DOI = re.compile(r"\b(10\.\d{4,9}/[^\s\"<>]+)", re.IGNORECASE)
_SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    path TEXT PRIMARY KEY, sha256 TEXT, size INTEGER, mtime_ns INTEGER, pages INTEGER, chars INTEGER,
    scanned INTEGER, doi TEXT, first_text TEXT, indexed_at REAL, error TEXT
);
CREATE VIRTUAL TABLE IF NOT EXISTS pages USING fts5(
    path UNINDEXED, page UNINDEXED, text, tokenize = 'unicode61 remove_diacritics 2'
);
"""


# --- pure pieces (tested without a PDF) -----------------------------------------------------------------------


def find_doi(text: str) -> str:
    """The first DOI in `text`, trimmed of the punctuation a sentence puts after it, or "".

    Only meant for a file's FIRST pages: a DOI found deeper is usually a reference's, which is a claim about
    another paper. The caller decides which pages to offer.
    """
    match = _DOI.search(text or "")
    if not match:
        return ""
    return match.group(1).rstrip(".,;:)]}'\u201d\u2019")


def is_scanned(chars: int, pages: int) -> bool:
    """Whether a file has no usable text layer."""
    return pages > 0 and chars / pages < SCANNED_CHARS_PER_PAGE


def _phrase(term: str) -> str:
    """One FTS5 phrase, with the query syntax in it defused: a name like `2,4-DNT` must be searched, not parsed."""
    return '"' + term.strip().replace('"', '""') + '"'


def fts_query(text: str, *, near: Iterable[str] = (), within: int = 30, also: Iterable[str] = ()) -> str:
    """The FTS5 expression for a search.

    `text` is ONE phrase (a compound's name is several words), or alternatives separated by `|` (synonyms and
    abbreviations). Each term in `near` must occur within `within` tokens of it; each in `also` anywhere on the
    same page. Everything is quoted, so nothing a user types is read as an operator.
    """
    alternatives = [part for part in (p.strip() for p in text.split("|")) if part]
    if not alternatives:
        raise ValueError("nothing to search for")
    near_terms = [t for t in (n.strip() for n in near) if t]
    parts = []
    for alternative in alternatives:
        if near_terms:
            terms = " ".join([_phrase(alternative), *(_phrase(t) for t in near_terms)])
            parts.append(f"NEAR({terms}, {int(within)})")
        else:
            parts.append(_phrase(alternative))
    expression = " OR ".join(parts)
    extras = [t for t in (a.strip() for a in also) if t]
    if extras:
        expression = f"({expression}) AND " + " AND ".join(_phrase(t) for t in extras)
    return expression


def slug(filename: str) -> str:
    """A key for a literature.toml entry from a file name: lower-case, `_`-separated, never empty."""
    stem = re.sub(r"\.pdf$", "", filename, flags=re.IGNORECASE)
    cleaned = re.sub(r"[^a-z0-9]+", "_", stem.lower()).strip("_")
    return cleaned or "paper"


# --- locating things ------------------------------------------------------------------------------------------


def library_path(explicit: str | None = None) -> Path:
    for candidate in (explicit, os.environ.get("OPENCHEM_PDF_LIBRARY"), str(DEFAULT_LIBRARY)):
        if candidate and Path(candidate).is_dir():
            return Path(candidate)
    raise SystemExit(
        "No PDF library found. Pass --library, or set OPENCHEM_PDF_LIBRARY to the folder of PDFs."
    )


def index_path(library: Path, explicit: str | None = None) -> Path:
    """`<library>.index.sqlite`, a sibling of the folder, so walking the library never meets it."""
    return Path(explicit) if explicit else library.with_name(library.name + ".index.sqlite")


def connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.executescript(_SCHEMA)
    return connection


def library_pdfs(library: Path) -> Iterator[Path]:
    for base, _dirs, names in os.walk(library):
        for name in sorted(names):
            if name.lower().endswith(".pdf"):
                yield Path(base) / name


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


# --- reading PDFs ---------------------------------------------------------------------------------------------


def extract_pages(path: Path) -> Iterator[str]:
    """The text of each page in turn. The only function that needs pymupdf."""
    try:
        import pymupdf
    except ImportError:
        try:
            import fitz as pymupdf
        except ImportError:
            raise SystemExit(
                "Indexing needs pymupdf, which is not a project dependency. Run it as:\n"
                "    uvx --with pymupdf python tools/library_index.py update"
            ) from None
    with pymupdf.open(path) as document:
        for page in document:
            yield page.get_text()


# --- the commands ---------------------------------------------------------------------------------------------


def update(library: Path, connection: sqlite3.Connection, *, prune: bool = True, say=print) -> dict[str, int]:
    """Index every new or changed PDF; forget the ones that are gone. Returns counts.

    A file is unchanged when its size and modification time are, which is the cheap test: hashing a
    library of this size on every run would cost more than reading what changed. The hash is still stored
    (it is what `index_literature.py` records), computed whenever a file is read.
    Committed per file, so an interrupted run loses one file, not an afternoon.
    """
    counts = {"indexed": 0, "unchanged": 0, "errors": 0, "removed": 0}
    known = {row["path"]: row for row in connection.execute("SELECT path, size, mtime_ns FROM files")}
    seen: set[str] = set()
    for pdf in library_pdfs(library):
        relative = pdf.relative_to(library).as_posix()
        seen.add(relative)
        status = pdf.stat()
        previous = known.get(relative)
        if previous is not None and previous["size"] == status.st_size and previous["mtime_ns"] == status.st_mtime_ns:
            counts["unchanged"] += 1
            continue
        started = time.time()
        connection.execute("DELETE FROM pages WHERE path = ?", (relative,))
        error, total_pages, chars, first, texts = "", 0, 0, [], []
        try:
            for number, text in enumerate(extract_pages(pdf), start=1):
                connection.execute("INSERT INTO pages (path, page, text) VALUES (?, ?, ?)", (relative, number, text))
                total_pages, chars = number, chars + len(text)
                if number <= DOI_PAGES:
                    texts.append(text)
                if number == 1:
                    first = text
        except SystemExit:
            raise
        except Exception as exc:  # noqa: BLE001 - a damaged PDF is recorded, never allowed to stop the run
            error = f"{type(exc).__name__}: {exc}"[:300]
            counts["errors"] += 1
        connection.execute(
            "INSERT OR REPLACE INTO files (path, sha256, size, mtime_ns, pages, chars, scanned, doi, first_text, "
            "indexed_at, error) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                relative, sha256_of(pdf), status.st_size, status.st_mtime_ns, total_pages, chars,
                int(is_scanned(chars, total_pages)), find_doi("\n".join(texts)), (first or "")[:600],
                time.time(), error,
            ),
        )
        connection.commit()
        counts["indexed"] += 1
        say(f"  indexed {relative}  ({total_pages} pages, {time.time() - started:.1f} s){'  ERROR ' + error if error else ''}")
    if prune:
        for gone in sorted(set(known) - seen):
            connection.execute("DELETE FROM pages WHERE path = ?", (gone,))
            connection.execute("DELETE FROM files WHERE path = ?", (gone,))
            counts["removed"] += 1
        connection.commit()
    return counts


def search(
    connection: sqlite3.Connection, expression: str, *, file_filter: str = "", limit: int = 20
) -> list[sqlite3.Row]:
    """Matching pages, best first, each with a snippet. `expression` is `fts_query`'s output."""
    sql = (
        "SELECT path, page, snippet(pages, 2, '[[', ']]', ' ... ', 24) AS snippet FROM pages "
        "WHERE pages MATCH ?" + (" AND path LIKE ?" if file_filter else "") + " ORDER BY rank LIMIT ?"
    )
    arguments: list = [expression]
    if file_filter:
        arguments.append(f"%{file_filter}%")
    arguments.append(limit)
    return list(connection.execute(sql, arguments))


def page_text(connection: sqlite3.Connection, path: str, page: int) -> str | None:
    row = connection.execute(
        "SELECT text FROM pages WHERE path = ? AND page = ?", (_resolve(connection, path), page)
    ).fetchone()
    return row["text"] if row else None


def _resolve(connection: sqlite3.Connection, name: str) -> str:
    """An indexed path from what was typed: exact, else the one file whose path contains it."""
    exact = connection.execute("SELECT path FROM files WHERE path = ?", (name,)).fetchone()
    if exact:
        return exact["path"]
    matches = [r["path"] for r in connection.execute("SELECT path FROM files WHERE path LIKE ?", (f"%{name}%",))]
    if len(matches) == 1:
        return matches[0]
    raise SystemExit(
        f"{name!r} matches {len(matches)} indexed files" + (": " + "; ".join(matches[:5]) if matches else ".")
    )


def stub(connection: sqlite3.Connection, name: str) -> str:
    """A DRAFT `[[source]]` for docs/research/literature.toml, from what the index holds.

    Only what a machine can know is filled: the hash, the page count and a DOI that is printed in the first
    pages. The title, venue, property and role are a person's reading of the paper's own first page and are left
    to be written -- an index guessing a title would put an unchecked claim into a record whose whole point is
    that its `printed.*` fields can be checked.
    """
    path = _resolve(connection, name)
    row = connection.execute("SELECT * FROM files WHERE path = ?", (path,)).fetchone()
    first_page = " ".join((row["first_text"] or "").split())[:240]
    return (
        f"# DRAFT from the library index. Fill printed.title / printed.venue from the paper's OWN first page;\n"
        f"# choose assigned.* from the vocabulary in tests/test_literature_manifest.py.\n"
        f"# First page begins: {first_page!r}\n"
        f"[[source]]\n"
        f'id = "{slug(path)}"\n'
        f'file = "{path}"\n'
        f'sha256 = "{row["sha256"]}"\n'
        f"pages = {row['pages']}\n"
        f'access = "held"\n'
        f'printed.doi = "{row["doi"] or ""}"\n'
        f'printed.title = ""\n'
        f'printed.venue = ""\n'
        f'assigned.property = ""\n'
        f'assigned.role = ""\n'
        f'note = ""\n'
    )


def stats(connection: sqlite3.Connection) -> str:
    files, pages = connection.execute("SELECT COUNT(*), COALESCE(SUM(pages), 0) FROM files").fetchone()
    scanned = [r["path"] for r in connection.execute("SELECT path FROM files WHERE scanned = 1 ORDER BY path")]
    broken = [(r["path"], r["error"]) for r in connection.execute("SELECT path, error FROM files WHERE error != ''")]
    lines = [f"{files} files, {pages} pages indexed", f"{len(scanned)} with no text layer (NOT searchable)"]
    lines += [f"    scan: {p}" for p in scanned[:40]]
    lines += [f"{len(broken)} that could not be read"] + [f"    error: {p}: {e}" for p, e in broken[:40]]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--library", help="the PDF folder (else OPENCHEM_PDF_LIBRARY, else the maintainer's)")
    parser.add_argument("--index", help="the index file (else `<library>.index.sqlite` beside the folder)")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("update", help="index new and changed PDFs, forget removed ones")
    commands.add_parser("stats", help="what is indexed, and what could not be")
    find = commands.add_parser("search", help="pages that match")
    find.add_argument("query", help="a phrase; `a | b` for alternatives (synonyms, abbreviations)")
    find.add_argument("--near", action="append", default=[], help="also within --within tokens of this (repeatable)")
    find.add_argument("--within", type=int, default=30)
    find.add_argument("--also", action="append", default=[], help="also somewhere on the same page (repeatable)")
    find.add_argument("--file", default="", help="only files whose path contains this")
    find.add_argument("--limit", type=int, default=20)
    show = commands.add_parser("show", help="print one page's text")
    show.add_argument("file")
    show.add_argument("page", type=int)
    draft = commands.add_parser("stub", help="print a draft literature.toml entry for a file")
    draft.add_argument("file")
    args = parser.parse_args(argv)

    library = library_path(args.library)
    database = index_path(library, args.index)
    if args.command != "update" and not database.is_file():
        raise SystemExit(f"No index at {database}. Build it first: uvx --with pymupdf python tools/library_index.py update")
    connection = connect(database)

    if args.command == "update":
        counts = update(library, connection)
        print(f"{counts['indexed']} indexed, {counts['unchanged']} unchanged, {counts['removed']} removed, {counts['errors']} errors")
        print(stats(connection))
    elif args.command == "stats":
        print(stats(connection))
    elif args.command == "search":
        expression = fts_query(args.query, near=args.near, within=args.within, also=args.also)
        hits = search(connection, expression, file_filter=args.file, limit=args.limit)
        for hit in hits:
            print(f"{hit['path']}  p{hit['page']}\n    {' '.join(hit['snippet'].split())}")
        print(f"{len(hits)} page(s)" + (f" (limit {args.limit})" if len(hits) == args.limit else ""))
        scanned = connection.execute("SELECT COUNT(*) FROM files WHERE scanned = 1").fetchone()[0]
        if scanned:
            print(f"NOTE: {scanned} indexed file(s) have no text layer and cannot match; see `stats`.")
    elif args.command == "show":
        text = page_text(connection, args.file, args.page)
        print(text if text is not None else "no such page")
    elif args.command == "stub":
        print(stub(connection, args.file))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
