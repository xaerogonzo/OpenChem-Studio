"""The pure part of the computed gas-phase enthalpy arbiter (see PLAN.md).

Everything here is arithmetic and bookkeeping: the species, the experimental reference values and where they came from, the
isodesmic reactions, the check that a reaction conserves atoms AND bond types, the conformer-ensemble average and the
reaction-enthalpy-to-formation-enthalpy step. No engine, no files. `arbiter_run.py` drives ORCA and feeds these functions.

A formation enthalpy that comes out of this module is `computed` (PREREGISTRATION.md 3.1): it never verifies a measurement and
never fills the `measured` gas-phase leg that R1 asks for.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass

from rdkit import Chem

R_KJ = 8.314462618e-3          # kJ/(mol K)
T_STD = 298.15
HARTREE_KJ = 2625.499638       # kJ/mol per hartree

# name -> (SMILES, experimental/evaluated gas-phase dfH(298.15 K) in kJ/mol, standard uncertainty, source)
# None for a species whose value is the question. ATcT numbers are read from the table saved in the library (version 1.228);
# the three nitro and nitrate-ester numbers are NIST WebBook entries (their single method and reference are in the source text).
REFERENCES: dict[str, tuple[str, float | None, float | None, str]] = {
    "methane": ("C", -74.500, 0.042, "ATcT 1.228"),
    "ethane": ("CC", -84.02, 0.11, "ATcT 1.228"),
    "methanol": ("CO", -200.85, 0.14, "ATcT 1.228"),
    "ethanol": ("CCO", -234.88, 0.19, "ATcT 1.228"),
    "neopentane": ("CC(C)(C)C", -167.08, 0.38, "ATcT 1.228"),
    "nitromethane": ("C[N+](=O)[O-]", -74.45, 0.40, "ATcT 1.228"),
    "nitroethane": ("CC[N+](=O)[O-]", -102.73, 0.62, "ATcT 1.228"),
    "ethylene_glycol": ("OCCO", -389.25, 0.40, "ATcT 1.228"),
    "methyl_nitrate": ("CO[N+](=O)[O-]", -122.0, 1.0, "NIST WebBook, Ray and Ogg 1959 (Cm)"),
    "ethyl_nitrate": ("CCO[N+](=O)[O-]", -155.0, 3.0, "NIST WebBook, Gray, Pratt and Larkin 1956 (Eqk)"),
    "tert_butyl_nitro": ("CC(C)(C)[N+](=O)[O-]", -177.1, 3.3, "NIST WebBook, Knobel et al. 1970 (Ccb, reanalysed by Pedley)"),
    # the species whose gas-phase value is the question, and the nearest comparator
    "pentaerythritol": ("OCC(CO)(CO)CO", None, None, "question"),
    "nibtn": ("[O-][N+](=O)OCC(CO[N+](=O)[O-])(CO[N+](=O)[O-])[N+](=O)[O-]", None, None, "question"),
    "petn": ("[O-][N+](=O)OCC(CO[N+](=O)[O-])(CO[N+](=O)[O-])CO[N+](=O)[O-]", None, None,
             "validation comparator, derived from a measured solid and a measured sublimation, see PLAN.md"),
}

# PETN's comparator: a measured solid (-538.5 +/- 0.8, Ornellas 1966) plus a measured sublimation (150.4 +/- 1.3); the derived
# range over the published sublimation values is -381 to -388, so the comparator tolerance is set wide on purpose.
PETN_COMPARATOR = (-388.1, 8.0)

# Each scheme: (target, {species: stoichiometric coefficient}) meaning  target + sum(left) -> sum(right).
# left and right are species names -> coefficients; the target is on the left with coefficient 1.
SCHEMES: dict[str, dict[str, dict]] = {
    "pentaerythritol/A": {"target": "pentaerythritol", "left": {"methane": 4}, "right": {"neopentane": 1, "methanol": 4}},
    "pentaerythritol/B": {"target": "pentaerythritol", "left": {"ethane": 4}, "right": {"neopentane": 1, "ethanol": 4}},
    "nibtn/A": {"target": "nibtn", "left": {"methane": 3}, "right": {"tert_butyl_nitro": 1, "methyl_nitrate": 3}},
    "nibtn/B": {"target": "nibtn", "left": {"methane": 3, "ethane": 1},
                "right": {"neopentane": 1, "nitromethane": 1, "methyl_nitrate": 3}},
    "petn/A": {"target": "petn", "left": {"methane": 4}, "right": {"neopentane": 1, "methyl_nitrate": 4}},
    "petn/B": {"target": "petn", "left": {"ethane": 4}, "right": {"neopentane": 1, "ethyl_nitrate": 4}},
    # validation: species with an experimental value, predicted from smaller ones by the same kind of reaction
    "ethanol/V": {"target": "ethanol", "left": {"methanol": 1, "ethane": 1}, "right": {"methane": 1}, "swap": True},
    "ethylene_glycol/V": {"target": "ethylene_glycol", "left": {"methanol": 2, "ethane": 1}, "right": {"methane": 2},
                          "swap": True},
    "nitroethane/V": {"target": "nitroethane", "left": {"nitromethane": 1, "ethane": 1}, "right": {"methane": 1}, "swap": True},
    "ethyl_nitrate/V": {"target": "ethyl_nitrate", "left": {"methyl_nitrate": 1, "ethane": 1}, "right": {"methane": 1},
                        "swap": True},
    "tert_butyl_nitro/V": {"target": "tert_butyl_nitro", "left": {"neopentane": 1, "nitromethane": 1},
                           "right": {"ethane": 1}, "swap": True},
}
# For a validation scheme ("swap": True) the target is a PRODUCT:  left -> target + right.  For the others the target is a
# reactant:  target + left -> right.


def formula(smiles: str) -> Counter:
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    return Counter(a.GetSymbol() for a in mol.GetAtoms())


def bond_types(smiles: str) -> Counter:
    """Bond-type census with the element pair and the bond order, hydrogens explicit. A nitro or nitrate group's resonance forms
    are made the same by treating N-O and the charged N=O alike: both are counted as 'N-O' (the group is conserved whole
    in every scheme here, which the group census below checks separately)."""
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    c: Counter = Counter()
    for b in mol.GetBonds():
        a, z = sorted((b.GetBeginAtom().GetSymbol(), b.GetEndAtom().GetSymbol()))
        if {a, z} == {"N", "O"}:
            c["N-O"] += 1
        else:
            c[f"{a}-{z}"] += 1
    return c


_GROUPS = {"nitro": "[CX4][N+](=O)[O-]", "nitrate": "[CX4]O[N+](=O)[O-]", "hydroxyl": "[CX4][OX2H]", "quaternary C": "[CX4;H0]([#6])([#6])([#6])[#6,#7]"}


def groups(smiles: str) -> Counter:
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    return Counter({name: len(mol.GetSubstructMatches(Chem.MolFromSmarts(sma))) for name, sma in _GROUPS.items()})


def _sides(scheme: dict) -> tuple[dict[str, int], dict[str, int]]:
    """(reactants, products) as name -> coefficient, whichever side the target is on."""
    t = scheme["target"]
    left, right = dict(scheme["left"]), dict(scheme["right"])
    if scheme.get("swap"):
        return left, {**right, t: right.get(t, 0) + 1}
    return {**left, t: left.get(t, 0) + 1}, right


def census(side: dict[str, int], fn) -> Counter:
    total: Counter = Counter()
    for name, k in side.items():
        for key, n in fn(REFERENCES[name][0]).items():
            total[key] += k * n
    return total


def balance(scheme_name: str) -> dict[str, bool]:
    """Does the reaction conserve atoms, bond types and the functional-group counts? A scheme is only admitted when all hold."""
    reactants, products = _sides(SCHEMES[scheme_name])
    out = {}
    for label, fn in (("atoms", formula), ("bonds", bond_types), ("groups", groups)):
        a, b = census(reactants, fn), census(products, fn)
        keys = set(a) | set(b)
        out[label] = all(a.get(k, 0) == b.get(k, 0) for k in keys)
    return out


def reaction_to_formation(scheme_name: str, delta_h_reaction: float) -> tuple[float, float]:
    """The target's gas-phase dfH(298.15 K) from a calculated reaction enthalpy, and the standard uncertainty that the
    REFERENCE values contribute (their uncertainties added in quadrature with their coefficients).

    delta_h_reaction is H(products) - H(reactants) in kJ/mol for the reaction as written by `_sides`.
    """
    scheme = SCHEMES[scheme_name]
    target = scheme["target"]
    reactants, products = _sides(scheme)
    h_ref_reactants = sum(k * REFERENCES[n][1] for n, k in reactants.items() if n != target)
    h_ref_products = sum(k * REFERENCES[n][1] for n, k in products.items() if n != target)
    u = math.sqrt(sum((k * REFERENCES[n][2]) ** 2 for n, k in (*reactants.items(), *products.items()) if n != target))
    # delta_h = [sum products] - [sum reactants]; the target is a product or a reactant
    if scheme.get("swap"):
        value = delta_h_reaction - h_ref_products + h_ref_reactants      # target is a product: dfH(T) = dH + reactants - other products
        return value, u
    value = h_ref_products - h_ref_reactants - delta_h_reaction          # target is a reactant: dfH(T) = sum(products) - other reactants - dH
    return value, u


def boltzmann_weights(free_energies_kj: list[float], temperature: float = T_STD) -> list[float]:
    low = min(free_energies_kj)
    w = [math.exp(-(g - low) / (R_KJ * temperature)) for g in free_energies_kj]
    s = sum(w)
    return [x / s for x in w]


def ensemble_enthalpy(enthalpies_kj: list[float], free_energies_kj: list[float]) -> float:
    """Ensemble enthalpy: each conformer's enthalpy weighted by its Boltzmann population from the FREE energies (the populations
    carry the conformational entropy; the enthalpy is what the reaction needs)."""
    w = boltzmann_weights(free_energies_kj)
    return sum(wi * h for wi, h in zip(w, enthalpies_kj))


def combine_schemes(a: float, b: float, u_ref_a: float, u_ref_b: float, u_validation: float) -> dict[str, float]:
    """The plan's uncertainty rule: the mean of the two schemes; the spread between them, the larger reference uncertainty and
    the validation error added in quadrature; claims are made at twice that."""
    spread = abs(a - b) / 2
    u = math.sqrt(spread**2 + max(u_ref_a, u_ref_b) ** 2 + u_validation**2)
    return {"value": (a + b) / 2, "spread": spread, "u": u, "expanded": 2 * u}


def validation_floor(errors_kj: list[float], floor: float = 3.0) -> float:
    """RMS of the validation errors, but never below the plan's floor: five points cannot certify a better number."""
    if not errors_kj:
        return floor
    return max(floor, math.sqrt(sum(e * e for e in errors_kj) / len(errors_kj)))


def consistent(value: float, expanded: float, row: float, row_u: float = 0.0) -> bool:
    return abs(value - row) <= math.sqrt(expanded**2 + row_u**2)
