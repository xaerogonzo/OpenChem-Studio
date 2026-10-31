"""Phase B crystal density: the published candidates D1 (Tarver 1979) and D4 (Keshavarz 2009, two papers), and Candidate D (the project's refit).

`PREREGISTRATION.md` sections 10.1, 15.7 and 17 say what this is for.  Nothing here compares a prediction with a label of the COD corpus.

What is committed (and why):
 * the **method parameters** of the three published methods, as printed (Tarver's group molar volumes, Keshavarz's two correlations), because
   a candidate cannot be evaluated without them and they are short;
 * **Candidate D's fixed specification** (the group list, the ridge grid, the weights, the refusals), written before any fitting;
 * a **manifest of entity keys** (`density_candidates_manifest.json`) for each published candidate's printed compounds: it carries no names, no
   measured values and no printed calculated values, because the three papers' tables (about 360 rows) are a bulk transcription and stay in the
   maintainer's private notes (`energetics-phase-b/density-candidates/`, owner's instruction of 2026-10-26); the manifest records their SHA-256.

The transcriptions were checked three ways, all recorded in the manifest's `checks`: each Tarver row against its own group sums, densities and
errors; each Keshavarz row against its printed correlation (with the ED/EI or CPG/CNG values the paper's rules allow); and, between papers, the
84 compounds Keshavarz's tables share with Tarver's against Keshavarz's own "Tarver" column (80 agree to the printed digit).
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
MANIFEST_PATH = HERE / "density_candidates_manifest.json"
BUILDER_VERSION = "epb-density-candidates-1"
PRIVATE_DIR_ENV = "OPENCHEM_DENSITY_CANDIDATES_DIR"   # where the private transcriptions live; unset = the full checks are NOT_RUN

# ------------------------------------------------------------------------------------------------ Tarver 1979 (D1)
# Group molar volumes, cm3/mol, J. Chem. Eng. Data 24 (1979) 136, p.137 (Tables I footnote and II) and p.140 (Table IV).
# Keys are the paper's designations. Table IV's Greek letters are kept as printed; the print shows the tertiary C-H group
# (C-C3,H, 2.96) with a psi that looks like the capital, and C-H,O3 (26.63) with the lowercase one.
TARVER_AROMATIC = {"Ca-NO2": 29.697, "Ca-H": 11.876, "Ca-OH": 16.019, "Ca-CH3": 25.963, "Ca-NH2": 15.663}
TARVER_TABLE_II = {
    "a": ("C-C,H3", 30.68), "b": ("C-C,H2,NO2", 42.61), "c": ("C-C2,H2", 15.69), "d": ("C-C2,H,NO2", 29.16),
    "e": ("C-C,(NO2)3", 74.86), "f": ("C-C,H,(NO2)2", 59.12), "g": ("C-C2,(NO2)2", 40.87), "h": ("C-C,O,=O", 21.88),
    "i": ("C-C,H2,O", 16.84), "j": ("C-C,H2,OH", 28.00), "k": ("C-C,H2,F", 31.22), "l": ("C-C2,H,OH", 15.12),
    "m": ("C-C3,OH", 1.94), "n": ("C-C,=O,OH", 23.01), "o": ("C-C,H,=C", 12.11), "p": ("C-C,H2,ONO2 (PETN)", 34.41),
    "q": ("C-H2,=C", 20.05), "r": ("C-C,F2,NO2", 59.92), "s": ("C-C2,F2", 25.63), "t": ("C-C,F3", 46.28),
    "u": ("C-C,F,(NO2)2", 65.83), "v": ("C-H2,O2", 33.32), "w": ("C-C,H2,ONO2 (NG)", 51.21), "x": ("C-C4", 41.49),
    "y": ("C-C3,NO2", 71.23), "z": ("C-C2,H,ONO2", 40.39),
}
TARVER_TABLE_IV = {
    "α": ("C-C,H2,NH2", 34.42), "β": ("C-C2,H,NH2", 22.49), "γ": ("C-C,H2,NH", 20.64), "δ": ("C-C2,H,NH", 8.42),
    "ε": ("C-H3,NH", 32.87), "η": ("C-C,H2,N", 16.09), "θ": ("C-H3,N", 31.00), "κ": ("C-C,H2,N-NO2", 25.57),
    "cκ": ("[C-C,H2,N-NO2]c", 26.80), "λ": ("C-C2,H,N-NO2", 9.70), "ξ": ("C-H3,N-NO2", 38.32),
    "σ": ("[C-H2,O,N-NO2]c", 28.02), "τ": ("C-O4", 28.45), "ψ": ("C-H,O3", 26.63), "χ": ("C-C,O,F2", 26.78), "Ψ": ("C-C3,H", 2.96),
    "ca": ("(C-C2,H2)c", 18.38), "cb": ("[C-H2,(N-NO2)2]c", 41.60),
    "[C-C2,H2]c=8": ("(C-C2,H2)c=8, no letter printed", 16.80), "[C-H2,(N-NO2)2]c=8": ("[C-H2,(N-NO2)2]c=8, no letter printed", 40.02),
    "cc": ("(C-C,H2,O)c", 21.75), "cd": ("(C-C,H,=C)c", 15.12), "ce": ("(C-H,O,=C)c", 20.66), "cf": ("(C-H,=C,NH)c", 19.81),
    "cg": ("(N-C,H,NH)c", 11.45), "ch": ("(C-H,=C,N)c + (C-H,N,=N)c", 46.27), "ci": ("(C-C,H2,NH)c", 22.35),
    "cj": ("(C-C2,=O)c", 13.44), "ck": ("(C-C2,H,NO2)c", 31.58), "cl": ("(C-C2,H,OH)c", 12.17), "cm": ("(C-C4)c", 24.67),
    "cn": ("(C-O4)c", 11.63), "co": ("(C-NO2,O,=C)c", 33.53), "cp": ("(C-C,F,=C)c", 20.21), "cq": ("(C-C,H,O,NO2)c", 36.04),
    "cr": ("[C-C2,(NO2)2]c", 43.56), "cs": ("[C-(N-NO2)2,=O]c", 36.66), "ct": ("[C-C,H,(N-NO2)2]c", 42.68),
    "cu": ("[C-C,F,(N-NO2)2]c", 47.77), "cv": ("[C-F2,(N-NO2)2]c", 51.78), "cw": ("(C-C2,=N)c + (N-O,=C)c", 15.92),
    "cx": ("(C-H,C,=N)c + (N-O,=C)c", 28.28), "cy": ("(C-C,N,=N)c + (N-C,=C)c", 11.82), "cz": ("(C-C,O,=N)c + (N-O,=C)c", 20.38),
    "[Ca-N(H,C)]": ("Ca-N(H,C), no letter printed", 20.38), "[Ca-N(C,C)]": ("Ca-N(C,C), no letter printed", 8.54),
    "[Ca-N(C,NO2)]": ("Ca-N(C,NO2), no letter printed", 21.66),
}


def tarver_volume_table() -> dict[str, float]:
    """Every designation the paper's rows use, mapped to its molar volume (aromatic groups as '[Ca-H]' etc. in a row's text)."""
    out = {k: v for k, (_, v) in TARVER_TABLE_II.items()}
    out.update({k: v for k, (_, v) in TARVER_TABLE_IV.items()})
    out.update({f"[{k}]": v for k, v in TARVER_AROMATIC.items()})
    return out


def parse_tarver_groups(expr: str) -> dict[str, int]:
    """Counts from a 'groups present' cell, e.g. `2(a + c + h + i)`, `3[Ca-NO2] + 2[Ca-H] + θ`, `4[C-H2,(N-NO2)2]c=8`."""
    def split_top(text: str) -> list[str]:
        out, depth, cur = [], 0, ""
        for ch in text:
            depth += ch == "("
            depth -= ch == ")"
            if ch == "+" and depth == 0:
                out.append(cur)
                cur = ""
            else:
                cur += ch
        out.append(cur)
        return out

    def count(text: str, mult: int, acc: dict[str, int]) -> dict[str, int]:
        for term in split_top(text):
            m = re.match(r"^(\d*)(.*)$", term)
            k = int(m.group(1)) if m.group(1) else 1
            rest = m.group(2)
            if rest.startswith("("):
                count(rest[1:-1], mult * k, acc)
            else:
                acc[rest] = acc.get(rest, 0) + mult * k
        return acc

    return count(expr.replace(" ", ""), 1, {})


def tarver_volume(groups: dict[str, int]) -> float:
    table = tarver_volume_table()
    unknown = [g for g in groups if g not in table]
    if unknown:
        raise KeyError(f"group(s) not in Tarver's tables: {unknown}")
    return sum(table[g] * n for g, n in groups.items())


def tarver_density(mol_wt: float, groups: dict[str, int]) -> float:
    return mol_wt / tarver_volume(groups)


# ------------------------------------------------------------------------------------------------ Keshavarz 2009 (D4)
# Nitroaliphatics, nitrate esters, nitramines (J. Hazard. Mater. 169, 158), Eq. (6): a, b, c = numbers of C, H, N atoms.
KESHAVARZ_NITRO = {"z1": 1.521, "C": 6.946, "H": -11.53, "N": 20.10, "ED": -0.1559, "EI": 0.1325}
KESHAVARZ_NITRO_ED = (0.0, 0.5, 0.75, 1.0, 1.5, 1.7)
KESHAVARZ_NITRO_EI = (0.0, 0.4, 0.5, 0.75, 1.0)
# Polynitro arenes and heteroarenes (J. Hazard. Mater. 165, 579), Eq. (5): a', b', c', d' = numbers of C, H, N, O divided by the molecular weight.
# The paper prints the CNG coefficient as -0.751. Every row of its Tables 1-4 that carries a CNG value is reproduced with -0.0751 and none with
# -0.751 (a difference of 0.68 per CNG unit): the constant below is the one that reproduces the paper's own tables; the printed one is kept beside it.
KESHAVARZ_ARENE = {"y1": -1.609, "C": 29.20, "H": 1.515, "N": 53.06, "O": 61.30, "CPG": 0.0703, "CNG": -0.0751}
KESHAVARZ_ARENE_CNG_AS_PRINTED = -0.751
KESHAVARZ_ARENE_CPG = (0.0, 0.5, 1.0, 2.0, 3.0)
KESHAVARZ_ARENE_CNG = (0.0, 0.75, 1.0, 1.5, 2.0)


def keshavarz_nitro_density(n_c: int, n_h: int, n_n: int, mol_wt: float, ed: float, ei: float) -> float:
    k = KESHAVARZ_NITRO
    return k["z1"] + k["C"] * n_c / mol_wt + k["H"] * n_h / mol_wt + k["N"] * n_n / mol_wt + k["ED"] * ed + k["EI"] * ei


def keshavarz_arene_density(n_c: int, n_h: int, n_n: int, n_o: int, mol_wt: float, cpg: float, cng: float) -> float:
    k = KESHAVARZ_ARENE
    return (k["y1"] + k["C"] * n_c / mol_wt + k["H"] * n_h / mol_wt + k["N"] * n_n / mol_wt + k["O"] * n_o / mol_wt
            + k["CPG"] * cpg + k["CNG"] * cng)


def _allowed_nitro_terms() -> list[float]:
    return sorted({round(KESHAVARZ_NITRO["ED"] * e + KESHAVARZ_NITRO["EI"] * i, 4) for e in KESHAVARZ_NITRO_ED for i in KESHAVARZ_NITRO_EI})


def _allowed_arene_terms() -> list[float]:
    return sorted({round(KESHAVARZ_ARENE["CPG"] * p + KESHAVARZ_ARENE["CNG"] * g, 4) for p in KESHAVARZ_ARENE_CPG for g in KESHAVARZ_ARENE_CNG})


def explains_nitro(n_c, n_h, n_n, mol_wt, printed, tol=0.0045) -> bool:
    """Is the printed 'new method' density the correlation plus some ED/EI term the paper's rules allow? (A formula check, not a proof of identity.)"""
    resid = printed - keshavarz_nitro_density(n_c, n_h, n_n, mol_wt, 0.0, 0.0)
    return any(abs(resid - t) < tol for t in _allowed_nitro_terms())


def explains_arene(n_c, n_h, n_n, n_o, mol_wt, printed, tol=0.0045) -> bool:
    resid = printed - keshavarz_arene_density(n_c, n_h, n_n, n_o, mol_wt, 0.0, 0.0)
    return any(abs(resid - t) < tol for t in _allowed_arene_terms())


# ------------------------------------------------------------------------------------------------ Candidate D (15.7, section 17.4)
# density = M / V,  V = sum_E v_E n_E + sum_g w_g n_g   (cm3/mol), intercept-free.
# The element list, the ten groups, the ridge grid, the weights and the refusals are fixed here, before any fitting, and are not edited after.
CANDIDATE_D_ELEMENTS = ("C", "H", "N", "O", "F", "Cl", "Br", "S")
# name -> SMARTS (counted as non-overlapping matches of the whole pattern's first atom set), or a ring rule handled in `candidate_d_counts`.
CANDIDATE_D_GROUPS: dict[str, str | None] = {
    "c_nitro": "[#6][N+](=O)[O-]",
    "n_nitro": "[#7][N+](=O)[O-]",
    "nitrate_ester": "[#6]O[N+](=O)[O-]",
    "azide": "N=[N+]=[N-]",
    "n_oxide": "[#7+;!$([N+](=O)[O-]);!$([N+]=[N-])][O-]",
    "furazan": "[#8;r5]1~[#7]~[#6]~[#6]~[#7]~1",
    "amino_ortho_nitro": "[NX3;H1,H2;!$(N[#7,#8])]c:c[N+](=O)[O-]",
    "hydroxyl": "[OX2H][#6]",
    "polyazole": None,          # a five-membered ring with at least three nitrogen atoms (ring rule)
    "aromatic_ring": None,      # an aromatic ring (ring rule)
}
CANDIDATE_D_RIDGE_GRID = (0.01, 0.1, 1.0, 10.0, 100.0)     # on the group coefficients only; chosen by the lowest density MAE on selection
CANDIDATE_D_MIN_ROWS_PER_PARAMETER = 10                     # 18 parameters, so at least 180 verified development rows, else it is not offered
CANDIDATE_D_WEIGHT = "1/V_exp"                              # weighted least squares on V_exp = M / rho_exp, weights 1/V_exp (relative error in V)


def candidate_d_parameter_count() -> int:
    return len(CANDIDATE_D_ELEMENTS) + len(CANDIDATE_D_GROUPS)


def candidate_d_counts(mol) -> dict[str, int] | None:
    """Element and group counts of a molecule (with or without hydrogens), or None when it holds an element outside the list (a refusal)."""
    from rdkit import Chem

    mh = Chem.AddHs(mol)
    elements = {s: 0 for s in CANDIDATE_D_ELEMENTS}
    for atom in mh.GetAtoms():
        if atom.GetSymbol() not in elements:
            return None
        elements[atom.GetSymbol()] += 1
    counts = dict(elements)
    for name, smarts in CANDIDATE_D_GROUPS.items():
        if smarts is not None:
            patt = Chem.MolFromSmarts(smarts)
            counts[name] = len(mh.GetSubstructMatches(patt, uniquify=True))
    ri = mh.GetRingInfo()
    counts["polyazole"] = sum(1 for ring in ri.AtomRings() if len(ring) == 5 and sum(1 for i in ring if mh.GetAtomWithIdx(i).GetSymbol() == "N") >= 3)
    counts["aromatic_ring"] = sum(1 for ring in ri.AtomRings() if all(mh.GetAtomWithIdx(i).GetIsAromatic() for i in ring))
    return counts


def fit_candidate_d(rows: list[tuple[dict[str, int], float, float]], ridge: float) -> dict[str, float]:
    """`rows` are (counts, mol_wt, density). Returns the coefficients; a column that is all zero in `rows` is left out (that group is unfitted and refuses)."""
    import numpy as np

    names = list(CANDIDATE_D_ELEMENTS) + list(CANDIDATE_D_GROUPS)
    present = [n for n in names if any(c.get(n, 0) for c, _, _ in rows)]
    x = np.array([[c.get(n, 0) for n in present] for c, _, _ in rows], dtype=float)
    v = np.array([mw / rho for _, mw, rho in rows], dtype=float)
    w = 1.0 / v
    xw = x * w[:, None]
    penalty = np.diag([ridge if n in CANDIDATE_D_GROUPS else 0.0 for n in present])
    beta = np.linalg.solve(xw.T @ xw + penalty, xw.T @ (v * w))
    return dict(zip(present, (float(b) for b in beta)))


def predict_candidate_d(coef: dict[str, float], counts: dict[str, int] | None, mol_wt: float) -> float | None:
    """None is a refusal: an unlisted element, a group the fit never saw, or a non-positive volume."""
    if counts is None:
        return None
    volume = 0.0
    for name, n in counts.items():
        if n and name not in coef:
            return None
        volume += coef.get(name, 0.0) * n
    return mol_wt / volume if volume > 0 else None


# ------------------------------------------------------------------------------------------------ the manifest and the private checks
def load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def private_dir() -> Path | None:
    value = os.environ.get(PRIVATE_DIR_ENV)
    return Path(value) if value else None


def verify_tarver_rows(rows: list[dict]) -> list[str]:
    """Problems found in the transcribed Tarver rows (empty list = every row reproduces from the committed group tables); a row that fails is
    reported by its id, and the printed inconsistencies the manifest lists are expected to be exactly these."""
    problems = []
    for r in rows:
        rid = f"{r['table']}:{r['row']}"
        try:
            vol = tarver_volume(parse_tarver_groups(r["groups"]))
        except KeyError as exc:
            problems.append(f"{rid} unknown group {exc}")
            continue
        if abs(vol - r["calc_vol"]) > 0.03:
            problems.append(f"{rid} volume {vol:.2f} vs printed {r['calc_vol']}")
        if abs(r["mw"] / r["calc_vol"] - r["calc_den"]) > 0.0007:
            problems.append(f"{rid} density {r['mw'] / r['calc_vol']:.4f} vs printed {r['calc_den']}")
        me = r["measd"]
        if me is not None and r["pct_err"] is not None and not isinstance(me, list):
            pct = 100 * abs(r["calc_den"] - me) / me
            if abs(pct - r["pct_err"]) > 0.05:
                problems.append(f"{rid} error {pct:.3f} vs printed {r['pct_err']}")
    return problems


def run_private_checks(directory: Path) -> dict:
    """Re-run the arithmetic checks on the private transcriptions (needs the directory; the CI cannot)."""
    from rdkit import Chem
    from rdkit.Chem import Descriptors

    out = {"tarver_problems": verify_tarver_rows(json.loads((directory / "tarver1979_full.json").read_text(encoding="utf-8"))["tarver_rows"])}
    for label, fname, explain in (("keshavarz_nitro", "keshavarz2009_nitro_rows.json", "nitro"), ("keshavarz_arene", "keshavarz2009_arene_rows.json", "arene")):
        unexplained = []
        for r in json.loads((directory / fname).read_text(encoding="utf-8")):
            if not r.get("smiles"):
                continue
            mh = Chem.AddHs(Chem.MolFromSmiles(r["smiles"]))
            n = {s: sum(1 for a in mh.GetAtoms() if a.GetSymbol() == s) for s in "CHNO"}
            mw = Descriptors.MolWt(mh)
            ok = (explains_nitro(n["C"], n["H"], n["N"], mw, r["calc_new"]) if explain == "nitro"
                  else explains_arene(n["C"], n["H"], n["N"], n["O"], mw, r["calc_new"]))
            if not ok:
                unexplained.append(f"{r['table']}:{r['row']}")
        out[f"{label}_unexplained"] = unexplained
    return out
