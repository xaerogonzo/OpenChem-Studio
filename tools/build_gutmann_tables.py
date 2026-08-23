"""Build `chem/data/gutmann_solvents.json` from a typed transcription.

    uv run --no-sync python tools/build_gutmann_tables.py

**TYPED, NOT FETCHED, AND THE TEXT LAYER WAS NOT USED.** Gutmann,
*Coord. Chem. Rev.* **18** (1976) 225-255 is a scanned 1976 journal and
its OCR is actively wrong -- "Dimethylsulphoxitie", "Acetonitriie",
"SuIphoIane", "l.o.0" for 10.0, ";:Z" where a number should be, and the
solvent names and their numbers extracted as two SEPARATE runs needing
positional alignment. Reading it that way would have been transcription
by guesswork.

Every value below was read off a **300 dpi render** of Tables 1 and 2
instead -- the same treatment the Drago E/C table got, and for the same
reason: that audit found one value in 53 out by 0.01, which no averaged
validation could see.

IT ALREADY CAUGHT ONE. The text layer gives t-butylamine's donicity as
57.6; the page says **57.5**.

TWO SCALES, AND THEY ARE NOT INTERCHANGEABLE:

  * **DN**, the donor number or donicity, Table 1 -- defined as
    `DN = -dH(EPD.SbCl5)` measured in DILUTE 1,2-dichloroethane
    solution, in kcal/mol. That is why 1,2-dichloroethane itself has no
    DN: it is the medium the measurement is made in.

  * **AN**, the acceptor number, Table 2 -- from the 31P NMR shift of
    triethylphosphine oxide, on a scale fixed by TWO points: hexane = 0
    and SbCl5 in dichloroethane = 100. Dimensionless by construction.

**BULK DONICITY IS A DIFFERENT QUANTITY AND IS KEPT APART.** The paper's
footnote a reads "Bulk donicity e.g. the donicity of the solvent in the
associated liquid". Six amines and hydrazine are reported ONLY that way,
and water is reported both ways -- `18.0 (33.0 a)`. Folding those into
one DN column would be the exact failure this project has now found
three times in a week: two different measurements sharing one name.
Water is the case that proves it matters, because it is the one row
where the two differ by 15 kcal/mol.
"""

from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "src" / "openchem" / "chem" / "data"

_ATTRIBUTION = (
    "V. Gutmann, 'Solvent effects on the reactivities of organometallic compounds', "
    "Coordination Chemistry Reviews 1976;18:225-255, Tables 1 and 2. "
    "doi:10.1016/S0010-8545(00)82045-7. Transcribed from a 300 dpi render."
)

_DEFINITIONS = {
    "dn": (
        "Donor number (donicity), kcal/mol. DN = -dH for the adduct of the "
        "electron-pair donor with SbCl5, measured in dilute 1,2-dichloroethane."
    ),
    "bulk_dn": (
        "BULK donicity, kcal/mol -- the donicity of the solvent in the "
        "associated liquid. The paper's footnote a. A DIFFERENT measurement "
        "from dn, not a variant of it: water is 18.0 dilute and 33.0 bulk."
    ),
    "an": (
        "Acceptor number, dimensionless. From the 31P NMR shift of "
        "triethylphosphine oxide, on a two-point scale: hexane = 0, "
        "SbCl5 in 1,2-dichloroethane = 100."
    ),
    "p31_shift": "31P NMR shift of Et3P=O relative to Et3PO in hexane, ppm.",
}

#: Table 1, "Donicities DN and dielectric constants of several donor
#: solvents", pages 230-231. Read at 300 dpi.
#:
#: `bulk` marks the paper's footnote a. `approximate` marks its "~".
#: 1,2-dichloroethane is present with NO donicity because it is the
#: solvent the measurement is made in -- an absence with a reason, which
#: is why it is listed rather than omitted.
_DONOR_NUMBERS: dict[str, dict] = {
    "1,2-dichloroethane": {"dn": None, "note": "the medium DN is measured in"},
    "benzene": {"dn": 0.1},
    "sulfuryl chloride": {"dn": 0.1},
    "thionyl chloride": {"dn": 0.4},
    "acetyl chloride": {"dn": 0.7},
    "tetrachloroethylene carbonate": {"dn": 0.8},
    "benzoyl fluoride": {"dn": 2.3},
    "benzoyl chloride": {"dn": 2.3},
    "nitromethane": {"dn": 2.7},
    "dichloroethylene carbonate": {"dn": 3.2},
    "nitrobenzene": {"dn": 4.4},
    "acetic anhydride": {"dn": 10.5},
    "phosphorus oxychloride": {"dn": 11.7},
    "benzonitrile": {"dn": 11.9},
    "selenium oxychloride": {"dn": 12.2},
    "acetonitrile": {"dn": 14.1},
    "sulpholane": {"dn": 14.8},
    "dioxan": {"dn": 14.8},
    "propanediol-1,2-carbonate": {"dn": 15.1},
    "benzyl cyanide": {"dn": 15.1},
    "ethylene sulphite": {"dn": 15.3},
    "iso-butyronitrile": {"dn": 15.4},
    "propionitrile": {"dn": 16.1},
    "ethylene carbonate": {"dn": 16.4},
    "phenylphosphonic difluoride": {"dn": 16.4},
    "methyl acetate": {"dn": 16.5},
    "n-butyronitrile": {"dn": 16.6},
    "acetone": {"dn": 17.0},
    "ethyl acetate": {"dn": 17.1},
    "water": {"dn": 18.0, "bulk_dn": 33.0},
    "phenylphosphonic dichloride": {"dn": 18.5},
    "diethyl ether": {"dn": 19.2},
    "tetrahydrofuran": {"dn": 20.0},
    "diphenylphosphonic chloride": {"dn": 22.4},
    "trimethyl phosphate": {"dn": 23.0},
    "tributyl phosphate": {"dn": 23.7},
    "dimethoxyethane": {"dn": 24.0, "approximate": True},
    "dimethylformamide": {"dn": 26.6},
    "n-methyl-e-caprolactam": {"dn": 27.1},
    "n-methyl-2-pyrrolidinone": {"dn": 27.3},
    "n,n-dimethylacetamide": {"dn": 27.8},
    "dimethyl sulphoxide": {"dn": 29.8},
    "n,n-diethylformamide": {"dn": 30.9},
    "n,n-diethylacetamide": {"dn": 32.2},
    "pyridine": {"dn": 33.1},
    "hexamethylphosphoramide": {"dn": 38.8},
    # Footnote a from here: reported as BULK donicities only.
    "hydrazine": {"bulk_dn": 44.0},
    "ethylenediamine": {"bulk_dn": 55.0},
    "ethylamine": {"bulk_dn": 55.5},
    "isopropylamine": {"bulk_dn": 57.5},
    # 57.5, NOT the 57.6 this paper's OCR reports.
    "t-butylamine": {"bulk_dn": 57.5},
    "ammonia": {"bulk_dn": 59.0},
    "triethylamine": {"dn": 61.0},
}

#: Table 2, page 232. `an` and the 31P shift it is derived from; the
#: paper's E_T and Z columns belong to Dimroth-Reichardt and Kosower and
#: are deliberately not carried here, since this file is about ONE pair
#: of scales.
_ACCEPTOR_NUMBERS: dict[str, dict] = {
    "hexane": {"an": 0.0, "p31_shift": 0.0, "note": "the AN scale's zero"},
    "diethyl ether": {"an": 3.9, "p31_shift": -1.64},
    "tetrahydrofuran": {"an": 8.0, "p31_shift": -3.39},
    "benzene": {"an": 8.2, "p31_shift": -3.49},
    "carbon tetrachloride": {"an": 8.6, "p31_shift": -3.64},
    "diglyme": {"an": 9.9, "p31_shift": -4.20},
    "glyme": {"an": 10.2, "p31_shift": -4.35},
    "hexamethylphosphoramide": {"an": 10.6, "p31_shift": -4.50},
    "dioxane": {"an": 10.8, "p31_shift": -4.59},
    "acetone": {"an": 12.5, "p31_shift": -5.33},
    "n-methyl-2-pyrrolidinone": {"an": 13.3, "p31_shift": -5.65},
    "n,n-dimethylacetamide": {"an": 13.6, "p31_shift": -5.80},
    "pyridine": {"an": 14.2, "p31_shift": -6.04},
    "nitrobenzene": {"an": 14.8, "p31_shift": -6.32},
    "benzonitrile": {"an": 15.5, "p31_shift": -6.61},
    "dimethylformamide": {"an": 16.0, "p31_shift": -6.82},
    "dichloroethylene carbonate": {"an": 16.7, "p31_shift": -7.11},
    "propanediol-1,2-carbonate": {"an": 18.3, "p31_shift": -7.77},
    "acetonitrile": {"an": 18.9, "p31_shift": -8.04},
    "dimethyl sulphoxide": {"an": 19.3, "p31_shift": -8.22},
    "dichloromethane": {"an": 20.4, "p31_shift": -8.67},
    "nitromethane": {"an": 20.5, "p31_shift": -8.74},
    "chloroform": {"an": 23.1, "p31_shift": -9.83},
    "isopropanol": {"an": 33.5, "p31_shift": -14.26},
    "ethanol": {"an": 37.1, "p31_shift": -15.80},
    "formamide": {"an": 39.8, "p31_shift": -16.95},
    "methanol": {"an": 41.3, "p31_shift": -17.60},
    "acetic acid": {"an": 52.9, "p31_shift": -22.51},
    "water": {"an": 54.8, "p31_shift": -23.35},
    "trifluoroacetic acid": {"an": 105.3, "p31_shift": -44.83},
    "methanesulphonic acid": {"an": 126.3, "p31_shift": -53.77},
    "antimony pentachloride in dichloroethane": {
        "an": 100.0,
        "p31_shift": -42.58,
        "note": "the AN scale's 100 -- a reference, not a solvent",
    },
}


#: Solvents THE TWO TABLES SPELL DIFFERENTLY, as `{as spelled in the
#: acceptor table: as spelled in the donor table}`.
#:
#: **FOUND BY A CONSUMER, NOT BY REVIEW.** Wiring these numbers to a
#: structure needed one row per liquid, and the mapping turned up two
#: liquids carrying half their data each: `donicity("dioxane")` answered
#: with an acceptor number and no donor number, while the paper prints
#: DN = 14.8 for it under the spelling "Dioxan" on the previous page.
#: Same for glyme, whose donor number is filed under "Dimethoxyethane
#: (DME)".
#:
#: Confirmed against the paper's own prose rather than by their names
#: looking similar -- p12 reads "faster in THF (DN = 20) than in dioxane
#: (DN = 14,8)", using the -e spelling for the row the DN table spells
#: without one, and the acceptor table's own entries read "Digtyme" and
#: "Ciyme" in the scan where the donor table names DME.
#:
#: DECLARED, NEVER FUZZY-MATCHED. `difflib` pairs "1,2-dichloroethane"
#: with "dichloromethane" at the same confidence, which is two different
#: liquids and a wrong merge that no numeric test would catch.
_SPELLING_VARIANTS: dict[str, str] = {
    "dioxane": "dioxan",
    "glyme": "dimethoxyethane",
}


def _merge_spelling_variants() -> None:
    """Fold each variant's acceptor row onto the donor table's spelling.

    FAIL CLOSED on both sides: a variant naming a row that does not exist
    is a typo here, and a variant whose two spellings BOTH already carry
    the same field would mean the paper printed the value twice, which is
    a different situation needing a different answer.
    """
    for spelled, canonical in _SPELLING_VARIANTS.items():
        assert spelled in _ACCEPTOR_NUMBERS, f"no acceptor row named {spelled!r}"
        assert canonical in _DONOR_NUMBERS, f"no donor row named {canonical!r}"
        assert canonical not in _ACCEPTOR_NUMBERS, (
            f"{canonical!r} is already in the acceptor table, so {spelled!r} is not "
            "a spelling of it -- they are two rows and merging them would lose one"
        )
        _ACCEPTOR_NUMBERS[canonical] = _ACCEPTOR_NUMBERS.pop(spelled)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    _merge_spelling_variants()

    # The scale's own two anchors, asserted at BUILD time rather than
    # left for a test: if a transcription slip moves either of them, the
    # whole acceptor column means something else and nothing downstream
    # could tell.
    assert _ACCEPTOR_NUMBERS["hexane"]["an"] == 0.0
    assert _ACCEPTOR_NUMBERS["antimony pentachloride in dichloroethane"]["an"] == 100.0

    payload = {
        "_source_key": "gutmann1976",
        "_supplementary_source_keys": ["mayer1975"],
        "attribution": _ATTRIBUTION,
        "definitions": _DEFINITIONS,
        "spelling_variants": _SPELLING_VARIANTS,
        "donor_numbers": _DONOR_NUMBERS,
        "acceptor_numbers": _ACCEPTOR_NUMBERS,
    }
    (OUT / "gutmann_solvents.json").write_text(
        json.dumps(payload, indent=1), encoding="utf-8"
    )
    merged = sorted(_SPELLING_VARIANTS.values())
    print(f"merged spelling variants: {', '.join(merged)}")
    dilute = sum(1 for e in _DONOR_NUMBERS.values() if e.get("dn") is not None)
    bulk = sum(1 for e in _DONOR_NUMBERS.values() if e.get("bulk_dn") is not None)
    print(
        f"donor numbers:    {len(_DONOR_NUMBERS)} solvents "
        f"({dilute} dilute, {bulk} bulk)\n"
        f"acceptor numbers: {len(_ACCEPTOR_NUMBERS)} solvents"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
