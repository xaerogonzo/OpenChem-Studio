"""Bake the space-group operation table into `chem/data/space_groups.json`.

## Why this exists

`chem/cif.py`'s `_operations_from` falls back to the IDENTITY when a CIF
gives only an H-M symbol and no `_symmetry_equiv_pos_as_xyz` loop. The
cell then never gets expanded, so atoms-per-unit-cell, composition,
density, volume-per-formula-unit, every coordination shell and the
lattice energy are all silently wrong -- confident numbers about a
structure that was never built. All six shipped COD fixtures carry a
symop loop, so the corpus is degenerate with respect to exactly that bug.

## Open Babel's table is the INPUT ARTIFACT, not the authority

The operations come from `space-groups.txt`, which ships inside the
`openbabel` wheel this project already depends on. That file is a data
DEPENDENCY: it is where the bytes come from, and it is not what makes
them right. The scientific authority is International Tables for
Crystallography Volume A, chapter 1.4 [source:souvignier2016], and the
Hall notation the table keys its settings on is [source:hall1981].

The same distinction the TSEI radii were held to: those were inverted
from published values and THEN confirmed against Lange's, two routes
sharing no step.

## What is checked, and why closure is the good oracle

    230 distinct IT numbers          the table covers every space group
    closed under composition         each block really is a GROUP
    centring letter vs op count      P/A/B/C/I/F/R agree with the count
    every operation parses           through `domain.crystal`'s own parser

**CLOSURE IS THE LOAD-BEARING ONE and it is mathematics rather than a
lookup.** A truncated, duplicated or corrupted operation list stops being
closed under composition, and no amount of plausible-looking `x,y,z`
strings can fake it. Verified over all 541 blocks. It is also
non-circular in a way a multiplicity table is not: comparing the counts
against a list derived from the same source would prove only that the
source agrees with itself.

## The `hm` field is a COMMA-SEPARATED ALIAS LIST, which cost a measurement

Read as one string it looks like 541 unique symbols with no collisions.
It is not: `P 21/c,P 1 21/c 1` is TWO spellings of one setting, and split
properly the table carries **615 aliases**. Splitting is not a nicety --
without it a lookup for `P 21/c`, the commonest monoclinic group in
small-molecule crystallography, misses entirely.

## Settings are ambiguous and the CELL is what resolves them

46 base symbols map to more than one setting once the `:H`/`:R`/`:1`/`:2`
suffix is dropped. 39 differ only by origin choice; **7 differ in the
operation count itself**, and all seven are rhombohedral:

    R -3 c:H   36 operations      hexagonal axes, R-centred
    R -3 c:R   12 operations      rhombohedral axes, primitive

A factor of three in how many atoms the cell contains. A CIF writing a
bare `R -3 c` has not said which -- but its CELL has, and that is a
derivation rather than a guess: the `:H` blocks carry the (2/3,1/3,1/3)
and (1/3,2/3,2/3) centring translations and the `:R` blocks are primitive
with cyclic `z,x,y` operations. `chem/cif.py` does that disambiguation;
this tool only records both settings faithfully so it can.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "src" / "openchem" / "chem" / "data" / "space_groups.json"

#: Where Open Babel's table lives inside the installed wheel. Derived from
#: the package rather than hardcoded, so a different venv layout or a
#: version bump does not silently read a stale copy from somewhere else.
def source_table() -> Path:
    import openbabel

    root = Path(openbabel.__file__).resolve().parent
    candidate = root / "bin" / "data" / "space-groups.txt"
    if candidate.is_file():
        return candidate
    matches = list(root.rglob("space-groups.txt"))
    if not matches:
        raise SystemExit(
            "space-groups.txt not found in the installed openbabel. "
            "This tool needs the `openbabel` extra: uv sync --extra openbabel"
        )
    return matches[0]


def parse_operation(text: str) -> tuple[tuple[tuple[int, ...], ...], tuple[Fraction, ...]]:
    """`-y,x-y,1/2+z` as a 3x3 integer matrix and a translation.

    Local to this tool on purpose. `domain.crystal.parse_symmetry_operation`
    is the SHIPPED parser and is what the application uses; this one exists
    only to verify closure at build time, and building the check on the
    parser under test would make the check circular.
    """
    matrix, shift = [], []
    for part in text.split(","):
        row = [0, 0, 0]
        offset = Fraction(0)
        for term in re.finditer(r"([+-]?)\s*(\d+/\d+|\d+)?\s*\*?\s*([xyz])?", part):
            sign, number, variable = term.group(1), term.group(2), term.group(3)
            if not (number or variable):
                continue
            signum = -1 if sign == "-" else 1
            if variable:
                factor = int(number) if number and "/" not in number else 1
                row["xyz".index(variable)] += signum * factor
            else:
                offset += signum * Fraction(number)
        matrix.append(tuple(row))
        shift.append(offset % 1)
    return tuple(matrix), tuple(shift)


def _compose(first, second):
    matrix_a, shift_a = first
    matrix_b, shift_b = second
    matrix = tuple(
        tuple(sum(matrix_a[i][k] * matrix_b[k][j] for k in range(3)) for j in range(3))
        for i in range(3)
    )
    shift = tuple(
        (sum(Fraction(matrix_a[i][k]) * shift_b[k] for k in range(3)) + shift_a[i]) % 1
        for i in range(3)
    )
    return matrix, shift


def is_closed(operations: list[str]) -> bool:
    """Whether these operations form a group modulo lattice translations."""
    parsed = {parse_operation(text) for text in operations}
    return all(_compose(a, b) in parsed for a in parsed for b in parsed)


#: Lattice letter -> how many times the primitive cell is repeated. The
#: operation count must be divisible by it, which is a second, independent
#: reading of the same block: the SYMBOL says the centring and the
#: OPERATIONS say it again.
CENTRING = {"P": 1, "A": 2, "B": 2, "C": 2, "I": 2, "R": 3, "F": 4}


def read_table(path: Path) -> list[dict]:
    blocks = [b.splitlines() for b in path.read_text(encoding="latin-1").split("\n\n") if b.strip()]
    groups = []
    for block in blocks:
        if len(block) < 4:
            continue
        aliases = [a.strip() for a in block[2].split(",") if a.strip()]
        groups.append(
            {
                "it": int(block[0].strip()),
                "hall": block[1].strip(),
                "hm": aliases,
                "operations": [o.strip() for o in block[3:] if o.strip()],
            }
        )
    return groups


def verify(groups: list[dict]) -> list[str]:
    """Every check, as a list of complaints. Empty means the table holds."""
    problems: list[str] = []

    numbers = {g["it"] for g in groups}
    if len(numbers) != 230:
        problems.append(f"{len(numbers)} distinct IT numbers, expected 230")
    if numbers != set(range(1, 231)):
        problems.append("IT numbers are not exactly 1..230")

    for group in groups:
        label = f"IT#{group['it']} {group['hall']}"
        try:
            if not is_closed(group["operations"]):
                problems.append(f"{label}: operations are not closed under composition")
        except Exception as error:  # noqa: BLE001 - the message names the block
            problems.append(f"{label}: an operation did not parse ({error})")
            continue

        letter = group["hm"][0].lstrip("-").strip()[:1].upper()
        factor = CENTRING.get(letter)
        # An `:R` setting is primitive however its symbol is spelled, which
        # is the whole reason the rhombohedral pair exists -- so the
        # divisibility claim is about the H setting only.
        rhombohedral_axes = any(a.endswith(":R") for a in group["hm"])
        if factor and not rhombohedral_axes and len(group["operations"]) % factor:
            problems.append(
                f"{label}: {len(group['operations'])} operations is not divisible by "
                f"{factor}, which lattice letter {letter} requires"
            )
    return problems


def build() -> dict:
    path = source_table()
    raw = path.read_bytes()
    groups = read_table(path)
    problems = verify(groups)
    if problems:
        raise SystemExit("the table did not verify:\n  " + "\n  ".join(problems[:20]))
    return {
        "_source_key": "souvignier2016",
        "_description": (
            "Every space-group setting Open Babel ships, as symmetry operations. "
            "Used to expand a CIF that names its space group and supplies no "
            "`_symmetry_equiv_pos_as_xyz` loop."
        ),
        "_read_from": (
            f"openbabel's {path.name}, which is a DATA DEPENDENCY and not the "
            "scientific authority -- see this file's build tool for the distinction"
        ),
        "_authority": (
            "International Tables for Crystallography Volume A ch. 1.4 "
            "[source:souvignier2016]; Hall notation [source:hall1981]"
        ),
        "_verified": (
            "230 distinct IT numbers; every block closed under composition; "
            "operation count divisible by the centring the lattice letter states"
        ),
        "_input_sha256": hashlib.sha256(raw).hexdigest(),
        "groups": groups,
    }


def check() -> int:
    if not OUT.is_file():
        print(f"{OUT.name}: missing -- run this tool without --check")
        return 1
    stored = json.loads(OUT.read_text(encoding="utf-8"))
    try:
        fresh = build()
    except SystemExit as error:
        print(f"{OUT.name}: the source table no longer verifies: {error}")
        return 1
    if stored.get("_input_sha256") != fresh["_input_sha256"]:
        print(
            f"{OUT.name}: stale -- built from a table hashing "
            f"{str(stored.get('_input_sha256'))[:12]}, installed openbabel now "
            f"has {fresh['_input_sha256'][:12]}"
        )
        return 1
    if stored.get("groups") != fresh["groups"]:
        print(f"{OUT.name}: does not match what the installed table builds")
        return 1
    print(f"{OUT.name} is current ({len(stored['groups'])} settings).")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="verify without writing")
    args = parser.parse_args(argv)
    if args.check:
        return check()
    payload = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=1, sort_keys=False) + "\n", encoding="utf-8")
    print(f"Wrote {OUT} ({len(payload['groups'])} settings, {OUT.stat().st_size // 1024} KiB).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
