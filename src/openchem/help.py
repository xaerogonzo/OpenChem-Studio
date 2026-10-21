"""In-application help, rendered from the repository's own markdown.

THE POINT IS THAT THERE IS ONLY ONE COPY. Help text written into Python
goes stale against the documentation the moment either is edited, and
nothing catches it because both are prose. Here the shipped documents ARE
the help: editing `docs/USER_GUIDE.md` during a documentation pass updates
what the application shows, with no second place to remember.

TOPICS ARE KEYED FROM THE MARKDOWN, NOT FROM A TABLE HERE. Each help topic
is an HTML comment placed immediately above a heading:

    <!-- help:docking -->
    ## Docking

That direction matters. The obvious alternative -- a registry in this file
mapping `"docking"` to the heading text `"## Docking"` -- breaks silently
the first time somebody rewords a heading, which is exactly the kind of
edit a documentation sweep makes. With the key in the document, a heading
can be rewritten freely and the anchor travels with it. HTML comments
render as nothing on GitHub, so the anchors cost the reader nothing.

A key that no longer exists is caught by `tests/test_help.py`, which
resolves every topic referenced by a panel. Loud at test time beats a
blank help window at run time.
"""

from __future__ import annotations

import atexit
import base64
import hashlib
import importlib
import json
import logging
import os
import re
import shutil
import stat
import sys
import tempfile
import zlib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger("openchem.help")

#: Searched in this order, and the order topics are listed in the UI.
#: Deliberately NOT every file in docs/: ARCHITECTURE, ROADMAP, PLUGIN_SDK
#: and VALIDATION are written for people working ON this application
#: rather than with it, and putting them in a user-facing help window
#: would bury the three documents that answer a user's question.
HELP_DOCUMENTS: tuple[str, ...] = (
    "QUICKSTART.md",
    "USER_GUIDE.md",
    "SCIENTIFIC_LIMITATIONS.md",
    # GENERATED from the calculator registry -- see
    # `tools/build_calculator_reference.py`. It is here rather than
    # excluded with ARCHITECTURE and ROADMAP because it answers a USER's
    # question ("what does this calculator do") rather than a maintainer's,
    # which is the line this tuple draws.
    "CALCULATOR_REFERENCE.md",
)

_ANCHOR = re.compile(r"^<!--\s*help:([a-z0-9-]+)\s*-->\s*$")
_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")


@dataclass(frozen=True)
class HelpTopic:
    key: str
    #: Taken from the heading the anchor sits above, so the sidebar and
    #: the document can never disagree about what a section is called.
    title: str
    document: str
    level: int


class HelpUnavailable(RuntimeError):
    """The documents are not where they should be."""


def docs_directory() -> Path:
    """Where the markdown lives, in a checkout or in a frozen build.

    Two locations because the source layout cannot be preserved: `docs/`
    sits beside `src/`, not inside the package, so a frozen build has to
    put it somewhere reachable. `packaging/openchem.spec` maps it to
    `openchem/docs`, which is the first candidate below.
    """
    candidates = [
        Path(__file__).resolve().parent / "docs",  # frozen
        Path(__file__).resolve().parent.parent.parent / "docs",  # checkout
    ]
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    raise HelpUnavailable(
        "Could not find the documentation directory. Looked in: "
        + ", ".join(str(c) for c in candidates)
    )


# ---------------------------------------------------------------------------
# Where the text comes from
# ---------------------------------------------------------------------------
# A release must not keep its help as loose files: the Help window offered to
# open them in an editor, and a save there could drop an anchor and leave F1
# landing on nothing. So the mode is decided by ONE fact, `sys.frozen`:
#
#   * not frozen (a checkout, the tests): read `docs/*.md`, always. A stray
#     generated bundle left by a crashed build is ignored, so it cannot shadow
#     an edited document, and `reload()` keeps working.
#   * frozen: read the bundle `build.ps1` generated into the compiled-module
#     archive, and NEVER fall back to disk. A fallback would hide a broken
#     release behind a loose file that happens to be sitting there.
#
# The bundle's canonical bytes are the UTF-8 JSON of {document: text} in
# HELP_DOCUMENTS order; the digest is over those exact bytes, and the stored
# payload is base85(zlib(those bytes)). It detects accidental damage, which is
# all it claims; it is not an authenticity check.

BUNDLE_SCHEMA = 1
_BUNDLE_MODULE = "openchem._help_bundle"


def _frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def content_source() -> str:
    """``"bundle"`` when the help is read from the compiled archive, else ``"files"``.

    Live state, for the frozen smoke test to assert: a release that quietly
    read loose files would pass every other check.
    """
    return "bundle" if _frozen() else "files"


def source_documents() -> dict[str, str]:
    """Every help document read from the markdown on disk, in HELP_DOCUMENTS order.

    The bundle generator's input, and the reference the bundle is tested
    against. Fails (rather than skipping) on a missing, empty or undecodable
    document, because a bundle built from fewer documents is a smaller help.
    """
    directory = docs_directory()
    documents: dict[str, str] = {}
    for name in HELP_DOCUMENTS:
        path = directory / name
        if not path.is_file():
            raise HelpUnavailable(f"Help document not found: {name}")
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise HelpUnavailable(f"Help document is not UTF-8: {name}") from exc
        if not text.strip():
            raise HelpUnavailable(f"Help document is empty: {name}")
        documents[name] = text
    return documents


def _canonical_bytes(documents: dict[str, str]) -> bytes:
    return json.dumps(documents, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def encode_bundle(documents: dict[str, str]) -> tuple[int, str, str]:
    """``(schema, digest, payload)`` for the generated module."""
    if tuple(documents) != HELP_DOCUMENTS:
        raise HelpUnavailable("The bundle must hold exactly HELP_DOCUMENTS, in order")
    canonical = _canonical_bytes(documents)
    payload = base64.b85encode(zlib.compress(canonical, 9)).decode("ascii")
    return BUNDLE_SCHEMA, hashlib.sha256(canonical).hexdigest(), payload


def decode_bundle(schema: object, digest: object, payload: object) -> dict[str, str]:
    """The documents a bundle holds, or `HelpUnavailable` naming what is wrong.

    Messages carry a category and never document text.
    """
    if schema != BUNDLE_SCHEMA:
        raise HelpUnavailable(f"Help bundle has an unsupported schema ({schema!r})")
    if not isinstance(digest, str) or not isinstance(payload, str):
        raise HelpUnavailable("Help bundle is malformed (digest or payload is not text)")
    try:
        canonical = zlib.decompress(base64.b85decode(payload))
    except (ValueError, zlib.error) as exc:
        raise HelpUnavailable("Help bundle payload cannot be decoded") from exc
    if hashlib.sha256(canonical).hexdigest() != digest:
        raise HelpUnavailable("Help bundle failed its integrity check (digest mismatch)")
    try:
        documents = json.loads(canonical.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise HelpUnavailable("Help bundle payload is not valid JSON") from exc
    if (
        not isinstance(documents, dict)
        or tuple(documents) != HELP_DOCUMENTS
        or not all(isinstance(text, str) and text.strip() for text in documents.values())
    ):
        raise HelpUnavailable("Help bundle does not hold exactly the help documents")
    return documents


def _load_bundle_module():
    """The generated module. A seam, so tests can stand in for it."""
    return importlib.import_module(_BUNDLE_MODULE)


@lru_cache(maxsize=1)
def _bundle_documents() -> dict[str, str]:
    """Decoded and verified once per process."""
    try:
        module = _load_bundle_module()
    except ModuleNotFoundError as exc:
        if exc.name == _BUNDLE_MODULE:
            raise HelpUnavailable("This build has no help bundle (the generated module is missing)") from exc
        raise HelpUnavailable(f"The help bundle could not be imported ({exc.name} is missing)") from exc
    except Exception as exc:  # noqa: BLE001 - a broken module is reported as such, not masked
        raise HelpUnavailable(f"The help bundle could not be imported ({type(exc).__name__})") from exc
    return decode_bundle(
        getattr(module, "SCHEMA", None),
        getattr(module, "DIGEST", None),
        getattr(module, "PAYLOAD", None),
    )


@lru_cache(maxsize=None)
def _document_lines(document: str) -> tuple[str, ...]:
    if _frozen():
        documents = _bundle_documents()
        if document not in documents:
            raise HelpUnavailable(f"Help document not found: {document}")
        return tuple(documents[document].splitlines())
    path = docs_directory() / document
    if not path.is_file():
        raise HelpUnavailable(f"Help document not found: {document}")
    return tuple(path.read_text(encoding="utf-8").splitlines())


def document_text(document: str) -> str:
    """A help document as written, anchors included (the reading copy's content)."""
    if document not in HELP_DOCUMENTS:
        raise HelpUnavailable(f"Not a help document: {document}")
    return "\n".join(_document_lines(document)) + "\n"


_COPY_DIRECTORY: Path | None = None


def _remove_copy_directory() -> None:
    directory = _COPY_DIRECTORY
    if directory is None or not directory.is_dir():
        return
    for path in directory.iterdir():
        try:
            os.chmod(path, stat.S_IWRITE)
        except OSError:
            pass
    # An editor may still hold a file; the system temp folder is the backstop.
    shutil.rmtree(directory, ignore_errors=True)


def reading_copy(document: str) -> Path:
    """A read-only copy of a help document in a private temporary folder.

    What "Open file" opens. The path is outside the install, which is the real
    protection; the read-only bit only stops an editor offering to save over it
    by accident. One folder per process, written once and reused, removed at
    exit on a best-effort basis (never on open, since an editor may load lazily).
    """
    global _COPY_DIRECTORY
    text = document_text(document)
    if _COPY_DIRECTORY is None or not _COPY_DIRECTORY.is_dir():
        _COPY_DIRECTORY = Path(tempfile.mkdtemp(prefix="openchem-help-"))
        atexit.register(_remove_copy_directory)
    path = _COPY_DIRECTORY / document
    if not path.exists():
        path.write_text(text, encoding="utf-8", newline="\n")
        os.chmod(path, stat.S_IREAD)
    return path


@lru_cache(maxsize=1)
def topics() -> tuple[HelpTopic, ...]:
    """Every anchored topic, in document then document order.

    Cached because it reads three files, and they cannot change under a
    running application -- except in a checkout, where `reload()` exists
    for exactly that.
    """
    if _frozen():
        # Fail closed: a broken bundle must not read as "fewer topics".
        _bundle_documents()
    found: list[HelpTopic] = []
    seen: dict[str, str] = {}
    for document in HELP_DOCUMENTS:
        try:
            lines = _document_lines(document)
        except HelpUnavailable:
            logger.warning("Help document missing, skipping: %s", document)
            continue
        for index, line in enumerate(lines):
            match = _ANCHOR.match(line)
            if match is None:
                continue
            key = match.group(1)
            heading = _next_heading(lines, index)
            if heading is None:
                # An anchor with no heading under it cannot be turned into
                # a section. Skipped rather than raised: a broken anchor
                # should not take the whole help system down, and the test
                # suite reports it.
                logger.warning("Help anchor %r in %s is not above a heading", key, document)
                continue
            level, title = heading
            if key in seen:
                logger.warning(
                    "Duplicate help key %r in %s (already in %s); keeping the first",
                    key,
                    document,
                    seen[key],
                )
                continue
            seen[key] = document
            found.append(HelpTopic(key=key, title=title, document=document, level=level))
    return tuple(found)


def _next_heading(lines: tuple[str, ...], start: int) -> tuple[int, str] | None:
    """The first heading at or after `start`, skipping blank lines only.

    Anything else between the anchor and a heading means the anchor is not
    labelling that heading, so it is not treated as one.
    """
    for line in lines[start + 1 :]:
        if not line.strip():
            continue
        match = _HEADING.match(line)
        return (len(match.group(1)), match.group(2)) if match else None
    return None


def topic(key: str) -> HelpTopic:
    for candidate in topics():
        if candidate.key == key:
            return candidate
    raise HelpUnavailable(f"No help topic keyed {key!r}")


def topic_markdown(key: str) -> str:
    """The section a topic anchors, heading included.

    The section ends at the next heading of the SAME OR HIGHER level, so
    `## Quantum chemistry` carries its `### IR spectra` subsection along
    with it while `### IR spectra` on its own does not swallow the section
    that follows. Sub-topics being readable both on their own and as part
    of their parent is the behaviour that makes per-panel help useful.
    """
    found = topic(key)
    lines = _document_lines(found.document)
    body: list[str] = []
    collecting = False
    for index, line in enumerate(lines):
        if not collecting:
            match = _ANCHOR.match(line)
            if match is not None and match.group(1) == key:
                collecting = True
            continue
        heading = _HEADING.match(line)
        if heading is not None and len(heading.group(1)) <= found.level and body:
            break
        # Anchors are markup for this module, not content for the reader.
        if _ANCHOR.match(line) is None:
            body.append(line)
        del index
    return "\n".join(body).strip()


def document_markdown(document: str) -> str:
    """A whole document, with the anchors stripped."""
    if document not in HELP_DOCUMENTS:
        raise HelpUnavailable(f"Not a help document: {document}")
    lines = _document_lines(document)
    return "\n".join(line for line in lines if _ANCHOR.match(line) is None).strip()


@dataclass(frozen=True)
class SearchHit:
    topic: HelpTopic
    #: How many times the query appears in the section body. Ranks the
    #: results, and tells a reader whether a topic mentions the term once
    #: in passing or is actually about it.
    occurrences: int
    #: True when the query is in the heading. Ranked above body matches:
    #: someone typing "docking" wants the Docking section first, not the
    #: batch section that mentions docking twice.
    in_title: bool
    #: One line of context, so a hit whose title looks unrelated explains
    #: itself without being opened.
    snippet: str


def search(query: str) -> tuple[SearchHit, ...]:
    """Topics matching `query`, best first.

    Searches the SECTION BODIES, not just the headings. Title-only
    filtering answers "what is this feature called", which is the question
    a reader who already knows the answer would ask. The real one is "what
    does it say about Vina" -- a word that appears in no heading in these
    documents and in four separate sections of their text, including the
    one that explains why its score is not a binding free energy.

    Plain case-insensitive substring matching, deliberately: these are
    three documents totalling a few thousand lines, so anything cleverer
    (stemming, fuzzy distance) would add ways to be surprised without
    adding reach.
    """
    needle = query.strip().lower()
    if not needle:
        return ()
    hits: list[SearchHit] = []
    for topic in topics():
        body = topic_markdown(topic.key)
        lowered = body.lower()
        occurrences = lowered.count(needle)
        in_title = needle in topic.title.lower()
        if not occurrences and not in_title:
            continue
        hits.append(
            SearchHit(
                topic=topic,
                occurrences=occurrences,
                in_title=in_title,
                snippet=_snippet(body, needle),
            )
        )
    # Title matches first, then by how often the term appears, then by
    # document order so the ranking is stable rather than arbitrary.
    order = {topic.key: index for index, topic in enumerate(topics())}
    hits.sort(key=lambda hit: (not hit.in_title, -hit.occurrences, order[hit.topic.key]))
    return tuple(hits)


def _snippet(body: str, needle: str, width: int = 90) -> str:
    """The first line containing `needle`, trimmed around the match.

    Line-based rather than a character window around the offset, because a
    fixed window cuts words in half at both ends and reads like corruption.
    """
    for line in body.splitlines():
        position = line.lower().find(needle)
        if position < 0:
            continue
        stripped = line.strip("# ").strip()
        if len(stripped) <= width:
            return stripped
        # Re-find in the stripped line; the offset moved.
        position = max(stripped.lower().find(needle), 0)
        start = max(0, position - width // 3)
        end = min(len(stripped), start + width)
        return ("..." if start else "") + stripped[start:end].strip() + ("..." if end < len(stripped) else "")
    return ""


def reload() -> None:
    """Drop the caches so an edited document is picked up.

    Only useful in a checkout, which is precisely where someone editing
    the guide would want to see the result without restarting. The frozen
    bundle is immutable and is deliberately not reloaded.
    """
    _document_lines.cache_clear()
    topics.cache_clear()
