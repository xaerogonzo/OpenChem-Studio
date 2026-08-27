"""Resolve a CIF's space-group symbol to the operations it stands for.

A CIF is allowed to name its space group and supply no
`_symmetry_equiv_pos_as_xyz` loop. `chem/cif.py` used to answer that with
the IDENTITY, so the cell was never expanded and every derived quantity --
atoms per cell, composition, density, volume per formula unit, every
coordination shell, the lattice energy -- came out confidently wrong about
a structure that had not been built.

This module is the lookup that lets it be expanded instead, and the
REFUSAL for when it cannot be.

## A symbol does not always determine the operations

    distinct base symbols (setting suffix dropped)   569
    ...ambiguous, i.e. matching more than one          46
        differing in the OPERATION COUNT                7
        differing only by origin choice                39

The seven are the rhombohedral groups, and they are the dangerous ones:

    R -3 c:H    36 operations   hexagonal axes, R-centred
    R -3 c:R    12 operations   rhombohedral axes, primitive

A factor of three in how many atoms the cell holds. Guessing would give a
plausible structure and the wrong one.

## The CELL resolves the rhombohedral seven, and it is a derivation

Those two settings describe the same crystal in different axis systems, so
the axes themselves say which is meant -- read off the table rather than
assumed: the `:H` blocks carry the (2/3,1/3,1/3) and (1/3,2/3,2/3)
centring translations, the `:R` blocks are primitive with cyclic `z,x,y`
operations.

    hexagonal axes       a == b,  alpha == beta == 90,  gamma == 120
    rhombohedral axes    a == b == c,  alpha == beta == gamma

## The other 39 are REFUSED, because no cell can tell them apart

Origin choice 1 against origin choice 2 is the same lattice with the
origin moved, so the cell is identical and only the coordinates differ.
There is nothing to derive from, and picking one would put every atom in
the wrong place while the cell, the formula and the density all still
looked right. `I 41/a m d` is the common case.

**A REFUSAL IS THE ANSWER, NOT A GAP.** Anything that resolves here goes
on to expand a real structure; anything that does not gets reported as
unexpanded, which is what `crystal_report` says out loud.

## Never fuzzy-match

`difflib` on a symbol is how `P 21/c` quietly becomes `P 21/n`. This
project already killed exactly that for solvent names, where it paired
"1,2-dichloroethane" with "dichloromethane" at equal confidence. Matching
is exact after whitespace and case are normalised, and an unknown symbol
fails closed.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from pathlib import Path

from openchem.domain.crystal import Lattice, SymmetryOperation, parse_symmetry_operation

_TABLE = Path(__file__).resolve().parent / "data" / "space_groups.json"

#: How close two cell lengths or angles must be to count as equal. A CIF
#: prints refined values, so a hexagonal cell is `gamma = 120.0` or
#: `119.997` and never exactly 120 -- and the two axis systems this has to
#: tell apart are nowhere near each other, so nothing turns on the exact
#: figure. It is deliberately loose.
ANGLE_TOLERANCE = 0.5
LENGTH_TOLERANCE = 1e-3


class Unresolved(Enum):
    """Why a symbol did not become a set of operations."""

    UNKNOWN_SYMBOL = "unknown_symbol"
    AMBIGUOUS_SETTING = "ambiguous_setting"


@dataclass(frozen=True)
class SpaceGroupSetting:
    """One row of the table: a setting, not merely a space group.

    `it` alone does not identify the operations -- 13 IT numbers carry
    settings whose operation counts differ -- which is why the Hall symbol
    is here. It is the notation that exists precisely to pin the setting
    and origin, and it is the disambiguating identity if the underlying
    table is ever swapped for another source.
    """

    it: int
    hall: str
    hm: tuple[str, ...]
    operations: tuple[str, ...]

    def symmetry_operations(self) -> tuple[SymmetryOperation, ...]:
        """Through `domain.crystal`'s own parser, never a second one."""
        return tuple(parse_symmetry_operation(text) for text in self.operations)


def normalise(symbol: str) -> str:
    """Whitespace and case removed; everything else kept.

    `P 21/c`, `P21/c` and `p 2 1 / c` are the same symbol. `P 21/c` and
    `P 21/n` are NOT, and nothing here should ever be tempted to think so.
    """
    return re.sub(r"[\s_]", "", symbol or "").lower()


@lru_cache(maxsize=1)
def _index() -> tuple[dict[str, SpaceGroupSetting], dict[str, tuple[SpaceGroupSetting, ...]]]:
    """`(exact alias -> setting, base symbol -> every setting under it)`."""
    payload = json.loads(_TABLE.read_text(encoding="utf-8"))
    exact: dict[str, SpaceGroupSetting] = {}
    base: dict[str, list[SpaceGroupSetting]] = {}
    for row in payload["groups"]:
        setting = SpaceGroupSetting(
            it=row["it"],
            hall=row["hall"],
            hm=tuple(row["hm"]),
            operations=tuple(row["operations"]),
        )
        for alias in row["hm"]:
            exact[normalise(alias)] = setting
            base.setdefault(normalise(alias.split(":")[0]), []).append(setting)
    return exact, {key: tuple(value) for key, value in base.items()}


def _has_hexagonal_axes(lattice: Lattice) -> bool:
    return (
        abs(lattice.a - lattice.b) < LENGTH_TOLERANCE
        and abs(lattice.alpha - 90.0) < ANGLE_TOLERANCE
        and abs(lattice.beta - 90.0) < ANGLE_TOLERANCE
        and abs(lattice.gamma - 120.0) < ANGLE_TOLERANCE
    )


def _has_rhombohedral_axes(lattice: Lattice) -> bool:
    return (
        abs(lattice.a - lattice.b) < LENGTH_TOLERANCE
        and abs(lattice.b - lattice.c) < LENGTH_TOLERANCE
        and abs(lattice.alpha - lattice.beta) < ANGLE_TOLERANCE
        and abs(lattice.beta - lattice.gamma) < ANGLE_TOLERANCE
        and abs(lattice.alpha - 90.0) >= ANGLE_TOLERANCE
    )


def _by_axes(candidates: tuple[SpaceGroupSetting, ...], lattice: Lattice | None):
    """Pick between `:H` and `:R` using the cell. None when it cannot."""
    if lattice is None:
        return None
    suffixed = {
        alias.split(":")[1].upper(): setting
        for setting in candidates
        for alias in setting.hm
        if ":" in alias
    }
    if set(suffixed) != {"H", "R"}:
        # Not the rhombohedral pair -- an origin choice, which no cell can
        # resolve because the lattice is identical either way.
        return None
    if _has_hexagonal_axes(lattice):
        return suffixed["H"]
    if _has_rhombohedral_axes(lattice):
        return suffixed["R"]
    return None


def resolve(symbol: str, lattice: Lattice | None = None) -> SpaceGroupSetting | Unresolved:
    """The setting a symbol names, or why it does not name one.

    Returning a REASON rather than None is the same call
    `IsotopeRefusal` and `BcsReason` already make here: "I have never
    heard of this symbol" and "this symbol means two different things"
    send a reader to different places, and collapsing them into a bare
    None loses the only useful half of the answer.
    """
    key = normalise(symbol)
    if not key:
        return Unresolved.UNKNOWN_SYMBOL

    exact, base = _index()
    if key in exact:
        return exact[key]

    candidates = base.get(key)
    if not candidates:
        return Unresolved.UNKNOWN_SYMBOL
    if len(candidates) == 1:
        return candidates[0]

    chosen = _by_axes(candidates, lattice)
    return chosen if chosen is not None else Unresolved.AMBIGUOUS_SETTING


def describe(reason: Unresolved, symbol: str) -> str:
    """One sentence, generated in one place."""
    if reason is Unresolved.AMBIGUOUS_SETTING:
        return (
            f"the space group {symbol!r} names more than one setting and the cell "
            f"does not say which. Origin choice 1 and 2 share a lattice, so nothing "
            f"here can tell them apart; give the file a "
            f"`_symmetry_equiv_pos_as_xyz` loop, or name the setting "
            f"(for example 'I 41/a m d:2')."
        )
    return (
        f"the space group {symbol!r} is not one this table knows. It carries 230 "
        f"space groups in 541 settings; a symbol outside that is refused rather "
        f"than guessed at."
    )
