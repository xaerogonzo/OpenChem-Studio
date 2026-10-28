"""The arithmetic of protocol v3 (`PREREGISTRATION.md` of this folder): when a radical gets a numerical frequency job, how its output is read, which records the judge accepts, the references of the three arms and the reading rules.
Pure functions with no engine; the only files read are the committed reference files. Tested in `tests/test_restart_v3_runner.py` against excerpts of real ORCA output.

THE RULE (section 3). v3 is v2 plus ONE stage for a RADICAL: when the first run's two stages (the optimization with frequencies, and the `Calc_Hess` re-run) leave a frequency below -20 cm-1 and the skeleton is intact, ONE numerical frequency job is run at the
geometry of that re-run (`NUMERICAL_HEADER`). Its enthalpy replaces the analytic one. v2's displaced restart is NOT applied to a radical, and nothing changes for a closed-shell structure. A numerical result below -20 cm-1 keeps its enthalpy and is labelled
`NOT_VERIFIED` (decision D2). A radical of more than `MAX_NUMERICAL_ATOMS` atoms is not given the job (decision D1).
"""
from __future__ import annotations

import importlib.util
import json
import math
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


#: The first run's judge (`benchmarks/bde/judge.py`), unchanged: its limits and statistics are the reading rules of Arms C and D. Pure, so loaded by path.
judge = _load("bde_judge_for_restart_v3", REPO / "benchmarks" / "bde" / "judge.py")

#: The numerical frequency job: the first run's functional, basis and grid, no `Opt`, finite differences of gradients (no coupled-perturbed SCF). Unrestricted, charge 0 and multiplicity 2 are the input block's.
NUMERICAL_HEADER = "! M062X def2-TZVPD TightSCF DefGrid3 NumFreq"
#: Decision D1: a radical of more than this many atoms is not given the numerical job (6N gradients is hours beyond it).
MAX_NUMERICAL_ATOMS = 12
#: A vibrational frequency below this (cm-1) is not accepted (the first run's rule, unchanged).
IMAGINARY_CM = -20.0
NOT_VERIFIED = "frequencies not verified: a soft mode below -20 cm-1 remains"
OVER_CAP = f"analytic frequencies not verified: the radical has more than {MAX_NUMERICAL_ATOMS} atoms, over the cap for the numerical job"
#: Arms C and D: NOT EVALUABLE when this many deciding bonds (or more) have no computed value (section 8).
NOT_EVALUABLE_AT_MISSING = 2
#: Arm C-Br's gross-failure limit (kcal/mol), the held-out arm's single-error limit.
GROSS_ERROR = 5.0
KJ_PER_KCAL = 4.184


# --- the rule ---------------------------------------------------------------------------------------------------------------------


def within_cap(atom_count: int) -> bool:
    return atom_count <= MAX_NUMERICAL_ATOMS


def needs_numerical(record: dict) -> bool:
    """Whether the job that ended the first run's two stages (the `Calc_Hess` re-run) triggers the numerical stage (R1): a RADICAL that finished, still has a frequency below -20 cm-1, and whose skeleton is intact.
    A structure whose skeleton changed is a failed structure, not a saddle point near a minimum (the same reading as v2's `needs_restart`)."""
    return bool(record.get("completed")) and record.get("role") == "radical" and record["lowest_frequency"] < IMAGINARY_CM and bool(record.get("skeleton_kept"))


def parse_numerical(text: str) -> dict:
    """One NumFreq output as the first run's reading of an `Opt Freq` output, minus the convergence line (there is no optimization) and with the geometry the job was GIVEN (the first coordinate block).
    298.15 K and 1 atm are checked. Raises ValueError naming the first thing missing, so an unfinished job is never a number."""
    if "ORCA TERMINATED NORMALLY" not in text:
        raise ValueError("the numerical job did not terminate normally")

    def last(pattern: str):
        found = re.findall(pattern, text)
        return found[-1] if found else None

    start = text.find("CARTESIAN COORDINATES (ANGSTROEM)")
    if start < 0:
        raise ValueError("no geometry in the output")
    symbols, coordinates = [], []
    for line in text[start:].splitlines()[2:]:
        m = re.match(r"^\s*([A-Z][a-z]?)\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s*$", line)
        if not m:
            break
        symbols.append(m.group(1))
        coordinates.append([float(m.group(2)), float(m.group(3)), float(m.group(4))])
    frequencies = []
    at = text.rfind("VIBRATIONAL FREQUENCIES")
    if at >= 0:
        for line in text[at:].splitlines():
            m = re.match(r"^\s*\d+:\s+(-?\d+\.\d+) cm\*\*-1", line)
            if m:
                frequencies.append(float(m.group(1)))
            elif frequencies and not line.strip():
                break
    enthalpy, energy = last(r"Total enthalpy\s+\.\.\.\s+(-?\d+\.\d+) Eh"), last(r"FINAL SINGLE POINT ENERGY\s+(-?\d+\.\d+)")
    temperature, pressure = last(r"Temperature\s+\.\.\.\s+(\d+\.\d+) K"), last(r"Pressure\s+\.\.\.\s+(\d+\.\d+) atm")
    for label, value in (("enthalpy", enthalpy), ("electronic energy", energy), ("frequencies", frequencies or None), ("temperature", temperature), ("pressure", pressure)):
        if value is None:
            raise ValueError(f"no {label} in the output")
    if abs(float(temperature) - 298.15) > 1e-6 or abs(float(pressure) - 1.0) > 1e-6:
        raise ValueError(f"thermochemistry at {temperature} K and {pressure} atm, not 298.15 K and 1 atm")
    s2 = last(r"Expectation value of <S\*\*2>\s+:\s+(-?\d+\.\d+)")
    return {"energy": float(energy), "enthalpy": float(enthalpy), "frequencies": frequencies, "lowest_frequency": min(frequencies), "symbols": symbols, "coordinates": coordinates,
            "s2": float(s2) if s2 else None, "orca_version": last(r"Program Version\s+(\S+)")}


def lowest_vibration(frequencies: list[float]) -> float | None:
    """The lowest frequency that is a vibration, for the report. `lowest_frequency` (the first run's field, the minimum of ALL printed values) is 0.0 for every good structure because the six translations and rotations are printed as zero, so it says nothing about the softest real mode;
    this drops the values within 1 cm-1 of zero. An imaginary mode is negative and is kept."""
    modes = [f for f in frequencies if abs(f) > 1.0]
    return min(modes) if modes else None


def numerical_fields(retry: dict, parsed: dict) -> dict:
    """What the numerical record adds to the parsed job: it is flagged `numerical`, it carries the analytic enthalpy and lowest frequency it replaced (so the effect of the replacement is always readable), whether its own frequencies pass,
    and the label when they do not."""
    verified = parsed["lowest_frequency"] >= IMAGINARY_CM
    return {"numerical": True, "verified": verified, "label": None if verified else NOT_VERIFIED, "analytic_enthalpy": retry["enthalpy"], "analytic_lowest_frequency": retry["lowest_frequency"]}


def accepted(records: list[dict]) -> list[dict]:
    """The records that count, for the judge: the first run's rule (a completed job; a species also with no frequency below -20 cm-1 and its skeleton kept; a structure's later record replaces its earlier one), EXCEPT that a numerical record is accepted
    at any frequency (decision D2: its enthalpy is kept and the label says the frequencies were not verified)."""
    latest: dict[str, dict] = {}
    for record in records:
        if record.get("completed"):
            latest[record["structure"]] = record
    return [r for r in latest.values() if r["role"] == "atom" or (r["skeleton_kept"] and (r.get("numerical") or r["lowest_frequency"] >= IMAGINARY_CM))]


def numerical_labels(records: list[dict]) -> dict[str, dict]:
    """For each ORIGINAL radical structure that got a numerical record: the enthalpy shift (numerical minus analytic, kcal/mol) and whether its frequencies pass. The report prints it beside the bond so a replacement is never silent."""
    hartree_to_kcal = 627.5094740631
    out = {}
    for r in records:
        if r.get("completed") and r.get("numerical"):
            out[r["parent_structure"]] = {"shift_kcal": (r["enthalpy"] - r["analytic_enthalpy"]) * hartree_to_kcal, "verified": r["verified"], "lowest_frequency": r["lowest_frequency"],
                                          "analytic_lowest_frequency": r["analytic_lowest_frequency"]}
    return out


# --- the references of the three arms ----------------------------------------------------------------------------------------------------


def _refs() -> dict:
    return json.loads((HERE / "references.json").read_text(encoding="utf-8"))


def sh_d298_kcal(bond: dict, constants: dict) -> tuple[float, float]:
    """(DH298, its uncertainty) in kcal/mol of one S-H reference of `references.json`. The published ethanethiol value is returned as printed; the others are the acidity cycle plus the computed thermal step (`thermal_step.py`)."""
    if "published_d298_kcal" in bond:
        return bond["published_d298_kcal"], bond["published_d298_uncertainty_kcal"]
    ie_h = constants["ionization_energy_of_hydrogen_ev"] * constants["kj_per_mol_per_ev"]
    d0 = bond["acidity_dH0_kj"] + bond["electron_affinity_ev"] * constants["kj_per_mol_per_ev"] - ie_h
    unc0 = math.hypot(bond["acidity_dH0_uncertainty_kj"], bond["electron_affinity_uncertainty_ev"] * constants["kj_per_mol_per_ev"])
    return (d0 + bond["thermal_step_kj"]) / KJ_PER_KCAL, math.hypot(unc0, bond["thermal_step_uncertainty_kj"]) / KJ_PER_KCAL


#: (name in references.json, name of the bond row, SMILES of the parent, atom that loses the hydrogen)
SH_BONDS = [("ethanethiol S-H", "ethanethiol S-H", "CCS", 2), ("1-propanethiol S-H", "1-propanethiol S-H", "CCCS", 3), ("2-propanethiol S-H", "2-propanethiol S-H", "CC(C)S", 3)]
#: Methanethiol's S-H is the first run's lost bond (spent): computed and reported beside Arm D, outside its verdict (Nicovich 1992, 298 K).
METHANETHIOL = {"name": "methanethiol S-H", "smiles": "CS", "atom": 1, "dh298": 87.35, "uncertainty": 0.58, "element": "S", "excluded": True}


def sh_bonds() -> list[dict]:
    """Arm D's bonds in the shape the first run's selection reads, with methanethiol last and excluded (reported beside, deciding nothing)."""
    refs = _refs()
    by_name = {b["name"]: b for b in refs["sh_bonds"]}
    out = []
    for key, name, smiles, atom in SH_BONDS:
        dh, unc = sh_d298_kcal(by_name[key], refs["constants"])
        out.append({"name": name, "smiles": smiles, "atom": atom, "dh298": dh, "uncertainty": unc, "element": "S", "excluded": False})
    return out + [dict(METHANETHIOL)]


def halogen_bonds() -> list[dict]:
    """Arm C's six bonds from `benchmarks/bde_heldout/candidates_halogen.json` (ATcT 1.228), in the same shape."""
    data = json.loads((REPO / "benchmarks" / "bde_heldout" / "candidates_halogen.json").read_text(encoding="utf-8"))
    return [{"name": b["name"], "smiles": b["smiles"], "atom": b["atom"], "dh298": b["dh298_kcal"], "uncertainty": b["uncertainty_kcal"], "element": b["element"], "excluded": b["excluded"]} for b in data["bonds"]]


#: The bromine bonds: name in references.json -> (SMILES of the parent, the carbon that loses the hydrogen). A kinetics value is the bond's reference; the others are printed beside it (section 6).
BROMINE = {"bromomethane C-H": ("CBr", 0), "dibromomethane C-H": ("BrCBr", 1), "bromochloromethane C-H": ("ClCBr", 1), "bromoethane alpha C-H": ("CCBr", 1)}


def bromine_bonds() -> list[dict]:
    """Arm C-Br's bonds: the shape of the others plus the other determinations and the calculated values, all converted to kcal/mol. `excluded` is True for every one (reported only, nothing decides)."""
    out = []
    for b in _refs()["bromine_bonds"]:
        smiles, atom = BROMINE[b["name"]]
        calculated = [v / KJ_PER_KCAL for v in (b["theory_fpd_kj"], b["theory_g3mp2_kj"]) if v is not None]
        out.append({"name": b["name"], "smiles": smiles, "atom": atom, "dh298": b["kinetics_kj"] / KJ_PER_KCAL, "uncertainty": b["kinetics_uncertainty_kj"] / KJ_PER_KCAL, "element": "C", "excluded": True,
                    "others": [o["value"] / KJ_PER_KCAL for o in b["other_determinations_kj"]], "calculated": calculated})
    return out


def thiophenol_bonds() -> list[dict]:
    """Arm D-Ph's one bond (REPORTED ONLY, decision D6): thiophenol S-H, with every determination converted to 298 K and the one-sided limit.

    There is no reference. The 0 K values (Lim 2007, 76.8 +- 0.3 kcal/mol; Devine 2008, an UPPER LIMIT of 80.15) become 298 K by adding the thermal step COMPUTED for thiophenol in `thermal_step.py`; Borges dos Santos 2002 (83.5 +- 1.1) and Luo's Table 8.1 range (79.4 to 83.5) are
    printed as 298 K values. `points` are the determinations that are values; `upper_limit` is Devine's; `dh298` is the middle of the span of the points, for the table column only (nothing is read against it)."""
    refs = _refs()
    t = refs["thiophenol_context"]
    step = t["thermal_step_kj"] / KJ_PER_KCAL
    cm = refs["methanethiol_anchor"]["cm1_to_kj_per_mol"]
    points = {"Lim 2007 (0 K value plus the computed step)": t["lim2007_d0_kcal"] + step, "Borges dos Santos 2002": t["borgesdossantos2002_d298_kcal"],
              "Luo Table 8.1, low end of the range": t["luo2007_range_298_kcal"][0], "Luo Table 8.1, high end of the range": t["luo2007_range_298_kcal"][1]}
    upper = t["devine2008_d0_cm1"] * cm / KJ_PER_KCAL + step
    low, high = min(points.values()), max(points.values())
    return [{"name": "thiophenol S-H", "smiles": "Sc1ccccc1", "atom": 0, "dh298": (low + high) / 2, "uncertainty": (high - low) / 2, "element": "S", "excluded": True, "points": points, "upper_limit": upper}]


def span_reading(computed_kcal: float | None, bond: dict) -> dict:
    """Arm D-Ph: the computed value against each determination, the span of the determinations that are values, and Devine's upper limit; and the one claim section 8 allows. `gross` is True only when the computed value is MORE THAN 5.0 kcal/mol outside the whole span, on whichever side:
    the determinations disagree by about 5 kcal/mol among themselves, so anything smaller is numbers and nothing is claimed. A value above the upper limit is reported as such, never as a claim (the limit is one-sided and its own uncertainty is 0.3)."""
    if computed_kcal is None:
        return {"computed": None, "gross": False, "claim": "no computed value"}
    low, high = min(bond["points"].values()), max(bond["points"].values())
    outside = max(low - computed_kcal, computed_kcal - high, 0.0)
    return {"computed": computed_kcal, "errors": {k: computed_kcal - v for k, v in bond["points"].items()}, "span": (low, high), "outside_span": outside,
            "above_upper_limit": computed_kcal - bond["upper_limit"], "gross": outside > GROSS_ERROR,
            "claim": f"a gross failure: {outside:.2f} kcal/mol outside the whole span of the determinations" if outside > GROSS_ERROR else "no claim (numbers only)"}


# --- the reading rules (section 8) ------------------------------------------------------------------------------------------------------


def arm_verdict(deciding: "judge.Stats") -> str:
    """Arms C and D: the first run's limits (PASS at MAE <= 2.5 with no error above 5.0 and |MSE| <= 1.5; PARTIAL up to MAE 3.5), NOT EVALUABLE when two or more of the deciding bonds have no computed value.
    `judge.verdict` is not used for the missing rule because its allowance (three) is the 27-bond arm's."""
    if deciding.missing >= NOT_EVALUABLE_AT_MISSING or deciding.count == 0:
        return judge.NOT_EVALUABLE
    return judge.verdict(judge.Stats(deciding.count, 0, deciding.mae, deciding.mse, deciding.max_abs), "primary")


def standard_error(errors: list[float]) -> float | None:
    """The standard error of the mean error (sample standard deviation over the square root of n); None for fewer than two errors."""
    n = len(errors)
    if n < 2:
        return None
    mean = sum(errors) / n
    return math.sqrt(sum((e - mean) ** 2 for e in errors) / (n - 1)) / math.sqrt(n)


def near_limits(deciding: "judge.Stats", band: float) -> list[str]:
    """The limits a result sits within `band` kcal/mol of, which it therefore cannot be told to be on one side of (Arm C: 0.5; Arm D: 0.7, section 8)."""
    if deciding.count == 0:
        return []
    out = []
    for label, value, limit in (("mean absolute error", deciding.mae, judge.MAE_PASS["primary"]), ("mean absolute error (PARTIAL)", deciding.mae, judge.MAE_PARTIAL), ("largest error", deciding.max_abs, judge.MAX_ERROR),
                                ("mean signed error", abs(deciding.mse), judge.MSE_LIMIT)):
        if abs(value - limit) <= band:
            out.append(f"{label} {value:.2f} is within {band} of its limit {limit}")
    return out


def bromine_reading(computed_kcal: float | None, bond: dict) -> dict:
    """Arm C-Br: the computed value's error against (i) the kinetics value, (ii) the range of the other determinations, (iii) each calculated value; and the one claim section 8 allows. `gross` is True only when the error exceeds 5.0 kcal/mol against the kinetics
    value AND against every calculated value (for a bond with none, MORE THAN 5.0 OUTSIDE THE WHOLE RANGE of the other determinations, on whichever side the computed value lies): a smaller disagreement is reported as numbers and nothing is claimed."""
    if computed_kcal is None:
        return {"computed": None, "gross": False, "claim": "no computed value"}
    vs_kinetics = computed_kcal - bond["dh298"]
    others = bond["others"]
    vs_range = None if not others else (computed_kcal - max(others), computed_kcal - min(others))
    vs_calculated = [computed_kcal - c for c in bond["calculated"]]
    # no calculated value: the distance from the nearest end of the range of the other determinations (zero inside it), so the high and the low side are treated alike
    outside = max(min(others) - computed_kcal, computed_kcal - max(others), 0.0) if others else 0.0
    against = vs_calculated if bond["calculated"] else [outside]
    gross = abs(vs_kinetics) > GROSS_ERROR and all(abs(e) > GROSS_ERROR for e in against)
    return {"computed": computed_kcal, "vs_kinetics": vs_kinetics, "vs_others_high_low": vs_range, "vs_calculated": vs_calculated, "gross": gross,
            "claim": "a gross failure: more than 5.0 kcal/mol from the kinetics value and from the calculated value" if gross else "no claim (numbers only)"}
