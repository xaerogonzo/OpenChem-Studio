"""Builds the held-out X-H bonds of the bond-dissociation benchmark from the Active Thermochemical Tables, and checks the arithmetic against bonds whose reference we already hold.

    python extract_atct.py "<path to 'ATcT Thermochemical Values ver. 1.228.htm'>"      writes candidates.json and crosscheck_v1.json beside this file

WHY THIS EXISTS (`benchmarks/restart_v2/PREREGISTRATION.md`): Blanksby and Ellison's Table 1 has no in-scope X-H bond that the first run did not already use, so the held-out arm takes its references from ATcT [source:ruscic2004]
(version 1.228, 3,455 species, enthalpies of formation at 298.15 K in kJ/mol with uncertainties). A bond enthalpy is `DH298 = dfH(R.) + dfH(H.) - dfH(RH)`, and its uncertainty the root sum of squares of the three.

THE BONDS ARE CHOSEN BY RULE, NOT BY LOOKING AT VALUES: `PAIRS` is every (closed-shell parent, radical) pair of the table's gas-phase species with at most ten heavy atoms of H, C, N, O, P, S in which the radical is the parent minus one hydrogen at ONE named site
(written down from the table's own names, each pair verified here by formula), minus the bonds of the first run. The list was written before any enthalpy of it was computed. Three pairs are EXCLUDED, with their reason and what would lift it, in `EXCLUDED`.
Run on the file as saved on 2026-10-22; the parse is of the table's own rows and fails loudly if it finds a different count.
"""
from __future__ import annotations

import html
import json
import math
import re
import sys
from pathlib import Path

from rdkit import Chem

HERE = Path(__file__).resolve().parent
KJ_PER_KCAL = 4.184
#: The table this was built from: its species count (a different file is a different version and must be re-checked by a person).
EXPECTED_SPECIES_ROWS = 3455
ELEMENTS = {"H", "C", "N", "O", "P", "S"}

#: (parent's ATcT name, parent SMILES, index of the heavy atom that loses the hydrogen, radical's ATcT name). One line per bond; both names are the table's own.
PAIRS = [
    ("Propane", "CCC", 0, "n-Propyl"),
    ("Ethanol", "CCO", 0, "2-Hydroxyethyl"),
    ("Ethanol", "CCO", 1, "1-Hydroxyethyl"),
    ("Propene", "C=CC", 1, "1-Methylethenyl"),
    ("Propyne", "C#CC", 2, "Propargyl"),
    ("Propyne", "C#CC", 0, "1-Propynyl"),
    ("Methylamine", "CN", 1, "Methylamidogen"),
    ("Methylamine", "CN", 0, "Aminomethyl"),
    ("Hydrazine", "NN", 0, "Hydrazino"),
    ("Methyl hydroperoxide", "COO", 0, "Hydroperoxymethyl"),
    ("n-Butane", "CCCC", 0, "n-Butyl"),
    ("1,3-Butadiene", "C=CC=C", 0, "1,3-Butadienyl"),
    ("Ethylamine", "CCN", 2, "Ethylamidogen"),
    ("Ethylamine", "CCN", 1, "1-Aminoethyl"),
    ("Ethylamine", "CCN", 0, "2-Aminoethyl"),
    ("Acetonitrile", "CC#N", 0, "Cyanomethyl"),
    ("Methoxymethane", "COC", 0, "Methoxymethyl"),
    ("Propionaldehyde", "CCC=O", 2, "1-Oxopropyl"),
    ("Dimethyl sulfide", "CSC", 0, "(Methylthio)methyl"),
    ("Hydroxylamine", "NO", 1, "Aminooxy"),
    ("Hydroxylamine", "NO", 0, "Hydroxyamidogen"),
    ("Acrolein", "C=CC=O", 2, "Acryloyl"),
    ("Methanimine", "C=N", 1, "Methyleneamidogen"),
    ("Methanimine", "C=N", 0, "Iminomethyl"),
    ("Ethanimine", "CC=N", 2, "Ethylideneamidogen"),
    ("Ethanimine", "CC=N", 1, "1-Iminoethyl"),
    ("Formaldoxime", "C=NO", 2, "Formaldiminoxy"),
    ("Isocyanic acid", "N=C=O", 0, "Cyanooxidanyl"),
    ("Hydrazoic acid", "N=[N+]=[N-]", 0, "Azido radical"),
    ("Ketene", "C=C=O", 0, "Ketenyl"),
]

#: The excluded bonds, by (parent, radical), each with why and what would lift it. An exclusion is a scope statement, recorded so it can be revisited, never a silent drop.
EXCLUDED = {
    ("Isocyanic acid", "Cyanooxidanyl"): {
        "reason": "the radical NCO is a linear heteroallene-type pi radical (a Renner-Teller case), not an ordinary doublet; the first run's scope was ordinary doublet radicals",
        "evidence": "Luo's handbook (Table 7.1.1) lists five experimental H-NCO values, from 109.6 to 111.5 kcal/mol, so the experimental reference itself is not tight",
        "would_lift": "a preregistered scope for linear pi radicals with its own check of the single-reference unrestricted treatment (a multireference or CCSD(T) energy of NCO, N3 and HCCO at the ORCA geometry), or a published M06-2X error for these radicals",
    },
    ("Hydrazoic acid", "Azido radical"): {
        "reason": "the radical N3 is a linear, strongly correlated pi radical, not an ordinary doublet",
        "evidence": "Luo's handbook (Table 7.1.1) lists five experimental H-N3 values spanning 88.7 to 93.7 kcal/mol, about five kcal/mol, so the experimental reference is the loosest of the three",
        "would_lift": "the same preregistered linear-pi-radical scope and check as NCO; ATcT's own value is tight, but the spread of the older measurements says the radical is hard to pin",
    },
    ("Ketene", "Ketenyl"): {
        "reason": "the radical HCCO is a bent-linear pi/sigma radical with a low-lying excited state, not an ordinary doublet; the parent is a cumulene",
        "evidence": "none read yet beyond ATcT's own value; Luo's handbook has ketene entries (pages 113, 219, 491 of the PDF) that were not used",
        "would_lift": "the same preregistered linear-pi-radical scope; read Luo's ketene entries and the literature on HCCO's electronic states first",
    },
}


def _clean(cell: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", cell)).replace("\xa0", " ").strip()


def parse_atct(path: Path) -> list[dict]:
    """The table's rows as dicts. Fails if the species count is not the one this was built from."""
    text = path.read_text(encoding="utf-8", errors="replace")
    rows = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", text, flags=re.S | re.I):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, flags=re.S | re.I)
        if len(cells) != 9:
            continue
        name, formula, _image, h0, h298, unc, units, _mass, atct_id = (_clean(c) for c in cells)
        rows.append({"name": name, "formula": formula, "h298": h298, "uncertainty": unc, "units": units, "id": atct_id})
    if len(rows) != EXPECTED_SPECIES_ROWS:
        raise SystemExit(f"{len(rows)} species rows, expected {EXPECTED_SPECIES_ROWS}: a different version of the table, which a person must check before this is run")
    return rows


def _number(text: str) -> float:
    return float(re.sub(r"[^0-9.]", "", text))


def gas_row(rows: list[dict], name: str) -> dict:
    found = [r for r in rows if r["name"] == name and r["formula"].rstrip().endswith("(g)") and r["units"] == "kJ/mol"]
    if len(found) != 1:
        raise SystemExit(f"{name!r}: {len(found)} gas-phase rows")
    return found[0]


def atct_composition(formula: str) -> dict[str, int]:
    f = re.sub(r"\s*\(.*?\)\s*$", "", formula).replace(" ", "")
    while "(" in f:
        m = re.search(r"\(([^()]*)\)(\d*)", f)
        f = f[:m.start()] + m.group(1) * int(m.group(2) or 1) + f[m.end():]
    out: dict[str, int] = {}
    for element, n in re.findall(r"([A-Z][a-z]?)(\d*)", f):
        out[element] = out.get(element, 0) + int(n or 1)
    return out


def composition(mol: Chem.Mol) -> dict[str, int]:
    out: dict[str, int] = {}
    for atom in mol.GetAtoms():
        out[atom.GetSymbol()] = out.get(atom.GetSymbol(), 0) + 1
    return {k: v for k, v in out.items() if v}


def site_class(smiles: str, atom: int) -> tuple[str, int]:
    """The parent's canonical SMILES and the symmetry class of the atom that loses the hydrogen: what makes two bonds the same bond."""
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    ranks = list(Chem.CanonicalRankAtoms(mol, breakTies=False))
    return Chem.MolToSmiles(Chem.RemoveHs(mol)), int(ranks[atom])


def bond_enthalpy(parent: dict, radical: dict, hydrogen: dict) -> tuple[float, float]:
    """(DH298, its uncertainty) in kcal/mol from the three enthalpies of formation, kJ/mol, as the table gives them."""
    dh = _number_signed(radical["h298"]) + _number_signed(hydrogen["h298"]) - _number_signed(parent["h298"])
    unc = math.sqrt(sum(_number(x["uncertainty"]) ** 2 for x in (parent, radical, hydrogen)))
    return dh / KJ_PER_KCAL, unc / KJ_PER_KCAL


def _number_signed(text: str) -> float:
    return float(text)


def build(rows: list[dict]) -> list[dict]:
    hydrogen = gas_row(rows, "Hydrogen atom")
    out = []
    for parent_name, smiles, atom, radical_name in PAIRS:
        mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
        parent, radical = gas_row(rows, parent_name), gas_row(rows, radical_name)
        parent_formula = composition(mol)
        if atct_composition(parent["formula"]) != parent_formula:
            raise SystemExit(f"{parent_name}: the SMILES {smiles} is not the table's formula {parent['formula']}")
        if not [n for n in mol.GetAtomWithIdx(atom).GetNeighbors() if n.GetAtomicNum() == 1]:
            raise SystemExit(f"{parent_name}: atom {atom} has no hydrogen")
        radical_formula = dict(parent_formula, H=parent_formula["H"] - 1)
        if atct_composition(radical["formula"]) != {k: v for k, v in radical_formula.items() if v}:
            raise SystemExit(f"{radical_name} is not {parent_name} minus one hydrogen")
        dh, unc = bond_enthalpy(parent, radical, hydrogen)
        entry = {
            "name": f"{parent_name.lower()} {mol.GetAtomWithIdx(atom).GetSymbol()}-H ({radical_name})",
            "parent": parent_name, "parent_atct_id": parent["id"], "parent_dfH298_kj": float(parent["h298"]), "parent_uncertainty_kj": _number(parent["uncertainty"]),
            "smiles": smiles, "atom": atom, "element": mol.GetAtomWithIdx(atom).GetSymbol(),
            "radical": radical_name, "radical_atct_id": radical["id"], "radical_dfH298_kj": float(radical["h298"]), "radical_uncertainty_kj": _number(radical["uncertainty"]),
            "hydrogen_atom_atct_id": hydrogen["id"], "hydrogen_atom_dfH298_kj": float(hydrogen["h298"]), "hydrogen_atom_uncertainty_kj": _number(hydrogen["uncertainty"]),
            "dh298_kcal": round(dh, 3), "uncertainty_kcal": round(unc, 3),
        }
        excluded = EXCLUDED.get((parent_name, radical_name))
        entry["excluded"] = excluded is not None
        if excluded:
            entry["exclusion"] = excluded
        out.append(entry)
    return out


#: The first run's bonds that ATcT can also give, by the table's names: the check that this arithmetic reproduces references already held.
CROSSCHECK = {
    "methane C-H": ("Methane", "Methyl"), "ethane C-H": ("Ethane", "Ethyl"), "propane secondary C-H": ("Propane", "iso-Propyl"), "ethene C-H": ("Ethylene", "Vinyl"),
    "ethyne C-H": ("Acetylene", "Ethynyl"), "benzene C-H": ("Benzene", "Phenyl"), "propene allylic C-H": ("Propene", "Allyl"), "toluene benzylic C-H": ("Toluene", "Benzyl"),
    "methanol C-H": ("Methanol", "Hydroxymethyl"), "methanol O-H": ("Methanol", "Methoxy"), "ethanol O-H": ("Ethanol", "Ethoxy"), "ammonia N-H": ("Ammonia", "Amidogen"),
    "water O-H": ("Water", "Hydroxyl"), "hydrogen peroxide O-H": ("Hydrogen peroxide", "Dioxidanyl"), "methyl hydroperoxide O-H": ("Methyl hydroperoxide", "Methylperoxy"),
    "formaldehyde C-H": ("Formaldehyde", "Formyl"), "acetaldehyde formyl C-H": ("Acetaldehyde", "Acetyl"), "acetaldehyde methyl C-H": ("Acetaldehyde", "Vinoxy"),
    "hydrogen cyanide C-H": ("Hydrogen cyanide", "Nitrilomethyl"), "hydrogen sulfide S-H": ("Hydrogen sulfide", "Sulfanyl"), "phenol O-H": ("Phenol", "Phenoxy"),
    "ethyl hydroperoxide O-H": ("Ethyl hydroperoxide", "Ethylperoxy"),
}


def crosscheck(rows: list[dict], first_run: list[dict]) -> list[dict]:
    """ATcT's DH298 against Blanksby and Ellison's for the first run's bonds both sources cover."""
    hydrogen = gas_row(rows, "Hydrogen atom")
    reference = {b["name"]: b for b in first_run}
    out = []
    for name, (parent_name, radical_name) in CROSSCHECK.items():
        dh, unc = bond_enthalpy(gas_row(rows, parent_name), gas_row(rows, radical_name), hydrogen)
        be = reference[name]
        out.append({"bond": name, "atct_dh298": round(dh, 3), "atct_uncertainty": round(unc, 3), "be_dh298": be["dh298"], "be_uncertainty": be["uncertainty"], "difference": round(dh - be["dh298"], 3)})
    return out


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    rows = parse_atct(Path(sys.argv[1]))
    candidates = build(rows)
    (HERE / "candidates.json").write_text(json.dumps({"source": "ATcT version 1.228, enthalpies of formation at 298.15 K (kJ/mol), saved 2026-10-22", "bonds": candidates}, indent=1), encoding="utf-8")
    first_run = json.loads((HERE.parent / "bde" / "reference_values.json").read_text(encoding="utf-8"))["bonds"]
    checks = crosscheck(rows, first_run)
    (HERE / "crosscheck_v1.json").write_text(json.dumps(checks, indent=1), encoding="utf-8")
    deciding = [c for c in candidates if not c["excluded"]]
    print(f"{len(candidates)} candidate bonds, {len(deciding)} deciding, {len(candidates) - len(deciding)} excluded; largest uncertainty {max(c['uncertainty_kcal'] for c in candidates):.2f} kcal/mol")
    differences = [c["difference"] for c in checks]
    print(f"cross-check on {len(checks)} first-run bonds: mean difference {sum(differences) / len(differences):+.2f}, largest {max(differences, key=abs):+.2f} kcal/mol")


if __name__ == "__main__":
    main()
