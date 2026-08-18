"""Build `chem/data/nuclides.json` from the committed NUBASE2020 snapshot.

Run:    uv run --no-sync python tools/build_nuclide_table.py
Check:  uv run --no-sync python tools/build_nuclide_table.py --check

Same shape as `tools/build_regulatory_rulesets.py`: the output is
committed, so the application loads a plain data file and nothing is
derived at startup.

**IT NEVER TOUCHES THE NETWORK, AND THE SOURCE IS COMMITTED RATHER THAN
HASHED.** A `--check` that fetched would make CI depend on an upstream
that can change under it or vanish -- a NUBASE revision would turn every
run red with nothing in this repository having moved. And a hash alone is
not reproducibility: it says which bytes were expected without giving a
future reader the bytes needed to regenerate. So `nubase_4.mas20.txt`
sits beside the output and the manifest records both its sha256 (which
bytes) and its revision (which scientific release) -- the second being
the one that answers "why does this disagree with NUBASE2024".

## Ground states only, and that is enforced rather than described

NUBASE carries isomers (T-half >= 100 ns) as well: 5,843 rows against
3,558 ground states. This ships the ground states, because a molfile
cannot express Tc-99m as distinct from Tc-99, so isomer rows would be
data nothing could reach. A documented policy nothing enforces is how
somebody helpfully adds them later, so `_check_invariants` refuses.

## A half-life has EIGHT states and TWO dimensions

`t_half_s` plus an `estimated` boolean cannot carry NUBASE's evaluation.
Counted on the half-life field: ~2,800 exact, 369 `#` from systematics,
253 `stbl`, 84 blank, 9 `>`, 6 `~`, 4 `<`, 3 `p-unst`.

And the value and its uncertainty are separate: **256 rows carry both a
value and a `dT` bound** (`43Al` is an estimated `4# ms` beside a measured
`>170 ns`), while **38 of the 84 blank values carry their only
information in `dT`** (`18B` is `< 26 ns`). One qualifier field would
force a rule like "if dT has a bound, override the primary qualifier",
which is the kind of silent precedence that goes wrong later. So the two
are recorded independently, and a blank value whose bound lives in `dT`
takes its VALUE from there rather than being written off as unavailable.

## The licence, stated no more strongly than the evidence supports

Three separate claims, because a paper's licence does not automatically
licence a separately distributed data file:

  * the ARTICLE is CC BY 3.0 (Kondev et al 2021, Chin. Phys. C 45 030001)
  * the article CONTAINS this table -- Table I runs ~160 of its 181
    pages, and U-238 was cross-checked against this parse: `4.463 Gy`,
    `IS=99.2742 10; A=100; SF=5.44e-5 7; 2B-=2.2e-10 3`. That establishes
    the correspondence, not that all 5,843 rows are byte-identical
  * the electronic FILE carries a citation request from AMDC, not a
    licence grant

The attribution below satisfies both obligations, which are one action.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "src" / "openchem" / "chem" / "data"
SOURCE = DATA / "nubase_4.mas20.txt"
OUTPUT = DATA / "nuclides.json"

GENERATOR = "build_nuclide_table.py"
SOURCE_REVISION = "NUBASE2020"
SOURCE_URL = "https://www-nds.iaea.org/amdc/ame2020/nubase_4.mas20.txt"

# --- the fixed-width columns, from the file's own header ---------------------
#   1: 3  AAA     mass number
#   5: 8  ZZZi    atomic number, i=0 ground state
#  70:78  T       half-life
#  79:80  unit
#  82:88  dT      uncertainty
#  89:102 Jpi
# 120:209 BR      decay modes, and IS= for abundance
_A = slice(0, 3)
_ZZZI = slice(4, 8)
_T = slice(69, 78)
_UNIT = slice(78, 80)
_DT = slice(80, 88)
_JPI = slice(88, 102)
_BR = slice(119, None)
_MASS_EXCESS = slice(18, 31)

#: Seconds per NUBASE half-life unit. **All twenty**, because a unit table
#: is exactly where one gets quietly truncated and the shortfall then
#: looks like a plausible number.
_SECONDS = {
    "ys": 1e-24, "zs": 1e-21, "as": 1e-18, "fs": 1e-15, "ps": 1e-12,
    "ns": 1e-9, "us": 1e-6, "ms": 1e-3, "s": 1.0,
    "m": 60.0, "h": 3600.0, "d": 86400.0,
    "y": 3.1556952e7, "ky": 3.1556952e10, "My": 3.1556952e13,
    "Gy": 3.1556952e16, "Ty": 3.1556952e19, "Py": 3.1556952e22,
    "Ey": 3.1556952e25, "Zy": 3.1556952e28, "Yy": 3.1556952e31,
}

#: The eight states a half-life can be in.
EXACT = "exact"
ESTIMATED = "estimated"
LOWER_BOUND = "lower_bound"
UPPER_BOUND = "upper_bound"
APPROXIMATE = "approximate"
STABLE = "stable"
PARTICLE_UNSTABLE = "particle_unstable"
UNAVAILABLE = "unavailable"

_MARK_TO_QUALIFIER = {"#": ESTIMATED, ">": LOWER_BOUND, "<": UPPER_BOUND, "~": APPROXIMATE}


class BuildError(RuntimeError):
    """The source did not say what this generator assumed."""


# --- half-life ---------------------------------------------------------------


def _parse_quantity(text: str, default_unit: str) -> tuple[float | None, str | None]:
    """A number with an optional embedded unit, e.g. `170ns` or `0.6`.

    The `dT` column carries its own unit when it holds a BOUND (`>170ns`)
    and none when it holds an ordinary uncertainty (`0.6`, in the same
    unit as the value). Both shapes appear, so both are read.
    """
    cleaned = text.replace(" ", "")
    match = re.fullmatch(r"([0-9.eE+\-]+)([A-Za-z]*)", cleaned)
    if match is None:
        return None, None
    try:
        value = float(match.group(1))
    except ValueError:
        return None, None
    return value, (match.group(2) or default_unit)


def _seconds(value: float, unit: str) -> float:
    if unit not in _SECONDS:
        raise BuildError(f"unknown half-life unit {unit!r}")
    return value * _SECONDS[unit]


def parse_half_life(t_field: str, unit_field: str, dt_field: str) -> dict:
    """The half-life as a value, a qualifier, and an uncertainty of its own.

    **The two dimensions are independent.** A row can be an estimated
    value beside a measured bound, and a row with no value at all can
    still carry one in `dT` -- which is then the VALUE, with the bound's
    direction as its qualifier, rather than "unavailable".
    """
    raw = t_field.strip()
    unit = unit_field.strip()
    dt_raw = dt_field.strip()

    if raw == "stbl":
        return {"qualifier": STABLE}
    if raw.startswith("p-unst"):
        return {"qualifier": PARTICLE_UNSTABLE}

    # The uncertainty, read first: it is the only information some rows have.
    uncertainty: float | None = None
    uncertainty_qualifier: str | None = None
    if dt_raw:
        mark = dt_raw[0] if dt_raw[0] in _MARK_TO_QUALIFIER else ""
        value, dt_unit = _parse_quantity(dt_raw[len(mark):], unit or "s")
        if value is not None and dt_unit:
            uncertainty = _seconds(value, dt_unit)
            uncertainty_qualifier = _MARK_TO_QUALIFIER[mark] if mark else EXACT

    if not raw:
        # **38 rows have their only half-life information in `dT`.** Read
        # as "unavailable" they would lose a real measurement; the bound
        # is the value, and its direction is the qualifier.
        if uncertainty is not None and uncertainty_qualifier in (LOWER_BOUND, UPPER_BOUND):
            return {"seconds": uncertainty, "qualifier": uncertainty_qualifier}
        return {"qualifier": UNAVAILABLE}

    qualifier = EXACT
    for mark, name in _MARK_TO_QUALIFIER.items():
        if mark in raw:
            qualifier = name
            raw = raw.replace(mark, "")
    value, _ = _parse_quantity(raw, unit or "s")
    if value is None:
        return {"qualifier": UNAVAILABLE}

    result: dict = {"seconds": _seconds(value, unit or "s"), "qualifier": qualifier}
    if uncertainty is not None:
        result["uncertainty_s"] = uncertainty
        result["uncertainty_qualifier"] = uncertainty_qualifier
    return result


# --- decay modes -------------------------------------------------------------

_MODE = re.compile(r"^([A-Za-z0-9+\-]+)\s*(=|<|>|~|\?)\s*([0-9.eE+\-]*)")


def parse_decays(br_field: str) -> tuple[list[dict], float | None]:
    """Decay modes with their branchings, and the natural abundance.

    `IS=` is not a decay mode. It is NATURAL TERRESTRIAL ISOTOPIC
    ABUNDANCE -- not cosmic abundance, not a share of all known isotopes,
    and not the standing fraction of a radionuclide maintained by decay.
    """
    modes: list[dict] = []
    abundance: float | None = None
    for part in br_field.strip().split(";"):
        match = _MODE.match(part.strip())
        if match is None:
            continue
        name, qualifier, value = match.group(1), match.group(2), match.group(3)
        if name == "IS":
            try:
                abundance = float(value)
            except ValueError:
                abundance = None
            continue
        entry: dict = {"mode": name}
        if qualifier == "=" and value:
            entry["branching"] = float(value)
        elif qualifier != "=":
            # `?` is by far the commonest: the mode is expected and the
            # branching was never measured. Kept as a qualifier rather
            # than dropped, so the UI can say which it is.
            entry["qualifier"] = qualifier
            if value:
                entry["branching"] = float(value)
        modes.append(entry)
    return modes, abundance


# --- the build ---------------------------------------------------------------


def build(source_text: str) -> dict:
    nuclides: dict[str, dict] = {}
    isomers = 0
    neutrons = 0

    for line in source_text.splitlines():
        if line.startswith("#") or len(line) < 120:
            continue
        try:
            a = int(line[_A])
            zzzi = line[_ZZZI]
            z = int(zzzi[:3])
        except ValueError:
            continue
        if zzzi[3] != "0":
            isomers += 1
            continue
        if z == 0:
            # **THE FREE NEUTRON**, which NUBASE lists first as `1n` with
            # Z=0. It is not an element, nothing in this application can
            # reference it, and every lookup here is by element symbol.
            # Skipped deliberately rather than tripping the Z >= 1
            # invariant -- which is how it was found.
            neutrons += 1
            continue

        entry: dict = {"z": z, "a": a}
        entry["half_life"] = parse_half_life(line[_T], line[_UNIT], line[_DT])
        modes, abundance = parse_decays(line[_BR])
        if modes:
            entry["decays"] = modes
        if abundance is not None:
            entry["abundance"] = abundance
        jpi = line[_JPI].strip()
        if jpi:
            entry["jpi"] = jpi
        excess, _ = _parse_quantity(line[_MASS_EXCESS].replace("#", ""), "")
        if excess is not None:
            entry["mass_excess_kev"] = excess

        key = f"{z}-{a}"
        if key in nuclides:
            raise BuildError(f"{key} appears twice; ground states must be unique")
        nuclides[key] = entry

    _check_invariants(nuclides, isomers, neutrons)
    _acceptance_checks(nuclides)

    digest = hashlib.sha256(source_text.encode("utf-8")).hexdigest()
    return {
        "_source_key": "nubase2020",
        "_about": {
            "purpose": "Ground-state nuclear properties: half-life, decay modes, "
                       "natural abundance, spin and parity, mass excess.",
            "generated_by": f"tools/{GENERATOR} -- do not hand-edit; re-run it",
            "source_url": SOURCE_URL,
            "source_revision": SOURCE_REVISION,
            "source_sha256": digest,
            "generated_on": date.today().isoformat(),
            "ground_states_only": (
                "NUBASE also carries isomers (T-half >= 100 ns); they are NOT here. "
                "A molfile cannot express Tc-99m as distinct from Tc-99, so isomer "
                "rows would be data nothing in this application could reach. "
                f"{len(nuclides)} ground states kept, {isomers} isomer rows skipped, "
                "and the free neutron (Z=0) with them -- it is not an element."
            ),
            "abundance_means": (
                "Natural terrestrial isotopic abundance, as a percentage -- NUBASE's "
                "IS= field. Not cosmic abundance, not a share of all known isotopes."
            ),
            "half_life_has_two_dimensions": (
                "`seconds` and `qualifier` describe the VALUE; `uncertainty_s` and "
                "`uncertainty_qualifier` describe its uncertainty, independently. A row "
                "can be an estimated value beside a measured bound. Where the value is "
                "absent and dT holds a bound, that bound IS the value."
            ),
            "attribution": (
                "Values reproduced from Table I of F. G. Kondev, M. Wang, W. J. Huang, "
                "S. Naimi and G. Audi, 'The NUBASE2020 evaluation of nuclear physics "
                "properties', Chinese Physics C 45, 030001 (2021), "
                "doi:10.1088/1674-1137/abddae -- an open-access article under the "
                "Creative Commons Attribution 3.0 licence. The electronic file is "
                "distributed by the AMDC, which asks that work using it cite the paper "
                "rather than the file; this attribution satisfies both."
            ),
        },
        "nuclides": nuclides,
    }


def _check_invariants(nuclides: dict[str, dict], isomers: int, neutrons: int) -> None:
    """Ground states only, and nothing structurally impossible.

    These establish no science. They catch a column read one field over,
    instantly -- which is how this repository has been bitten twice, both
    times by a parser producing a plausible-looking count.
    """
    if not nuclides:
        raise BuildError("no ground states parsed at all")
    if isomers == 0:
        raise BuildError(
            "no isomer rows were skipped, so the ground-state filter is not working "
            "-- NUBASE2020 contains about 2,285 of them"
        )
    if neutrons != 1:
        raise BuildError(
            f"expected to skip exactly one Z=0 row (the free neutron), skipped {neutrons}"
        )
    for key, entry in nuclides.items():
        z, a = entry["z"], entry["a"]
        if z < 1:
            raise BuildError(f"{key}: Z must be at least 1")
        if a < z:
            raise BuildError(f"{key}: A ({a}) is below Z ({z})")
        abundance = entry.get("abundance")
        if abundance is not None and not 0.0 <= abundance <= 100.0:
            raise BuildError(f"{key}: abundance {abundance} is outside 0..100")
        seconds = entry["half_life"].get("seconds")
        if seconds is not None and seconds <= 0:
            raise BuildError(f"{key}: half-life {seconds} is not positive")


def _acceptance_checks(nuclides: dict[str, dict]) -> None:
    """A row count is not evidence.

    This project has recorded one PDF extraction that ran past the end of
    its table and another that gave every element its neighbour's data,
    both with entirely plausible counts. These are values anybody can
    check against a textbook.
    """
    stable = sum(1 for e in nuclides.values() if e["half_life"]["qualifier"] == STABLE)
    if stable != 253:
        raise BuildError(f"expected 253 stable nuclides, parsed {stable}")

    expected = {
        # key       half-life seconds   tolerance   abundance
        "92-238": (1.4100e17, 1e15, 99.2742),
        "84-209": (3.9131e9, 1e7, None),
        "6-14": (1.7988e11, 1e9, None),
        "43-99": (6.6618e12, 1e10, None),
    }
    for key, (seconds, tolerance, abundance) in expected.items():
        entry = nuclides.get(key)
        if entry is None:
            raise BuildError(f"{key} is missing")
        got = entry["half_life"].get("seconds")
        if got is None or abs(got - seconds) > tolerance:
            raise BuildError(f"{key}: half-life {got} is not {seconds}")
        if abundance is not None and entry.get("abundance") != abundance:
            raise BuildError(f"{key}: abundance {entry.get('abundance')} is not {abundance}")

    uranium = nuclides["92-238"]["decays"]
    by_mode = {d["mode"]: d.get("branching") for d in uranium}
    if by_mode.get("A") != 100.0:
        raise BuildError(f"U-238 alpha branching is {by_mode.get('A')}, expected 100")
    if by_mode.get("SF") != 5.44e-05:
        raise BuildError(f"U-238 SF branching is {by_mode.get('SF')}, expected 5.44e-05")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="rebuild from the committed snapshot and compare, without writing",
    )
    args = parser.parse_args()

    source_text = SOURCE.read_text(encoding="utf-8", errors="replace")
    data = build(source_text)

    if args.check:
        if not OUTPUT.exists():
            print(f"{OUTPUT} does not exist; run without --check", file=sys.stderr)
            return 1
        committed = json.loads(OUTPUT.read_text(encoding="utf-8"))
        if committed.get("nuclides") != data["nuclides"]:
            print("nuclides.json does not match the committed source", file=sys.stderr)
            return 1
        recorded = committed.get("_about", {}).get("source_sha256")
        if recorded != data["_about"]["source_sha256"]:
            print(
                "nuclides.json was generated from a different snapshot "
                f"({recorded} vs {data['_about']['source_sha256']})",
                file=sys.stderr,
            )
            return 1
        print(f"OK: {len(data['nuclides'])} nuclides match the committed snapshot")
        return 0

    OUTPUT.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {OUTPUT} ({len(data['nuclides'])} ground states)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
