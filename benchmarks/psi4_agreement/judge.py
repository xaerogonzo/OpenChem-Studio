"""The judge of `PLAN.md`: the tolerances from the floors, and the reading rule over the records. Pure arithmetic over plain records, no engine and no file read, so the rule is tested without any job
(`tests/test_psi4_agreement_judge.py`) and cannot move after a result is seen.

A record is a dict. Single points: `{"molecule", "functional", "basis", "orca", "psi4"}` with the energies in Hartree (`None` for a missing cell). Optimizations: `{"molecule", "orca", "psi4", "rmsd"}` with
the final energies in Hartree and the RMSD in Angstrom (`None` where a job is missing). `functional` is the label as a person writes it ("B3LYP", "HF", "B3LYP/G").
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import median

#: Verdicts, worst last; `NOT EVALUABLE` is decided before the others and is not "worse than FAIL", it is "no claim".
PASS, PARTIAL, FAIL, NOT_EVALUABLE = "PASS", "PARTIAL", "FAIL", "NOT EVALUABLE"
_ORDER = {PASS: 0, PARTIAL: 1, FAIL: 2}

#: The tolerances never fall below this (mEh): ten times ORCA's default SCF energy convergence, 1e-6 Eh.
RESOLUTION_MEH = 0.01
#: The smallest geometry tolerance (Angstrom): no optimizer here converges a structure finer than the third decimal.
RESOLUTION_ANGSTROM = 0.001
#: A tolerance above this (mEh, 0.31 kcal/mol) makes the check NOT EVALUABLE.
CEILING_MEH = 0.5
#: A combination whose MEDIAN difference exceeds this (mEh) has a systematic offset: a definitional difference between the engines. Fixed and not derived from a floor (amendment of 2026-10-19, `PLAN.md`):
#: two programs' implementations of one functional differ by a steady 0.1 to 0.2 mEh (constants, default grids) that no within-engine floor sees, while the two real definitional errors found in this
#: project were 1.8 mEh (cartesian against spherical d functions) and 37 mEh (VWN1RPA against VWN5).
SYSTEMATIC_MEH = 0.5
#: The share of cells that may be missing before the check is NOT EVALUABLE.
MISSING_LIMIT = 0.05
#: The share of cells that must be within tolerance for a PASS.
WITHIN_NEEDED = 0.95
#: A difference beyond this many tolerances is a FAIL on its own.
GROSS = 5.0
#: Floors are doubled to give tolerances.
FLOOR_FACTOR = 2.0
KCAL_PER_MEH = 0.627509
HARTREE_TO_MEH = 1000.0


@dataclass(frozen=True)
class Tolerances:
    hf_meh: float
    dft_meh: float
    opt_energy_meh: float
    geometry_angstrom: float

    def energy(self, functional: str) -> float:
        return self.hf_meh if functional.upper() == "HF" else self.dft_meh

    def relative_kcal(self, functional: str) -> float:
        """An isomer difference carries two errors: twice the class tolerance, in kcal/mol."""
        return 2.0 * self.energy(functional) * KCAL_PER_MEH

    def loudest_meh(self) -> float:
        return max(self.hf_meh, self.dft_meh, self.opt_energy_meh)


def floor(differences: list[float]) -> float:
    """The floor of a class: the largest absolute change a harmless setting made (empty = no measurement, which is an error)."""
    if not differences:
        raise ValueError("a floor needs at least one measured difference")
    return max(abs(d) for d in differences)


def tolerances(floor_hf_meh: float, floor_dft_meh: float, floor_opt_energy_meh: float, floor_rmsd_angstrom: float) -> Tolerances:
    """The tolerances of PLAN.md, from the four floors (the energies in mEh, the RMSD in Angstrom)."""
    t_dft = max(FLOOR_FACTOR * floor_dft_meh, RESOLUTION_MEH)
    return Tolerances(
        hf_meh=max(FLOOR_FACTOR * floor_hf_meh, RESOLUTION_MEH),
        dft_meh=t_dft,
        opt_energy_meh=max(t_dft, FLOOR_FACTOR * floor_opt_energy_meh),
        geometry_angstrom=max(FLOOR_FACTOR * floor_rmsd_angstrom, RESOLUTION_ANGSTROM),
    )


def _difference_meh(record: dict) -> float | None:
    if record.get("orca") is None or record.get("psi4") is None:
        return None
    return (record["psi4"] - record["orca"]) * HARTREE_TO_MEH


def _worst(verdicts: list[str]) -> str:
    return max(verdicts, key=lambda v: _ORDER[v])


@dataclass(frozen=True)
class Part:
    """One arm's verdict and what decided it."""

    verdict: str
    why: tuple[str, ...]


def judge_single_points(records: list[dict], tol: Tolerances) -> Part:
    """PLAN.md rule 2 (as amended). Per class (HF, DFT): FAIL on a systematic offset (the median d of a combination above SYSTEMATIC_MEH) or on any cell more than 5 T from its combination's median;
    else PASS at 95% of cells within T of their combination's median; else PARTIAL."""
    why: list[str] = []
    verdicts: list[str] = []
    for label, is_hf in (("HF", True), ("DFT", False)):
        cells = [r for r in records if (r["functional"].upper() == "HF") is is_hf]
        if not cells:
            continue
        limit = tol.hf_meh if is_hf else tol.dft_meh
        found = [(r, _difference_meh(r)) for r in cells]
        present = [(r, d) for r, d in found if d is not None]
        by_combination: dict[tuple[str, str], list[float]] = {}
        for r, d in present:
            by_combination.setdefault((r["functional"], r["basis"]), []).append(d)
        medians = {key: median(ds) for key, ds in by_combination.items()}
        offsets = sorted(f"{f} {b} (median {m:+.3f} mEh)" for (f, b), m in medians.items() if abs(m) > SYSTEMATIC_MEH)
        # a cell is judged against its OWN combination's median: the steady cross-engine difference is the offset's business, the scatter around it is the tolerance's
        scatter = [(r, d - medians[(r["functional"], r["basis"])]) for r, d in present]
        gross = sorted(f"{r['molecule']} {r['functional']} {r['basis']} ({s:+.3f} mEh from the median)" for r, s in scatter if abs(s) > GROSS * limit)
        within = sum(1 for _r, s in scatter if abs(s) <= limit) / max(len(present), 1)
        if offsets or gross:
            verdict = FAIL
        elif within >= WITHIN_NEEDED:
            verdict = PASS
        else:
            verdict = PARTIAL
        verdicts.append(verdict)
        why.append(f"{label}: {verdict}; T = {limit:.3f} mEh; {within:.1%} of {len(present)} cells within T of their combination's median; systematic offsets (median above {SYSTEMATIC_MEH} mEh): {offsets or 'none'}; beyond 5 T from the median: {gross or 'none'}")
    return Part(_worst(verdicts) if verdicts else NOT_EVALUABLE, tuple(why))


def relative_cells(records: list[dict], pairs: list[tuple[str, str]]) -> list[dict]:
    """The isomer differences, in kcal/mol, per pair and combination: `{"pair", "functional", "basis", "orca", "psi4"}` (None if either member is missing)."""
    index = {(r["molecule"], r["functional"], r["basis"]): r for r in records}
    out = []
    for a, b in pairs:
        for (molecule, functional, basis), ra in index.items():
            if molecule != a:
                continue
            rb = index.get((b, functional, basis))
            cell = {"pair": f"{a} / {b}", "functional": functional, "basis": basis, "orca": None, "psi4": None}
            if rb is not None and None not in (ra["orca"], rb["orca"], ra["psi4"], rb["psi4"]):
                cell["orca"] = (ra["orca"] - rb["orca"]) * HARTREE_TO_MEH * KCAL_PER_MEH
                cell["psi4"] = (ra["psi4"] - rb["psi4"]) * HARTREE_TO_MEH * KCAL_PER_MEH
            out.append(cell)
    return out


def judge_relative(cells: list[dict], tol: Tolerances) -> Part:
    """PLAN.md rule 3, on cells whose energies are already in kcal/mol: FAIL above 5 T_rel, else PASS at 95% within T_rel, else PARTIAL."""
    present = [(c, c["psi4"] - c["orca"]) for c in cells if c["orca"] is not None and c["psi4"] is not None]
    if not present:
        return Part(NOT_EVALUABLE, ("no relative energy could be formed",))
    gross = sorted(f"{c['pair']} {c['functional']} {c['basis']} ({d:+.3f} kcal/mol)" for c, d in present if abs(d) > GROSS * tol.relative_kcal(c["functional"]))
    within = sum(1 for c, d in present if abs(d) <= tol.relative_kcal(c["functional"])) / len(present)
    if gross:
        verdict = FAIL
    elif within >= WITHIN_NEEDED:
        verdict = PASS
    else:
        verdict = PARTIAL
    return Part(verdict, (f"relative energies: {verdict}; {within:.1%} of {len(present)} cells within T_rel; beyond 5 T_rel: {gross or 'none'}",))


def judge_optimizations(records: list[dict], tol: Tolerances) -> Part:
    """PLAN.md rule 4: FAIL if any energy difference is above 5 T_Eopt or any RMSD above 5 T_geom; else PASS if every molecule is within both; else PARTIAL."""
    present = [r for r in records if r.get("rmsd") is not None and _difference_meh(r) is not None]
    if not present:
        return Part(NOT_EVALUABLE, ("no optimization could be compared",))
    energy_gross = [r["molecule"] for r in present if abs(_difference_meh(r)) > GROSS * tol.opt_energy_meh]
    geometry_gross = [r["molecule"] for r in present if r["rmsd"] > GROSS * tol.geometry_angstrom]
    outside = [r["molecule"] for r in present if abs(_difference_meh(r)) > tol.opt_energy_meh or r["rmsd"] > tol.geometry_angstrom]
    if energy_gross or geometry_gross:
        verdict = FAIL
    elif not outside:
        verdict = PASS
    else:
        verdict = PARTIAL
    return Part(verdict, (f"optimizations: {verdict}; T_E = {tol.opt_energy_meh:.3f} mEh, T_geom = {tol.geometry_angstrom:.4f} A; outside: {outside or 'none'}; "
                          f"energy beyond 5 T: {energy_gross or 'none'}; geometry beyond 5 T: {geometry_gross or 'none'}",))


def missing_share(single_points: list[dict], optimizations: list[dict]) -> float:
    """The larger share of missing cells of the two arms (a cell is missing when either engine's value is)."""
    shares = []
    for records in (single_points, optimizations):
        if records:
            shares.append(sum(1 for r in records if _difference_meh(r) is None or ("rmsd" in r and r["rmsd"] is None)) / len(records))
    return max(shares) if shares else 1.0


def judge(single_points: list[dict], optimizations: list[dict], pairs: list[tuple[str, str]], tol: Tolerances) -> tuple[str, list[str]]:
    """PLAN.md rules 1 and 5: NOT EVALUABLE on a floor above the ceiling or too many missing cells, else the worst of the three arms."""
    if tol.loudest_meh() > CEILING_MEH:
        return NOT_EVALUABLE, [f"a tolerance is {tol.loudest_meh():.3f} mEh, above the {CEILING_MEH} mEh ceiling"]
    share = missing_share(single_points, optimizations)
    if share > MISSING_LIMIT:
        return NOT_EVALUABLE, [f"{share:.1%} of the cells are missing, above the {MISSING_LIMIT:.0%} limit"]
    parts = [
        judge_single_points(single_points, tol),
        judge_relative(relative_cells(single_points, pairs), tol),
        judge_optimizations(optimizations, tol),
    ]
    if any(p.verdict == NOT_EVALUABLE for p in parts):
        return NOT_EVALUABLE, [line for p in parts for line in p.why]
    return _worst([p.verdict for p in parts]), [line for p in parts for line in p.why]
