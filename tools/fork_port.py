"""Port this repository's vendored naming changes to the standalone fork (`xaerogonzo/open-iupac-namer`).

    python tools/fork_port.py --fork D:/_scratch/open-iupac-namer --base 470ff2c --head naming-round-9
    python tools/fork_port.py --fork ... --base ... --head ... --dry-run     # classify every changed file, write nothing

Follows `src/openchem/vendor/VENDORING.md` ("Pushing a change OUT to the fork: merge, never copy"): each file is a
THREE-WAY MERGE with `git merge-file`, where

    ours    the fork's committed file
    base    this repository's file at the commit the fork was last synced to, import-rewritten
    theirs  this repository's file at HEAD, import-rewritten

and the rewrite is the inverse of the vendoring import substitution plus the deliberate content differences
(`OPENCHEM_NAMER_DEBUG` -> `IUPAC_NAMER_DEBUG`, and the repository-relative path to KNOWN_LIMITATIONS.md).

**`--base` is the commit whose `src` the fork ALREADY HOLDS**, not the fork's own commit. The last sync's row in VENDORING.md names it
("corresponding to this repository's ... `470ff2c`"). A wrong base merges the wrong delta and reads as a hundred conflicts.

CHANGELOG.md, KNOWN_LIMITATIONS.md and BENCHMARK_HISTORY.md are WRITTEN in the fork, never copied, so this tool never touches them.

**Which tests come across is decided by what a test imports, not by a list.** Naming round 5 missed `test_namer_preference_key.py` from a
hand-kept list and the fork's stale copy failed 24 times while every ported engine file was fine. A changed `tests/test_*.py` is
PORTABLE when it reaches the engine only through `openchem.vendor.iupac_namer` and imports nothing else of `openchem` (no provider, no
panel, no benchmark tree); it is reported as APP-READING otherwise and NOT ported, because the fork has none of those layers and a
hand-written variant is the right answer (round 8 wrote one for the pinned-shapes test). The audit at the end compares the numstat of the
engine and data files here and in the fork, so a merge that silently dropped a hunk shows as a different count.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# The vendor directory's own documents (CHANGELOG.md, KNOWN_LIMITATIONS.md, BENCHMARK_HISTORY.md, VENDORING.md) are written in the fork and never
# copied. There is deliberately NO list of them here: only `iupac_namer/` and `data/` are mapped, so a document directly under the vendor
# directory falls through to "not ported" on its own. (A first version kept the list; deleting it changed no behaviour, which is what an
# equivalent mutant looks like, and the list was removed rather than claimed.)
VENDOR = "src/openchem/vendor/"
TRACKED_ROOTS = ("src/openchem/vendor", "tests/vendor", "tests")


def rewrite(text: str) -> str:
    """The inverse of the vendoring import substitution, plus the deliberate content differences."""
    text = re.sub(r"\b(from|import) openchem\.vendor\.iupac_namer\b", r"\1 iupac_namer", text)
    text = text.replace("openchem.vendor.iupac_namer", "iupac_namer")
    text = text.replace("OPENCHEM_NAMER_DEBUG", "IUPAC_NAMER_DEBUG")
    text = text.replace("OPENCHEM_NAMER_OWNERSHIP", "IUPAC_NAMER_OWNERSHIP")
    text = text.replace("src/openchem/vendor/KNOWN_LIMITATIONS.md", "KNOWN_LIMITATIONS.md")
    return text


#: A path a test builds from the repository layout: the fork has no benchmark tree, no tools and no docs directory.
_REPO_PATH = re.compile(r"^(benchmarks|tools|docs|src/openchem)(/|$)")


def _tools_modules() -> set[str]:
    return {p.stem for p in (REPO / "tools").glob("*.py")}


def classify_test(text: str) -> str:
    """Decide from the test's SYNTAX, never from a word in its prose (a comment that cites `benchmarks/naming` reads the tree no more
    than a docstring that cites a paper reads the paper -- the first version of this classifier judged by text and called the
    known-defects test app-reading for exactly that).

    `portable`     reaches the engine through `openchem.vendor.iupac_namer` and imports nothing else of `openchem`, none of this
                   repository's tools, and builds no path into `benchmarks/`, `tools/`, `docs/` or `src/openchem`;
    `app-reading`  imports anything else of `openchem` or a repository tool, or builds such a path;
    `unrelated`    does not touch the namer at all.
    """
    import ast

    try:
        tree = ast.parse(text)
    except SyntaxError:
        return "app-reading"  # cannot be judged, so it is not ported silently
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
    if not any(m == "openchem.vendor.iupac_namer" or m.startswith("openchem.vendor.iupac_namer.") for m in imported):
        return "unrelated"
    if any(m.split(".")[0] == "openchem" and not m.startswith("openchem.vendor.iupac_namer") for m in imported):
        return "app-reading"
    if imported & _tools_modules():
        return "app-reading"
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                docstrings.add(id(first.value))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings:
            if _REPO_PATH.match(node.value.replace("\\", "/")):
                return "app-reading"
    return "portable"


def fork_path(repo_rel: str, text: str | None = None) -> str | None:
    """Where a repository file lands in the fork, or None if it is not ported (see the module docstring)."""
    if repo_rel.startswith(VENDOR + "iupac_namer/") or repo_rel.startswith(VENDOR + "data/"):
        return repo_rel[len(VENDOR):]
    if repo_rel.startswith("tests/vendor/iupac_namer/"):
        return "tests/" + repo_rel[len("tests/vendor/iupac_namer/"):]
    if re.fullmatch(r"tests/test_[^/]+\.py", repo_rel) and text is not None and classify_test(text) == "portable":
        return repo_rel
    return None


def _git(args: list[str], cwd: Path = REPO) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="surrogateescape")


def show(ref: str, path: str) -> str | None:
    out = _git(["show", f"{ref}:{path}"])
    return out.stdout if out.returncode == 0 else None


def merge_file(ours: str, base: str, theirs: str) -> tuple[str, int]:
    """`git merge-file` on three texts. Returns the merged text (with conflict markers if any) and the number of conflict hunks."""
    with tempfile.TemporaryDirectory() as tmp:
        paths = []
        for name, body in (("ours", ours), ("base", base), ("theirs", theirs)):
            path = Path(tmp) / name
            path.write_text(body, encoding="utf-8", newline="")
            paths.append(str(path))
        # BYTES, decoded here: `text=True` would translate CRLF to LF on the way out and silently change every line ending of a file
        # the fork keeps as it is.
        run = subprocess.run(["git", "merge-file", "-p", "--diff3", *paths], capture_output=True)
    if run.returncode < 0 or run.returncode > 127:
        raise RuntimeError(f"git merge-file failed: {run.stderr.decode('utf-8', 'replace')}")
    return run.stdout.decode("utf-8", errors="surrogateescape"), run.returncode


def merge_into(dest: Path, base: str, theirs: str, *, write: bool = True) -> int:
    """Three-way merge `theirs` into the fork's file `dest`, keeping the file's own line endings. Returns the conflict-hunk count.

    The fork's working copy is CRLF on Windows and this repository's text comes from git as LF, so `ours` is normalised to LF for the
    merge (otherwise every line differs and the merge is one giant conflict) and written back in the style it was read in.
    """
    ours_raw = dest.read_bytes().decode("utf-8", errors="surrogateescape")
    crlf = "\r\n" in ours_raw
    text, conflicts = merge_file(ours_raw.replace("\r\n", "\n"), base, theirs)
    if write:
        out = text.replace("\n", "\r\n") if crlf else text
        dest.write_bytes(out.encode("utf-8", errors="surrogateescape"))
    return conflicts


def changed_files(base: str, head: str) -> list[str]:
    out = _git(["diff", "--name-only", f"{base}..{head}", "--", *TRACKED_ROOTS]).stdout
    return sorted(set(out.split()))


def numstat(repo_or_fork: Path, base: str, head: str, paths: list[str]) -> tuple[int, int]:
    """Total added and removed lines over `paths` between two commits, in a checkout that has both."""
    out = _git(["diff", "--numstat", f"{base}..{head}", "--", *paths], cwd=repo_or_fork).stdout
    added = removed = 0
    for line in out.splitlines():
        a, r, _name = line.split("\t", 2)
        if a.isdigit() and r.isdigit():
            added += int(a)
            removed += int(r)
    return added, removed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fork", type=Path, required=True, help="a checkout of the fork (its own repository)")
    parser.add_argument("--base", required=True, help="the commit of THIS repository whose src the fork already holds")
    parser.add_argument("--head", required=True, help="the commit or branch to port")
    parser.add_argument("--dry-run", action="store_true", help="classify and print; write nothing")
    args = parser.parse_args()

    merged, conflicted, added, skipped, app_reading = [], [], [], [], []
    for rel in changed_files(args.base, args.head):
        theirs_raw = show(args.head, rel)
        if theirs_raw is None:  # deleted at HEAD: not ported (the fork's copy is removed by hand, and named in the commit)
            skipped.append(f"{rel} (deleted at {args.head})")
            continue
        if rel.startswith("tests/test_") and classify_test(theirs_raw) == "app-reading":
            app_reading.append(rel)
            continue
        dest_rel = fork_path(rel, theirs_raw)
        if dest_rel is None:
            skipped.append(rel)
            continue
        theirs = rewrite(theirs_raw)
        base_raw = show(args.base, rel)
        dest = args.fork / dest_rel
        if base_raw is None or not dest.exists():
            added.append(dest_rel)
            if not args.dry_run:
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(theirs.encode("utf-8", errors="surrogateescape"))  # LF: the fork's own git normalises on commit
            continue
        conflicts = merge_into(dest, rewrite(base_raw), theirs, write=not args.dry_run)
        (conflicted if conflicts else merged).append(f"{dest_rel} ({conflicts} conflict hunks)" if conflicts else dest_rel)

    print(f"merged clean: {len(merged)}")
    print(f"added new:    {len(added)}")
    for a in added:
        print("   +", a)
    print(f"skipped (written there, not copied, or not ported): {len(skipped)}")
    for s in skipped:
        print("   -", s)
    print(f"APP-READING tests NOT ported (hand-write a fork variant if the fork needs one): {len(app_reading)}")
    for s in app_reading:
        print("   ~", s)
    if conflicted:
        print(f"CONFLICTS: {len(conflicted)}")
        for c in conflicted:
            print("   !", c)
    if not args.dry_run:
        engine = ["src/openchem/vendor/iupac_namer", "src/openchem/vendor/data"]
        repo_stat = numstat(REPO, args.base, args.head, engine)
        print(f"audit: repository engine+data numstat {repo_stat[0]:+d}/{-repo_stat[1]:d}; "
              "compare with `git diff --numstat` in the fork over iupac_namer/ and data/ after committing")
    return 1 if conflicted else 0


if __name__ == "__main__":
    sys.exit(main())
