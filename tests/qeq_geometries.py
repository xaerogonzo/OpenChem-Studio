"""Cartesian geometries for Rappé & Goddard's polyatomic oracles, built from
Harmony et al. 1979 by the rules of preregistration amendment A4.

Not a test module: `tests/test_charge_equilibration.py` and
`benchmarks/charges/rappe_goddard/oracle.py` both build from here, so the
suite and the report can never run on two different constructions.

Every rule below is A4's. Nothing is tuned: the structure-type order and each
conformation were committed before any polyatomic charge existed.
"""

from __future__ import annotations

import csv
import math
import pathlib

import numpy as np

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "charges" / "harmony1979_structures.csv"

#: A4: nearest to the equilibrium structure first.
PREFERRED = ("equilibrium", "substitution", "average", "effective")
#: The diagnostic A4 reports and never gates on.
REVERSED = tuple(reversed(PREFERRED))


def _rows() -> list[dict[str, str]]:
    lines = [line for line in FIXTURE.read_text(encoding="utf-8").splitlines() if not line.startswith("#")]
    return list(csv.DictReader(lines))


def parameters(molecule: str, order: tuple[str, ...] = PREFERRED) -> tuple[dict[str, float], dict[str, str]]:
    """Each printed parameter of `molecule`, taking the first structure type in
    `order`, and which type that was."""
    chosen: dict[str, float] = {}
    types: dict[str, str] = {}
    rows = [r for r in _rows() if r["molecule"] == molecule]
    if not rows:
        raise KeyError(molecule)
    for name in dict.fromkeys(r["parameter"] for r in rows):
        by_type = {r["structure_type"]: float(r["value"]) for r in rows if r["parameter"] == name}
        kind = next(k for k in order if k in by_type)
        chosen[name], types[name] = by_type[kind], kind
    return chosen, types


def _unit(v):
    v = np.asarray(v, dtype=float)
    return v / np.linalg.norm(v)


def _place(a, b, c, bond, angle_deg, dihedral_deg):
    """The atom bonded to `a` at `bond`, with angle (new, a, b) and dihedral
    (new, a, b, c) -- the natural-extension reference frame."""
    a, b, c = (np.asarray(x, dtype=float) for x in (a, b, c))
    theta, phi = math.radians(angle_deg), math.radians(dihedral_deg)
    bc = _unit(a - b)
    n = _unit(np.cross(b - c, bc))
    m = np.cross(n, bc)
    local = np.array([-bond * math.cos(theta), bond * math.sin(theta) * math.cos(phi), bond * math.sin(theta) * math.sin(phi)])
    return a + local[0] * bc + local[1] * m + local[2] * n


def _pyramid(bond: float, angle_deg: float, count: int = 3):
    """`count` bonds of equal length at mutual angle `angle_deg` about +z."""
    cos_t = math.cos(math.radians(angle_deg))
    sin2 = (1.0 - cos_t) / (1.0 - math.cos(2 * math.pi / count))
    alpha = math.asin(math.sqrt(sin2))
    return [bond * np.array([math.sin(alpha) * math.cos(2 * math.pi * k / count), math.sin(alpha) * math.sin(2 * math.pi * k / count), -math.cos(alpha)]) for k in range(count)]


def build(molecule: str, order: tuple[str, ...] = PREFERRED):
    """(elements, coordinates in angstrom, Table IV printed_order -> atom indices, structure types used)."""
    p, types = parameters(molecule, order)
    O = np.zeros(3)
    z = np.array([0.0, 0.0, 1.0])
    x = np.array([1.0, 0.0, 0.0])

    if molecule in ("H2O",):
        half = math.radians(p["HOH"] / 2)
        coords = [O, p["OH"] * np.array([math.sin(half), 0, math.cos(half)]), p["OH"] * np.array([-math.sin(half), 0, math.cos(half)])]
        return ["O", "H", "H"], np.array(coords), {1: [1, 2]}, types
    if molecule in ("NH3", "PH3"):
        heavy, bond, angle = ("N", "NH", "HNH") if molecule == "NH3" else ("P", "PH", "HPH")
        return [heavy, "H", "H", "H"], np.array([O, *_pyramid(p[bond], p[angle])]), {1: [1, 2, 3]}, types
    if molecule in ("CH4", "SiH4"):
        heavy, bond = ("C", "CH") if molecule == "CH4" else ("Si", "SiH")
        vertices = [_unit(v) * p[bond] for v in ([1, 1, 1], [1, -1, -1], [-1, 1, -1], [-1, -1, 1])]
        return [heavy, "H", "H", "H", "H"], np.array([O, *vertices]), {1: [1, 2, 3, 4]}, types
    if molecule == "CO2":
        return ["C", "O", "O"], np.array([O, p["CO"] * z, -p["CO"] * z]), {1: [1, 2]}, types
    if molecule == "C2H2":
        cc, ch = p["CC"], p["CH"]
        return ["C", "C", "H", "H"], np.array([O, cc * z, -ch * z, (cc + ch) * z]), {1: [2, 3]}, types
    if molecule == "H2CO":
        c, o = O, p["CO"] * z
        a = (360 - p["HCH"]) / 2
        h1 = _place(c, o, o + x, p["CH"], a, 0)
        h2 = _place(c, o, o + x, p["CH"], a, 180)
        return ["O", "C", "H", "H"], np.array([o, c, h1, h2]), {1: [0], 2: [1], 3: [2, 3]}, types
    if molecule == "H2C=C=O":
        c1, c2 = O, p["CC"] * z
        o = c2 + p["CO"] * z
        a = (360 - p["HCH"]) / 2
        h1 = _place(c1, c2, c2 + x, p["CH"], a, 0)
        h2 = _place(c1, c2, c2 + x, p["CH"], a, 180)
        return ["O", "C", "C", "H", "H"], np.array([o, c2, c1, h1, h2]), {1: [0], 2: [1], 3: [2]}, types
    if molecule == "H3CCN":
        methyl, nitrile = O, p["CC"] * z
        n = nitrile + p["CN"] * z
        hs = [_place(methyl, nitrile, nitrile + x, p["CH"], p["HCC"], d) for d in (0, 120, 240)]
        return ["N", "C", "C", "H", "H", "H"], np.array([n, nitrile, methyl, *hs]), {1: [0], 2: [1], 3: [2], 4: [3, 4, 5]}, types
    if molecule == "C2H4":
        c1, c2 = O, p["CC"] * z
        a = (360 - p["HCH"]) / 2
        hs = [_place(c1, c2, c2 + x, p["CH"], a, 0), _place(c1, c2, c2 + x, p["CH"], a, 180),
              _place(c2, c1, c1 + x, p["CH"], a, 0), _place(c2, c1, c1 + x, p["CH"], a, 180)]
        return ["C", "C", "H", "H", "H", "H"], np.array([c1, c2, *hs]), {1: [2, 3, 4, 5]}, types
    if molecule == "C6H6":
        cs = [p["CC"] * np.array([math.cos(k * math.pi / 3), math.sin(k * math.pi / 3), 0]) for k in range(6)]
        hs = [(p["CC"] + p["CH"]) * np.array([math.cos(k * math.pi / 3), math.sin(k * math.pi / 3), 0]) for k in range(6)]
        return ["C"] * 6 + ["H"] * 6, np.array(cs + hs), {1: list(range(6, 12))}, types
    if molecule == "HOC(O)H":
        c, o1 = O, p["CO1"] * z
        o2 = _place(c, o1, o1 + x, p["CO2"], p["OCO"], 0)
        hc = _place(c, o1, o2, p["CH"], p["HCO"], 180)
        ho = _place(o2, c, o1, p["OH"], p["COH"], 0)  # syn to O1
        return ["O", "C", "H", "O", "H"], np.array([o1, c, hc, o2, ho]), {1: [0], 2: [1], 3: [2], 4: [3], 5: [4]}, types
    if molecule == "H2NC(O)H":
        c, o = O, p["CO"] * z
        n = _place(c, o, o + x, p["CN"], p["NCO"], 0)
        hc = _place(c, n, o, p["CH"], p["NCH"], 180)
        h1 = _place(n, c, o, p["NH1"], p["H1NC"], 0)  # cis to O
        h2 = _place(n, c, o, p["NH2"], 360 - p["H1NH2"] - p["H1NC"], 180)
        return ["O", "C", "N", "H", "H", "H"], np.array([o, c, n, h1, h2, hc]), {1: [0], 2: [1], 3: [2], 4: [3], 5: [4]}, types
    if molecule == "H3COH":
        c, o = O, p["CO"] * z
        ho = _place(o, c, c + x, p["OH"], p["COH"], 0)  # the hydroxyl H sits on the +x side
        tilt = math.radians(p["phi"])
        axis = np.array([-math.sin(tilt), 0.0, -math.cos(tilt)])  # away from O, tilted away from the OH group
        e1 = np.array([math.cos(tilt), 0.0, -math.sin(tilt)])
        e2 = np.array([0.0, 1.0, 0.0])
        cos_t = math.cos(math.radians(p["HCH"]))
        alpha = math.asin(math.sqrt((1 - cos_t) / 1.5))
        methyl = [c + p["CH"] * (math.cos(alpha) * axis + math.sin(alpha) * (math.cos(b) * e1 + math.sin(b) * e2))
                  for b in (math.pi, math.pi / 3, -math.pi / 3)]  # b = pi is anti to the hydroxyl H
        return ["H", "O", "C", "H", "H", "H"], np.array([ho, o, c, *methyl]), {1: [0], 2: [1], 3: [2], 4: [4, 5], 5: [3]}, types
    raise KeyError(molecule)


#: Table III/IV compound names -> Harmony molecule keys.
TABLE_NAMES = {
    "H2O": "H2O", "NH3": "NH3", "CH4": "CH4", "C2H2": "C2H2", "C2H4": "C2H4", "C6H6": "C6H6",
    "CO2": "CO2", "H2CO": "H2CO", "H3COH": "H3COH", "H2NC(O)H": "H2NC(O)H", "HOC(O)H": "HOC(O)H",
    "H3CCN": "H3CCN", "H2C=C=O": "H2C=C=O", "SiH4": "SiH4", "PH3": "PH3",
}
