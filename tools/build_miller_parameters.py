"""Build `chem/data/miller_polarizability.json` from a typed transcription.

    uv run --no-sync python tools/build_miller_parameters.py

**THE PARAMETERS ARE PUBLISHED AFTER ALL, WHICH IS THE WHOLE POINT.**
`docs/VALIDATION.md` recorded Miller polarizability as measured and not
shipped: "The parameters are unpublished. A reconstruction missed benzene
by +27% and CCl4 by -50%, so there was nothing to validate against." The
first sentence was a claim about ChemAxon's documentation, not about the
literature. Miller, *JACS* **112** (1990) 8533-8542, Table I, "Parameters
for Atoms in Hybrid Configurations", prints all of them.

**READ OFF A 400 DPI RENDER, NOT THE TEXT LAYER.** That layer gives
`0.392 0.31 1 0.3 13 0.387` for a row of four numbers, `3 .000` for
3.000, `TA` for tau_A and `A312` for A^(3/2). The same treatment the
Drago E/C table got, after an audit there found one value in 53 out by
0.01 -- an error no averaged validation can see.

EVERY ROW KEEPS ITS SOURCE IDENTITY. `symbol` and `hybrid` are the
paper's own, carried beside the derived key, so a future audit can be
done against the page row by row rather than by re-deriving which line
was meant. `tools/build_lewis_parameters.py` is the precedent.

TWO METHODS, AND THEY ARE NOT INTERCHANGEABLE:

    ahc   alpha = (4/N) * (SUM tau_A)^2      N = TOTAL ELECTRONS
    ahp   alpha = SUM alpha_A                plain additivity

The ahc form is the 1979 paper's ([source:miller1979]) and is the one the
molecular tables are computed with. Squaring a sum is what makes it not a
group-additivity scheme, and using the ahp column in that formula -- or
the tau column additively -- produces plausible numbers that are wrong.

**THE TRAP THAT SANK THE EARLIER RECONSTRUCTION IS THE `CBR` ROW.** Its
symbol reads like "carbon in a benzene ring" and it is not: the 1979
paper says the difficulty "was traced to the two kinds of carbon atoms
present in the pi-electronic system. In ethylene AND BENZENE the pi
system is directed only along two bonds, whereas in the 9 and 10
positions of naphthalene it is directed along all three bonds." So
benzene's carbons are `CTR`; `CBR` is for pi-BRANCHED carbons, the fusion
positions of polycyclics. Assigning benzene to CBR gives 13.99 A^3
against an experimental 10.39 -- +36%, which is the same error class as
the +27% on record.
"""

from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "src" / "openchem" / "chem" / "data"

_ATTRIBUTION = (
    "K. J. Miller, 'Additivity methods in molecular polarizability', "
    "J. Am. Chem. Soc. 1990;112:8533-8542, Table I. "
    "doi:10.1021/ja00179a044. Method: K. J. Miller & J. A. Savchik, "
    "J. Am. Chem. Soc. 1979;101:7206-7213, doi:10.1021/ja00518a014. "
    "Transcribed from a 400 dpi render."
)

#: Table I, in the paper's own row order. Keys are the paper's `symbol`
#: column; `hybrid` is its `hybrid` column, kept verbatim so a row can be
#: found on the page without guessing.
#:
#:   tau_ahc    tau_A(ahc), A^(3/2) -- the ahc method's parameter
#:   alpha_ahp  alpha_A(ahp), A^3   -- the ahp method's parameter
#:
#: The paper's four other columns (the conjugate * sets and the van der
#: Waals radii) are deliberately not carried: nothing here computes with
#: them, and shipping numbers no code reads is how a table rots unnoticed.
_TABLE_I: dict[str, dict] = {
    "H":     {"hybrid": "sigma",        "group": "-H",  "tau_ahc": 0.313, "alpha_ahp": 0.387},
    "F":     {"hybrid": "sigma",        "group": "-F",  "tau_ahc": 1.089, "alpha_ahp": 0.296},
    "Cl":    {"hybrid": "sigma",        "group": "-Cl", "tau_ahc": 3.165, "alpha_ahp": 2.315},
    "Br":    {"hybrid": "sigma",        "group": "-Br", "tau_ahc": 5.566, "alpha_ahp": 3.013},
    "I":     {"hybrid": "sigma",        "group": "-I",  "tau_ahc": 8.593, "alpha_ahp": 5.415},
    "CTE":   {"hybrid": "tetetete",     "group": ">C<", "tau_ahc": 1.294, "alpha_ahp": 1.061},
    "CTR":   {"hybrid": "trtrtrpi",     "group": "=C-", "tau_ahc": 1.433, "alpha_ahp": 1.352},
    "CBR":   {"hybrid": "trtrtrpi",     "group": "branched pi",
              "tau_ahc": 1.707, "alpha_ahp": 1.896},
    "CDI":   {"hybrid": "didipipi",     "group": "-C#", "tau_ahc": 1.393, "alpha_ahp": 1.283},
    "NTE":   {"hybrid": "te2tetete",    "group": ">N:", "tau_ahc": 1.373, "alpha_ahp": 0.964},
    "NTR2":  {"hybrid": "tr2trtrpi",    "group": "=N:", "tau_ahc": 1.262, "alpha_ahp": 1.030},
    "NPI2":  {"hybrid": "trtrtrpi2",    "group": ">N-", "tau_ahc": 1.220, "alpha_ahp": 1.090},
    "NDI":   {"hybrid": "di2dipipi",    "group": "#N:", "tau_ahc": 1.304, "alpha_ahp": 0.956},
    "OTE":   {"hybrid": "te2te2tete",   "group": ">O:", "tau_ahc": 1.249, "alpha_ahp": 0.637},
    "OTR4":  {"hybrid": "tr2tr2trpi",   "group": "=O:", "tau_ahc": 1.216, "alpha_ahp": 0.569},
    "OPI2":  {"hybrid": "tr2trtrpi2",   "group": ">O: pi",
              "tau_ahc": 1.083, "alpha_ahp": 0.274},
    "STE":   {"hybrid": "te2te2tete",   "group": ">S:", "tau_ahc": 3.496, "alpha_ahp": 3.000},
    "STR4":  {"hybrid": "tr2tr2trpi",   "group": "=S:", "tau_ahc": 3.827, "alpha_ahp": 3.729},
    "SPI2":  {"hybrid": "tr2trtrpi2",   "group": ">S: pi",
              "tau_ahc": 2.982, "alpha_ahp": 2.700},
    "PTE":   {"hybrid": "tetetete",     "group": ">P:", "tau_ahc": 2.485, "alpha_ahp": 1.538},
}

#: Molecular polarizabilities the papers themselves print, for the
#: acceptance test. `alpha_exp` is the experimental column.
#:
#: BENZENE AND CCl4 ARE HERE BECAUSE THEY ARE THE TWO THE EARLIER
#: RECONSTRUCTION GOT WRONG -- +27% and -50% on record. If either fails,
#: the transcription or the hybrid assignment is wrong and nothing built
#: on this table should be trusted.
_REFERENCE_MOLECULES = {
    "benzene": {"smiles": "c1ccccc1", "alpha_exp": 10.39, "source": "miller1979 Table X"},
    "naphthalene": {"smiles": "c1ccc2ccccc2c1", "alpha_exp": 17.48,
                    "source": "miller1979 Table X"},
    "carbon tetrachloride": {"smiles": "ClC(Cl)(Cl)Cl", "alpha_exp": 10.5,
                             "source": "miller1979, halogenated derivatives"},
}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    payload = {
        "_source_key": "miller1990",
        "_supplementary_source_keys": ["miller1979"],
        "attribution": _ATTRIBUTION,
        "methods": {
            "ahc": "alpha = (4/N) * (sum of tau_A)^2, N = total electrons. A^3.",
            "ahp": "alpha = sum of alpha_A. A^3.",
        },
        "parameters": _TABLE_I,
        "reference_molecules": _REFERENCE_MOLECULES,
    }
    (OUT / "miller_polarizability.json").write_text(
        json.dumps(payload, indent=1), encoding="utf-8"
    )
    print(f"parameters: {len(_TABLE_I)} atomic hybrid rows from Table I")
    print(f"references: {len(_REFERENCE_MOLECULES)} molecules for the acceptance test")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
