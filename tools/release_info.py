"""What the release workflow needs to know about a version, from the repository's own files.

    python tools/release_info.py version
    python tools/release_info.py check-tag v0.10.0
    python tools/release_info.py notes v0.10.0 --out notes.md

Standard library only, so the workflow can run it on a bare runner before anything is
installed. Three things, each a way a release goes wrong quietly:

  * `check-tag`: the tag a release is cut from must be `v` + the version in
    `pyproject.toml`. A mismatch means the installer's version, the zip's name and
    About all say one thing and the tag another.
  * `notes`: the release notes are the `## [<version>]` section of `CHANGELOG.md`,
    and a version with no section, or an empty one, is refused. "Unreleased" is not
    a version: shipping it would announce a release whose notes say nothing about it.
  * `version`: the single source for the number, so no step parses it a second way.
"""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: A release tag: `v` and a plain dotted version. Pre-release suffixes are not used here.
TAG = re.compile(r"^v(\d+\.\d+\.\d+)$")


class ReleaseInfoError(ValueError):
    """The release cannot be cut as asked."""


def project_version(pyproject: Path = ROOT / "pyproject.toml") -> str:
    try:
        version = tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]["version"]
    except (OSError, KeyError, tomllib.TOMLDecodeError) as exc:
        raise ReleaseInfoError(f"cannot read the project version from {pyproject}: {exc}") from exc
    if not isinstance(version, str) or not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ReleaseInfoError(f"the project version {version!r} is not a plain dotted version")
    return version


def check_tag(tag: str, version: str) -> str:
    """The version a tag names, if it is a release tag AND matches `version`."""
    match = TAG.fullmatch(tag)
    if match is None:
        raise ReleaseInfoError(f"{tag!r} is not a release tag (expected v<major>.<minor>.<patch>)")
    if match.group(1) != version:
        raise ReleaseInfoError(
            f"the tag {tag} says {match.group(1)} but pyproject.toml says {version}; "
            "bump the version in a merged PR first, then tag that commit"
        )
    return match.group(1)


def release_notes(changelog: str, version: str) -> str:
    """The text under `## [<version>]` in a Keep a Changelog file, up to the next `## [`."""
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ReleaseInfoError(f"{version!r} is not a version; only a released version has release notes")
    lines = changelog.splitlines()
    heading = re.compile(rf"^## \[{re.escape(version)}\](\s|$)")
    start = next((i for i, line in enumerate(lines) if heading.match(line)), None)
    if start is None:
        raise ReleaseInfoError(
            f"CHANGELOG.md has no '## [{version}]' section. Move the Unreleased entries under a "
            f"'## [{version}] — <date>' heading in the same PR that bumps the version."
        )
    body: list[str] = []
    for line in lines[start + 1 :]:
        if line.startswith("## ["):
            break
        body.append(line)
    text = "\n".join(body).strip()
    if not text:
        raise ReleaseInfoError(f"the '## [{version}]' section of CHANGELOG.md is empty")
    return text + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("version")
    check = sub.add_parser("check-tag")
    check.add_argument("tag")
    notes = sub.add_parser("notes")
    notes.add_argument("tag")
    notes.add_argument("--out", type=Path)
    notes.add_argument("--changelog", type=Path, default=ROOT / "CHANGELOG.md")
    args = parser.parse_args(argv)
    try:
        version = project_version()
        if args.command == "version":
            print(version)
        elif args.command == "check-tag":
            print(check_tag(args.tag, version))
        else:
            text = release_notes(args.changelog.read_text(encoding="utf-8"), check_tag(args.tag, version))
            if args.out:
                args.out.write_text(text, encoding="utf-8", newline="\n")
            else:
                sys.stdout.write(text)
    except (ReleaseInfoError, OSError) as exc:
        print(f"release_info: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
