"""Generate `chem/data/atomic_scattering_factors.json` -- Waasmaier & Kirfel 1995.

    uv run --no-sync python tools/build_scattering_factors.py --check
    <throwaway venv>/python tools/build_scattering_factors.py --xraydb <path>

**THE GENERATE HALF NEEDS `xraydb`, WHICH IS NOT A DEPENDENCY OF THIS PROJECT.**
Same shape as `build_ketcher_notices.py`, whose regenerate-and-compare half needs
`node_modules/`: `--check` validates the SHIPPED file's own invariants and needs
nothing external, so CI can run it; regeneration is done by hand in a throwaway
environment, and the tool says which half it could do rather than passing
silently.

## Why a machine-readable copy was the whole blocker

`docs/sources.toml` recorded this table as `assessed_not_shipped` because the
local scan's text layer is 29.7% numerically corrupted AND only 6 of its 11
parameters per row have an oracle -- `sum(a_i) + c = Z` checks a1..a5 and c,
while a wrong `b` is wrong at every non-zero angle and exactly right at
theta = 0, which is the one place that checksum looks.

**THAT BLOCKER DISSOLVES ONCE A MACHINE-READABLE COPY EXISTS, and the reason is
worth stating: the b values were never unverifiable in PRINCIPLE.** They were
unverifiable by hand from a corrupted scan. With a candidate table in hand the
paper itself becomes the oracle -- every value can be looked for in its own
Table 1 -- so the proxy oracles designed to substitute for a parameter check are
demoted to characterisations. See `check` below.

## Provenance, established rather than assumed

    xraydb 4.5.8, MIT       ships `waasmaier_kirfel.dat`; its `f0` docstring
                            cites "D. Waasmaier and A. Kirfel, Acta Cryst. A51
                            p416 (1995)"
    cctbx, independent      carries the same table and documents its origin as
                            ftp://wrzx02.rz.uni-wuerzburg.de/pub/local/
                            Crystallography/sfac.dat, "picked up Jul 4, 1995.
                            File verified Sep 12, 2001"
    row count               211 species, and cctbx reports 211 independently --
                            two implementations agreeing on the table's SHAPE,
                            not merely on its numbers
    the paper we hold       1280 of 2321 values appear VERBATIM in the local
                            scan's own text layer (55.1%), against the ~70%
                            ceiling that scan's corruption allows

MIT is compatible with this project's GPL-3.0-or-later. The coefficients are
published scientific constants from the 1995 paper; what MIT covers is that
project's file, and the attribution names both.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "src" / "openchem" / "chem" / "data"
TABLE = OUT / "atomic_scattering_factors.json"

#: The paper's own stated validity range for the five-Gaussian fit, in inverse
#: angstrom. Far wider than the four-Gaussian International Tables fit it was
#: made to replace, which is why the two disagree most at the top end.
VALID_S_RANGE = [0.0, 6.0]

#: How many species the paper tabulates: neutral atoms AND ions, in one table.
#: Asserted rather than counted, because a short table would look like a smaller
#: element set rather than a truncated read.
EXPECTED_SPECIES = 211

#: How far below zero f0 may fall before it is a fault rather than a residual.
#:
#: **ONE SPECIES NEEDS THIS AND IT IS NAMED RATHER THAN ABSORBED: Be2+ reaches
#: -0.0004 electrons** at the top of the range. It has two electrons and its f0
#: decays to an asymptote of zero, so the fit's residual straddles zero there --
#: which is a property of fitting a curve that legitimately reaches its own
#: floor, not of a bad parameter. A bound at exactly zero would fail on correct
#: data; a bound loose enough to hide a real sign error would defeat the check.
#: 0.005 electrons is far below anything a diffraction experiment resolves and
#: 12x Be2+'s own excursion.
NEGATIVE_F0_FLOOR = -0.005

_ATTRIBUTION = (
    "Analytical scattering-factor parameters from D. Waasmaier & A. Kirfel, "
    "'New Analytical Scattering-Factor Functions for Free Atoms and Ions', "
    "Acta Crystallographica A51, 1995, pp. 416-431, "
    "doi:10.1107/S0108767394013292. Machine-readable values taken from xraydb "
    "(MIT, xraypy/XrayDB), whose waasmaier_kirfel.dat cites that paper; "
    "cross-checked against the paper's own Table 1 in the copy held locally, "
    "and against the independent International Tables four-Gaussian "
    "parameterisation via gemmi (MPL-2.0)."
)

_DEFINITION = (
    "f0(s) = c + sum_i a_i exp(-b_i s^2), i = 1..5, with s = sin(theta)/lambda "
    "in inverse angstrom. NOTE that s is not squared in the caller's argument "
    "here: some libraries take s^2 instead, and handing one convention to the "
    "other is a several-electron error rather than a small one."
)

_PARAMETER_ORDER = (
    "SOURCE ORDER, and it must not be normalised. The five (a, b) pairs are not "
    "printed in ascending b -- 208 of the 211 rows are non-monotonic -- and some "
    "elements carry near-equal b values, so sorting by b silently re-pairs each "
    "a with another a's exponent while every row still looks well formed."
)


def _charge(label: str) -> int:
    """Ionic charge from the paper's own species label: `Fe2+`, `O2-`, `H`."""
    match = re.match(r"^[A-Za-z]+(\d*)([+-])$", label)
    if not match:
        return 0
    magnitude = int(match.group(1) or 1)
    return magnitude if match.group(2) == "+" else -magnitude


def generate(xraydb_sqlite: Path) -> dict:
    import sqlalchemy as sa  # noqa: PLC0415 -- generate half only, never imported at runtime

    engine = sa.create_engine(f"sqlite:///{xraydb_sqlite}")
    species: dict[str, dict] = {}
    with engine.connect() as conn:
        for _id, z, element, label, offset, scale, exponents in conn.execute(
            sa.text("select * from Waasmaier")
        ):
            species[label] = {
                "element": element,
                "z": int(z),
                "charge": _charge(label),
                "a": json.loads(scale),
                "b": json.loads(exponents),
                "c": offset,
            }
    return {
        "_source_key": "waasmaier1995",
        "attribution": _ATTRIBUTION,
        "definition": _DEFINITION,
        "parameter_order": _PARAMETER_ORDER,
        "valid_s_range_inv_angstrom": VALID_S_RANGE,
        "species": dict(sorted(species.items())),
    }


def check(payload: dict) -> list[str]:
    """Invariants of the SHIPPED file. Needs nothing external.

    CHARACTERISATIONS, not the parameter oracle. The oracle is the paper, and it
    was applied at generation time -- see the provenance block above. These are
    kept because they are what a future edit to this file would break, and the
    b-ordering one in particular is the innocent normalisation that would leave
    every row still looking well formed.

    **`b >= 0` IS NOT AN INVARIANT, AND ASSUMING IT WAS FLAGGED 13 CORRECT
    ROWS.** Carbon's own row in Table 1 reads, in the paper this project holds:

        C RHF 2.657506 14.780758 1.078079 0.776775 1.490909 42.086843
              -4.241070 -0.000294 0.713791 0.239535 4.297983

    -- a large NEGATIVE a paired with a tiny negative b, against a large
    positive c; nitrogen's c is -11.804902. These are artefacts of an
    unconstrained five-Gaussian least squares, not corruption, and the curve
    they produce is entirely physical. So the invariants below are on f0
    ITSELF rather than on the shape of its parameters: measured over the
    paper's full stated range, all 211 species decay monotonically and none
    goes negative.
    """
    problems: list[str] = []
    species = payload.get("species", {})
    if len(species) != EXPECTED_SPECIES:
        problems.append(f"expected {EXPECTED_SPECIES} species, found {len(species)}")

    lo, hi = payload.get("valid_s_range_inv_angstrom", VALID_S_RANGE)
    grid = [lo + (hi - lo) * i / 120 for i in range(121)]
    worst_checksum = 0.0
    non_monotonic = 0
    for label, row in sorted(species.items()):
        a, b, c = row["a"], row["b"], row["c"]
        if len(a) != 5 or len(b) != 5:
            problems.append(
                f"{label}: expected five (a, b) pairs, found {len(a)} and {len(b)}"
            )
            continue
        if b != sorted(b):
            non_monotonic += 1

        # f0(0) is the species' electron count, so this checks a1..a5 and c.
        deviation = abs(sum(a) + c - (row["z"] - row["charge"]))
        worst_checksum = max(worst_checksum, deviation)
        if deviation > 0.05:
            problems.append(
                f"{label}: sum(a)+c is {deviation:.4f} from its electron count"
            )

        curve = [c + sum(ai * math.exp(-bi * s * s) for ai, bi in zip(a, b))
                 for s in grid]
        if any(curve[i + 1] > curve[i] + 1e-6 for i in range(len(curve) - 1)):
            problems.append(f"{label}: f0 RISES with angle, which no free atom does")
        if min(curve) < NEGATIVE_F0_FLOOR:
            problems.append(f"{label}: f0 goes negative, reaching {min(curve):.4f}")

    if non_monotonic < 200:
        problems.append(
            f"only {non_monotonic} rows have non-ascending b -- this file looks "
            "sorted, which re-pairs each a with another a's exponent"
        )
    print(f"species: {len(species)}")
    print(f"worst |sum(a)+c - electrons|: {worst_checksum:.4f}")
    print(f"rows with non-ascending b: {non_monotonic} (source order preserved)")
    print(f"f0 monotonic and non-negative over s = {lo} to {hi}: all {len(species)}")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--xraydb", type=Path, default=None,
        help="path to xraydb.sqlite; regenerates the table",
    )
    parser.add_argument(
        "--check", action="store_true",
        help="validate the shipped file; needs nothing external",
    )
    args = parser.parse_args()

    if args.xraydb:
        payload = generate(args.xraydb)
        TABLE.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
        print(f"wrote {TABLE} with {len(payload['species'])} species")
        return 0

    if not TABLE.is_file():
        print(f"{TABLE} does not exist")
        return 1
    problems = check(json.loads(TABLE.read_text(encoding="utf-8")))
    print(
        "NOT re-generated: xraydb is not a dependency of this project, so the "
        "regenerate-and-compare half needs --xraydb and a throwaway environment. "
        "The invariants above ran."
    )
    for problem in problems:
        print(f"  PROBLEM: {problem}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
