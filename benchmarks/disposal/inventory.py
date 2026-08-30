"""Inventory every hand-written Qt disposal sequence under `tests/`.

## WHY THIS EXISTS AT ALL

`setParent(None)` + `deleteLater()` + a per-object `DeferredDelete` flush
is copy-pasted across dozens of test files under at least six different
names. Consolidating it into one helper is right -- this project has paid
four times for two implementations of one idea drifting -- but a
consolidation is only safe if the "before" is known, and **a green suite
is not that evidence**. The crash this work is about is roughly 50/50 on a
byte-identical tree, so the suite cannot detect a change in it either way.

So the sequences are inventoried MECHANICALLY, grouped by exactly what
each site does today, and committed. The consolidation then has to
preserve every group or name every deviation.

## WHAT A "SEQUENCE" IS HERE

A contiguous run of expression statements, inside one block, that all act
on the same object, and that contains a `sendPostedEvents(..., DeferredDelete)`.
The object is taken from the call itself:

    widget.setParent(None)                     subject = "widget"
    QCoreApplication.sendPostedEvents(widget,  subject = "widget"  (first ARG)
                                      DeferredDelete)

Grouping on the subject is what makes a site whose flush names a
DIFFERENT object than the rest of its run visible rather than absorbed --
that is a real deviation and the inventory must show it, not smooth it.

## AN IMPORT IS TRANSPARENT, AND THE FIRST VERSION OF THIS SCRIPT WAS WRONG

`tests/test_isotopes.py:815` writes a local `from PySide6.QtCore import
QCoreApplication, QEvent` BETWEEN the `deleteLater()` and the flush. A
strict contiguity rule breaks the run there and reports a bare
`sendPostedEvents(...)` with nothing before it -- which reads as a real
deviation and is an artefact of this walker. Measured: that is the only
site where it happens, and it is the canonical three-line recipe.

So `Import`/`ImportFrom` are stepped over, because a binding cannot touch
a Qt object's lifetime. **Nothing else is**, deliberately -- an assignment
or a call on another object between the steps IS a difference worth
seeing, and smoothing those would be the failure this whole inventory
exists to prevent. Sites that were reached this way carry `via import`.

Run `--check` to fail when the committed markdown no longer matches the
tree, in the shape `tools/build_sources_doc.py` already uses.
"""

from __future__ import annotations

import argparse
import ast
import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TESTS = ROOT / "tests"
INVENTORY_MD = Path(__file__).with_name("inventory.md")
INVENTORY_JSON = Path(__file__).with_name("inventory.json")

#: The flush this whole investigation is about. A `sendPostedEvents` whose
#: second argument is anything else is a different operation and is not
#: part of this population.
FLUSH = "sendPostedEvents"
#: The event type that makes it a DISPOSAL rather than any other
#: forced delivery. A flush of some other event is a different
#: operation and is deliberately not in this population.
DEFERRED = "DeferredDelete"


def _called_attr(node: ast.stmt) -> ast.Call | None:
    """The `x.y(...)` call this statement IS, or None."""
    if not isinstance(node, ast.Expr):
        return None
    call = node.value
    if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute):
        return call
    return None


def _is_deferred_flush(call: ast.Call) -> bool:
    if call.func.attr != FLUSH:  # type: ignore[union-attr]
        return False
    return any(DEFERRED in ast.unparse(arg) for arg in call.args)


def _subject(call: ast.Call) -> str:
    """Which object this call acts on.

    For the flush that is its FIRST ARGUMENT, not its receiver: the
    receiver is always `QCoreApplication`/`QApplication` and carries no
    information about which widget is being disposed.
    """
    if call.func.attr == FLUSH:  # type: ignore[union-attr]
        return ast.unparse(call.args[0]) if call.args else "<no argument>"
    return ast.unparse(call.func.value)  # type: ignore[union-attr]


def _step(call: ast.Call) -> str:
    """A normalised one-line spelling of the call, subject stripped."""
    name = call.func.attr  # type: ignore[union-attr]
    if name == FLUSH:
        rest = ", ".join(ast.unparse(a) for a in call.args[1:])
        return f"{FLUSH}(<subject>, {rest})"
    args = ", ".join(ast.unparse(a) for a in call.args)
    return f"{name}({args})"


def _blocks(tree: ast.AST):
    """Every statement list in the module."""
    for node in ast.walk(tree):
        for field in ("body", "orelse", "finalbody"):
            block = getattr(node, field, None)
            if isinstance(block, list) and block and isinstance(block[0], ast.stmt):
                yield block


def sequences_in(path: Path) -> list[dict]:
    """Every disposal sequence in one file."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: list[dict] = []
    for block in _blocks(tree):
        # Split the block into runs of consecutive attribute-calls that
        # share a subject. A run is a candidate disposal sequence.
        run: list[ast.Call] = []
        subject: str | None = None
        stepped_over = False
        pending_import = False
        for statement in list(block) + [None]:  # sentinel flushes the last run
            # An import cannot touch a Qt object's lifetime, so it does not
            # break a run. See the module docstring: exactly one site needs
            # this, and without it that site reports as a false deviation.
            if run and isinstance(statement, (ast.Import, ast.ImportFrom)):
                pending_import = True
                continue
            call = _called_attr(statement) if statement is not None else None
            here = _subject(call) if call is not None else None
            if call is not None and (subject is None or here == subject):
                subject = here
                run.append(call)
                # Only NOW is the import genuinely BETWEEN two steps. An
                # import trailing a finished sequence is not, and flagging
                # it would make the marker mean "an import is nearby" --
                # which is how a diagnostic gets quoted for something it
                # does not say.
                stepped_over = stepped_over or pending_import
                pending_import = False
                continue
            if any(_is_deferred_flush(c) for c in run):
                found.append(
                    {
                        "file": str(path.relative_to(ROOT)).replace("\\", "/"),
                        "line": run[0].lineno,
                        "subject": subject,
                        "steps": [_step(c) for c in run],
                        "via_import": stepped_over,
                    }
                )
            run = [call] if call is not None else []
            subject = here
            stepped_over = False
            pending_import = False
    return found


def collect() -> list[dict]:
    out: list[dict] = []
    for path in sorted(TESTS.rglob("*.py")):
        out.extend(sequences_in(path))
    return out


def render(sequences: list[dict]) -> str:
    groups: dict[tuple[str, ...], list[dict]] = collections.defaultdict(list)
    for sequence in sequences:
        groups[tuple(sequence["steps"])].append(sequence)

    files = sorted({s["file"] for s in sequences})
    lines = [
        "# The disposal sequences, as they were BEFORE consolidation",
        "",
        "Generated by `benchmarks/disposal/inventory.py`. Do not hand-edit;",
        "run the script.",
        "",
        "**This is the evidence the consolidation is behaviour-preserving.**",
        "A green suite is not: the crash this work is about is roughly 50/50",
        "on a byte-identical tree, so the suite cannot detect a change in it",
        "in either direction. Every group below must survive the refactor or",
        "be named as a deviation.",
        "",
        f"- sequences: **{len(sequences)}**",
        f"- distinct sequences: **{len(groups)}**",
        f"- files: **{len(files)}**",
        "",
    ]
    for steps, members in sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        lines.append(f"## {len(members)}x  " + "  ->  ".join(steps))
        lines.append("")
        for member in sorted(members, key=lambda m: (m["file"], m["line"])):
            via = "  -- via import" if member["via_import"] else ""
            lines.append(
                f"- `{member['file']}:{member['line']}` (`{member['subject']}`){via}"
            )
        lines.append("")
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail if the committed inventory no longer matches the tree",
    )
    args = parser.parse_args(argv[1:])

    sequences = collect()
    markdown = render(sequences)
    payload = json.dumps(sequences, indent=1) + "\n"

    if args.check:
        stale = []
        if not INVENTORY_MD.is_file() or INVENTORY_MD.read_text(encoding="utf-8") != markdown:
            stale.append(INVENTORY_MD.name)
        if not INVENTORY_JSON.is_file() or INVENTORY_JSON.read_text(encoding="utf-8") != payload:
            stale.append(INVENTORY_JSON.name)
        if stale:
            print(f"STALE: {', '.join(stale)} -- re-run benchmarks/disposal/inventory.py")
            return 1
        print(f"current: {len(sequences)} sequences across {len({s['file'] for s in sequences})} files")
        return 0

    INVENTORY_MD.write_text(markdown, encoding="utf-8")
    INVENTORY_JSON.write_text(payload, encoding="utf-8")
    print(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
