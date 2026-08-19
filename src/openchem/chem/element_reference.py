"""One element's worth of facts, assembled from the three places they live.

Nothing is duplicated. RDKit's own periodic table already carries the name,
the atomic weight, both radii, the outer-electron count, the valence list,
the period, and -- the useful surprise -- the full natural-abundance
isotope table. `electronegativity.json` already carries Pauling values with
their source. `elements.json` carries only what neither of those has.

That split is why this module exists: a dialog should ask one question and
get one answer, not know which of three files to look in.

Where a fact is genuinely unknown, the field is None and the caller says so
in words. The superheavy elements are the honest case -- oganesson has been
made a handful of atoms at a time, and its "common oxidation states" are
not a thing anybody has measured.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

_DATA_PATH = Path(__file__).resolve().parent / "data" / "elements.json"


@dataclass(frozen=True)
class Isotope:
    mass_number: int
    mass: float
    abundance: float  # percent of natural occurrence


@dataclass(frozen=True)
class ElementFacts:
    symbol: str
    atomic_number: int
    name: str
    period: int
    #: None for the lanthanides and actinides, which are drawn as their own
    #: rows below the table and so occupy no column in the main grid.
    group: int | None
    block: str
    category: str
    electron_configuration: str
    atomic_weight: float
    outer_electrons: int
    #: None where RDKit reports no defined valence -- every transition
    #: metal, which is a real statement rather than missing data, and the
    #: same fact the valence checker declines to do arithmetic on.
    valences: tuple[int, ...] | None
    van_der_waals_radius: float | None
    covalent_radius: float | None
    electronegativity: float | None
    #: Degrees Celsius, or None where nothing is measured -- fifteen
    #: superheavies, and francium, whose longest-lived isotope lasts 22
    #: minutes. None is "not established", never "zero".
    melting_point_c: float | None = None
    boiling_point_c: float | None = None
    #: **STATED BY THE SOURCE, not inferred from a missing boiling point.**
    #: Arsenic and carbon. A missing point means unknown, and conflating
    #: the two would put every superheavy in this class.
    sublimes_at_1_bar: bool = False
    #: Empty when not well established, which is different from "zero".
    common_oxidation_states: tuple[int, ...] = ()
    isotopes: tuple[Isotope, ...] = ()
    examples: tuple[str, ...] = field(default_factory=tuple)

    @property
    def has_established_oxidation_states(self) -> bool:
        return bool(self.common_oxidation_states)


@lru_cache(maxsize=1)
def _reference_data() -> dict[str, dict[str, Any]]:
    return json.loads(_DATA_PATH.read_text(encoding="utf-8"))["elements"]


@lru_cache(maxsize=1)
def _electronegativities() -> dict[str, float]:
    from openchem.chem.oxidation_states import electronegativity_table

    return {symbol: entry["pauling"] for symbol, entry in electronegativity_table().items()}


@lru_cache(maxsize=128)
def facts_for(symbol: str) -> ElementFacts | None:
    """Everything known about one element, or None if it is not an element."""
    entry = _reference_data().get(symbol)
    if entry is None:
        return None

    from rdkit import Chem

    table = Chem.GetPeriodicTable()
    z = entry["atomic_number"]

    valences = tuple(table.GetValenceList(z))
    return ElementFacts(
        symbol=symbol,
        atomic_number=z,
        name=table.GetElementName(z),
        period=entry["period"],
        group=entry["group"],
        block=entry["block"],
        category=entry["category"],
        electron_configuration=entry["electron_configuration"],
        atomic_weight=table.GetAtomicWeight(z),
        outer_electrons=table.GetNOuterElecs(z),
        valences=None if valences == (-1,) else valences,
        van_der_waals_radius=table.GetRvdw(z) or None,
        covalent_radius=table.GetRcovalent(z) or None,
        electronegativity=_electronegativities().get(symbol),
        melting_point_c=entry.get("melting_point_c"),
        boiling_point_c=entry.get("boiling_point_c"),
        sublimes_at_1_bar=bool(entry.get("sublimes_at_1_bar", False)),
        common_oxidation_states=tuple(entry.get("common_oxidation_states", ())),
        isotopes=_isotopes_for(z),
        examples=tuple(entry.get("examples", ())),
    )


def _isotopes_for(z: int) -> tuple[Isotope, ...]:
    """The naturally occurring isotopes, from RDKit's own abundance table.

    Scanned rather than looked up because RDKit exposes abundance per
    (element, mass number) with no way to enumerate. The range is bounded
    generously and only non-zero abundances are kept, so a synthetic
    element correctly yields nothing at all.
    """
    from rdkit import Chem

    table = Chem.GetPeriodicTable()
    found = []
    for mass_number in range(max(1, z), 4 * z + 30):
        try:
            abundance = table.GetAbundanceForIsotope(z, mass_number)
        except Exception:
            continue
        if abundance and abundance > 0:
            found.append(Isotope(mass_number, table.GetMassForIsotope(z, mass_number), abundance))
    return tuple(found)


@lru_cache(maxsize=1)
def all_symbols() -> tuple[str, ...]:
    """Every element, by atomic number."""
    return tuple(
        symbol
        for symbol, _ in sorted(_reference_data().items(), key=lambda kv: kv[1]["atomic_number"])
    )


def grid_position(symbol: str) -> tuple[int, int] | None:
    """(row, column) in the 18-column layout, or None for the f-block.

    The f-block is placed by the caller, in its own two rows below the
    table, because those rows are a drawing convention rather than a
    property of the elements.
    """
    entry = _reference_data().get(symbol)
    if entry is None or entry["group"] is None:
        return None
    return entry["period"], entry["group"]


def f_block_series() -> tuple[tuple[str, ...], tuple[str, ...]]:
    """The lanthanides and the actinides, in order."""
    data = _reference_data()
    lanthanides = tuple(
        s for s in all_symbols() if data[s]["category"] == "lanthanide"
    )
    actinides = tuple(s for s in all_symbols() if data[s]["category"] == "actinide")
    return lanthanides, actinides
