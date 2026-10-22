"""Changelog fragments: a PR adds a file under `changelog.d/`, never a section of CHANGELOG.md.

    python tools/changelog.py new <slug>        # create changelog.d/<stamp>-<slug>-<hex>.md
    python tools/changelog.py check             # validate every fragment (read-only)
    python tools/changelog.py check --no-pending  # release gate: no fragment may remain
    python tools/changelog.py preview           # print the CHANGELOG.md `build` would write
    python tools/changelog.py build             # fold fragments into [Unreleased], delete them

Why this exists: every PR used to insert its section at the same line (the top of
`## [Unreleased]`), so whichever PR merged second conflicted, was rebased, and waited for CI
again. Two files with different names cannot conflict.

Contracts worth knowing:

  * The filename is `YYYYMMDDHHMM-<slug>-<4 hex>.md` (UTC). The hex makes two same-slug
    fragments from independent branches differ; the stamp is the ORDER, newest first. Order
    is therefore "when the author started the fragment", not merge time, and it needs no Git
    history, so it is the same in a shallow CI clone and for an uncommitted file.
  * `build` writes CHANGELOG.md completely before it deletes any fragment, touches no Git
    index and makes no commit. A failure leaves everything as it was.
  * Only the repository's root CHANGELOG.md is ever read. The vendored namer's own
    changelog under src/openchem/vendor/ is a different document with a different process.

Standard library only, so a release job can run it on a bare runner.
"""

from __future__ import annotations

import argparse
import os
import re
import secrets
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRAGMENT_DIR = "changelog.d"

#: What a fragment's filename looks like. README.md can never match it.
FRAGMENT_NAME = re.compile(r"^\d{12}-[a-z0-9]+(?:-[a-z0-9]+)*-[0-9a-f]{4}\.md$")

#: `new` writes this; `check` rejects it, so an unedited template cannot reach master.
PLACEHOLDER = "REPLACE ME"
TEMPLATE = f"### {PLACEHOLDER}: one-line title of the change\n- {PLACEHOLDER}: what changed and why\n"

UNRELEASED = "## [Unreleased]"


class ChangelogError(ValueError):
    """The request cannot be carried out."""


def _norm_title(title: str) -> str:
    return " ".join(title.lower().split())


def slugify(raw: str) -> str:
    """A safe slug, or a refusal. Separators and `..` are refused, not quietly rewritten."""
    if re.search(r"[/\\]|\.\.", raw):
        raise ChangelogError(f"{raw!r} is not a slug: no path separators or '..'")
    slug = re.sub(r"[^a-z0-9]+", "-", raw.lower()).strip("-")
    if not slug:
        raise ChangelogError(f"{raw!r} has no letters or digits to make a slug from")
    return slug


def fragment_paths(root: Path) -> list[Path]:
    """Real fragments, newest first (filename order, reversed)."""
    directory = root / FRAGMENT_DIR
    if not directory.is_dir():
        return []
    names = sorted((p.name for p in directory.iterdir() if FRAGMENT_NAME.fullmatch(p.name)), reverse=True)
    return [directory / n for n in names]


def new_fragment(root: Path, raw_slug: str, now: datetime | None = None) -> Path:
    """Create a template fragment with an exclusive open, so it can never overwrite one."""
    slug = slugify(raw_slug)
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%d%H%M")
    directory = root / FRAGMENT_DIR
    directory.mkdir(exist_ok=True)
    for _ in range(50):
        path = directory / f"{stamp}-{slug}-{secrets.token_hex(2)}.md"
        try:
            with open(path, "x", encoding="utf-8", newline="\n") as handle:
                handle.write(TEMPLATE)
        except FileExistsError:
            continue
        return path
    raise ChangelogError("could not find an unused fragment name")  # pragma: no cover


def parse_fragment(text: str) -> tuple[str | None, list[str]]:
    """(title, problems). A fenced block hides its lines from every rule below."""
    problems: list[str] = []
    lines = text.lstrip("﻿").replace("\r\n", "\n").split("\n")
    in_fence = False
    h3: list[str] = []
    bullets = 0
    first_content = None
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(("```", "~~~")):
            in_fence = not in_fence
            first_content = first_content or line
            continue
        if not stripped:
            continue
        first_content = first_content or line
        if in_fence:
            continue
        if line.startswith("### "):
            h3.append(line[4:].strip())
        elif re.match(r"^#{1,2} ", line):
            problems.append("a '#' or '##' heading would break the changelog's structure")
        elif re.match(r"^\s*[-*] \S", line):
            bullets += 1
    if in_fence:
        problems.append("a code fence is never closed")
    if first_content is None:
        return None, ["the file is empty"]
    if not first_content.startswith("### "):
        problems.append("the first line must be the '### Title' line (nothing before it)")
    if len(h3) != 1:
        problems.append(f"expected exactly one '### ' title, found {len(h3)}")
    title = h3[0] if h3 else None
    if title is not None and not title:
        problems.append("the title is empty")
    if bullets == 0:
        problems.append("no '- ' bullet outside a code block")
    if PLACEHOLDER in text:
        problems.append(f"still contains the template placeholder {PLACEHOLDER!r}")
    return title, problems


def unreleased_span(lines: list[str]) -> tuple[int, int]:
    """(heading index, index of the next '## [' heading or len). Exactly one Unreleased."""
    starts = [i for i, line in enumerate(lines) if line.rstrip() == UNRELEASED]
    if len(starts) != 1:
        raise ChangelogError(f"CHANGELOG.md must have exactly one '{UNRELEASED}' heading, found {len(starts)}")
    start = starts[0]
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## [")), len(lines))
    return start, end


def legacy_titles(changelog: str) -> set[str]:
    lines = changelog.replace("\r\n", "\n").split("\n")
    start, end = unreleased_span(lines)
    return {_norm_title(line[4:]) for line in lines[start + 1 : end] if line.startswith("### ")}


def validate(root: Path, changelog: str) -> list[str]:
    """Every problem across all fragments, each naming its file. Empty means clean."""
    errors: list[str] = []
    seen: dict[str, str] = {}
    try:
        legacy = legacy_titles(changelog)
    except ChangelogError as exc:
        return [str(exc)]
    for path in fragment_paths(root):
        title, problems = parse_fragment(path.read_text(encoding="utf-8"))
        errors += [f"{FRAGMENT_DIR}/{path.name}: {p}" for p in problems]
        if not title:
            continue
        key = _norm_title(title)
        if key in legacy:
            errors.append(f"{FRAGMENT_DIR}/{path.name}: title {title!r} is already in [Unreleased]")
        elif key in seen:
            errors.append(f"{FRAGMENT_DIR}/{path.name}: title {title!r} duplicates {seen[key]}")
        else:
            seen[key] = f"{FRAGMENT_DIR}/{path.name}"
    return errors


def render(changelog: str, fragments: list[str]) -> str:
    """The changelog with each fragment prepended to [Unreleased], in the order given.

    Pure: strings in, string out, which is why preview and build cannot disagree.
    The file's own line ending (LF or CRLF) is kept.
    """
    if not fragments:
        return changelog
    eol = "\r\n" if "\r\n" in changelog else "\n"
    lines = changelog.replace("\r\n", "\n").split("\n")
    start, _ = unreleased_span(lines)
    rest = lines[start + 1 :]
    while rest and not rest[0].strip():
        rest.pop(0)
    blocks: list[str] = []
    for text in fragments:
        blocks += text.replace("\r\n", "\n").lstrip("﻿").strip().split("\n") + [""]
    out = lines[: start + 1] + [""] + blocks + rest
    return eol.join(out)


def _read(root: Path) -> tuple[Path, str]:
    path = root / "CHANGELOG.md"
    try:
        return path, path.read_bytes().decode("utf-8")
    except OSError as exc:
        raise ChangelogError(f"cannot read {path}: {exc}") from exc


def build(root: Path, write: bool) -> tuple[str, list[Path]]:
    """(new text, fragments consumed). Validates everything first; writes only if `write`."""
    path, changelog = _read(root)
    errors = validate(root, changelog)
    if errors:
        raise ChangelogError("invalid fragments, nothing changed:\n  " + "\n  ".join(errors))
    paths = fragment_paths(root)
    text = render(changelog, [p.read_text(encoding="utf-8") for p in paths])
    if write and paths:
        fd, tmp = tempfile.mkstemp(dir=root, prefix=".CHANGELOG.", suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(text.encode("utf-8"))
            os.replace(tmp, path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
        for fragment in paths:  # only after the changelog is safely on disk
            fragment.unlink()
    return text, paths


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=ROOT, help="repository root (default: this checkout)")
    sub = parser.add_subparsers(dest="command", required=True)
    new = sub.add_parser("new", help="create a template fragment (fails `check` until edited)")
    new.add_argument("slug")
    check = sub.add_parser("check", help="validate fragments; read-only")
    check.add_argument("--no-pending", action="store_true", help="also fail if any fragment exists")
    sub.add_parser("preview", help="print the CHANGELOG.md `build` would write; read-only")
    sub.add_parser("build", help="fold fragments into [Unreleased] and delete them; no git changes")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        if args.command == "new":
            print(new_fragment(root, args.slug).relative_to(root).as_posix())
        elif args.command == "check":
            errors = validate(root, _read(root)[1])
            pending = fragment_paths(root)
            if args.no_pending and pending:
                errors += [f"{FRAGMENT_DIR}/{p.name}: pending; run tools/changelog.py build" for p in pending]
            if errors:
                print("changelog: problems\n  " + "\n  ".join(errors), file=sys.stderr)
                return 1
            print(f"changelog: {len(pending)} fragment(s) ok")
        elif args.command == "preview":
            sys.stdout.buffer.write(build(root, write=False)[0].encode("utf-8"))
        else:
            _, consumed = build(root, write=True)
            print(f"changelog: folded {len(consumed)} fragment(s)" if consumed else "changelog: no pending fragments")
    except ChangelogError as exc:
        print(f"changelog: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
