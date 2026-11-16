"""Freeze and verify a sidecar environment from a recipe, not from a saved tree.

A recipe is Python version + lockfile hash + pins + sha256 of the heavy files.
It does not install packages, download models, or copy a venv. Recreate from
the recipe with uv (and the tool that fetched the files) when you need the
tree again.

The first committed recipe is `benchmarks/synthesis/sidecar_recipe.json`, the
AiZynthFinder 4.4.1 environment the quality benchmark ran.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path

ALLOWED_KEYS = frozenset(
    {
        "kind",
        "format",
        "id",
        "python",
        "lockfile",
        "lockfile_sha256",
        "pins",
        "obtain_data",
        "files",
        "smoke_package",
        "smoke_version",
    }
)
KIND = "sidecar-recipe"
FORMAT = 1


class RecipeError(ValueError):
    """The file is not a sidecar recipe this tool can read."""


@dataclass(frozen=True)
class DataFile:
    path: str
    sha256: str
    bytes: int


@dataclass(frozen=True)
class Recipe:
    id: str
    python: str
    lockfile: str
    lockfile_sha256: str
    pins: tuple[str, ...]
    obtain_data: str
    files: tuple[DataFile, ...]
    smoke_package: str
    smoke_version: str
    source: Path


@dataclass(frozen=True)
class Report:
    ok: bool
    lock: str
    data: str
    detail: str = ""


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _digest_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def load(path: Path) -> Recipe:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise RecipeError("recipe must be a JSON object")
    unknown = sorted(set(raw) - ALLOWED_KEYS)
    if unknown:
        raise RecipeError(f"unknown key: {', '.join(unknown)}")
    missing = sorted(ALLOWED_KEYS - set(raw))
    if missing:
        raise RecipeError(f"missing key: {', '.join(missing)}")
    if raw["kind"] != KIND:
        raise RecipeError(f"kind must be {KIND!r}")
    if raw["format"] != FORMAT:
        raise RecipeError(f"format must be {FORMAT}")
    files = []
    for entry in raw["files"]:
        if set(entry) != {"path", "sha256", "bytes"}:
            raise RecipeError("each file needs path, sha256 and bytes")
        files.append(
            DataFile(
                path=str(entry["path"]),
                sha256=str(entry["sha256"]),
                bytes=int(entry["bytes"]),
            )
        )
    return Recipe(
        id=str(raw["id"]),
        python=str(raw["python"]),
        lockfile=str(raw["lockfile"]),
        lockfile_sha256=str(raw["lockfile_sha256"]),
        pins=tuple(str(pin) for pin in raw["pins"]),
        obtain_data=str(raw["obtain_data"]),
        files=tuple(files),
        smoke_package=str(raw["smoke_package"]),
        smoke_version=str(raw["smoke_version"]),
        source=path,
    )


def verify(path: Path, data_dir: Path | None = None) -> Report:
    recipe = load(path)
    lock_path = path.parent / recipe.lockfile
    if not lock_path.is_file():
        return Report(ok=False, lock="absent", data="unchecked", detail=str(lock_path))
    lock_hash = _digest(lock_path.read_bytes())
    if lock_hash != recipe.lockfile_sha256:
        return Report(ok=False, lock="mismatch", data="unchecked")
    if not recipe.files:
        return Report(ok=True, lock="ok", data="none")
    if data_dir is None:
        return Report(ok=False, lock="ok", data="absent")
    for entry in recipe.files:
        candidate = data_dir / entry.path
        if not candidate.is_file():
            return Report(ok=False, lock="ok", data="absent", detail=entry.path)
        size = candidate.stat().st_size
        digest = _digest_file(candidate)
        if size != entry.bytes or digest != entry.sha256:
            return Report(ok=False, lock="ok", data="mismatch", detail=entry.path)
    return Report(ok=True, lock="ok", data="ok")


def freeze(path: Path, data_dir: Path) -> Recipe:
    recipe = load(path)
    lock_path = path.parent / recipe.lockfile
    if not lock_path.is_file():
        raise RecipeError(f"lockfile is not there: {lock_path}")
    files = []
    for entry in recipe.files:
        candidate = data_dir / entry.path
        if not candidate.is_file():
            raise RecipeError(f"data file is not there: {candidate}")
        files.append(
            {
                "path": entry.path,
                "sha256": _digest_file(candidate),
                "bytes": candidate.stat().st_size,
            }
        )
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["lockfile_sha256"] = _digest(lock_path.read_bytes())
    raw["files"] = files
    path.write_bytes((json.dumps(raw, indent=2) + "\n").encode("utf-8"))
    return load(path)


def recreate_commands(recipe: Recipe) -> list[str]:
    """The commands that rebuild the environment. This tool does not run them."""
    return [
        f"uv python install {recipe.python}",
        f"uv venv --python {recipe.python} .venv",
        f"uv pip install --python .venv -r {recipe.lockfile}",
        f"# then, in that interpreter: {recipe.obtain_data}",
        f"# smoke: importlib.metadata.version({recipe.smoke_package!r}) == {recipe.smoke_version!r}",
    ]


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("verify", "freeze", "commands"))
    parser.add_argument("recipe", type=Path)
    parser.add_argument("--data", type=Path, default=None)
    args = parser.parse_args(argv)
    if args.command == "verify":
        report = verify(args.recipe, data_dir=args.data)
        print(json.dumps({"ok": report.ok, "lock": report.lock, "data": report.data, "detail": report.detail}))
        return 0 if report.ok else 1
    if args.command == "freeze":
        if args.data is None:
            parser.error("freeze needs --data")
        freeze(args.recipe, data_dir=args.data)
        return 0
    recipe = load(args.recipe)
    for line in recreate_commands(recipe):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(_main())
