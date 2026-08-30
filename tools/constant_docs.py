"""Which module-level constants carry a `#:` doc comment, and which do not.

## THE DEFECT THIS EXISTS FOR

A `#:` block documents the statement that FOLLOWS it. Insert a new constant
between a block and the constant it was written for, and the comment silently
becomes documentation of something else -- while the constant it belonged to
is left with none. That happened in `chem/energetics.py`:

    #: ... "CHNO explosives run roughly -200 to +200 kcal/mol, so this is
    #: outside anything real by a wide margin."
    NEW_TOLERANCE = 1e-3          <- took the comment
    ENTHALPY_NOT_SUPPLIED = -1000.0   <- the comment was about THIS, and it
                                         was left with no documentation at all

CLAUDE.md recorded that as "Nothing catches that; it needs a reader". **That
was wrong, and it was repeated into a plan before anyone measured it.** The
orphaned constant is a structural signal: a constant with no `#:` in a file
that uses `#:` everywhere else. Measured when this was written, 97 files use
the convention on public constants and 39 of them carry an undocumented one.

**THE PRECISE SIGNATURE IS NOT DETECTABLE AND THIS IS THE PROXY.** "A
documented constant followed by an undocumented one" is also what two ordinary
constants look like, so nothing can distinguish the orphaning from the normal
case by shape alone. What IS detectable is the constant's arrival in the
undocumented set, which is what `tests/test_constant_docs.py` ratchets against.

## IT IS A RATCHET, NOT A MIGRATION, AND THE DIFFERENCE IS DELIBERATE

`tooltip_migration_debt.json` recorded a backlog that was burned down to zero,
because every control in it genuinely owed the user an explanation. **This is
not that.** `_TOKEN = "x"` and `APP_NAME = "OpenChem Studio"` do not want a doc
comment, and a guard demanding one would be answered with `#: The app name.`
-- the degenerate string the tooltip work spent a phase refusing.

So the recorded set may only SHRINK and nobody is expected to empty it. The
invariant is that a constant does not FALL INTO it, which is exactly the
orphaning above.

## THE SCOPE, AND WHY IT IS PER FILE

Only files that already use the convention are held to it. A module that
documents no constants is making no claim and is not in the population --
without that, this becomes "every constant in the project must be documented",
a much larger rule nobody agreed to.

**PRIVATE CONSTANTS COUNT.** Excluding `_LEADING_UNDERSCORE` would halve the
recorded set and would be a rule keyed on NAMING rather than on whether
documentation is warranted -- which is how `inapplicable_calculators` rotted
into 27 wrong entries. Both populations are mixed in practice:
`METAL_COORDINATION_CUTOFF` is public and wants documentation,
`_Q_CARBON_DIOXIDE` is private and wants it just as much, while `APP_NAME` is
public and does not.
"""

from __future__ import annotations

import argparse
import ast
import sys
from dataclasses import dataclass
from pathlib import Path

#: The repository root, so recorded paths are relative and a fixture written
#: on one machine means the same thing on another. An absolute path would
#: make the debt file unreadable on CI.
ROOT = Path(__file__).resolve().parent.parent

#: The package this walks. Not configurable: a guard that could be pointed
#: somewhere else is a guard whose population is an argument.
PACKAGE = ROOT / "src" / "openchem"

#: Where the recorded set lives. Beside the other test fixtures, because it
#: is a test fixture: nothing in the application reads it.
DEBT_PATH = ROOT / "tests" / "fixtures" / "constant_doc_debt.json"

#: Directories whose contents are somebody else's code and not held to this
#: repository's conventions.
EXCLUDED_PARTS = frozenset({"vendor"})


@dataclass(frozen=True)
class Constant:
    """One module-level constant and whether it carries documentation."""

    path: str
    name: str
    line: int
    documented: bool

    @property
    def key(self) -> str:
        """`path::NAME` -- what the debt fixture records.

        The CONSTANT rather than a `file:line`, for the reason the tooltip
        debt fixture gives: a line number moves under any edit, while the
        thing being guarded survives one.
        """
        return f"{self.path}::{self.name}"


def _names(node: ast.stmt) -> list[str]:
    """Every upper-case name this statement binds at module level.

    Handles `A = 1`, `A: int = 1`, `A = B = 1` and `A, B = 1, 2` -- the last
    because `chem/decay_svg.py` really does declare `CELL_W, CELL_H` that way,
    and a walk that skipped tuples would silently shrink its own population.
    """
    if isinstance(node, ast.AnnAssign):
        targets: list[ast.expr] = [node.target]
    elif isinstance(node, ast.Assign):
        targets = list(node.targets)
    else:
        return []
    found: list[str] = []
    for target in targets:
        elements = target.elts if isinstance(target, ast.Tuple) else [target]
        for element in elements:
            if isinstance(element, ast.Name) and element.id.isupper():
                found.append(element.id)
    return found


def constants_in(path: Path, source: str | None = None) -> list[Constant]:
    """Every module-level constant in one file, with its documented state.

    **`tree.body` ONLY**, so a constant assigned inside `if TYPE_CHECKING:`
    or a `try` is not counted. Measured: this project has none, and the
    restriction keeps the walk from having to decide what a conditionally
    defined constant even means.

    Two documented forms are honoured, because Sphinx honours both: a `#:`
    block immediately above, and a bare string literal immediately below.
    Recognising only the first would report the one constant here that uses
    the second as undocumented, which is a false positive on correct code.
    """
    text = source if source is not None else path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    lines = text.splitlines()
    body = tree.body
    found: list[Constant] = []
    for index, node in enumerate(body):
        names = _names(node)
        if not names:
            continue
        index_above = node.lineno - 2
        documented = False
        while index_above >= 0 and lines[index_above].strip().startswith("#:"):
            documented = True
            index_above -= 1
        if not documented and index + 1 < len(body):
            follower = body[index + 1]
            if isinstance(follower, ast.Expr) and isinstance(follower.value, ast.Constant):
                documented = isinstance(follower.value.value, str)
        try:
            relative = path.resolve().relative_to(ROOT).as_posix()
        except ValueError:
            relative = path.as_posix()
        for name in names:
            found.append(
                Constant(
                    path=relative,
                    name=name,
                    line=node.lineno,
                    documented=documented,
                )
            )
    return found


def uses_the_convention(constants: list[Constant]) -> bool:
    """Whether this file documents any constant, and so is in the population.

    A module that documents none is making no claim. Holding it to the
    convention anyway would turn this into a project-wide style rule.
    """
    return any(c.documented for c in constants)


def walk(package: Path = PACKAGE) -> list[Constant]:
    """Every constant in every file that uses the convention."""
    found: list[Constant] = []
    for path in sorted(package.rglob("*.py")):
        if EXCLUDED_PARTS & set(path.parts):
            continue
        constants = constants_in(path)
        if uses_the_convention(constants):
            found.extend(constants)
    return found


def undocumented(package: Path = PACKAGE) -> list[Constant]:
    """The recorded set: constants with no documentation, in files that use it."""
    return [c for c in walk(package) if not c.documented]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--missing",
        action="store_true",
        help="list constants with no doc comment, in files that use the convention",
    )
    parser.add_argument("--count", action="store_true", help="print totals only")
    parser.add_argument(
        "--record",
        action="store_true",
        help="rewrite the debt fixture from the tree as it stands (it may only shrink)",
    )
    args = parser.parse_args(argv)

    every = walk()
    missing = [c for c in every if not c.documented]
    files = {c.path for c in every}
    if args.record:
        import json

        DEBT_PATH.write_text(
            json.dumps(
                {
                    "_note": (
                        "Module-level constants with no `#:` doc comment, in files "
                        "that use the convention. THIS SET MAY ONLY SHRINK -- it is a "
                        "ratchet against a doc comment being orphaned from its "
                        "constant, not a backlog anybody is expected to empty. "
                        "Regenerate with: python tools/constant_docs.py --record"
                    ),
                    "constants": sorted(c.key for c in missing),
                },
                indent=1,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"recorded {len(missing)} constants to {DEBT_PATH.relative_to(ROOT).as_posix()}")
        return 0
    if args.count or not args.missing:
        print(
            f"{len(files)} files use the convention, {len(every)} constants, "
            f"{len(missing)} undocumented"
        )
    if args.missing:
        if not missing:
            print("Nothing matched.")
        for constant in missing:
            print(f"{constant.path}:{constant.line}  {constant.name}")
    return 0


if __name__ == "__main__":  # pragma: no cover - the CLI entry point
    raise SystemExit(main())
