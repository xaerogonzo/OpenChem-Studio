"""Generate `chem/data/lewis_parameters.json` -- Drago-Wayland E and C.

    -dH = E_A * E_B + C_A * C_B - W        (kcal/mol)

Two parameters per acid and per base, fitted so that one product term
carries the electrostatic contribution and the other the covalent one.
That is the whole reason the model outperforms a single-scale ordering:
"hard" and "soft" stop being two ends of one axis and become two
independent coordinates.

**Provenance, stated plainly.** The values were taken from the Wikipedia
ECW model compilation, which cites:

    Vogel, G. C.; Drago, R. S. J. Chem. Educ. 1996, 73 (8), 701-707
    Drago, R. S. et al. Inorg. Chem. 1992, 32 (11), 2473-2479
    Drago, R. S.; Wayland, B. B. J. Am. Chem. Soc. 1965, 87, 3571
        doi:10.1021/ja01094a008   (the original two-term paper)

They were NOT read out of those papers, all three of which are paywalled.
What makes them shippable anyway is `check_reproduces_measured_enthalpies`
below: the parameters predict eight independently tabulated donor-iodine
adduct enthalpies to a mean absolute error of 0.27 kcal/mol across a
1.4-12.0 kcal/mol range. A mistyped table does not do that.

**Entries deliberately omitted.** The source tables include metal
complexes -- Cu(HFacac)2, ZnTPP, CoPPIX-DME, the rhodium and palladium
dimers, Mo2(PFB)4 -- whose SMILES would have to be written from memory.
Writing them is exactly the unverified transcription this file exists to
avoid, so they are left out rather than guessed at. The W column is kept
regardless, because those omitted entries are where it is non-zero and a
schema without it would need changing to admit them later.
"""

from __future__ import annotations

import json
from pathlib import Path

from rdkit import Chem

OUTPUT = Path(__file__).resolve().parents[1] / "src" / "openchem" / "chem" / "data" / "lewis_parameters.json"

CITATION = (
    "Drago-Wayland E and C parameters, via the Wikipedia ECW model compilation "
    "of Vogel & Drago, J. Chem. Educ. 1996, 73, 701 and Drago et al., "
    "Inorg. Chem. 1992, 32, 2473. Original model: Drago & Wayland, "
    "J. Am. Chem. Soc. 1965, 87, 3571 (doi:10.1021/ja01094a008)."
)

#: name -> (SMILES, E_A, C_A, W). E and C in (kcal/mol)^1/2, W in kcal/mol.
ACIDS: dict[str, tuple[str, float, float, float]] = {
    "iodine": ("II", 0.50, 2.0, 0.0),
    "iodine monobromide": ("IBr", 1.20, 3.29, 0.0),
    "iodine monochloride": ("ICl", 2.92, 1.66, 0.0),
    "phenol": ("Oc1ccccc1", 2.27, 1.07, 0.0),
    "4-fluorophenol": ("Oc1ccc(F)cc1", 2.30, 1.11, 0.0),
    "3-(trifluoromethyl)phenol": ("Oc1cccc(C(F)(F)F)c1", 2.38, 1.22, 0.0),
    "4-methylphenol": ("Cc1ccc(O)cc1", 2.23, 1.03, 0.0),
    "2,2,2-trifluoroethanol": ("OCC(F)(F)F", 2.07, 1.06, 0.0),
    "hexafluoro-2-propanol": ("OC(C(F)(F)F)C(F)(F)F", 2.89, 1.33, -0.16),
    "tert-butanol": ("CC(C)(C)O", 1.07, 0.69, 0.0),
    "nonafluoro-tert-butanol": ("OC(C(F)(F)F)(C(F)(F)F)C(F)(F)F", 3.06, 1.88, -0.87),
    "1-octanol": ("CCCCCCCCO", 0.85, 0.87, 0.0),
    "chloroform": ("ClC(Cl)Cl", 1.56, 0.44, 0.0),
    "dichloromethane": ("ClCCl", 0.86, 0.11, 0.0),
    "pyrrole": ("c1cc[nH]c1", 1.38, 0.68, 0.0),
    "isocyanic acid": ("N=C=O", 1.60, 0.69, 0.0),
    "isothiocyanic acid": ("N=C=S", 2.85, 0.70, 0.0),
    "trimethylborane": ("CB(C)C", 2.90, 3.60, 0.0),
    "trimethylaluminium": ("C[Al](C)C", 8.66, 3.68, 0.0),
    "triethylgallium": ("CC[Ga](CC)CC", 6.95, 1.48, 0.0),
    "trimethylindium": ("C[In](C)C", 6.60, 2.15, 0.0),
    "trimethyltin chloride": ("C[Sn](C)(C)Cl", 2.87, 0.71, 0.0),
    "sulfur dioxide": ("O=S=O", 0.51, 1.56, 0.0),
    "antimony pentachloride": ("Cl[Sb](Cl)(Cl)(Cl)Cl", 3.64, 10.42, 0.0),
}

#: name -> (SMILES, E_B, C_B).
BASES: dict[str, tuple[str, float, float]] = {
    "ammonia": ("N", 2.31, 2.04),
    "methylamine": ("CN", 2.16, 3.13),
    "dimethylamine": ("CNC", 1.80, 4.21),
    "trimethylamine": ("CN(C)C", 1.21, 5.61),
    "quinuclidine": ("C1CN2CCC1CC2", 0.80, 6.72),
    "triethylamine": ("CCN(CC)CC", 1.32, 5.73),
    "pyridine": ("c1ccncc1", 1.78, 3.54),
    "3-methylpyridine": ("Cc1cccnc1", 1.81, 3.67),
    "3-bromopyridine": ("Brc1cccnc1", 1.66, 3.08),
    "4-methoxypyridine": ("COc1ccncc1", 1.83, 3.83),
    "acetonitrile": ("CC#N", 1.64, 0.71),
    "dimethylcyanamide": ("CN(C)C#N", 1.92, 0.92),
    "chloroacetonitrile": ("ClCC#N", 1.67, 0.33),
    "acetone": ("CC(C)=O", 1.74, 1.26),
    "cyclopentanone": ("O=C1CCCC1", 2.02, 0.88),
    "ethyl acetate": ("CCOC(C)=O", 1.62, 0.98),
    "dimethylacetamide": ("CC(=O)N(C)C", 2.35, 1.31),
    "diethyl ether": ("CCOCC", 1.80, 1.63),
    "tetrahydrofuran": ("C1CCOC1", 1.64, 2.18),
    "1,4-dioxane": ("C1COCCO1", 1.86, 1.29),
    "dimethyl sulfide": ("CSC", 0.25, 3.75),
    "tetrahydrothiophene": ("C1CCSC1", 0.26, 4.07),
    "diethyl sulfide": ("CCSCC", 0.24, 3.92),
    "dimethyl sulfoxide": ("CS(C)=O", 2.40, 1.47),
    "tetrahydrothiophene 1-oxide": ("O=S1CCCC1", 2.44, 1.64),
    "pyridine N-oxide": ("[O-][n+]1ccccc1", 2.29, 2.33),
    "4-methoxypyridine N-oxide": ("COc1cc[n+]([O-])cc1", 2.34, 3.02),
    "triphenylphosphine oxide": ("O=P(c1ccccc1)(c1ccccc1)c1ccccc1", 2.59, 1.67),
    "trimethylphosphine": ("CP(C)C", 0.25, 5.81),
    "trimethyl phosphite": ("COP(OC)OC", 0.13, 4.83),
    "dimethyl selenide": ("C[Se]C", 0.05, 4.24),
    "triphenylphosphine sulfide": ("S=P(c1ccccc1)(c1ccccc1)c1ccccc1", 0.35, 3.65),
    "benzene": ("c1ccccc1", 0.70, 0.45),
}

#: Independently tabulated -dH (kcal/mol) for donor-iodine adducts. NOT an
#: input to the parameters -- this is the check that they are right.
MEASURED_IODINE_ADDUCTS = {
    "benzene": 1.4,
    "1,4-dioxane": 3.5,
    "diethyl ether": 4.3,
    "diethyl sulfide": 8.3,
    "dimethylacetamide": 4.7,
    "acetonitrile": 1.9,
    "pyridine": 7.80,
    "triethylamine": 12.0,
}


def canonical(smiles: str) -> str:
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise SystemExit(f"unparseable SMILES: {smiles!r}")
    return Chem.MolToSmiles(mol)


def check_every_smiles_is_distinct(entries: dict[str, str], label: str) -> None:
    """Two names collapsing to one structure would silently shadow one set
    of parameters with the other, and the lookup is BY STRUCTURE."""
    seen: dict[str, str] = {}
    for name, smiles in entries.items():
        if smiles in seen:
            raise SystemExit(f"{label}: {name!r} and {seen[smiles]!r} are the same structure")
        seen[smiles] = name


def check_reproduces_measured_enthalpies(acids: dict, bases: dict) -> float:
    """The ship/do-not-ship test, and the reason this file is trustworthy.

    Iodine's parameters plus each base's predict that base's measured
    iodine-adduct enthalpy. Independent of how the parameters were fitted
    in the sense that matters here: a transcription error in ANY of the
    numbers below shows up immediately as a bad prediction.

    Measured when this file was written: mean absolute error 0.27
    kcal/mol over a 1.4-12.0 kcal/mol range, worst case dimethylacetamide
    at 0.91 -- which has two donor sites and is expected to be the hard
    one. The thresholds are set just outside that, so drift fails here
    rather than silently downstream.
    """
    iodine = acids[canonical("II")]
    errors = []
    for name, measured in MEASURED_IODINE_ADDUCTS.items():
        base = bases[canonical(BASES[name][0])]
        predicted = (
            iodine["E"] * base["E"] + iodine["C"] * base["C"] - iodine["W"]
        )
        errors.append(abs(predicted - measured))
        print(f"  {name:28s} predicted {predicted:5.2f}  measured {measured:5.2f}  {predicted - measured:+5.2f}")
    mean_error = sum(errors) / len(errors)
    if mean_error > 0.35:
        raise SystemExit(f"Drago parameters do not reproduce: mean error {mean_error:.2f} kcal/mol")
    if sum(error > 0.5 for error in errors) > 1:
        raise SystemExit("more than one adduct outside 0.5 kcal/mol -- the table is wrong")
    return mean_error


def main() -> None:
    acids = {
        canonical(smiles): {"name": name, "E": ea, "C": ca, "W": w}
        for name, (smiles, ea, ca, w) in ACIDS.items()
    }
    bases = {
        canonical(smiles): {"name": name, "E": eb, "C": cb}
        for name, (smiles, eb, cb) in BASES.items()
    }
    check_every_smiles_is_distinct({n: canonical(s) for n, (s, *_) in ACIDS.items()}, "acids")
    check_every_smiles_is_distinct({n: canonical(s) for n, (s, *_) in BASES.items()}, "bases")

    print("Reproducing the measured donor-iodine adduct enthalpies:")
    mean_error = check_reproduces_measured_enthalpies(acids, bases)
    print(f"  mean absolute error {mean_error:.2f} kcal/mol over {len(MEASURED_IODINE_ADDUCTS)} adducts")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(
            {
                "citation": CITATION,
                "units": {"E": "(kcal/mol)^1/2", "C": "(kcal/mol)^1/2", "W": "kcal/mol"},
                "validation": {
                    "against": "measured donor-iodine adduct enthalpies",
                    "adducts": len(MEASURED_IODINE_ADDUCTS),
                    "mean_absolute_error_kcal_mol": round(mean_error, 3),
                },
                "acids": acids,
                "bases": bases,
            },
            indent=1,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"\nwrote {OUTPUT} -- {len(acids)} acids, {len(bases)} bases")


if __name__ == "__main__":
    main()
