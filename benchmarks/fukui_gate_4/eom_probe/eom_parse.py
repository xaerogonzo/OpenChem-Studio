"""Reads an ORCA IP-EOM-CCSD output of a PLANAR molecule oriented with its plane as xy: which occupied orbital each root removes an electron from, and whether that orbital is sigma or pi.

The roots are Koopmans-like states of the cation, so a root's kind is its dominant occupied orbital's kind. The orbital's kind comes from ORCA's own `LOEWDIN REDUCED ORBITAL POPULATIONS PER MO`
(`%output Print[P_ReducedOrbPopMO_L] 1`): the share of the orbital on the functions that are ODD in z (pz, dxz, dyz, and the f functions f0, f-2 and f+2), which is 1 for a pi orbital and 0 for a sigma
one of a planar molecule in the xy plane. An orbital whose share is neither near 0 nor near 1 is reported as such, never rounded to a kind. The component names that are in no table fail loudly.
"""
from __future__ import annotations

import re

#: Components of a function that change sign under z -> -z (verified against a cc-pVTZ output: s, p, d and f are the only shells there).
ODD_IN_Z = frozenset({"pz", "dxz", "dyz", "f0", "f-2", "f+2"})
#: Components that do not change sign under z -> -z.
EVEN_IN_Z = frozenset({"s", "px", "py", "dz2", "dx2y2", "dxy", "f+1", "f-1", "f+3", "f-3"})
#: The share of an orbital on odd-in-z functions at or above which it is a pi orbital, and at or below which a sigma one (gate 4's limits).
PI_AT_LEAST, SIGMA_AT_MOST = 0.75, 0.25

_MO_HEADER = "LOEWDIN REDUCED ORBITAL POPULATIONS PER MO"
_INDEX_ROW = re.compile(r"^\s+(\d+(?:\s+\d+)*)\s*$")
_COMPONENT_ROW = re.compile(r"^\s*(\d+)\s+([A-Z][a-z]?)\s+([a-z][a-z0-9+\-]*)\s+((?:-?\d+\.\d+\s*)+)$")
_ROOT = re.compile(r"^IROOT=\s*(\d+):\s+(\d+\.\d+)\s+au\s+(\d+\.\d+)\s+eV", re.MULTILINE)
_SINGLE = re.compile(r"^\s+(-?\d+\.\d+)\s+(\d+)\s+->\s+x\s*$")
_SINGLES_PERCENT = re.compile(r"Percentage singles character=\s*(\d+\.\d+)")


def parse_orbital_parity(out: str) -> dict[int, float]:
    """The share (0 to 1) of each molecular orbital on odd-in-z functions, from the first reduced-population table of an RHF output (orbitals numbered from 0, as the EOM roots number them)."""
    start = out.find(_MO_HEADER)
    if start < 0:
        return {}
    odd: dict[int, float] = {}
    total: dict[int, float] = {}
    columns: list[int] = []
    for line in out[start:].splitlines()[3:]:
        if not line.strip() or re.match(r"^\s*-{3,}(\s+-{3,})*\s*$", line):
            continue
        row = _COMPONENT_ROW.match(line)
        if row and columns:
            component = row.group(3)
            if component not in ODD_IN_Z and component not in EVEN_IN_Z:
                raise ValueError(f"the orbital component {component!r} is in no parity table")
            values = [float(v) for v in row.group(4).split()]
            for column, value in zip(columns, values):
                total[column] = total.get(column, 0.0) + value
                if component in ODD_IN_Z:
                    odd[column] = odd.get(column, 0.0) + value
            continue
        index = _INDEX_ROW.match(line)
        if index and "." not in line:
            columns = [int(v) for v in index.group(1).split()]
            continue
        if columns and re.match(r"^\s+-?\d+\.\d+(\s+-?\d+\.\d+)*\s*$", line):
            continue  # an orbital-energy or occupation row
        if columns:
            break  # the table has ended
    return {column: (odd.get(column, 0.0) / total[column] if total[column] else 0.0) for column in total}


def kind_of(parity: float) -> str:
    """'pi', 'sigma', or 'mixed' for an orbital's odd-in-z share."""
    return "pi" if parity >= PI_AT_LEAST else "sigma" if parity <= SIGMA_AT_MOST else "mixed"


def parse_roots(out: str) -> list[dict]:
    """Every IP-EOM-CCSD root of the final results block: its energy in eV, its dominant occupied orbital (largest single-excitation amplitude) and that amplitude, and its singles character in per cent."""
    block = out[out.rfind("EOM-CCSD RESULTS"):] if "EOM-CCSD RESULTS" in out else ""
    roots: list[dict] = []
    matches = list(_ROOT.finditer(block))
    for index, match in enumerate(matches):
        stretch = block[match.end(): matches[index + 1].start() if index + 1 < len(matches) else len(block)]
        singles = [(float(m.group(1)), int(m.group(2))) for m in (_SINGLE.match(line) for line in stretch.splitlines()) if m]
        percent = _SINGLES_PERCENT.search(stretch)
        if not singles:
            continue
        amplitude, orbital = max(singles, key=lambda pair: abs(pair[0]))
        roots.append({"root": int(match.group(1)), "energy_ev": float(match.group(3)), "orbital": orbital, "amplitude": amplitude, "singles_percent": float(percent.group(1)) if percent else None})
    return roots


def classified_roots(out: str) -> list[dict]:
    """The roots with each one's orbital kind and that orbital's odd-in-z share added, lowest energy first."""
    parity = parse_orbital_parity(out)
    result = []
    for root in sorted(parse_roots(out), key=lambda r: r["energy_ev"]):
        share = parity.get(root["orbital"])
        result.append({**root, "parity": share, "kind": None if share is None else kind_of(share)})
    return result
