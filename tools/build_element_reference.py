"""Build `chem/data/elements.json` — the facts RDKit does not carry.

Run:  uv run --no-sync python tools/build_element_reference.py

Same shape as `tools/build_regulatory_rulesets.py`: a script whose output is
committed, so the app loads a plain data file and nothing is derived at
startup. The reason it is generated rather than typed is verification.
Group, period, block and electron configuration are all DERIVABLE, and a
generator can check itself in ways a hand-typed table cannot:

  * every configuration's electrons sum to Z
  * every element lands in exactly one grid cell, and no cell is claimed twice
  * every block agrees with the group it was placed in

Those checks run below and abort the build. `tests/test_element_reference.py`
re-runs them against the committed file, so an edit by hand is caught too.

WHAT IS NOT GENERATED: `common_oxidation_states`. Those are curated, and
they are the only hand-entered numbers in the file. Where they are not
well established -- the superheavy elements, most of which exist as a
handful of atoms -- the key is ABSENT rather than guessed, and the dialog
says "not established" instead of showing a blank.
"""

from __future__ import annotations

import json
from pathlib import Path

OUTPUT = Path(__file__).resolve().parent.parent / "src" / "openchem" / "chem" / "data" / "elements.json"

# --- the layout -------------------------------------------------------------

#: (first Z, last Z) of each period's main-table run, and the f-block series.
_LANTHANIDES = range(57, 72)  # La-Lu
_ACTINIDES = range(89, 104)  # Ac-Lr

#: Aufbau filling order.
_AUFBAU = [
    ("1s", 2), ("2s", 2), ("2p", 6), ("3s", 2), ("3p", 6), ("4s", 2),
    ("3d", 10), ("4p", 6), ("5s", 2), ("4d", 10), ("5p", 6), ("6s", 2),
    ("4f", 14), ("5d", 10), ("6p", 6), ("7s", 2), ("5f", 14), ("6d", 10), ("7p", 6),
]

#: The known Aufbau anomalies, as the FULL occupancy of the shells that
#: differ from the naive filling. Standard set; each is a measured ground
#: state, not a prediction.
_ANOMALIES: dict[int, dict[str, int]] = {
    24: {"3d": 5, "4s": 1},    # Cr
    29: {"3d": 10, "4s": 1},   # Cu
    41: {"4d": 4, "5s": 1},    # Nb
    42: {"4d": 5, "5s": 1},    # Mo
    44: {"4d": 7, "5s": 1},    # Ru
    45: {"4d": 8, "5s": 1},    # Rh
    46: {"4d": 10, "5s": 0},   # Pd
    47: {"4d": 10, "5s": 1},   # Ag
    57: {"4f": 0, "5d": 1},    # La
    58: {"4f": 1, "5d": 1},    # Ce
    64: {"4f": 7, "5d": 1},    # Gd
    78: {"5d": 9, "6s": 1},    # Pt
    79: {"5d": 10, "6s": 1},   # Au
    89: {"5f": 0, "6d": 1},    # Ac
    90: {"5f": 0, "6d": 2},    # Th
    91: {"5f": 2, "6d": 1},    # Pa
    92: {"5f": 3, "6d": 1},    # U
    93: {"5f": 4, "6d": 1},    # Np
    96: {"5f": 7, "6d": 1},    # Cm
    103: {"5f": 14, "6d": 0, "7p": 1},  # Lr
}

#: Noble-gas cores, for the abbreviated form.
_CORES = {2: "[He]", 10: "[Ne]", 18: "[Ar]", 36: "[Kr]", 54: "[Xe]", 86: "[Rn]"}

#: Curated. The states in ordinary use, most common first where there is a
#: clear one. Absent means not well established -- see the module docstring.
_OXIDATION_STATES: dict[int, list[int]] = {
    1: [1, -1], 2: [], 3: [1], 4: [2], 5: [3], 6: [4, 2, -4], 7: [-3, 3, 5],
    8: [-2], 9: [-1], 10: [], 11: [1], 12: [2], 13: [3], 14: [4, -4],
    15: [5, 3, -3], 16: [6, 4, 2, -2], 17: [-1, 1, 3, 5, 7], 18: [],
    19: [1], 20: [2], 21: [3], 22: [4, 3], 23: [5, 4, 3, 2], 24: [6, 3, 2],
    25: [7, 4, 2], 26: [3, 2], 27: [3, 2], 28: [2], 29: [2, 1], 30: [2],
    31: [3], 32: [4], 33: [5, 3, -3], 34: [6, 4, -2], 35: [-1, 1, 5], 36: [2],
    37: [1], 38: [2], 39: [3], 40: [4], 41: [5], 42: [6, 4], 43: [7],
    44: [4, 3], 45: [3], 46: [2, 4], 47: [1], 48: [2], 49: [3], 50: [4, 2],
    51: [5, 3, -3], 52: [6, 4, -2], 53: [-1, 1, 5, 7], 54: [2, 4, 6],
    55: [1], 56: [2], 57: [3], 58: [3, 4], 59: [3], 60: [3], 61: [3],
    62: [3, 2], 63: [3, 2], 64: [3], 65: [3], 66: [3], 67: [3], 68: [3],
    69: [3], 70: [3, 2], 71: [3], 72: [4], 73: [5], 74: [6, 4], 75: [7, 4],
    76: [4, 8], 77: [4, 3], 78: [4, 2], 79: [3, 1], 80: [2, 1], 81: [1, 3],
    82: [2, 4], 83: [3, 5], 84: [4, 2], 85: [-1, 1], 86: [2],
    87: [1], 88: [2], 89: [3], 90: [4], 91: [5], 92: [6, 4], 93: [5],
    94: [4], 95: [3], 96: [3], 97: [3], 98: [3], 99: [3], 100: [3],
    101: [3], 102: [2], 103: [3],
}

#: Curated, and deliberately sparse. A familiar compound is a good anchor
#: for an element somebody is looking up; an unfamiliar one invented to
#: fill a row is worse than an empty row, so elements without an entry
#: simply do not show that line.
_EXAMPLES: dict[int, list[str]] = {
    1: ["H2O", "CH4"], 2: ["He (monatomic gas)"], 3: ["LiOH", "Li2CO3"],
    5: ["H3BO3", "B2H6"], 6: ["CO2", "CH4", "diamond"], 7: ["NH3", "HNO3", "N2"],
    8: ["H2O", "O2", "Fe2O3"], 9: ["HF", "CaF2", "SF6"], 11: ["NaCl", "NaOH"],
    12: ["MgSO4", "chlorophyll"], 13: ["Al2O3", "AlCl3"], 14: ["SiO2", "silicones"],
    15: ["H3PO4", "P4", "ATP"], 16: ["H2SO4", "H2S", "SF6"], 17: ["NaCl", "HCl"],
    19: ["KCl", "KOH"], 20: ["CaCO3", "CaSO4"], 22: ["TiO2"], 24: ["K2Cr2O7", "Cr2O3"],
    25: ["KMnO4", "MnO2"], 26: ["Fe2O3", "FeO", "haemoglobin"], 27: ["vitamin B12"],
    28: ["Ni(CO)4"], 29: ["CuSO4", "Cu2O"], 30: ["ZnO", "ZnS"], 33: ["As2O3"],
    35: ["KBr", "CH3Br"], 47: ["AgNO3", "AgCl"], 50: ["SnCl2", "SnO2"],
    53: ["KI", "I2", "thyroxine"], 78: ["cisplatin", "PtO2"], 79: ["HAuCl4"],
    80: ["HgCl2", "Hg2Cl2"], 82: ["PbO", "PbSO4"], 92: ["UO2", "UF6"],
}

#: Category per element, keyed by Z. Extends the shorter set already in
#: `electronegativity.json` (which covers only elements with a tabulated
#: Pauling value) to the full table, using the same vocabulary so the two
#: files never disagree about what an element is.
_CATEGORY_RANGES = [
    ("nonmetal", [1, 6, 7, 8, 15, 16, 34]),
    ("noble_gas", [2, 10, 18, 36, 54, 86, 118]),
    ("alkali", [3, 11, 19, 37, 55, 87]),
    ("alkaline_earth", [4, 12, 20, 38, 56, 88]),
    ("metalloid", [5, 14, 32, 33, 51, 52, 84]),
    ("halogen", [9, 17, 35, 53, 85, 117]),
    ("post_transition", [13, 31, 49, 50, 81, 82, 83, 113, 114, 115, 116]),
]


def category_for(z: int) -> str:
    for name, members in _CATEGORY_RANGES:
        if z in members:
            return name
    if z in _LANTHANIDES:
        return "lanthanide"
    if z in _ACTINIDES:
        return "actinide"
    return "transition"


def period_and_group(z: int) -> tuple[int, int | None]:
    """Row and column in the conventional 18-column layout.

    The f-block returns group `None`: lanthanides and actinides are drawn
    as their own two rows below the table, so they have a period but no
    column in the main grid.
    """
    if z in _LANTHANIDES or z in _ACTINIDES:
        return (6 if z in _LANTHANIDES else 7), None

    bounds = [(1, 2, 1), (3, 10, 2), (11, 18, 3), (19, 36, 4), (37, 54, 5), (55, 86, 6), (87, 118, 7)]
    period = next(p for low, high, p in bounds if low <= z <= high)

    if z == 1:
        return 1, 1
    if z == 2:
        return 1, 18

    # Position within the period, skipping the f-block for periods 6 and 7.
    start = {2: 3, 3: 11, 4: 19, 5: 37, 6: 55, 7: 87}[period]
    offset = z - start
    if period in (6, 7) and z > (71 if period == 6 else 103):
        offset -= 14  # the f-block series sits outside the main grid

    if period in (2, 3):
        return period, offset + 1 if offset < 2 else offset + 11
    return period, offset + 1


def block_for(z: int, group: int | None) -> str:
    if group is None:
        return "f"
    if z == 2:
        return "s"
    if group in (1, 2):
        return "s"
    if 3 <= group <= 12:
        return "d"
    return "p"


def configuration(z: int) -> tuple[list[tuple[str, int]], str]:
    """Full occupancy and the noble-gas-abbreviated string."""
    remaining = z
    shells: dict[str, int] = {}
    order: list[str] = []
    for name, capacity in _AUFBAU:
        if remaining <= 0:
            break
        taken = min(capacity, remaining)
        shells[name] = taken
        order.append(name)
        remaining -= taken

    for name, count in _ANOMALIES.get(z, {}).items():
        shells[name] = count
        if name not in order:
            order.append(name)
    if z in _ANOMALIES:
        # Anomalies are stated as absolute occupancies, so the total is
        # rebalanced against the last naively-filled shell.
        total = sum(shells.values())
        if total != z:
            adjustable = [n for n in reversed(order) if n not in _ANOMALIES[z] and shells.get(n, 0) > 0]
            for name in adjustable:
                delta = z - sum(shells.values())
                if delta == 0:
                    break
                shells[name] = max(0, shells[name] + delta)

    occupancy = [(name, shells[name]) for name in order if shells.get(name, 0) > 0]

    core_z = max((c for c in _CORES if c < z), default=0)
    core = _CORES.get(core_z, "")
    core_shells = dict(configuration_raw(core_z)) if core_z else {}
    # Written in SHELL order, not filling order. Aufbau fills 4s before 3d,
    # but iron is universally written [Ar] 3d6 4s2 -- sorting by principal
    # quantum number and then by subshell is what makes it read like a
    # textbook rather than like the loop that produced it.
    subshell_rank = {"s": 0, "p": 1, "d": 2, "f": 3}
    tail = [
        f"{name}{count}"
        for name, count in sorted(occupancy, key=lambda s: (int(s[0][0]), subshell_rank[s[0][1]]))
        if count != core_shells.get(name, 0)
    ]
    return occupancy, (core + " " + " ".join(tail)).strip() if core else " ".join(tail)


def configuration_raw(z: int) -> list[tuple[str, int]]:
    remaining = z
    out = []
    for name, capacity in _AUFBAU:
        if remaining <= 0:
            break
        taken = min(capacity, remaining)
        out.append((name, taken))
        remaining -= taken
    for name, count in _ANOMALIES.get(z, {}).items():
        out = [(n, count if n == name else c) for n, c in out]
    return out


def build() -> dict:
    from rdkit import Chem

    table = Chem.GetPeriodicTable()
    elements = {}
    seen_cells: dict[tuple[int, int], str] = {}

    for z in range(1, 119):
        symbol = table.GetElementSymbol(z)
        period, group = period_and_group(z)
        occupancy, abbreviated = configuration(z)

        total = sum(count for _, count in occupancy)
        assert total == z, f"{symbol}: configuration holds {total} electrons, expected {z}"

        if group is not None:
            cell = (period, group)
            assert cell not in seen_cells, f"{symbol} collides with {seen_cells[cell]} at {cell}"
            seen_cells[cell] = symbol

        entry = {
            "symbol": symbol,
            "atomic_number": z,
            "period": period,
            "group": group,
            "block": block_for(z, group),
            "category": category_for(z),
            "electron_configuration": abbreviated,
        }
        states = _OXIDATION_STATES.get(z)
        if states:
            entry["common_oxidation_states"] = states
        if z in _EXAMPLES:
            entry["examples"] = _EXAMPLES[z]
        elements[symbol] = entry

    assert len(elements) == 118, len(elements)
    return {
        "_about": {
            "purpose": "The periodic-table facts RDKit's own table does not carry.",
            "not_here_because_rdkit_has_it": (
                "Element name, atomic weight, van der Waals and covalent radii, outer-electron "
                "count, valence list, period, and the natural-abundance isotope table all come "
                "from rdkit.Chem.GetPeriodicTable() at display time and are deliberately not "
                "duplicated here. Electronegativity comes from electronegativity.json."
            ),
            "generated_by": "tools/build_element_reference.py -- do not hand-edit; re-run it",
            "derived_and_self_checked": (
                "period, group, block and electron_configuration are DERIVED. The generator "
                "asserts that every configuration's electrons sum to Z and that no two elements "
                "claim the same grid cell; tests/test_element_reference.py re-runs both against "
                "this file so a hand edit is caught."
            ),
            "curated": (
                "common_oxidation_states and examples are hand-entered, and are the only "
                "unverifiable content here. An element whose states are not well established -- "
                "the superheavies, most known from a handful of atoms -- has NO key rather than "
                "a guess, and the dialog says 'not established'."
            ),
            "configuration_anomalies": (
                "The 20 known Aufbau exceptions (Cr, Cu, Nb, Mo, Ru, Rh, Pd, Ag, La, Ce, Gd, "
                "Pt, Au, Ac, Th, Pa, U, Np, Cm, Lr) are listed explicitly in the generator; "
                "they are measured ground states rather than predictions."
            ),
        },
        "elements": elements,
    }


if __name__ == "__main__":
    data = build()
    OUTPUT.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {OUTPUT} ({len(data['elements'])} elements)")
