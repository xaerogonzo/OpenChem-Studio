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

import logging
import re
import sys
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


@lru_cache(maxsize=None)
def _document_lines(document: str) -> tuple[str, ...]:
    path = docs_directory() / document
    if not path.is_file():
        raise HelpUnavailable(f"Help document not found: {document}")
    return tuple(path.read_text(encoding="utf-8").splitlines())


@lru_cache(maxsize=1)
def topics() -> tuple[HelpTopic, ...]:
    """Every anchored topic, in document then document order.

    Cached because it reads three files, and they cannot change under a
    running application -- except in a checkout, where `reload()` exists
    for exactly that.
    """
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


def reload() -> None:
    """Drop the caches so an edited document is picked up.

    Only useful in a checkout, which is precisely where someone editing
    the guide would want to see the result without restarting.
    """
    _document_lines.cache_clear()
    topics.cache_clear()


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))
