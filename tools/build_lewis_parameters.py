"""Generate `chem/data/lewis_parameters.json` -- Drago-Wayland E and C.

    -dH = E_A * E_B + C_A * C_B - W        (kcal/mol)

Two parameters per acid and per base, fitted so that one product term
carries the electrostatic contribution and the other the covalent one.
That is the whole reason the model outperforms a single-scale ordering:
"hard" and "soft" stop being two ends of one axis and become two
independent coordinates.

**Provenance, stated plainly.** The E and C VALUES were taken from the
Wikipedia ECW model compilation of:

    Vogel, G. C.; Drago, R. S. J. Chem. Educ. 1996, 73 (8), 701-707
    Drago, R. S. et al. Inorg. Chem. 1992, 32 (11), 2473-2479

They were not read out of those two papers. The original paper HAS since
been read:

    Drago, R. S.; Wayland, B. B. J. Am. Chem. Soc. 1965, 87, 3571
        doi:10.1021/ja01094a008

and its parameters are deliberately NOT used, because they are on a
different scale: that paper normalises iodine to E_A = C_A = 1.000
("the values reported in Tables V and VI are relative to E_A and C_A of
iodine being 1"), while the modern compilation puts iodine at
E_A = 0.50, C_A = 2.0. Mixing the two would be silently wrong. What the
1965 paper contributes instead is its EXPERIMENTAL enthalpies, which are
scale-independent and were not used to fit the modern values.

Two independent checks therefore run below, and the file is not written
if either fails:

- `check_reproduces_measured_enthalpies` -- eight donor-iodine adducts,
  mean absolute error 0.27 kcal/mol over a 1.4-12.0 range.
- `check_reproduces_the_original_paper` -- twelve observed enthalpies
  read from Tables I, II and III of the 1965 paper itself.

The second is the one the plan for this work actually asked for, and it
also reproduces a measured FAILURE of the model: see that function.

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
    # C_B was 3.13 here until the source was read: Vogel & Drago 1996,
    # J. Chem. Educ. 73(8) 702, Table 1, row [2] prints 3.12. Read off a
    # 520-dpi render of the scan, unambiguous. A transcription slip
    # inherited from the Wikipedia compilation these values came through --
    # the one value in 53 that did not match its source.
    "methylamine": ("CN", 2.16, 3.12),
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


#: Observed (not calculated) enthalpies from Drago & Wayland 1965, read
#: from the paper: Table I (iodine), Table II (phenol), Table III
#: (trimethylborane), all with the same four amines. These did not go into
#: fitting the modern parameters, so they are a genuinely independent test.
ORIGINAL_PAPER_ENTHALPIES: dict[str, tuple[str, dict[str, float]]] = {
    "iodine": ("II", {"ammonia": 4.8, "methylamine": 7.1, "dimethylamine": 9.8, "trimethylamine": 12.1}),
    "phenol": ("Oc1ccccc1", {"ammonia": 8.0, "methylamine": 9.3, "dimethylamine": 9.3, "trimethylamine": 9.5}),
    "trimethylborane": ("CB(C)C", {"ammonia": 13.75, "methylamine": 17.64, "dimethylamine": 19.26, "trimethylamine": 17.62}),
}

#: The paper's own attribution of the trimethylborane discrepancies to
#: F-strain: 1.5 kcal/mol for dimethylamine and 8.2 for trimethylamine,
#: the latter agreeing with an independently reported 7.8.
PAPER_STERIC_EFFECTS = {"dimethylamine": 1.5, "trimethylamine": 8.2}


def _predict(acids: dict, bases: dict, acid_smiles: str, base_name: str) -> float:
    acid = acids[canonical(acid_smiles)]
    base = bases[canonical(BASES[base_name][0])]
    return acid["E"] * base["E"] + acid["C"] * base["C"] + acid.get("W", 0.0)


def check_reproduces_the_original_paper(acids: dict, bases: dict) -> None:
    """The 1965 paper's own observed enthalpies, in three acid series.

    Iodine and phenol are ordinary agreement checks. **Trimethylborane is
    not, and is the point of including it**: the paper reports that its
    amine adducts are destabilised by F-strain, by 1.5 kcal/mol for
    dimethylamine and 8.2 for trimethylamine. An E and C equation has no
    steric term, so the model MUST over-predict those two -- and this
    application's `lewis_adduct` names sterics as a limitation partly on
    the strength of it.

    So the assertion is not "trimethylborane agrees". It is that the two
    unhindered adducts agree and the two hindered ones over-predict, in
    the order and roughly the magnitude the paper measured. A table that
    happened to fit all four would mean the parameters had absorbed a
    steric effect they are not supposed to contain.
    """
    for acid_name, (acid_smiles, observed) in ORIGINAL_PAPER_ENTHALPIES.items():
        errors = []
        for base_name, measured in observed.items():
            predicted = _predict(acids, bases, acid_smiles, base_name)
            error = predicted - measured
            errors.append((base_name, error))
            steric = PAPER_STERIC_EFFECTS.get(base_name, 0.0) if acid_name == "trimethylborane" else 0.0
            flag = f"  (paper's steric effect {steric:.1f})" if steric else ""
            print(f"  {acid_name:16s} + {base_name:14s} {predicted:6.2f} vs {measured:6.2f} observed  {error:+5.2f}{flag}")

        if acid_name == "trimethylborane":
            by_base = dict(errors)
            if not by_base["ammonia"] < 1.0 or not by_base["methylamine"] < 1.0:
                raise SystemExit("the UNHINDERED trimethylborane adducts should agree and do not")
            if not by_base["trimethylamine"] > by_base["dimethylamine"] > 0.5:
                raise SystemExit(
                    "the hindered trimethylborane adducts should be over-predicted, "
                    "trimethylamine worst -- the parameters may have absorbed a steric effect"
                )
            continue

        mean_error = sum(abs(e) for _n, e in errors) / len(errors)
        if mean_error > 1.0:
            raise SystemExit(f"{acid_name}: mean error {mean_error:.2f} against the 1965 paper")
        print(f"  {acid_name:16s} mean absolute error {mean_error:.2f} kcal/mol")


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

    print("\nAgainst the 1965 paper's own observed enthalpies:")
    check_reproduces_the_original_paper(acids, bases)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(
            {
                # WRITTEN HERE, NOT INTO THE JSON, and that is not a style
                # choice -- hand-added keys were silently dropped by the very
                # next run of this script, which is the same trap
                # `build_element_reference.py` already carries a comment
                # about. This file did not say it was generated, so nothing
                # warned against the hand edit; `_generated_by` below fixes
                # that for whoever opens it next.
                "_generated_by": (
                    "tools/build_lewis_parameters.py -- do not hand-edit; re-run it"
                ),
                "_source_key": "vogel_drago1996",
                "_supplementary_source_keys": ["drago1965", "drago1992"],
                "_parameter_scale": "modern_ecw",
                "_scale_note": (
                    "Two DIFFERENT claims, kept apart on purpose. _source_key says where "
                    "these numbers came from; _parameter_scale says what numerical "
                    "convention they are in, and the two are not the same question. Drago "
                    "& Wayland 1965 normalise iodine to E_A = C_A = 1.000, where this "
                    "table has iodine at E = 0.5, C = 2.0 -- so citing the 1965 paper as "
                    "the source would imply a scale these values are not on. Verified "
                    "against Table 1 of the 1996 paper, whose own footnote warns that "
                    "these parameters 'should not be mixed with those parameters found in "
                    "the literature prior to 1991'. "
                    "test_lewis_parameters_match_the_declared_parameter_scale DERIVES the "
                    "scale from the iodine entry rather than trusting this label."
                ),
                "citation": CITATION,
                "units": {"E": "(kcal/mol)^1/2", "C": "(kcal/mol)^1/2", "W": "kcal/mol"},
                "validation": {
                    "against": "measured donor-iodine adduct enthalpies",
                    "adducts": len(MEASURED_IODINE_ADDUCTS),
                    "mean_absolute_error_kcal_mol": round(mean_error, 3),
                    "also_checked_against": (
                        "the observed enthalpies in Tables I, II and III of "
                        "Drago & Wayland 1965 -- iodine 0.36 and phenol 0.77 "
                        "kcal/mol mean error, with the two sterically hindered "
                        "trimethylborane adducts over-predicted as that paper's "
                        "own measured F-strain requires"
                    ),
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
