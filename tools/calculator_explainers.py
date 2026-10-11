"""Parse and render the hand-written calculator explainers in `docs/explainers/`.

`docs/CALCULATOR_REFERENCE.md` is generated from the registry, and a registry
declaration says what a calculator IS, NEEDS and REFUSES. It has no room for
what the calculator DOES: the idea behind the model, what the output means,
when to prefer it. That prose is authored by hand, so it needs a source file
of its own, merged into the generated reference -- the same split
`docs/sources.toml` -> `docs/SOURCES.md` already uses.

**THIS MODULE PARSES AND RENDERS. IT DOES NOT JUDGE.** Whether every
calculator has a block, whether a block names a real calculator, whether a
cited source exists: `tests/test_calculator_explainers.py` owns all of that,
for the reason `build_calculator_reference.py` owns none of it -- a tool that
also validated would report a problem in the one place nobody runs. Parsing
therefore collects `problems` instead of raising, so a test can say which kind
of failure it found, and rendering degrades visibly (an unknown source key is
printed as written) rather than hiding the error.

THE SOURCE FORMAT, one top-level block per calculator, keyed by its id (never
by a display name or a heading slug, either of which can change on its own):

    ## <calculator_id>
    ### What it does
    ### How it works
    ### What the result means
    ### When to use it, when not
    ### Search for
    ### Sources

A calculator with several model choices adds one `### Method: <choice>` block
per choice (`### Method: a, b` where two choices share an explanation), whose
sections sit one level lower (`####`). Text common to every method is written
once at the top level; what differs is written in the method block.

`[source:key]` in prose is the repository's existing citation syntax, found by
`tests/test_sources_are_current.py` as well. The renderer turns each into a
numbered reference and prints the registry's own citation and its DOI as plain
text, never as a link: a URL rots, and a DOI is the one identifier designed to
outlive the site that hosts it.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXPLAINERS_DIR = ROOT / "docs" / "explainers"
SOURCES_TOML = ROOT / "docs" / "sources.toml"

#: The reader-facing order. Authors may write sections in any order; the
#: reference always prints them in this one, so two blocks read alike.
SECTIONS = (
    "What it does",
    "How it works",
    "What the result means",
    "When to use it, when not",
    "Search for",
    "Sources",
)

#: What a calculator with NO method blocks must say, and what each part of a
#: multi-method calculator must say. A method that explains nothing has to
#: fail even when its parent carries every heading, so the two are separate.
REQUIRED_SINGLE = SECTIONS
REQUIRED_PARENT_OF_METHODS = ("What it does", "Search for")
REQUIRED_METHOD = ("How it works", "What the result means", "Sources")

METHOD_PREFIX = "Method:"

SOURCE_REF = re.compile(r"\[source:([^\]]*)\]")
_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")


@dataclass
class MethodBlock:
    choices: tuple[str, ...]
    sections: dict[str, str] = field(default_factory=dict)


@dataclass
class Block:
    calculator_id: str
    file: str
    sections: dict[str, str] = field(default_factory=dict)
    methods: list[MethodBlock] = field(default_factory=list)


@dataclass
class Explainers:
    blocks: dict[str, Block] = field(default_factory=dict)
    #: (kind, where, detail): kinds are `duplicate`, `unknown_heading`,
    #: `stray_text`, `empty_method`, `bad_level`. Tests group by kind.
    problems: list[tuple[str, str, str]] = field(default_factory=list)


def parse(directory: Path | None = None) -> Explainers:
    """Every `*.md` under the explainers directory, in file-name order."""
    directory = directory or EXPLAINERS_DIR
    found = Explainers()
    if not directory.is_dir():
        return found
    for path in sorted(directory.glob("*.md")):
        _parse_file(path, found)
    return found


def _parse_file(path: Path, found: Explainers) -> None:
    name = path.name
    block: Block | None = None
    target: dict[str, str] | None = None
    section: str | None = None
    buffer: list[str] = []
    #: Text under the file's own `#` title is a note for the maintainer, never rendered
    #: and never a problem; text anywhere else outside a section is.
    in_title = False

    def flush() -> None:
        nonlocal buffer
        if target is not None and section is not None:
            target[section] = "\n".join(buffer).strip()
        elif "".join(buffer).strip() and not in_title:
            found.problems.append(("stray_text", name, "".join(buffer).strip()[:60]))
        buffer = []

    for raw in path.read_text(encoding="utf-8").splitlines():
        heading = _HEADING.match(raw)
        if heading is None:
            buffer.append(raw)
            continue
        level, title = len(heading.group(1)), heading.group(2).strip()
        flush()
        in_title = level == 1
        if level == 1:
            target, section, block = None, None, None
            continue
        if level == 2:
            if title in found.blocks:
                found.problems.append(("duplicate", name, title))
            block = Block(calculator_id=title, file=name)
            found.blocks.setdefault(title, block)
            target, section = None, None
        elif level == 3 and block is not None and title.startswith(METHOD_PREFIX):
            choices = tuple(c.strip() for c in title[len(METHOD_PREFIX):].split(",") if c.strip())
            method = MethodBlock(choices=choices)
            block.methods.append(method)
            target, section = method.sections, None
        elif level == 3 and block is not None:
            _enter(found, name, block, block.sections, title, "### ")
            target, section = (block.sections, title) if title in SECTIONS else (None, None)
        elif level == 4 and block is not None and block.methods:
            method = block.methods[-1]
            _enter(found, name, block, method.sections, title, "#### ")
            target, section = (method.sections, title) if title in SECTIONS else (None, None)
        else:
            found.problems.append(("bad_level", name, f"{'#' * level} {title}"))
            target, section = None, None
    flush()


def _enter(found: Explainers, name: str, block: Block, sections: dict, title: str, marker: str) -> None:
    if title not in SECTIONS:
        found.problems.append(("unknown_heading", f"{name}:{block.calculator_id}", marker + title))
    elif title in sections:
        found.problems.append(("duplicate", f"{name}:{block.calculator_id}", marker + title))


# --- sources ------------------------------------------------------------


def load_sources(path: Path | None = None) -> dict[str, dict]:
    """The registry as `{key: row}`; the one place citations are read from."""
    data = tomllib.loads((path or SOURCES_TOML).read_text(encoding="utf-8"))
    return {row["key"]: row for row in data.get("source", [])}


def source_keys(text: str) -> list[str]:
    """Every `[source:key]` in `text`, in order, duplicates kept."""
    return [key.strip() for key in SOURCE_REF.findall(text)]


def keywords(block_or_method) -> list[str]:
    """The `Search for` line as distinct, trimmed keywords (case-insensitive)."""
    raw = block_or_method.sections.get("Search for", "")
    seen: dict[str, str] = {}
    for part in re.split(r"[,\n;]", raw):
        word = part.strip().strip("-* ").strip()
        if word:
            seen.setdefault(word.lower(), word)
    return list(seen.values())


def reference_line(row: dict | None, key: str) -> str:
    """One bibliography entry: the registry's citation, then its DOI/ISBN as text.

    A `url` identifier is deliberately not printed (see the module docstring);
    that source is still cited by its citation string.
    """
    if row is None:
        return f"[source:{key}]"
    line = row["citation"].strip()
    identifier = str(row.get("identifier", "")).strip()
    kind = row.get("identifier_type")
    if identifier and kind == "doi":
        line += f" DOI {identifier}."
    elif identifier and kind == "isbn":
        line += f" ISBN {identifier}."
    return line


# --- rendering ----------------------------------------------------------


def render(block: Block, sources: dict[str, dict], base_level: int = 4) -> list[str]:
    """The markdown lines for one calculator's explainer.

    `base_level` is the heading depth of every heading emitted: the reference
    prints a calculator as `###`, so its sections and its method titles are
    `####`, and a method's own sections are bold labels. Nothing here may
    create a heading at or above the calculator's own level, or the Help
    window would end the calculator's topic early and the explainer would
    stop being searchable under it.
    """
    numbers: dict[str, int] = {}

    def number(key: str) -> int:
        return numbers.setdefault(key, len(numbers) + 1)

    # Number in the order a reader meets them, so [1] is the first one printed.
    ordered = _in_print_order(block)
    for text in ordered:
        for key in source_keys(text):
            number(key)

    def prose(text: str) -> str:
        return SOURCE_REF.sub(lambda m: f"[{number(m.group(1).strip())}]", text)

    def sources_list(text: str) -> str:
        out = []
        for line in text.splitlines():
            keys = source_keys(line)
            if not keys:
                out.append(line)
                continue
            rest = SOURCE_REF.sub("", line).strip().lstrip("-*:—– ").strip()
            entries = " ".join(
                f"[{number(k)}] {reference_line(sources.get(k), k)}" for k in keys
            )
            out.append(f"- {entries}" + (f" Supports: {rest}" if rest else ""))
        return "\n".join(out)

    def emit(sections: dict[str, str], heading: bool) -> list[str]:
        lines: list[str] = []
        for title in SECTIONS:
            if title not in sections:
                continue
            body = sources_list(sections[title]) if title == "Sources" else prose(sections[title])
            # A heading for the calculator's own sections, a bold label for a method's: the
            # Help window's markdown view draws levels 5 and 6 SMALLER than body text
            # (measured in a shot), so nesting deeper made the labels the hardest thing on
            # the page to read. Everything stays at `base_level`, which is also what keeps
            # it inside the calculator's Help topic.
            label = f"{'#' * base_level} {title}" if heading else f"**{title}**"
            lines += [label, "", body, ""]
        return lines

    lines = emit(block.sections, heading=True)
    for method in block.methods:
        label = ", ".join(f"`{c}`" for c in method.choices)
        lines += [f"{'#' * base_level} {METHOD_PREFIX} {label}", ""]
        lines += emit(method.sections, heading=False)
    return lines


def _in_print_order(block: Block) -> list[str]:
    texts = [block.sections[t] for t in SECTIONS if t in block.sections]
    for method in block.methods:
        texts += [method.sections[t] for t in SECTIONS if t in method.sections]
    return texts
